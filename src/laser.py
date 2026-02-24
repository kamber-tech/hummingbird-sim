"""
laser.py - Gaussian beam propagation and laser WPT physics engine
Aether Sim | Laser Wireless Power Transmission Module

Sources:
  - Saleh & Teich, "Fundamentals of Photonics" (Gaussian beams)
  - Beer-Lambert atmospheric attenuation: Koschmieder visibility law
  - Turbulence: Rytov variance, Kolmogorov spectrum (Andrews & Phillips 2005)
  - Atmospheric coefficients: McMaster ECE / SPIE 2000 (clear=0.1/km, haze=1/km, fog=10/km)
  - PV efficiency at 1070nm: MDPI Photonics 2025 (55% InP multijunction), GaAs ~40-50%
  - Pointing jitter loss model: Andrews & Phillips, "Laser Beam Propagation through Random Media"
  - Hufnagel-Valley turbulence model: Andrews & Phillips Ch. 12
  - Fried parameter: Fried 1966 JOSA; Andrews & Phillips Eq. 5.1
  - PV temperature coefficient: Typical Si/GaAs ~0.4%/°C
  - M² beam quality: Self 1983 Applied Optics
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional

# ── Physical constants ─────────────────────────────────────────────────────
C_LIGHT = 2.998e8      # m/s
LAMBDA_NM = 1070.0     # nm  (Yb-doped fiber laser, industry standard for WPT)
LAMBDA_M  = LAMBDA_NM * 1e-9  # m

# ── Atmospheric attenuation coefficients @ 1070 nm (Beer-Lambert) ─────────
# Units: 1/km (extinction coefficient beta; dB/km = beta * 4.343)
# Validated sources (2025):
#   Clear sky: 0.93–0.98 transmittance/km → 0.02–0.07 dB/km (use midpoint 0.05 dB/km)
#   Light haze: 0.5–2 dB/km (use 1.0 dB/km)
#   Fog: 10–30 dB/km → HARD BLOCK (availability gate, not just a penalty)
#   Rain: 0.09–0.35 dB/km — rain is NOT the worst for laser; fog/cloud is
#   Smoke: ~5 dB/km battlefield estimate
# Conversion: beta = dB_per_km / 4.343
FOG_HARD_BLOCK_CONDITIONS = {"fog", "light_fog"}  # link unavailable; return zero efficiency

ATMO_CONDITIONS = {
    "clear":      0.0115,  # ≈0.05 dB/km  — validated clear day (0.02–0.07 dB/km range)
    "haze":       0.230,   # ≈1.0  dB/km  — light haze (0.5–2 dB/km range)
    "light_fog":  1.15,    # ≈5.0  dB/km  — light fog; HARD BLOCK above ~2 km
    "fog":        6.91,    # ≈30.0 dB/km  — dense fog; HARD BLOCK at any range
    "smoke":      1.84,    # ≈8.0  dB/km  — dense battlefield smoke (MIL-C-70214B; 5-15 dB/km range)
    "dust":       0.693,   # ≈3.0  dB/km  — desert dust storm
    "rain":       0.046,   # ≈0.20 dB/km  — validated rain (0.09–0.35 dB/km range)
                           #                 Note: rain is mild for laser vs fog/cloud
}

# ── Atmospheric turbulence: Cn² by condition ──────────────────────────────
# Hufnagel-Valley inspired ground-level Cn² estimates [m^(-2/3)]
# clear: 1e-14 (moderate), haze: 5e-14 (elevated, thermal mixing), smoke: 2e-13 (strong)
CN2_BY_CONDITION = {
    "clear":     1e-14,
    "haze":      5e-14,
    "light_fog": 1e-14,
    "fog":       1e-14,
    "smoke":     2e-13,
    "dust":      5e-14,
    "rain":      5e-14,  # rain associated with elevated humidity, mixing
}

# PV cell efficiency at 1070 nm by technology
PV_EFFICIENCY = {
    "gaas":              0.50,   # GaAs laser PV cells ~50% at 1070 nm
    "inp_multijunction": 0.55,   # InP-based 8-junction, MDPI Photonics 2025
    "si":                0.30,   # Silicon cells — lower at 1070 nm
    "geass":             0.47,   # Ge/GaAs dual junction
}

# PV temperature coefficient (%/°C) — efficiency drops above 25°C reference
PV_TEMP_COEFF_PCT_C = 0.4   # %/°C (typical for GaAs/InP, conservative)
PV_OPERATING_TEMP_C = 60.0  # typical deployed cell temperature (°C)
PV_REF_TEMP_C       = 25.0  # STC reference temperature (°C)

# Central obscuration factor (secondary mirror in receiver telescope)
CENTRAL_OBSCURATION_FRACTION = 0.20   # 20% area blocked


@dataclass
class LaserBeam:
    """Gaussian beam parameters at the transmitter aperture."""
    wavelength_m: float = LAMBDA_M          # wavelength
    waist_radius_m: float = 0.05            # w0 = beam waist (1/e² radius at focus), m
    m_squared: float = 1.3                  # beam quality factor (M²; real fiber ~1.1-1.8)
    output_power_w: float = 10_000.0        # optical output power at aperture (W)
    wall_plug_efficiency: float = 0.40      # wall-plug → photon efficiency (40% for Yb fiber laser)

@dataclass
class LaserReceiver:
    """Photovoltaic receiver array at the remote end."""
    pv_type: str = "gaas"                   # cell technology key
    aperture_radius_m: float = 0.30         # physical receiver aperture radius (m)
    fill_factor: float = 0.90               # fraction of aperture covered by cells
    concentration_factor: float = 1.0       # optional optical concentrator
    power_conditioning_eff: float = 0.95    # DC-DC converter efficiency
    cell_temp_c: float = PV_OPERATING_TEMP_C  # operating cell temperature (°C)

@dataclass
class AtmosphericConditions:
    """Atmospheric state for a given link."""
    condition: str = "clear"                # key into ATMO_CONDITIONS
    custom_beta_per_km: Optional[float] = None  # override attenuation if desired
    turbulence_Cn2: float = None            # if None, derived from condition via CN2_BY_CONDITION
                                            # m^(-2/3): 1e-17 weak, 1e-14 moderate, 1e-13 strong


# ── Core physics functions ─────────────────────────────────────────────────

def get_Cn2(atmosphere: 'AtmosphericConditions') -> float:
    """Return Cn² for atmosphere, using condition table if not explicitly set."""
    if atmosphere.turbulence_Cn2 is not None:
        return atmosphere.turbulence_Cn2
    return CN2_BY_CONDITION.get(atmosphere.condition, 1e-14)


def rayleigh_range(waist_m: float, wavelength_m: float, m_squared: float = 1.0) -> float:
    """
    Rayleigh range z_R (m): distance at which beam area doubles.
    z_R = π * w0² / (M² * λ)
    Ref: Saleh & Teich Eq. 3.1-13 (modified for M²)
    """
    return np.pi * waist_m**2 / (m_squared * wavelength_m)


def beam_radius_at_range(range_m: float, beam: LaserBeam) -> float:
    """
    1/e² beam radius w(z) at distance z from waist.
    w(z) = w0 * M² * sqrt(1 + (z/z_R)²)
    M² factor effectively increases divergence for real beams.
    """
    z_R = rayleigh_range(beam.waist_radius_m, beam.wavelength_m, beam.m_squared)
    return beam.waist_radius_m * beam.m_squared * np.sqrt(1 + (range_m / z_R)**2)


def peak_irradiance_at_range(range_m: float, beam: LaserBeam) -> float:
    """
    Peak irradiance I0(z) = 2*P / (π * w(z)²)  [W/m²]
    """
    w = beam_radius_at_range(range_m, beam)
    return 2.0 * beam.output_power_w / (np.pi * w**2)


def power_in_bucket(range_m: float, beam: LaserBeam, bucket_radius_m: float) -> float:
    """
    Power within a circular aperture of radius r at range z.
    P_bucket = P * (1 - exp(-2r²/w²))
    Ref: Saleh & Teich Eq. 3.1-23
    """
    w = beam_radius_at_range(range_m, beam)
    return beam.output_power_w * (1.0 - np.exp(-2.0 * bucket_radius_m**2 / w**2))


def atmospheric_transmittance(range_km: float, conditions: AtmosphericConditions) -> float:
    """
    Beer-Lambert transmittance T = exp(-beta * L)
    beta: extinction coefficient [1/km], L: path length [km]
    """
    if conditions.custom_beta_per_km is not None:
        beta = conditions.custom_beta_per_km
    else:
        beta = ATMO_CONDITIONS.get(conditions.condition, 0.10)
    return np.exp(-beta * range_km)


def atmospheric_attenuation_db(range_km: float, conditions: AtmosphericConditions) -> float:
    """Atmospheric path loss in dB."""
    T = atmospheric_transmittance(range_km, conditions)
    if T <= 0:
        return np.inf
    return -10.0 * np.log10(T)


def rytov_variance(range_m: float, conditions: AtmosphericConditions,
                   wavelength_m: float = LAMBDA_M) -> float:
    """
    Rytov variance σ_R² — measure of scintillation strength.
    σ_R² = 1.23 * Cn² * k^(7/6) * L^(11/6)
    Ref: Andrews & Phillips Eq. 8.13
    """
    k = 2 * np.pi / wavelength_m
    Cn2 = get_Cn2(conditions)
    return 1.23 * Cn2 * k**(7/6) * range_m**(11/6)


def fried_parameter(range_m: float, conditions: AtmosphericConditions,
                    wavelength_m_val: float = LAMBDA_M) -> float:
    """
    Fried coherence length r₀ (m) using Hufnagel-Valley inspired formula.
    r₀ = 0.185 * (λ² / (Cn² * L))^0.6
    Ref: Andrews & Phillips; Fried 1966 JOSA
    """
    Cn2 = get_Cn2(conditions)
    # Avoid division by zero
    if Cn2 <= 0 or range_m <= 0:
        return 1000.0  # effectively infinite coherence
    r0 = 0.185 * (wavelength_m_val**2 / (Cn2 * range_m))**0.6
    return max(r0, 1e-4)  # physical floor


def turbulence_strehl_ratio(beam: LaserBeam, range_m: float,
                             conditions: AtmosphericConditions) -> float:
    """
    Strehl ratio due to atmospheric turbulence (PEAK irradiance metric).
    S_turb = exp(-(D/r₀)^(5/3))
    where D = transmitter aperture diameter = 2*w0

    NOTE: This is for COHERENT systems / peak irradiance only.
    For WPT power collection, use turbulence_wpt_factor() instead.
    Ref: Roddier 1981; Maréchal approximation for strong turbulence
    """
    r0 = fried_parameter(range_m, conditions, beam.wavelength_m)
    D = 2 * beam.waist_radius_m
    S = np.exp(-((D / r0)**(5.0/3.0)))
    return float(np.clip(S, 1e-6, 1.0))


def turbulence_wpt_factor(beam: LaserBeam, range_m: float,
                           conditions: AtmosphericConditions,
                           receiver_radius_m: float) -> float:
    """
    Power delivery factor for WPT due to atmospheric turbulence.

    Unlike Strehl (peak irradiance for coherent systems), this computes the
    TOTAL POWER fraction delivered to a finite aperture after turbulence
    broadens the long-term beam profile.

    Two effects modeled:
    1. Beam spreading: turbulence increases the long-term beam radius,
       potentially pushing some energy outside the receiver aperture.
       w_LT = w_vac * sqrt(1 + (w₀/r₀)^(5/3))    [long-term broadening]
    2. Scintillation penalty: rapid intensity fluctuations reduce average
       PV output. For strong turbulence (σ_R² ≥ 1), penalty ~0.5–1.5 dB.
       T_scint = max(0.60, exp(-0.12 * min(sigma_R2, 4.0)))

    Ref: Andrews & Phillips "Laser Beam Propagation through Random Media"
         (long-term beam profile, aperture averaging)
    """
    w_vac = beam_radius_at_range(range_m, beam)
    r0 = fried_parameter(range_m, conditions, beam.wavelength_m)

    # Long-term beam radius including turbulence spreading
    broadening = 1.0 + (beam.waist_radius_m / max(r0, 1e-6))**(5.0/3.0)
    w_LT = w_vac * np.sqrt(broadening)

    # Power in receiver aperture (turbulence-broadened long-term beam)
    p_lt = 1.0 - np.exp(-2.0 * receiver_radius_m**2 / w_LT**2)
    # Power in receiver aperture (diffraction-limited, no turbulence)
    p_vac = 1.0 - np.exp(-2.0 * receiver_radius_m**2 / w_vac**2)

    spreading_factor = (p_lt / p_vac) if p_vac > 1e-10 else 1.0

    # Scintillation penalty (intensity fluctuations reduce average PV output)
    sigma_R2 = rytov_variance(range_m, conditions, beam.wavelength_m)
    # Capped at σ_R² = 4 (saturation regime); max ~1.5 dB penalty
    scint_penalty = max(0.60, np.exp(-0.12 * min(sigma_R2, 4.0)))

    return float(np.clip(spreading_factor * scint_penalty, 0.01, 1.0))


def pointing_jitter_loss(beam: LaserBeam, range_m: float, jitter_urad: float = 5.0) -> float:
    """
    Intensity loss fraction due to pointing/tracking jitter.
    Loss = exp(-2 * (σ_jitter * range / w(range))²)
    where w(range) is the 1/e² beam radius at the receiver.
    Default 5 µrad is typical for a good tracking system.
    Ref: Andrews & Phillips Eq. 7.2
    """
    sigma_rad = jitter_urad * 1e-6
    sigma_r = sigma_rad * range_m          # 1-sigma pointing displacement at receiver (m)
    w = beam_radius_at_range(range_m, beam)
    return float(np.exp(-2.0 * sigma_r**2 / w**2))


def pv_temperature_derating(pv_type: str, cell_temp_c: float) -> float:
    """
    PV efficiency temperature derating factor.
    Efficiency drops PV_TEMP_COEFF_PCT_C %/°C above 25°C STC.
    For cell_temp_c = 60°C: derating = 1 - 0.004 * 35 = 0.86 (14% penalty)
    """
    delta_t = max(0.0, cell_temp_c - PV_REF_TEMP_C)
    derating = 1.0 - (PV_TEMP_COEFF_PCT_C / 100.0) * delta_t
    return float(np.clip(derating, 0.5, 1.0))


def central_obscuration_factor() -> float:
    """
    Power loss due to central obscuration of receiver telescope secondary mirror.
    Area blocked = CENTRAL_OBSCURATION_FRACTION = 20%
    """
    return 1.0 - CENTRAL_OBSCURATION_FRACTION


# ── End-to-end link budget ────────────────────────────────────────────────

@dataclass
class LaserLinkResult:
    """Full laser link budget and efficiency breakdown."""
    range_m: float
    condition: str
    # Powers
    electrical_input_w: float        # wall-plug input
    optical_tx_power_w: float        # power out of laser aperture
    beam_power_at_rx_w: float        # before receiver aperture loss
    captured_power_w: float          # inside receiver aperture (geometric + atmo)
    pv_output_w: float               # after PV conversion
    dc_output_w: float               # after DC-DC conditioning
    # Efficiencies
    wall_plug_eff: float
    atmospheric_transmittance: float
    geometric_collection_eff: float
    turbulence_strehl: float
    pointing_loss: float
    m2_beam_quality: float
    pv_efficiency: float
    pv_temp_derating: float
    obscuration_factor: float
    conditioning_eff: float
    total_system_eff: float          # dc_out / electrical_in
    # Derived
    link_budget_db: float
    beam_radius_at_rx_m: float
    rytov_variance: float
    fried_r0_m: float
    Cn2: float
    # Safety
    peak_irradiance_wx_m2: float     # W/m² at receiver face
    # Loss budget details
    loss_budget: dict
    loss_fractions: dict


# ── DARPA PRAD anchor point (sanity check reference) ─────────────────────
# DARPA POWER PRAD 2025: 800 W delivered, 8.6 km range, ~20% system efficiency
# This is state-of-the-art. Use as external validation anchor in feasibility checks.
DARPA_PRAD_ANCHOR = {
    "description": "DARPA POWER PRAD 2025 field demo",
    "dc_power_w": 800,
    "range_km": 8.6,
    "system_efficiency_pct": 20.0,
    "notes": "Laser-out to electricity-out. Best demonstrated result as of 2025.",
}
JAXA_MW_ANCHOR = {
    "description": "JAXA microwave WPT demo 2021",
    "system_efficiency_pct": 22.0,
    "notes": "Best demonstrated microwave WPT end-to-end efficiency as of 2021.",
}

# Real-world system overhead factor: accounts for control electronics, thermal mgmt,
# array non-uniformity, connector losses, regulatory derating, etc.
# Anchored to: DARPA PRAD 20%, JAXA MW 22% vs component-chain ~30-40%
SYSTEM_OVERHEAD_FACTOR = 0.65   # multiply physics-chain efficiency by this
MAX_SYSTEM_EFF = 0.35           # hard cap: 35% (above DARPA/JAXA state-of-art)


def compute_laser_link(
    range_m: float,
    beam: LaserBeam,
    receiver: LaserReceiver,
    atmosphere: AtmosphericConditions,
    jitter_urad: float = 5.0,
) -> LaserLinkResult:
    """
    Full end-to-end laser link budget computation (v2 — enhanced physics).

    New physics added:
      - Cn² from condition table (Hufnagel-Valley inspired)
      - Fried parameter r₀ = 0.185 * (λ²/(Cn²·L))^0.6
      - Turbulence Strehl: S = exp(-(D/r₀)^(5/3))
      - Pointing jitter: exp(-2·(σ·R/w(R))²) with w(R) correctly computed
      - M² beam quality: increases divergence, larger w(R) → less geometric collection
      - PV temperature derating: 0.4%/°C above 25°C, cell at 60°C → 14% penalty
      - Central obscuration: 20% area loss for secondary mirror
      - Fog hard block: fog/light_fog conditions return zero efficiency (availability gate)
      - System overhead factor: 0.65× physics chain, capped at 35%
    """
    # ── Fog hard block ────────────────────────────────────────────────────
    if atmosphere.condition in FOG_HARD_BLOCK_CONDITIONS:
        elec_input = beam.output_power_w / beam.wall_plug_efficiency
        zero_lb = {
            "wall_plug_loss_db": round(-10*np.log10(beam.wall_plug_efficiency), 2),
            "atmospheric_absorption_db": 999.0,
            "turbulence_strehl_db": 0.0, "pointing_jitter_db": 0.0,
            "geometric_collection_db": 0.0, "central_obscuration_db": 0.0,
            "pv_base_efficiency_db": 0.0, "pv_temp_derating_db": 0.0,
            "dc_dc_conditioning_db": 0.0, "m2_beam_quality": beam.m_squared,
            "fried_r0_m": 0.0, "Cn2_m_neg23": get_Cn2(atmosphere),
            "rytov_variance": 0.0,
            "total_loss_db": None,
            "fog_hard_block": True,
        }
        return LaserLinkResult(
            range_m=range_m, condition=atmosphere.condition,
            electrical_input_w=elec_input, optical_tx_power_w=beam.output_power_w,
            beam_power_at_rx_w=0.0, captured_power_w=0.0,
            pv_output_w=0.0, dc_output_w=0.0,
            wall_plug_eff=beam.wall_plug_efficiency, atmospheric_transmittance=0.0,
            geometric_collection_eff=0.0, turbulence_strehl=0.0, pointing_loss=0.0,
            m2_beam_quality=beam.m_squared, pv_efficiency=0.0, pv_temp_derating=0.0,
            obscuration_factor=0.0, conditioning_eff=receiver.power_conditioning_eff,
            total_system_eff=0.0, link_budget_db=-999.0,
            beam_radius_at_rx_m=beam_radius_at_range(range_m, beam),
            rytov_variance=0.0, fried_r0_m=0.0, Cn2=get_Cn2(atmosphere),
            peak_irradiance_wx_m2=0.0, loss_budget=zero_lb, loss_fractions={},
        )

    # ── Electrical input ──────────────────────────────────────────────────
    elec_input = beam.output_power_w / beam.wall_plug_efficiency
    wall_plug_eff = beam.wall_plug_efficiency

    # ── Gaussian propagation ──────────────────────────────────────────────
    w_rx = beam_radius_at_range(range_m, beam)

    # M² factor: captured in beam_radius_at_range (already uses M²)
    m2_factor = beam.m_squared

    # ── Geometric collection efficiency ───────────────────────────────────
    p_in_bucket_full = power_in_bucket(range_m, beam, receiver.aperture_radius_m)
    geo_eff = p_in_bucket_full / beam.output_power_w

    # ── Atmospheric transmittance (Beer-Lambert) ───────────────────────────
    range_km = range_m / 1000.0
    T_atmo = atmospheric_transmittance(range_km, atmosphere)
    atmo_db = atmospheric_attenuation_db(range_km, atmosphere)

    # ── Turbulence ────────────────────────────────────────────────────────
    Cn2_val  = get_Cn2(atmosphere)
    r0       = fried_parameter(range_m, atmosphere, beam.wavelength_m)
    # Strehl for diagnostics/peak irradiance only — NOT used in power chain
    S_turb   = turbulence_strehl_ratio(beam, range_m, atmosphere)
    # WPT power factor: accounts for beam spreading into large aperture
    T_turb_wpt = turbulence_wpt_factor(beam, range_m, atmosphere, receiver.aperture_radius_m)
    sigma_r2 = rytov_variance(range_m, atmosphere)

    # ── Pointing jitter ───────────────────────────────────────────────────
    L_jitter = pointing_jitter_loss(beam, range_m, jitter_urad)
    jitter_db = -10 * np.log10(max(L_jitter, 1e-10))

    # ── Central obscuration ───────────────────────────────────────────────
    obs_factor = central_obscuration_factor()
    obscuration_db = -10 * np.log10(obs_factor)

    # ── PV temperature derating ───────────────────────────────────────────
    pv_temp_derating_factor = pv_temperature_derating(receiver.pv_type, receiver.cell_temp_c)
    pv_temp_db = -10 * np.log10(max(pv_temp_derating_factor, 1e-4))

    # ── Power at receiver ─────────────────────────────────────────────────
    # Use WPT turbulence factor (not Strehl) — Strehl is for coherent peak only.
    # WPT turbulence factor captures: long-term beam broadening + scintillation penalty.
    p_at_rx = beam.output_power_w * T_atmo * T_turb_wpt * L_jitter

    # Geometric + fill factor + obscuration on the captured fraction
    p_captured = p_at_rx * geo_eff * receiver.fill_factor * obs_factor

    # ── PV conversion ─────────────────────────────────────────────────────
    pv_eff_base = PV_EFFICIENCY.get(receiver.pv_type, 0.40)
    pv_eff_derated = pv_eff_base * pv_temp_derating_factor
    p_pv = p_captured * pv_eff_derated

    # ── Power conditioning ────────────────────────────────────────────────
    p_dc = p_pv * receiver.power_conditioning_eff

    # ── System efficiency — apply real-world overhead + cap ───────────────
    physics_eff = p_dc / elec_input if elec_input > 0 else 0.0
    total_eff = min(MAX_SYSTEM_EFF, physics_eff * SYSTEM_OVERHEAD_FACTOR)
    # Back-calculate DC power after overhead adjustment
    p_dc = total_eff * elec_input

    # ── Link budget (dB) ──────────────────────────────────────────────────
    lb_db = 10 * np.log10(total_eff) if total_eff > 0 else -999.0

    # ── Peak irradiance at receiver face ──────────────────────────────────
    peak_irr = peak_irradiance_at_range(range_m, beam) * T_atmo * S_turb * L_jitter

    # ── Loss budget (dB) ──────────────────────────────────────────────────
    wall_plug_db      = -10 * np.log10(wall_plug_eff)
    atmo_db_val       = atmo_db
    # WPT turbulence factor (power delivery) — replaces Strehl in power chain
    turb_wpt_db       = -10 * np.log10(max(T_turb_wpt, 1e-10))
    # Strehl kept for diagnostics (peak irradiance / coherent imaging reference)
    turb_strehl_db    = -10 * np.log10(max(S_turb, 1e-10))
    geo_db            = -10 * np.log10(max(geo_eff * receiver.fill_factor, 1e-10))
    rect_eff_db       = -10 * np.log10(pv_eff_derated)
    dc_dc_db          = -10 * np.log10(receiver.power_conditioning_eff)
    m2_db             = -10 * np.log10(max(1.0 / m2_factor**2, 1e-10)) if m2_factor > 1 else 0.0

    loss_budget = {
        "wall_plug_loss_db":           round(wall_plug_db, 2),
        "atmospheric_absorption_db":   round(atmo_db_val, 3),
        # WPT turbulence (beam spreading + scintillation, large aperture)
        "turbulence_strehl_db":        round(turb_wpt_db, 2),
        # Coherent Strehl (diagnostic only — not used in power chain)
        "coherent_strehl_db_info_only": round(turb_strehl_db, 2),
        "pointing_jitter_db":          round(jitter_db, 2),
        "geometric_collection_db":     round(geo_db, 2),
        "central_obscuration_db":      round(obscuration_db, 2),
        "pv_base_efficiency_db":       round(-10 * np.log10(pv_eff_base), 2),
        "pv_temp_derating_db":         round(pv_temp_db, 2),
        "dc_dc_conditioning_db":       round(dc_dc_db, 2),
        "m2_beam_quality":             round(m2_factor, 2),
        "fried_r0_m":                  round(r0, 4),
        "Cn2_m_neg23":                 Cn2_val,
        "rytov_variance":              round(sigma_r2, 6),
        "total_loss_db":               round(-lb_db, 2) if p_dc > 0 else None,
    }

    loss_fractions = {
        "wall_plug":                  round(wall_plug_eff, 4),
        "atmospheric":                round(T_atmo, 6),
        "turbulence_wpt_factor":      round(T_turb_wpt, 4),  # used in power chain
        "turbulence_strehl_info":     round(S_turb, 6),       # diagnostic only
        "pointing_jitter":            round(L_jitter, 4),
        "geometric_collection":       round(geo_eff, 4),
        "fill_factor":                round(receiver.fill_factor, 4),
        "central_obscuration":        round(obs_factor, 4),
        "pv_base_efficiency":         round(pv_eff_base, 4),
        "pv_temp_derating":           round(pv_temp_derating_factor, 4),
        "dc_dc_conditioning":         round(receiver.power_conditioning_eff, 4),
    }

    return LaserLinkResult(
        range_m=range_m,
        condition=atmosphere.condition,
        electrical_input_w=elec_input,
        optical_tx_power_w=beam.output_power_w,
        beam_power_at_rx_w=p_at_rx,
        captured_power_w=p_captured,
        pv_output_w=p_pv,
        dc_output_w=p_dc,
        wall_plug_eff=wall_plug_eff,
        atmospheric_transmittance=T_atmo,
        geometric_collection_eff=geo_eff,
        turbulence_strehl=T_turb_wpt,  # WPT power factor (not coherent Strehl)
        pointing_loss=L_jitter,
        m2_beam_quality=m2_factor,
        pv_efficiency=pv_eff_derated,
        pv_temp_derating=pv_temp_derating_factor,
        obscuration_factor=obs_factor,
        conditioning_eff=receiver.power_conditioning_eff,
        total_system_eff=total_eff,
        link_budget_db=lb_db,
        beam_radius_at_rx_m=w_rx,
        rytov_variance=sigma_r2,
        fried_r0_m=r0,
        Cn2=Cn2_val,
        peak_irradiance_wx_m2=peak_irr,
        loss_budget=loss_budget,
        loss_fractions=loss_fractions,
    )


def print_laser_report(result: LaserLinkResult) -> str:
    """Format a readable laser link budget report."""
    lb = result.loss_budget
    lines = [
        "=" * 65,
        "  LASER WPT LINK BUDGET REPORT (v2 - Enhanced Physics)",
        "=" * 65,
        f"  Range:              {result.range_m/1000:.2f} km",
        f"  Condition:          {result.condition}",
        f"  Wavelength:         {LAMBDA_NM:.0f} nm",
        f"  M² beam quality:    {result.m2_beam_quality:.2f}",
        f"  Cn²:               {result.Cn2:.2e} m^(-2/3)",
        f"  Fried r₀:           {result.fried_r0_m*100:.2f} cm",
        "",
        "  ── Power Chain ──────────────────────────────────────────",
        f"  Electrical input:   {result.electrical_input_w/1000:.2f} kW",
        f"  Optical TX power:   {result.optical_tx_power_w/1000:.2f} kW",
        f"  Power at RX:        {result.beam_power_at_rx_w/1000:.3f} kW",
        f"  Captured by RX:     {result.captured_power_w/1000:.3f} kW",
        f"  PV DC output:       {result.pv_output_w/1000:.3f} kW",
        f"  Conditioned DC:     {result.dc_output_w/1000:.3f} kW",
        "",
        "  ── Loss Budget (dB) ─────────────────────────────────────",
        f"  Wall-plug loss:    +{lb.get('wall_plug_loss_db', 0):.2f} dB",
        f"  Atmospheric abs:   +{lb.get('atmospheric_absorption_db', 0):.3f} dB",
        f"  Turbulence Strehl: +{lb.get('turbulence_strehl_db', 0):.2f} dB",
        f"  Pointing jitter:   +{lb.get('pointing_jitter_db', 0):.2f} dB",
        f"  Geometric capture: +{lb.get('geometric_collection_db', 0):.2f} dB",
        f"  Central obscur.:   +{lb.get('central_obscuration_db', 0):.2f} dB",
        f"  PV base eff:       +{lb.get('pv_base_efficiency_db', 0):.2f} dB",
        f"  PV temp derating:  +{lb.get('pv_temp_derating_db', 0):.2f} dB",
        f"  DC-DC cond.:       +{lb.get('dc_dc_conditioning_db', 0):.2f} dB",
        "",
        f"  TOTAL system eff:   {result.total_system_eff*100:.2f}%",
        f"  Link budget:        {result.link_budget_db:.1f} dB",
        "",
        "  ── Beam Properties ──────────────────────────────────────",
        f"  Beam radius @ RX:   {result.beam_radius_at_rx_m*100:.2f} cm",
        f"  Rytov variance:     {result.rytov_variance:.6f}",
        "",
        "  ── Safety ───────────────────────────────────────────────",
        f"  Peak irradiance:    {result.peak_irradiance_wx_m2/1e4:.2f} W/cm²",
        "=" * 65,
    ]
    return "\n".join(lines)
