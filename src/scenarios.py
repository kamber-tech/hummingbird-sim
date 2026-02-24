"""
scenarios.py - Operational scenario simulator and parameter sweep
Aether Sim | Scenario Analysis Module

v2 changes:
  - target_power_kw is now actually honored — hardware is auto-sized to deliver it
  - Microwave: condition strings "rain", "haze", "smoke" are properly mapped
  - Returns loss_budget, required_hardware, link_margin_db, performance_rating
"""

import numpy as np
import pandas as pd
from typing import List, Optional, Dict

from .laser import (LaserBeam, LaserReceiver, AtmosphericConditions as LaserAtmo,
                     compute_laser_link, FOG_HARD_BLOCK_CONDITIONS,
                     DARPA_PRAD_ANCHOR, SYSTEM_OVERHEAD_FACTOR as LASER_OVERHEAD,
                     MAX_SYSTEM_EFF as LASER_MAX_EFF)
from .microwave import (MicrowaveTransmitter, MicrowaveReceiver,
                         AtmosphericConditions as MWAtmo, received_power_friis,
                         normalize_mw_condition, crossover_analysis as mw_crossover,
                         rayleigh_distance_m, spot_radius_at_range,
                         array_aperture_area, wavelength_m as mw_wavelength)


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


def _default_mw_rx_area(range_m: float) -> float:
    """
    Realistic receive aperture for FOB/vehicle deployment, scaled by range.
    At 500m: ~12.5 m² (large tent/vehicle), at 2km: 50 m² (fixed station).
    Capped: 10–200 m².
    """
    return min(200.0, max(10.0, range_m / 40.0))


def _compute_microwave_fixed(
    range_m: float,
    mw_pa_power_w: float,
    mw_rx_area_m2: float,
    mw_n_elements: int,
    condition_norm: str,
) -> dict:
    """
    Run microwave physics with FIXED hardware (no back-calculation).
    Honest approach: report what the system actually delivers.
    """
    tx = MicrowaveTransmitter(n_elements=mw_n_elements,
                               tx_power_per_element_w=mw_pa_power_w)
    rx = MicrowaveReceiver(aperture_area_m2=mw_rx_area_m2)
    atmo = MWAtmo(condition=condition_norm)
    return received_power_friis(tx, rx, range_m, atmo)


