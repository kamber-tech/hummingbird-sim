"""
scenarios.py - Operational scenario simulator and parameter sweep
Hummingbird Sim | Scenario Analysis Module

v2 changes:
  - target_power_kw is now actually honored — hardware is auto-sized to deliver it
  - Microwave: condition strings "rain", "haze", "smoke" are properly mapped
  - Returns loss_budget, required_hardware, link_margin_db, performance_rating
"""

import numpy as np
import pandas as pd
from typing import List, Optional, Dict

from .laser import (LaserBeam, LaserReceiver, AtmosphericConditions as LaserAtmo,
                     compute_laser_link)
from .microwave import (MicrowaveTransmitter, MicrowaveReceiver,
                         AtmosphericConditions as MWAtmo, received_power_friis,
                         normalize_mw_condition)


# ── FOB load profiles ─────────────────────────────────────────────────────

FOB_PROFILES = {
    "small_patrol":   {"base_kw": 2.0,  "peak_kw": 4.0,  "num_personnel": 12},
    "squad_outpost":  {"base_kw": 5.0,  "peak_kw": 8.0,  "num_personnel": 30},
    "platoon_fob":    {"base_kw": 15.0, "peak_kw": 25.0,  "num_personnel": 60},
    "company_fob":    {"base_kw": 50.0, "peak_kw": 80.0,  "num_personnel": 150},
}

# Generator fuel burn rates (L/hr at rated load)
GENERATOR_FUEL_RATE_L_HR = {
    2.0:  0.7,    # 2 kW @ full load
    5.0:  1.7,    # 5 kW (MEP-802A equivalent)
    15.0: 4.5,    # 15 kW (MEP-804A equivalent)
    50.0: 14.0,   # 50 kW (TQG generator)
}

DIESEL_FULLY_BURDENED_USD_L = 12.0  # DoD fully burdened cost

# Max sensible hardware limits
MAX_MW_ELEMENTS = 262144    # 512×512 array cap
MAX_LASER_POWER_W = 5e6     # 5 MW optical cap


def get_fuel_rate(power_kw: float) -> float:
    """Interpolate generator fuel consumption rate at given power."""
    powers = sorted(GENERATOR_FUEL_RATE_L_HR.keys())
    rates  = [GENERATOR_FUEL_RATE_L_HR[p] for p in powers]
    return float(np.interp(power_kw, powers, rates))


def _performance_rating(system_eff_pct: float) -> str:
    """Rate system performance by end-to-end efficiency."""
    if system_eff_pct >= 5.0:
        return "excellent"
    elif system_eff_pct >= 1.5:
        return "marginal"
    else:
        return "poor"


def _size_microwave(
    target_power_w: float,
    range_m: float,
    mw_pa_power_w: float,
    mw_rx_area_m2: float,
    condition_norm: str,
) -> tuple:
    """
    Auto-size microwave array to deliver target_power_w.
    Returns (n_elements, result_dict).

    Since received power scales as n_elements² (both TX power and array gain
    scale linearly with n_elements → P_rx ∝ n²), we use:
      n_needed = n_base * sqrt(target / p_base)
    Then run a verification pass with the sized array.
    """
    # Baseline run with 1024 elements
    n_base = 1024
    tx_base = MicrowaveTransmitter(n_elements=n_base,
                                    tx_power_per_element_w=mw_pa_power_w)
    rx = MicrowaveReceiver(aperture_area_m2=mw_rx_area_m2)
    atmo = MWAtmo(condition=condition_norm)

    r_base = received_power_friis(tx_base, rx, range_m, atmo)
    p_base = r_base["dc_output_w"]

    if p_base > 0:
        ratio = target_power_w / p_base
        n_needed = int(np.ceil(n_base * np.sqrt(ratio)))
        n_needed = max(16, min(n_needed, MAX_MW_ELEMENTS))
    else:
        # Physics says basically nothing gets through — use max
        n_needed = MAX_MW_ELEMENTS

    # Verification / final run with sized array
    tx_final = MicrowaveTransmitter(n_elements=n_needed,
                                     tx_power_per_element_w=mw_pa_power_w)
    r_final = received_power_friis(tx_final, rx, range_m, atmo)
    return n_needed, r_final


