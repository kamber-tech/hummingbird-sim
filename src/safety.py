"""
safety.py - Safety model for laser and microwave WPT
Hummingbird Sim | Safety & Interlock Module

Sources:
  - Laser: IEC 60825-1:2014, ANSI Z136.1-2022
    MPE (skin, large area): 100 mW/cm² for t > 10s @ 1070 nm (Class 4 regime)
    MPE (eye, intrabeam, CW): 5.1e-4 W/cm² for t=0.25s baseline; for > 10s CW: ~1 mW/cm²
    Note: at 1070 nm, retinal damage threshold is lower than skin MPE
  - RF: IEEE C95.1-2019, ICNIRP 2020 guidelines
    Occupational (controlled): S_max = f(GHz)/200 W/m²  → at 5.8 GHz: 29 mW/cm²  
    General public (uncontrolled): S_max = f(GHz)/2000 W/m² → 2.9 mW/cm²
    Legacy ANSI C95.1: 10 mW/cm² (occupational, all frequencies above 3 GHz)
  - IEC 62368-1 / MIL-STD-882E: system hazard analysis framework
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional

# ── Laser safety constants ────────────────────────────────────────────────

# MPE limits (ANSI Z136.1-2022 / IEC 60825-1)
# @ 1070 nm, CW exposure > 10 seconds
MPE_EYE_1070NM_W_CM2   = 1.0e-3    # 1 mW/cm²  — eye, intrabeam CW (conservative)
MPE_SKIN_1070NM_W_CM2  = 0.1       # 100 mW/cm² — skin, large area, CW (ANSI Z136.1 §8)

# Nominal Ocular Hazard Distance parameters
# NOHD = sqrt(P / (π * MPE * w0²)) — simplified
# For safety zone, we use irradiance falloff with range

# ── RF safety constants ───────────────────────────────────────────────────
# IEEE C95.1-2019, Table 1 — power density limits
# At 5.8 GHz (frequency-dependent tier)
RF_LIMIT_OCCUPATIONAL_MW_CM2  = 10.0   # mW/cm² (conservative legacy ANSI, 3–300 GHz)
RF_LIMIT_PUBLIC_MW_CM2        = 2.0    # mW/cm² (general public uncontrolled)

# ── Interlock timing ─────────────────────────────────────────────────────
INTERLOCK_RESPONSE_MS = {
    "beam_block":      10.0,   # mechanical shutter, ms
    "rf_kill":          1.0,   # solid-state PA shutdown, ms
    "tracking_lost":   50.0,   # acquisition loop timeout, ms
    "safety_pilot":   200.0,   # human operator override, ms
    "power_down_full": 500.0,  # full system safe state, ms
}


@dataclass
class LaserSafetyResult:
    nominal_hazard_distance_m: float   # NOHD — min safe distance for eye
    skin_hazard_distance_m: float      # min distance where skin MPE is satisfied
    exclusion_zone_radius_m: float     # recommended exclusion zone
    irradiance_at_nohd_w_cm2: float
    irradiance_at_100m_w_cm2: float
    irradiance_at_1km_w_cm2: float
    eye_mpe_w_cm2: float
    skin_mpe_w_cm2: float
    compliant_at_range: bool           # does beam comply at operational range?
    warnings: list


@dataclass
class MicrowaveSafetyResult:
    occupational_safe_distance_m: float   # where PD drops to occ. limit
    public_safe_distance_m: float         # where PD drops to public limit
    main_beam_pd_at_range_mw_cm2: float
    sidelobe_pd_at_50m_mw_cm2: float
    compliant_main_beam: bool
    compliant_sidelobes: bool
    warnings: list


@dataclass
class InterlockScenario:
    trigger: str                          # e.g. "tracking_lost"
    tx_power_w: float
    response_time_ms: float
    energy_deposited_j: float             # power × response time = max uncontrolled energy
    safe: bool
    mitigation: str


# ── Laser safety calculations ─────────────────────────────────────────────

def laser_irradiance_at_range(power_w: float, range_m: float,
                               waist_m: float, m_squared: float = 1.2,
                               wavelength_m: float = 1070e-9) -> float:
    """
    Peak irradiance W/m² → W/cm² of a Gaussian beam at range.
    Accounts for beam spreading only (no atmo here — worst case is no atmo loss).
    """
    z_R = np.pi * waist_m**2 / (m_squared * wavelength_m)
    w_z = waist_m * m_squared * np.sqrt(1 + (range_m / z_R)**2)
    irr_w_m2 = 2 * power_w / (np.pi * w_z**2)
    return irr_w_m2 / 1e4   # W/m² → W/cm²


def nominal_hazard_distance_eye(power_w: float, waist_m: float,
                                 m_squared: float = 1.2,
                                 wavelength_m: float = 1070e-9) -> float:
    """
    Nominal Ocular Hazard Distance (NOHD) for direct intrabeam viewing.
    NOHD = sqrt( (2*P) / (π * MPE_eye * w0² * M²²) - z_R² )  ... simplified
    Iterative solver: find z where irradiance = MPE_eye.
    """
    mpe = MPE_EYE_1070NM_W_CM2
    # Binary search
    z_lo, z_hi = 0.1, 1e6
    for _ in range(60):
        z_mid = (z_lo + z_hi) / 2
        irr = laser_irradiance_at_range(power_w, z_mid, waist_m, m_squared, wavelength_m)
        if irr > mpe:
            z_lo = z_mid
        else:
            z_hi = z_mid
    return z_hi


def nominal_hazard_distance_skin(power_w: float, waist_m: float,
                                  m_squared: float = 1.2,
                                  wavelength_m: float = 1070e-9) -> float:
    """
    Skin hazard distance — irradiance drops to skin MPE.
    """
    mpe = MPE_SKIN_1070NM_W_CM2
    z_lo, z_hi = 0.1, 1e6
    for _ in range(60):
        z_mid = (z_lo + z_hi) / 2
        irr = laser_irradiance_at_range(power_w, z_mid, waist_m, m_squared, wavelength_m)
        if irr > mpe:
            z_lo = z_mid
        else:
            z_hi = z_mid
    return z_hi


def compute_laser_safety(power_w: float, range_m: float,
                          waist_m: float = 0.05,
                          m_squared: float = 1.2) -> LaserSafetyResult:
    """
    Full laser safety assessment per ANSI Z136.1 / IEC 60825-1.
    """
    nohd_eye  = nominal_hazard_distance_eye(power_w, waist_m, m_squared)
    nohd_skin = nominal_hazard_distance_skin(power_w, waist_m, m_squared)
    excl_zone = max(nohd_eye, 10.0)  # at minimum 10 m safety exclusion

    irr_at_nohd  = laser_irradiance_at_range(power_w, nohd_eye,  waist_m, m_squared)
    irr_at_100m  = laser_irradiance_at_range(power_w, 100.0,    waist_m, m_squared)
    irr_at_1km   = laser_irradiance_at_range(power_w, 1000.0,   waist_m, m_squared)

    compliant = (irr_at_100m < MPE_EYE_1070NM_W_CM2 or range_m > nohd_eye)

    warnings = []
    if nohd_eye > 500:
        warnings.append(f"⚠ Eye NOHD = {nohd_eye:.0f} m — requires wide exclusion zone and beam tracking interlock")
    if nohd_skin > 50:
        warnings.append(f"⚠ Skin hazard zone extends {nohd_skin:.0f} m — PPE required within zone")
    if power_w > 5000:
        warnings.append("⚠ Power > 5 kW — Class 4 laser, MIL-STD-1425A compliance required for DoD use")
    warnings.append("ℹ Interlock required: beam kill <10 ms on tracking loss")
    warnings.append("ℹ Atmospheric scintillation can cause momentary hot-spots — add 3× safety margin")

    return LaserSafetyResult(
        nominal_hazard_distance_m   = nohd_eye,
        skin_hazard_distance_m      = nohd_skin,
        exclusion_zone_radius_m     = excl_zone,
        irradiance_at_nohd_w_cm2   = irr_at_nohd,
        irradiance_at_100m_w_cm2   = irr_at_100m,
        irradiance_at_1km_w_cm2    = irr_at_1km,
        eye_mpe_w_cm2               = MPE_EYE_1070NM_W_CM2,
        skin_mpe_w_cm2              = MPE_SKIN_1070NM_W_CM2,
        compliant_at_range          = compliant,
        warnings                    = warnings,
    )


# ── Microwave safety calculations ─────────────────────────────────────────

def rf_safe_distance(total_tx_rf_w: float, gain_linear: float,
                      limit_mw_cm2: float) -> float:
    """
    Distance at which isotropic + gain power density equals limit.
    PD = P_t * G / (4π * R²)  [W/m²]
    R = sqrt(P_t * G / (4π * limit_W_m2))
    """
    limit_w_m2 = limit_mw_cm2 * 10.0  # mW/cm² → W/m²
    R2 = total_tx_rf_w * gain_linear / (4 * np.pi * limit_w_m2)
    return np.sqrt(max(R2, 0.0))


def compute_microwave_safety(total_tx_rf_w: float, gain_dbi: float,
                              range_m: float, pd_at_range_mw_cm2: float,
                              n_elements: int = 1024) -> MicrowaveSafetyResult:
    """
    Full microwave safety assessment per IEEE C95.1-2019 / ICNIRP.
    """
    G_lin = 10**(gain_dbi / 10)

    occ_dist  = rf_safe_distance(total_tx_rf_w, G_lin, RF_LIMIT_OCCUPATIONAL_MW_CM2)
    pub_dist  = rf_safe_distance(total_tx_rf_w, G_lin, RF_LIMIT_PUBLIC_MW_CM2)

    # Sidelobe power density estimate at 50 m (SLL ~ -20 dB → gain reduced by 100×)
    sl_gain   = G_lin * 0.01   # -20 dB sidelobe
    pd_sl_50m_w_m2 = total_tx_rf_w * sl_gain / (4 * np.pi * 50**2)
    pd_sl_50m_mw_cm2 = pd_sl_50m_w_m2 / 10

    compliant_main = pd_at_range_mw_cm2 < RF_LIMIT_OCCUPATIONAL_MW_CM2
    compliant_sl   = pd_sl_50m_mw_cm2  < RF_LIMIT_PUBLIC_MW_CM2

    warnings = []
    if not compliant_main:
        warnings.append(f"⚠ Main beam PD {pd_at_range_mw_cm2:.1f} mW/cm² exceeds occupational limit {RF_LIMIT_OCCUPATIONAL_MW_CM2} mW/cm²")
    if not compliant_sl:
        warnings.append(f"⚠ Sidelobe PD {pd_sl_50m_mw_cm2:.2f} mW/cm² at 50 m exceeds public limit")
    if occ_dist > 10:
        warnings.append(f"ℹ Exclusion zone (occupational): {occ_dist:.0f} m radius from antenna")
    if pub_dist > occ_dist:
        warnings.append(f"ℹ Public safety distance: {pub_dist:.0f} m — post RF hazard signs beyond this")
    warnings.append("ℹ FCC 47 CFR §15.247 licensing required for 5.8 GHz at this power level")

    return MicrowaveSafetyResult(
        occupational_safe_distance_m  = occ_dist,
        public_safe_distance_m        = pub_dist,
        main_beam_pd_at_range_mw_cm2  = pd_at_range_mw_cm2,
        sidelobe_pd_at_50m_mw_cm2     = pd_sl_50m_mw_cm2,
        compliant_main_beam           = compliant_main,
        compliant_sidelobes           = compliant_sl,
        warnings                      = warnings,
    )


# ── Interlock modeling ────────────────────────────────────────────────────

def model_interlock_scenario(trigger: str, tx_power_w: float) -> InterlockScenario:
    """
    Model a safety interlock dropout/recovery scenario.
    Computes max uncontrolled energy during interlock response.
    """
    t_ms = INTERLOCK_RESPONSE_MS.get(trigger, 100.0)
    t_s  = t_ms / 1000.0
    energy = tx_power_w * t_s  # Joules

    # Safe threshold: < 10 J uncontrolled energy for occupational zones
    safe = energy < 10.0

    mitigations = {
        "beam_block":    "Mechanical shutter: fastest physical kill. Install on transmitter aperture.",
        "rf_kill":       "Solid-state PA gate-off. Sub-ms response. Primary RF safety.",
        "tracking_lost": "Beam steering to safe direction + RF kill within 50 ms.",
        "safety_pilot":  "Human-in-loop: pilot eye monitors beam, initiates kill-switch.",
        "power_down_full": "Full power-off sequence. Emergency only.",
    }

    return InterlockScenario(
        trigger          = trigger,
        tx_power_w       = tx_power_w,
        response_time_ms = t_ms,
        energy_deposited_j = energy,
        safe             = safe,
        mitigation       = mitigations.get(trigger, "Unknown interlock type"),
    )


def print_safety_report(laser_safety: Optional[LaserSafetyResult] = None,
                         mw_safety: Optional[MicrowaveSafetyResult] = None,
                         interlocks: Optional[list] = None) -> str:
    lines = ["=" * 65, "  SAFETY ASSESSMENT REPORT", "=" * 65]

    if laser_safety:
        lines += [
            "",
            "  ── Laser Safety (ANSI Z136.1 / IEC 60825-1) ───────────",
            f"  Eye MPE (1070 nm CW):   {laser_safety.eye_mpe_w_cm2*1000:.1f} mW/cm²",
            f"  Skin MPE:               {laser_safety.skin_mpe_w_cm2*1000:.0f} mW/cm²",
            f"  Eye NOHD:               {laser_safety.nominal_hazard_distance_m:.0f} m",
            f"  Skin hazard distance:   {laser_safety.skin_hazard_distance_m:.1f} m",
            f"  Exclusion zone:         {laser_safety.exclusion_zone_radius_m:.0f} m radius",
            f"  Irradiance @ 100 m:     {laser_safety.irradiance_at_100m_w_cm2*1000:.2f} mW/cm²",
            f"  Irradiance @ 1 km:      {laser_safety.irradiance_at_1km_w_cm2*1000:.4f} mW/cm²",
            f"  Compliant at range:     {'YES ✓' if laser_safety.compliant_at_range else 'NO ✗'}",
        ]
        for w in laser_safety.warnings:
            lines.append(f"  {w}")

    if mw_safety:
        lines += [
            "",
            "  ── RF Safety (IEEE C95.1-2019 / ICNIRP) ────────────────",
            f"  Main-beam PD at range:  {mw_safety.main_beam_pd_at_range_mw_cm2:.3f} mW/cm²",
            f"  Occ. limit (5.8 GHz):   {RF_LIMIT_OCCUPATIONAL_MW_CM2} mW/cm²",
            f"  Public limit:           {RF_LIMIT_PUBLIC_MW_CM2} mW/cm²",
            f"  Occ. safe distance:     {mw_safety.occupational_safe_distance_m:.0f} m",
            f"  Public safe distance:   {mw_safety.public_safe_distance_m:.0f} m",
            f"  Sidelobe PD @ 50 m:     {mw_safety.sidelobe_pd_at_50m_mw_cm2:.3f} mW/cm²",
            f"  Main beam compliant:    {'YES ✓' if mw_safety.compliant_main_beam else 'NO ✗'}",
            f"  Sidelobe compliant:     {'YES ✓' if mw_safety.compliant_sidelobes else 'NO ✗'}",
        ]
        for w in mw_safety.warnings:
            lines.append(f"  {w}")

    if interlocks:
        lines += ["", "  ── Interlock Scenarios ─────────────────────────────────"]
        for ilk in interlocks:
            status = "SAFE ✓" if ilk.safe else "UNSAFE ✗"
            lines.append(
                f"  [{status}] {ilk.trigger}: {ilk.response_time_ms} ms → "
                f"{ilk.energy_deposited_j:.2f} J at {ilk.tx_power_w/1000:.1f} kW"
            )
            lines.append(f"    → {ilk.mitigation}")

    lines.append("=" * 65)
    return "\n".join(lines)