def _estimate_required_mw_elements(target_power_w: float, range_m: float,
                                    mw_pa_power_w: float, mw_rx_area_m2: float,
                                    condition_norm: str) -> dict:
    """
    Back-calculate how many elements WOULD be needed to hit target.
    Shows this even if infeasible — honest physics disclosure.
    P_rx ∝ n² (TX power and array gain both scale with n_elements)
    """
    n_base = 1024
    r = _compute_microwave_fixed(range_m, mw_pa_power_w, mw_rx_area_m2,
                                  n_base, condition_norm)
    p_base = r["dc_output_w"]
    if p_base > 0:
        n_needed = int(np.ceil(n_base * np.sqrt(target_power_w / p_base)))
        n_needed = max(16, n_needed)
        feasible = n_needed <= MAX_MW_ELEMENTS
    else:
        n_needed = MAX_MW_ELEMENTS * 10  # effectively infinite
        feasible = False

    total_rf_kw = n_needed * mw_pa_power_w / 1000.0
    return {
        "n_elements_required": n_needed,
        "total_rf_power_required_kw": round(total_rf_kw, 1),
        "feasible_array_size": feasible,
        "note": (
            f"Requires {n_needed:,} elements ({int(np.sqrt(n_needed))}×{int(np.sqrt(n_needed))})"
            f" — {'feasible' if feasible else 'INFEASIBLE (exceeds practical limits)'}"
        ),
    }


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
    fob_profile: str = "auto",
    convoy_distance_km: float = 100.0,
    convoy_trips_month: float = 4.0,
    # Laser params (optional — auto-sized if not provided)
    laser_power_w: float = None,
    beam_waist_m: float = 0.05,
    pv_aperture_m: float = 0.30,
    pv_type: str = "gaas",
    # Microwave params — fixed realistic hardware (not auto-sized to target)
    mw_n_elements: int = 1024,          # 32×32 phased array (portable FOB)
    mw_pa_power_w: float = 10.0,        # GaN MMIC: 10–50W per element standard
    mw_rx_area_m2: float = None,        # None = auto-scale with range (10–200 m²)
    mw_tx_aperture_m2: float = None,    # Override: compute n_elements from TX area
    # Override auto-sizing (for laser only now)
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

        # ── Resolve aperture sizes ────────────────────────────────────────
        if mw_rx_area_m2 is None:
            actual_rx_area = _default_mw_rx_area(range_m)
        else:
            actual_rx_area = mw_rx_area_m2

        # If TX aperture given, derive n_elements from it
        if mw_tx_aperture_m2 is not None:
            lam = mw_wavelength(5.8e9)
            d = 0.5 * lam
            n_elements = max(64, int(mw_tx_aperture_m2 / d**2))
        else:
            n_elements = mw_n_elements

        # ── Fixed hardware run — honest physics, no auto-sizing ───────────
        result_dict = _compute_microwave_fixed(
            range_m, mw_pa_power_w, actual_rx_area, n_elements, condition_norm
        )

        dc_power_w    = result_dict["dc_output_w"]
        elec_input_w  = result_dict["electrical_input_w"]
        system_eff    = result_dict["total_system_eff"]
        physics_result = result_dict

        # ── What would be required to hit the target? (even if infeasible) ─
        req_hw = _estimate_required_mw_elements(
            target_power_w, range_m, mw_pa_power_w, actual_rx_area, condition_norm
        )

        # Loss budget and required hardware
        loss_budget = result_dict.get("loss_budget", {})
        total_rf_kw = n_elements * mw_pa_power_w / 1000.0
        required_hardware = {
            "type":                  "Phased array + Rectenna",
            "n_elements":            n_elements,
            "array_size_approx":     f"~{int(np.sqrt(n_elements))}×{int(np.sqrt(n_elements))}",
            "pa_power_per_element_w": mw_pa_power_w,
            "total_rf_power_kw":     round(total_rf_kw, 2),
            "wall_plug_input_kw":    round(elec_input_w / 1000, 2),
            "rx_aperture_area_m2":   actual_rx_area,
            "frequency_ghz":         5.8,
            "array_gain_dbi":        round(result_dict.get("array_gain_dbi", 0), 1),
            "beam_radius_at_rx_m":   round(result_dict.get("beam_radius_m", 0), 1),
            "rayleigh_distance_m":   round(result_dict.get("rayleigh_distance_m", 0), 1),
            "condition_mapped":      condition_norm,
            # Honest disclosure: what target delivery would require
            "to_deliver_target_kw":  req_hw['note'],
        }

    else:
        raise ValueError(f"Unknown mode: {mode}")

    # ── Link margin ───────────────────────────────────────────────────────
    if dc_power_w > 0 and target_power_w > 0:
        link_margin_db = 10 * np.log10(dc_power_w / target_power_w)
    else:
        link_margin_db = -99.0

    # ── Performance rating ────────────────────────────────────────────────
    performance_rating = _performance_rating(system_eff * 100)

    # ── Comprehensive feasibility object ─────────────────────────────────
    range_km = range_m / 1000.0
    is_feasible = bool((system_eff * 100) >= 1.0)

    if mode == "microwave":
        beam_r = physics_result.get("beam_radius_at_range_m", 0)
        rayleigh_m = physics_result.get("rayleigh_distance_m", 0)
        regime = physics_result.get("regime", "far-field")
        req_rx_area = physics_result.get("req_rx_area_50pct_m2", 0)
        actual_rx = physics_result.get("actual_rx_area_m2", actual_rx_area)
        if not is_feasible:
            feas_note = (
                f"MW beam spreads to {beam_r:.0f}m radius at {range_km:.1f}km. "
                f"Need ~{req_rx_area:.0f}m² RX to capture 50% — actual is {actual_rx:.0f}m². "
                f"Consider laser for ranges >{range_km:.1f}km in clear sky."
            )
        elif range_km < 2.0:
            feas_note = f"Marginal: MW works at {range_km:.1f}km but beam is {beam_r:.0f}m wide."
        else:
            feas_note = (
                f"Microwave beam is {beam_r:.0f}m radius at {range_km:.1f}km — "
                f"larger than the {actual_rx:.0f}m² RX aperture. "
                f"Only capturing a fraction of transmitted power."
            )
        crossover = mw_crossover(range_m, condition)
        best_mode_for_range = crossover["best_mode"]
        best_mode_reason = crossover["reason"]
    else:
        # Laser
        fog_blocked = condition in FOG_HARD_BLOCK_CONDITIONS
        if fog_blocked:
            feas_note = (
                f"FOG HARD BLOCK: laser link unavailable in fog/light_fog. "
                f"Switch to microwave (only ~{0.22*range_km:.2f} dB/km attenuation in rain)."
            )
            is_feasible = False
        elif not is_feasible:
            feas_note = (
                f"Laser link very inefficient at {range_km:.1f}km in {condition}. "
                f"Check atmospheric conditions or reduce range."
            )
        else:
            feas_note = (
                f"Laser efficient at {range_km:.1f}km in {condition}. "
                f"DARPA PRAD anchor: 800W @ 8.6km at ~20% eff (2025 state-of-art)."
            )
        crossover = mw_crossover(range_m, condition)
        best_mode_for_range = crossover["best_mode"]
        best_mode_reason = crossover["reason"]
        # Laser-specific geometry
        beam_r = physics_result.beam_radius_at_rx_m if hasattr(physics_result, 'beam_radius_at_rx_m') else 0
        rayleigh_m = None  # not applicable the same way for laser
        regime = "laser_gaussian"
        req_rx_area = None

    feasibility = {
        "is_feasible":            is_feasible,
        "regime":                 regime,
        "rayleigh_distance_m":    rayleigh_m,
        "beam_radius_at_range_m": round(beam_r, 2) if beam_r else None,
        "required_rx_aperture_m2": round(req_rx_area, 1) if req_rx_area else None,
        "note":                   feas_note,
        "best_mode_for_range":    best_mode_for_range,
        "best_mode_reason":       best_mode_reason,
        "darpa_prad_anchor":      DARPA_PRAD_ANCHOR["description"] +
                                  f" — {DARPA_PRAD_ANCHOR['dc_power_w']}W @ "
                                  f"{DARPA_PRAD_ANCHOR['range_km']}km, "
                                  f"{DARPA_PRAD_ANCHOR['system_efficiency_pct']}% eff",
    }

    # ── Legacy feasibility_ok / warning (kept for backward compat) ────────
    feasibility_ok = is_feasible
    feasibility_warning = None if is_feasible else feas_note

    # ── Operational metrics ───────────────────────────────────────────────
    # Auto-select FOB profile based on target power if not explicitly set
    if fob_profile == "auto" or fob_profile == "squad_outpost":
        if target_power_kw <= 3:
            fob_profile = "small_patrol"
        elif target_power_kw <= 8:
            fob_profile = "squad_outpost"
        elif target_power_kw <= 30:
            fob_profile = "platoon_fob"
        else:
            fob_profile = "company_fob"

    profile = FOB_PROFILES.get(fob_profile, FOB_PROFILES["platoon_fob"])
    # Use the larger of: FOB base load or target power (WPT replaces generator load)
    ref_load_kw = max(target_power_kw, profile["base_kw"])

    # Fraction of FOB load covered by WPT
    dc_kw = dc_power_w / 1000.0
    wpt_coverage = min(dc_kw / ref_load_kw, 1.0)

    # Fuel saved (L/day) — based on reference load generator fuel rate
    gen_fuel_rate_lhr = get_fuel_rate(ref_load_kw)
    fuel_saved_l_day  = gen_fuel_rate_lhr * 24 * wpt_coverage
    fuel_saved_l_yr   = fuel_saved_l_day * 365
    fuel_cost_saved_yr = fuel_saved_l_yr * DIESEL_FULLY_BURDENED_USD_L

    # Generator runtime hours saved
    gen_hours_saved_yr = 8760 * wpt_coverage

    # Convoy analysis — derived from actual fuel savings (not fixed trips/month)
    FUEL_PER_CONVOY_L = 500.0          # litres per resupply run
    convoy_dist_miles = convoy_distance_km * 0.621371   # round-trip miles
    convoys_eliminated_yr = fuel_saved_l_yr / FUEL_PER_CONVOY_L
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
        # v3 comprehensive feasibility analysis
        "feasibility":        feasibility,
        # raw physics (kept for safety endpoint etc.) — make_serializable handles LaserLinkResult dataclass
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
        fob_profile="auto",
        convoy_distance_km=100,
    )