def _size_laser(
    target_power_w: float,
    range_m: float,
    beam_waist_m: float,
    pv_aperture_m: float,
    pv_type: str,
    condition: str,
) -> tuple:
    """
    Auto-size laser optical power to deliver target_power_w.
    Since dc_output scales linearly with optical power, we can compute
    efficiency at 1 W and scale up directly.
    Returns (laser_power_w, LaserLinkResult).
    """
    beam_1w = LaserBeam(output_power_w=1.0, waist_radius_m=beam_waist_m)
    receiver = LaserReceiver(pv_type=pv_type, aperture_radius_m=pv_aperture_m)
    atmo = LaserAtmo(condition=condition)

    r_1w = compute_laser_link(range_m, beam_1w, receiver, atmo)
    dc_per_optical_w = r_1w.dc_output_w  # DC per 1 W of optical power

    if dc_per_optical_w > 0:
        laser_power_w = target_power_w / dc_per_optical_w
        laser_power_w = max(100.0, min(laser_power_w, MAX_LASER_POWER_W))
    else:
        laser_power_w = MAX_LASER_POWER_W

    # Final run with sized laser
    beam_final = LaserBeam(output_power_w=laser_power_w, waist_radius_m=beam_waist_m)
    r_final = compute_laser_link(range_m, beam_final, receiver, atmo)
    return laser_power_w, r_final


