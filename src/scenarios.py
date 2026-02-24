"""
scenarios.py - Operational scenario simulator and parameter sweep
Hummingbird Sim | Scenario Analysis Module
"""

import numpy as np
import pandas as pd
from typing import List, Optional, Dict

from .laser import (LaserBeam, LaserReceiver, AtmosphericConditions as LaserAtmo,
                     compute_laser_link)
from .microwave import (MicrowaveTransmitter, MicrowaveReceiver,
                         AtmosphericConditions as MWAtmo, received_power_friis)


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


def get_fuel_rate(power_kw: float) -> float:
    """Interpolate generator fuel consumption rate at given power."""
    powers = sorted(GENERATOR_FUEL_RATE_L_HR.keys())
    rates  = [GENERATOR_FUEL_RATE_L_HR[p] for p in powers]
    return float(np.interp(power_kw, powers, rates))


def compute_scenario(
    mode: str,
    range_m: float,
    target_power_kw: float,
    condition: str = "clear",
    fob_profile: str = "squad_outpost",
    convoy_distance_km: float = 50.0,
    convoy_trips_month: float = 4.0,
    # Laser params
    laser_power_w: float = None,
    beam_waist_m: float = 0.05,
    pv_aperture_m: float = 0.30,
    pv_type: str = "gaas",
    # Microwave params
    mw_n_elements: int = 1024,
    mw_pa_power_w: float = 5.0,
    mw_rx_area_m2: float = 3.0,
) -> dict:
    """
    Run a single operational scenario and return a results dict.
    """
    target_power_w = target_power_kw * 1000.0

    # ── Physics simulation ────────────────────────────────────────────────
    if mode == "laser":
        if laser_power_w is None:
            laser_power_w = target_power_w / 0.08  # rough efficiency guess

        beam = LaserBeam(
            output_power_w=laser_power_w,
            waist_radius_m=beam_waist_m,
        )
        receiver = LaserReceiver(
            pv_type=pv_type,
            aperture_radius_m=pv_aperture_m,
        )
        atmo = LaserAtmo(condition=condition)
        result = compute_laser_link(range_m, beam, receiver, atmo)
        dc_power_w    = result.dc_output_w
        elec_input_w  = result.electrical_input_w
        system_eff    = result.total_system_eff
        physics_result = result

    elif mode == "microwave":
        tx = MicrowaveTransmitter(
            n_elements=mw_n_elements,
            tx_power_per_element_w=mw_pa_power_w,
        )
        rx = MicrowaveReceiver(aperture_area_m2=mw_rx_area_m2)
        atmo = MWAtmo(condition=condition if condition in ["clear","drizzle","light_rain","moderate_rain","heavy_rain"] else "clear")
        result_dict = received_power_friis(tx, rx, range_m, atmo)
        dc_power_w    = result_dict["dc_output_w"]
        elec_input_w  = result_dict["electrical_input_w"]
        system_eff    = result_dict["total_system_eff"]
        physics_result = result_dict

    else:
        raise ValueError(f"Unknown mode: {mode}")

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
    fuel_l_per_convoy = gen_fuel_rate_lhr * (convoy_distance_km / 25.0)  # travel time
    fuel_convoys_per_yr = fuel_saved_l_yr / (fuel_l_per_convoy * 30) if fuel_l_per_convoy > 0 else 0
    convoys_eliminated_yr = min(convoy_trips_month * 12 * wpt_coverage, convoy_trips_month * 12)
    convoy_cost_saved_yr  = convoys_eliminated_yr * convoy_dist_miles * 600  # $600/mile

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
            if mode == "laser":
                laser_pw = p_kw * 1000 / 0.08  # rough
                s = compute_scenario(mode=mode, range_m=range_m,
                                      target_power_kw=p_kw, condition=condition,
                                      laser_power_w=laser_pw, **kwargs)
            else:
                n_elem = max(16, int(p_kw * 1000 / (5.0 * 0.3)))  # scale elements
                s = compute_scenario(mode=mode, range_m=range_m,
                                      target_power_kw=p_kw, condition=condition,
                                      mw_n_elements=n_elem, **kwargs)
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
    Laser: sized for actual 5 kW delivery with GaAs PV
    Microwave: 1024-element array, 3 m² rectenna
    """
    if mode == "laser":
        # Size laser to deliver 5 kW at 2 km:
        # With ~8% system eff → need ~62.5 kW input → 25 kW optical
        # Let's compute with realistic 50% wall-plug eff:
        # Actually: run at high optical power and see what delivers
        # GaAs: 50% PV, 40% wall-plug, ~90% atmo, ~80% geo, ~0.98 jitter → ~14% end-end
        # Need optical power = 5kW / (0.9 * 0.8 * 0.98 * 0.5 * 0.95) ≈ 15 kW optical
        return compute_scenario(
            mode="laser",
            range_m=2000,
            target_power_kw=5.0,
            condition="clear",
            fob_profile="squad_outpost",
            laser_power_w=15_000,     # 15 kW optical output
            beam_waist_m=0.075,       # 7.5 cm waist — good collimation at 2 km
            pv_aperture_m=0.50,       # 50 cm radius receiver
            pv_type="gaas",
            convoy_distance_km=50,
        )
    else:  # microwave
        # 1024-element 5.8 GHz array, 3 m² rectenna
        return compute_scenario(
            mode="microwave",
            range_m=2000,
            target_power_kw=5.0,
            condition="clear",
            fob_profile="squad_outpost",
            mw_n_elements=1024,
            mw_pa_power_w=10.0,       # 10 W/element → 10.24 kW RF total
            mw_rx_area_m2=5.0,        # 5 m² rectenna
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