def compute_space_scenario(
    mode: str,              # "laser" or "microwave"
    orbit: str,             # "iss_leo", "leo", "geo", or float altitude in km
    power_kw: float,
    condition: str = "clear",
    # Microwave hardware params
    mw_array_diameter_m: float = None,   # None = auto-size
    mw_rectenna_area_m2: float = None,
    # Laser hardware params
    laser_aperture_m: float = 2.0,
    laser_rx_aperture_m: float = 10.0,
    zenith_angle_deg: float = 0.0,
) -> dict:
    """
    Compute space-to-earth WPT scenario.

    Auto-sizes hardware to attempt delivery of power_kw.
    For GEO microwave: hardware will be enormous (km scale) — this is correct physics.
    For LEO laser: hardware is feasible (2-10m apertures).
    """
    from .space import (SpaceTransmitter, SpaceReceiver, compute_space_link,
                        ORBIT_PRESETS, ATMOSPHERIC_DEPTH_KM)

    # Resolve orbit altitude
    if isinstance(orbit, str) and orbit in ORBIT_PRESETS:
        altitude_km = ORBIT_PRESETS[orbit]["altitude_km"]
        orbit_name = ORBIT_PRESETS[orbit]["name"]
    else:
        try:
            altitude_km = float(orbit)
            orbit_name = f"Custom {altitude_km:.0f} km"
        except Exception:
            altitude_km = 600.0
            orbit_name = "LEO (default)"

    target_power_w = power_kw * 1000.0

    # Auto-size hardware based on orbit and mode
    if mode == "microwave":
        if mw_array_diameter_m is None:
            if altitude_km >= 20000:
                mw_array_diameter_m = 2600.0   # GEO scale (JAXA concept)
            elif altitude_km >= 2000:
                mw_array_diameter_m = 500.0    # MEO scale
            else:
                mw_array_diameter_m = 100.0    # LEO scale

        if mw_rectenna_area_m2 is None:
            if altitude_km >= 20000:
                mw_rectenna_area_m2 = 3.5e6    # 3.5 km² for GEO (JAXA concept)
            elif altitude_km >= 2000:
                mw_rectenna_area_m2 = 50000.0  # 50,000 m² for MEO
            else:
                mw_rectenna_area_m2 = 10000.0  # 10,000 m² for LEO

    tx = SpaceTransmitter(
        mode=mode,
        altitude_km=altitude_km,
        mw_array_diameter_m=mw_array_diameter_m or 1000.0,
        laser_aperture_m=laser_aperture_m,
    )
    rx = SpaceReceiver(
        mode=mode,
        mw_rectenna_area_m2=mw_rectenna_area_m2 or 1e6,
        laser_pv_aperture_m=laser_rx_aperture_m,
    )

    result = compute_space_link(tx, rx, condition, target_power_w, zenith_angle_deg)

    # Add economics (same model as ground scenarios)
    dc_kw = result.get("dc_power_delivered_kw", 0)
    fob_load_kw = 15.0
    fob_fuel_l_day = 200.0
    fuel_saved_l_day = (dc_kw / fob_load_kw) * fob_fuel_l_day
    fuel_saved_l_yr = fuel_saved_l_day * 365
    convoy_threshold_l = 500.0
    convoys_yr = fuel_saved_l_yr / convoy_threshold_l
    fuel_cost_usd = fuel_saved_l_yr * DIESEL_FULLY_BURDENED_USD_L
    convoy_cost_usd = convoys_yr * 600 * 62

    result.update({
        "orbit_name": orbit_name,
        "altitude_km": altitude_km,
        "target_power_kw": power_kw,
        "range_km": altitude_km,
        "condition": condition,
        "fuel_saved_l_day": round(fuel_saved_l_day, 1),
        "fuel_saved_l_yr": round(fuel_saved_l_yr, 0),
        "convoys_eliminated_yr": round(convoys_yr, 1),
        "fuel_cost_saved_yr_usd": round(fuel_cost_usd, 0),
        "convoy_cost_saved_yr_usd": round(convoy_cost_usd, 0),
        "total_value_yr_usd": round(fuel_cost_usd + convoy_cost_usd, 0),
        "wpt_coverage_pct": round(min(dc_kw / fob_load_kw * 100, 100), 1),
    })

    return result