def compute_scenario(
    mode: str,
    range_m: float,
    target_power_kw: float,
    condition: str = "clear",
    fob_profile: str = "squad_outpost",
    convoy_distance_km: float = 50.0,
    convoy_trips_month: float = 4.0,
    # Laser params (optional — auto-sized if not provided)
    laser_power_w: float = None,
    beam_waist_m: float = 0.05,
    pv_aperture_m: float = 0.30,
    pv_type: str = "gaas",
    # Microwave params (optional — auto-sized if not provided)
    mw_n_elements: int = None,
    mw_pa_power_w: float = 5.0,
    mw_rx_area_m2: float = 3.0,
    # Override auto-sizing
    force_hardware: bool = False,
) -> dict:
    """
    Run a single operational scenario and return a results dict.

    v2: target_power_kw is honored — hardware is auto-sized to deliver it.
    Returns loss_budget, required_hardware, link_margin_db, performance_rating.
    """
    target_power_w = target_power_kw * 1000.0

    # ── Physics simulation ────────────────────────────────────────────────
    if mode == "laser":
        if laser_power_w is None or not force_hardware:
            # Auto-size laser to deliver target power
            sized_laser_w, result = _size_laser(
                target_power_w, range_m, beam_waist_m, pv_aperture_m, pv_type, condition
            )
            actual_laser_w = sized_laser_w
        else:
            actual_laser_w = laser_power_w
            beam = LaserBeam(output_power_w=actual_laser_w, waist_radius_m=beam_waist_m)
            receiver = LaserReceiver(pv_type=pv_type, aperture_radius_m=pv_aperture_m)
            atmo = LaserAtmo(condition=condition)
            result = compute_laser_link(range_m, beam, receiver, atmo)

        dc_power_w    = result.dc_output_w
        elec_input_w  = result.electrical_input_w
        system_eff    = result.total_system_eff
        physics_result = result

        # Loss budget and required hardware
        loss_budget = result.loss_budget
        required_hardware = {
            "type":              "Fiber laser + PV array",
            "laser_optical_power_kw": round(actual_laser_w / 1000, 2),
            "laser_wall_plug_input_kw": round(elec_input_w / 1000, 2),
            "beam_waist_m":      beam_waist_m,
            "pv_aperture_radius_m": pv_aperture_m,
            "pv_aperture_area_m2": round(np.pi * pv_aperture_m**2, 3),
            "pv_type":           pv_type,
            "wavelength_nm":     1070,
            "beam_radius_at_rx_m": round(result.beam_radius_at_rx_m, 2),
            "m2_beam_quality":   result.m2_beam_quality,
        }

    elif mode == "microwave":
        # Normalize condition string for microwave physics
        condition_norm = normalize_mw_condition(condition)

        if mw_n_elements is None or not force_hardware:
            # Auto-size array to deliver target power
            n_elements, result_dict = _size_microwave(
                target_power_w, range_m, mw_pa_power_w, mw_rx_area_m2, condition_norm
            )
        else:
            n_elements = mw_n_elements
            tx = MicrowaveTransmitter(n_elements=n_elements,
                                       tx_power_per_element_w=mw_pa_power_w)
            rx = MicrowaveReceiver(aperture_area_m2=mw_rx_area_m2)
            atmo = MWAtmo(condition=condition_norm)
            result_dict = received_power_friis(tx, rx, range_m, atmo)

        dc_power_w    = result_dict["dc_output_w"]
        elec_input_w  = result_dict["electrical_input_w"]
        system_eff    = result_dict["total_system_eff"]
        physics_result = result_dict

        # Loss budget and required hardware
        loss_budget = result_dict.get("loss_budget", {})
        total_rf_kw = n_elements * mw_pa_power_w / 1000.0
        required_hardware = {
            "type":              "Phased array + Rectenna",
            "n_elements":        n_elements,
            "array_size_approx": f"~{int(np.sqrt(n_elements))}×{int(np.sqrt(n_elements))}",
            "pa_power_per_element_w": mw_pa_power_w,
            "total_rf_power_kw": round(total_rf_kw, 2),
            "wall_plug_input_kw":round(elec_input_w / 1000, 2),
            "rx_aperture_area_m2": mw_rx_area_m2,
            "frequency_ghz":     5.8,
            "array_gain_dbi":    round(result_dict.get("array_gain_dbi", 0), 1),
            "beam_radius_at_rx_m": round(result_dict.get("beam_radius_m", 0), 1),
            "condition_mapped":  condition_norm,
        }

    else:
        raise ValueError(f"Unknown mode: {mode}")

    # ── Link margin ───────────────────────────────────────────────────────
    # How much headroom above target (dB)
    if dc_power_w > 0 and target_power_w > 0:
        link_margin_db = 10 * np.log10(dc_power_w / target_power_w)
    else:
        link_margin_db = -99.0

    # ── Performance rating ────────────────────────────────────────────────
    performance_rating = _performance_rating(system_eff * 100)

    # ── Feasibility warning ───────────────────────────────────────────────
    feasibility_ok = bool(dc_power_w >= target_power_w * 0.5)  # within 50% of target
    feasibility_warning = None
    if not feasibility_ok:
        feasibility_warning = (
            f"Target {target_power_kw:.1f} kW at {range_m/1000:.1f} km requires "
            f"hardware ({required_hardware.get('wall_plug_input_kw', '?')} kW input) "
            f"that may be impractical. "
            f"System efficiency is only {system_eff*100:.2f}%."
        )

    # ── Operational metrics ───────────────────────────────────────────────
    profile = FOB_PROFILES.get(fob_profile, FOB_PROFILES["squad_outpost"])
    base_load_kw = profile["base_kw"]

    # Fraction of FOB load covered by WPT
    wpt_coverage = min(dc_power_w / 1000.0 / base_load_kw, 1.0)

    # Fuel saved (L/day) — WPT covers fraction of load
    gen_fuel_rate_lhr = get_fuel_rate(base_load_kw)
    fuel_saved_l_day  = gen_fuel_rate_lhr * 24 * wpt_coverage
    fuel_saved_l_yr   = fuel_saved_l_day * 365
    fuel_cost_saved_yr = fuel_saved_l_yr * DIESEL_FULLY_BURDENED_USD_L

    # Generator runtime hours saved
    gen_hours_saved_yr = 8760 * wpt_coverage

    # Convoy analysis
    convoy_dist_miles = convoy_distance_km * 0.621371
    fuel_l_per_convoy = gen_fuel_rate_lhr * (convoy_distance_km / 25.0)
    convoys_eliminated_yr = min(convoy_trips_month * 12 * wpt_coverage, convoy_trips_month * 12)
    convoy_cost_saved_yr  = convoys_eliminated_yr * convoy_dist_miles * 600

    return {
        "mode":               mode,
        "range_km":           range_m / 1000,
        "condition":          condition,
        "fob_profile":        fob_profile,
        "target_power_kw":    target_power_kw,
        "dc_power_delivered_kw": dc_power_w / 1000,
        "electrical_input_kw":   elec_input_w / 1000,
        "system_efficiency_pct": system_eff * 100,
        "wpt_coverage_pct":   wpt_coverage * 100,
        "fuel_saved_l_day":   fuel_saved_l_day,
        "fuel_saved_l_yr":    fuel_saved_l_yr,
        "fuel_cost_saved_yr_usd": fuel_cost_saved_yr,
        "gen_hours_saved_yr": gen_hours_saved_yr,
        "convoys_eliminated_yr": convoys_eliminated_yr,
        "convoy_cost_saved_yr_usd": convoy_cost_saved_yr,
        "total_value_yr_usd": fuel_cost_saved_yr + convoy_cost_saved_yr,
        # v2 additions
        "loss_budget":        loss_budget,
        "required_hardware":  required_hardware,
        "link_margin_db":     round(link_margin_db, 2),
        "performance_rating": performance_rating,
        "feasibility_ok":     feasibility_ok,
        "feasibility_warning": feasibility_warning,
        # raw physics (kept for safety endpoint etc.)
        "physics": physics_result,
    }


def sweep_range_and_conditions(
    mode: str,
    ranges_km: List[float] = None,
    conditions: List[str] = None,
    target_power_kw: float = 5.0,
    **kwargs,
) -> pd.DataFrame:
    """
    Sweep across range and atmospheric conditions for given mode.
    Returns a pandas DataFrame for analysis and plotting.
    """
    if ranges_km is None:
        ranges_km = [0.5, 1.0, 2.0, 3.0, 5.0, 7.5, 10.0]
    if conditions is None:
        if mode == "laser":
            conditions = ["clear", "haze", "smoke", "rain"]
        else:
            conditions = ["clear", "drizzle", "light_rain", "moderate_rain"]

    rows = []
    for r_km in ranges_km:
        for cond in conditions:
            try:
                s = compute_scenario(
                    mode=mode,
                    range_m=r_km * 1000,
                    target_power_kw=target_power_kw,
                    condition=cond,
                    **kwargs,
                )
                rows.append({
                    "range_km":      r_km,
                    "condition":     cond,
                    "dc_power_kw":   s["dc_power_delivered_kw"],
                    "elec_input_kw": s["electrical_input_kw"],
                    "system_eff_pct": s["system_efficiency_pct"],
                    "fuel_saved_l_day": s["fuel_saved_l_day"],
                })
            except Exception as e:
                rows.append({
                    "range_km": r_km, "condition": cond,
                    "dc_power_kw": np.nan, "elec_input_kw": np.nan,
                    "system_eff_pct": np.nan, "fuel_saved_l_day": np.nan,
                })
    return pd.DataFrame(rows)


def sweep_power_levels(
    mode: str,
    power_levels_kw: List[float] = None,
    range_m: float = 2000.0,
    condition: str = "clear",
    **kwargs,
) -> pd.DataFrame:
    """
    Sweep across output power levels for a fixed range.
    Returns DataFrame.
    """
    if power_levels_kw is None:
        power_levels_kw = [1, 2, 5, 10, 20, 50, 100]

    rows = []
    for p_kw in power_levels_kw:
        try:
            s = compute_scenario(mode=mode, range_m=range_m,
                                  target_power_kw=p_kw, condition=condition, **kwargs)
            rows.append({
                "power_kw":   p_kw,
                "dc_power_kw": s["dc_power_delivered_kw"],
                "system_eff_pct": s["system_efficiency_pct"],
                "elec_input_kw": s["electrical_input_kw"],
            })
        except Exception:
            rows.append({"power_kw": p_kw, "dc_power_kw": np.nan,
                         "system_eff_pct": np.nan, "elec_input_kw": np.nan})
    return pd.DataFrame(rows)


def run_mvp_scenario(mode: str) -> dict:
    """
    Standard MVP scenario: 5 kW delivered at 2 km, clear sky.
    Hardware is auto-sized to deliver the target.
    """
    return compute_scenario(
        mode=mode,
        range_m=2000,
        target_power_kw=5.0,
        condition="clear",
        fob_profile="squad_outpost",
        convoy_distance_km=50,
    )


def print_scenario_report(s: dict) -> str:
    lines = [
        "=" * 65,
        f"  OPERATIONAL SCENARIO: {s['mode'].upper()} @ {s['range_km']:.1f} km ({s['condition']})",
        "=" * 65,
        f"  FOB profile:            {s['fob_profile']}",
        f"  Target delivered power: {s['target_power_kw']:.1f} kW",
        f"  Actual DC delivered:    {s['dc_power_delivered_kw']:.2f} kW",
        f"  Electrical input:       {s['electrical_input_kw']:.2f} kW",
        f"  System efficiency:      {s['system_efficiency_pct']:.2f}%",
        f"  WPT coverage of FOB:    {s['wpt_coverage_pct']:.0f}%",
        f"  Link margin:            {s['link_margin_db']:.1f} dB",
        f"  Performance rating:     {s['performance_rating'].upper()}",
        "",
        "  ── Required Hardware ────────────────────────────────────",
    ]
    hw = s.get("required_hardware", {})
    for k, v in hw.items():
        lines.append(f"  {k:<28}: {v}")
    lines += [
        "",
        "  ── Logistics Savings ────────────────────────────────────",
        f"  Fuel saved:             {s['fuel_saved_l_day']:.1f} L/day  ({s['fuel_saved_l_yr']:.0f} L/yr)",
        f"  Fuel cost avoided:      ${s['fuel_cost_saved_yr_usd']:,.0f}/yr",
        f"  Generator hours saved:  {s['gen_hours_saved_yr']:.0f} hr/yr",
        f"  Convoys eliminated:     {s['convoys_eliminated_yr']:.0f}/yr",
        f"  Convoy cost saved:      ${s['convoy_cost_saved_yr_usd']:,.0f}/yr",
        f"  Total value/yr:         ${s['total_value_yr_usd']:,.0f}/yr",
        "=" * 65,
    ]
    return "\n".join(lines)