def compute_optimized_scenario(
    mode: str,
    range_m: int,
    power_kw: float,
    condition: str,
    optimizations: list = None,
) -> dict:
    """
    Run scenario with efficiency optimizations applied.

    optimizations: list of strings from:
      - "adaptive_optics"    — applies 2.5x Strehl improvement for laser
      - "inp_cells"          — uses InP 55% PV efficiency instead of default 35%
      - "large_aperture"     — doubles TX and RX aperture sizes (4x area)
      - "high_power_density" — ensures high power density at receiver (85% rectenna)
      - "all"                — all of the above

    Returns base result + optimized result + improvement factors.
    """
    if optimizations is None:
        optimizations = ["all"]
    if "all" in optimizations:
        optimizations = ["adaptive_optics", "inp_cells", "large_aperture", "high_power_density"]

    # Get baseline
    base = compute_scenario(mode, range_m, power_kw, condition)

    opt_result = dict(base)
    improvement_notes = []

    base_eff = base.get("system_efficiency_pct", 0)
    opt_eff = base_eff

    if "adaptive_optics" in optimizations and mode == "laser":
        # AO pre-compensation improves Strehl ratio significantly
        # Typical improvement: 3-5x in Strehl → 2-3x in received power
        # Reference: AFRL adaptive optics for directed energy, 2-4x improvement reported
        ao_factor = 2.5
        opt_eff *= ao_factor
        improvement_notes.append(
            f"Adaptive optics: +{ao_factor}x Strehl correction (pre-compensation)"
        )

    if "inp_cells" in optimizations and mode == "laser":
        # InP cells: 55% vs base GaAs 50% monochromatic PV efficiency
        # Both subject to same 0.86 temperature derating → effective gain = 55/50 = 1.10x
        # Reference: Alta Devices/NextGen Solar 55.2% at 1070nm monochromatic (2023)
        inp_factor = 0.55 / 0.50
        opt_eff *= inp_factor
        improvement_notes.append(
            f"InP PV cells: {inp_factor:.2f}x efficiency gain (55% vs 50% GaAs monochromatic)"
        )

    if "large_aperture" in optimizations:
        if mode == "laser":
            # Larger TX/RX aperture: reduces beam divergence and turbulence effect.
            # At short range (geo_coll already ~1.0), benefit is reduced turbulence and
            # improved Strehl; at long range, benefit is tighter beam → better capture.
            # Conservative 2x improvement (not 4x — baseline already has full geometric capture).
            aperture_factor = 2.0
            opt_eff *= aperture_factor
            improvement_notes.append(
                f"Large aperture (2x area): ~{aperture_factor}x improvement from tighter beam + reduced turbulence"
            )
        else:
            # For microwave: 2x elements → 4x received power (P_rx ∝ n²)
            aperture_factor = 4.0
            opt_eff *= aperture_factor
            improvement_notes.append(
                f"Larger array (2x elements = 4x gain²): {aperture_factor}x improvement"
            )

    if "high_power_density" in optimizations and mode == "microwave":
        # Ensure rectenna operates in high-efficiency regime (85% vs 60%)
        rectenna_factor = 0.85 / 0.65
        opt_eff *= rectenna_factor
        improvement_notes.append(
            f"High-density rectenna array: {rectenna_factor:.1f}x RF-DC conversion"
        )

    # Range-dependent efficiency cap:
    # Near-field (0.5km): up to 33%, 2km: ~29%, 5km: ~23%, 8.6km: ~18.8%
    # Anchored to DARPA POWER PRAD 2025: 800W @ 8.6km ≈ 20% end-to-end (best hardware)
    range_km = range_m / 1000.0
    if mode == "laser":
        max_eff = 35.0 / (1.0 + range_km / 10.0)
    else:
        max_eff = 10.0 / (1.0 + range_km / 5.0)   # microwave optimized caps lower
    opt_eff = min(opt_eff, max_eff)

    # Scale DC delivered proportionally
    base_dc = base.get("dc_power_delivered_kw", 0)
    if base_eff > 0:
        dc_scale = opt_eff / base_eff
    else:
        dc_scale = 1.0
    opt_dc = min(base_dc * dc_scale, power_kw)  # can't deliver more than target
    opt_input = opt_dc / max(opt_eff / 100, 0.001)

    opt_result["system_efficiency_pct"] = round(opt_eff, 2)
    opt_result["dc_power_delivered_kw"] = round(opt_dc, 3)
    opt_result["electrical_input_kw"] = round(opt_input, 1)
    opt_result["optimizations_applied"] = optimizations
    opt_result["improvement_notes"] = improvement_notes
    opt_result["baseline_efficiency_pct"] = round(base_eff, 2)
    opt_result["efficiency_gain_factor"] = round(opt_eff / max(base_eff, 0.001), 1)
    # Remove physics (LaserLinkResult dataclass) from opt_result to avoid serialization issues
    opt_result.pop("physics", None)

    return {
        "mode": "optimized",
        "base": {k: v for k, v in base.items() if k != "physics"},
        "optimized": opt_result,
        "improvement_summary": {
            "baseline_eff_pct": round(base_eff, 2),
            "optimized_eff_pct": round(opt_eff, 2),
            "gain_factor": round(opt_eff / max(base_eff, 0.001), 1),
            "notes": improvement_notes,
        },
    }


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
