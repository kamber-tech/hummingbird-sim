"""
laser.py - Gaussian beam propagation and laser WPT physics engine
Hummingbird Sim | Laser Wireless Power Transmission Module

Sources:
  - Saleh & Teich, "Fundamentals of Photonics" (Gaussian beams)
  - Beer-Lambert atmospheric attenuation: Koschmieder visibility law
  - Turbulence: Rytov variance, Kolmogorov spectrum (Andrews & Phillips 2005)
  - Atmospheric coefficients: McMaster ECE / SPIE 2000 (clear=0.1/km, haze=1/km, fog=10/km)
  - PV efficiency at 1070nm: MDPI Photonics 2025 (55% InP multijunction), GaAs ~40-50%
  - Pointing jitter loss model: Andrews & Phillips, "Laser Beam Propagation through Random Media"
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional

# ── Physical constants ─────────────────────────────────────────────────────
C_LIGHT = 2.998e8      # m/s
LAMBDA_NM = 1070.0     # nm  (Yb-doped fiber laser, industry standard for WPT)
LAMBDA_M  = LAMBDA_NM * 1e-9  # m

# ── Atmospheric attenuation coefficients @ 1070 nm (Beer-Lambert) ─────────
# Units: 1/km (extinction coefficient beta)
# Ref: McMaster ECE SPIE2000 / Koschmieder model
ATMO_CONDITIONS = {
    "clear":      0.10,   # 0.43 dB/km  — standard clear day (V > 23 km)
    "haze":       1.00,   # 4.34 dB/km  — haze (V ~ 2-4 km)
    "light_fog":  4.00,   # 17.4 dB/km  — light fog (V ~ 0.5 km)
    "fog":       10.00,   # 43.4 dB/km  — dense fog
    "smoke":      3.00,   # 13.0 dB/km  — battlefield smoke (estimated)
    "dust":       2.00,   # 8.7  dB/km  — desert dust storm (estimated)
    "rain":       0.50,   # 2.17 dB/km  — moderate rain (1070 nm less affected than visible)
}

# PV cell efficiency at 1070 nm by technology
PV_EFFICIENCY = {
    "gaas":           0.50,   # GaAs laser PV cells ~50% at 1070 nm (wall-plug photons→e-)
    "inp_multijunction": 0.55, # InP-based 8-junction, MDPI Photonics 2025
    "si":             0.30,   # Silicon cells — lower efficiency at 1070 nm (out of bandgap peak)
    "geass":          0.47,   # Ge/GaAs dual junction
}

@dataclass
class LaserBeam:
    """Gaussian beam parameters at the transmitter aperture."""
    wavelength_m: float = LAMBDA_M          # wavelength
    waist_radius_m: float = 0.05            # w0 = beam waist (1/e² radius at focus), m
    m_squared: float = 1.2                  # beam quality factor (M²=1 ideal, ~1.1-2 real laser)
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

@dataclass
class AtmosphericConditions:
    """Atmospheric state for a given link."""
    condition: str = "clear"                # key into ATMO_CONDITIONS
    custom_beta_per_km: Optional[float] = None  # override attenuation if desired
    turbulence_Cn2: float = 1e-15           # refractive index structure parameter [m^(-2/3)]
                                            # 1e-17 = weak, 1e-15 = moderate, 1e-13 = strong


# ── Core physics functions ─────────────────────────────────────────────────

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
    For a collimated transmitter, waist is at z=0 (transmitter).
    """
    z_R = rayleigh_range(beam.waist_radius_m, beam.wavelength_m, beam.m_squared)
    return beam.waist_radius_m * beam.m_squared * np.sqrt(1 + (range_m / z_R)**2)


def peak_irradiance_at_range(range_m: float, beam: LaserBeam) -> float:
    """
    Peak irradiance I0(z) = 2*P / (π * w(z)²)  [W/m²]
    For a Gaussian beam, peak intensity on axis.
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


def rytov_variance(range_m: float, conditions: AtmosphericConditions, wavelength_m: float = LAMBDA_M) -> float:
    """
    Rytov variance σ_R² — measure of scintillation strength.
    σ_R² = 1.23 * Cn² * k^(7/6) * L^(11/6)
    Ref: Andrews & Phillips "Laser Beam Propagation Through Random Media" Eq. 8.13
    Weak turbulence: σ_R² << 1; strong: σ_R² >> 1
    """
    k = 2 * np.pi / wavelength_m  # wavenumber
    Cn2 = conditions.turbulence_Cn2
    return 1.23 * Cn2 * k**(7/6) * range_m**(11/6)


def fried_parameter(range_m: float, conditions: AtmosphericConditions, wavelength_m: float = LAMBDA_M) -> float:
    """
    Fried coherence length r0 (m) for horizontal path.
    r0 = (0.423 * k² * Cn² * L)^(-3/5)
    Ref: Fried 1966 JOSA; Andrews & Phillips Eq. 5.1
    r0 > aperture_diameter → low turbulence effect
    """
    k = 2 * np.pi / wavelength_m
    Cn2 = conditions.turbulence_Cn2
    r0 = (0.423 * k**2 * Cn2 * range_m)**(-3/5)
    return r0


def turbulence_strehl_ratio(beam: LaserBeam, range_m: float, conditions: AtmosphericConditions) -> float:
    """
    Strehl ratio due to turbulence (wave-front distortion).
    S = 1 / (1 + (D/r0)^(5/3))   [Maréchal / Roddier approximation]
    where D = transmitter aperture diameter = 2*w0
    For adaptive optics corrected: S approaches 1.
    """
    r0 = fried_parameter(range_m, conditions, beam.wavelength_m)
    D = 2 * beam.waist_radius_m
    S = 1.0 / (1.0 + (D / r0)**(5/3))
    return np.clip(S, 0.0, 1.0)


def pointing_jitter_loss(beam: LaserBeam, range_m: float, jitter_urad: float = 5.0) -> float:
    """
    Intensity loss fraction due to pointing/tracking jitter.
    σ_θ: 1-sigma angular jitter in µrad → σ_r = σ_θ * range at receiver
    Loss factor = exp(-2 * σ_r² / w(z)²)
    Ref: Andrews & Phillips Eq. 7.2 (Gaussian beam, jitter model)
    Default 5 µrad is typical for a good tracking system.
    """
    sigma_rad = jitter_urad * 1e-6
    sigma_r = sigma_rad * range_m          # 1-sigma pointing error at receiver (m)
    w = beam_radius_at_range(range_m, beam)
    return np.exp(-2.0 * sigma_r**2 / w**2)


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
    pv_efficiency: float
    conditioning_eff: float
    total_system_eff: float          # dc_out / electrical_in
    # Derived
    link_budget_db: float
    beam_radius_at_rx_m: float
    rytov_variance: float
    fried_r0_m: float
    # Safety
    peak_irradiance_wx_m2: float     # W/m² at receiver face


def compute_laser_link(
    range_m: float,
    beam: LaserBeam,
    receiver: LaserReceiver,
    atmosphere: AtmosphericConditions,
    jitter_urad: float = 5.0,
) -> LaserLinkResult:
    """
    Full end-to-end laser link budget computation.
    Returns LaserLinkResult with all intermediate values.
    """
    # Electrical input
    elec_input = beam.output_power_w / beam.wall_plug_efficiency

    # Gaussian propagation — beam radius at receiver
    w_rx = beam_radius_at_range(range_m, beam)

    # Geometric collection efficiency (power-in-bucket)
    p_in_bucket = power_in_bucket(range_m, beam, receiver.aperture_radius_m)
    geo_eff = p_in_bucket / beam.output_power_w

    # Atmospheric transmittance
    range_km = range_m / 1000.0
    T_atmo = atmospheric_transmittance(range_km, atmosphere)

    # Turbulence Strehl
    S_turb = turbulence_strehl_ratio(beam, range_m, atmosphere)

    # Pointing jitter loss
    L_jitter = pointing_jitter_loss(beam, range_m, jitter_urad)

    # Power at receiver
    p_at_rx = beam.output_power_w * T_atmo * S_turb * L_jitter
    p_captured = p_at_rx * geo_eff * receiver.fill_factor

    # PV conversion
    pv_eff = PV_EFFICIENCY.get(receiver.pv_type, 0.40)
    p_pv = p_captured * pv_eff

    # Power conditioning
    p_dc = p_pv * receiver.power_conditioning_eff

    # System efficiency
    total_eff = p_dc / elec_input if elec_input > 0 else 0.0

    # Link budget in dB
    lb_db = 10 * np.log10(p_dc / elec_input) if (p_dc > 0 and elec_input > 0) else -999.0

    # Peak irradiance at receiver face
    peak_irr = peak_irradiance_at_range(range_m, beam) * T_atmo * S_turb * L_jitter

    # Turbulence params
    sigma_r2 = rytov_variance(range_m, atmosphere)
    r0 = fried_parameter(range_m, atmosphere)

    return LaserLinkResult(
        range_m=range_m,
        condition=atmosphere.condition,
        electrical_input_w=elec_input,
        optical_tx_power_w=beam.output_power_w,
        beam_power_at_rx_w=p_at_rx,
        captured_power_w=p_captured,
        pv_output_w=p_pv,
        dc_output_w=p_dc,
        wall_plug_eff=beam.wall_plug_efficiency,
        atmospheric_transmittance=T_atmo,
        geometric_collection_eff=geo_eff,
        turbulence_strehl=S_turb,
        pointing_loss=L_jitter,
        pv_efficiency=pv_eff,
        conditioning_eff=receiver.power_conditioning_eff,
        total_system_eff=total_eff,
        link_budget_db=lb_db,
        beam_radius_at_rx_m=w_rx,
        rytov_variance=sigma_r2,
        fried_r0_m=r0,
        peak_irradiance_wx_m2=peak_irr,
    )


def print_laser_report(result: LaserLinkResult) -> str:
    """Format a readable laser link budget report."""
    lines = [
        "=" * 65,
        "  LASER WPT LINK BUDGET REPORT",
        "=" * 65,
        f"  Range:              {result.range_m/1000:.2f} km",
        f"  Condition:          {result.condition}",
        f"  Wavelength:         {LAMBDA_NM:.0f} nm",
        "",
        "  ── Power Chain ──────────────────────────────────────────",
        f"  Electrical input:   {result.electrical_input_w/1000:.2f} kW",
        f"  Optical TX power:   {result.optical_tx_power_w/1000:.2f} kW",
        f"  Power at RX:        {result.beam_power_at_rx_w/1000:.3f} kW",
        f"  Captured by RX:     {result.captured_power_w/1000:.3f} kW",
        f"  PV DC output:       {result.pv_output_w/1000:.3f} kW",
        f"  Conditioned DC:     {result.dc_output_w/1000:.3f} kW",
        "",
        "  ── Efficiency Breakdown ─────────────────────────────────",
        f"  Wall-plug → photon: {result.wall_plug_eff*100:.1f}%",
        f"  Atmospheric T:      {result.atmospheric_transmittance*100:.2f}%",
        f"  Geometric capture:  {result.geometric_collection_eff*100:.2f}%",
        f"  Turbulence Strehl:  {result.turbulence_strehl*100:.2f}%",
        f"  Pointing loss:      {result.pointing_loss*100:.2f}%",
        f"  PV efficiency:      {result.pv_efficiency*100:.1f}%",
        f"  Power conditioning: {result.conditioning_eff*100:.1f}%",
        f"  TOTAL system eff:   {result.total_system_eff*100:.2f}%",
        "",
        "  ── Beam Properties ──────────────────────────────────────",
        f"  Beam radius @ RX:   {result.beam_radius_at_rx_m*100:.2f} cm",
        f"  Rytov variance:     {result.rytov_variance:.4f}",
        f"  Fried r0:           {result.fried_r0_m*100:.2f} cm",
        f"  Link budget:        {result.link_budget_db:.1f} dB",
        "",
        "  ── Safety ───────────────────────────────────────────────",
        f"  Peak irradiance:    {result.peak_irradiance_wx_m2/1e4:.2f} W/cm²",
        "=" * 65,
    ]
    return "\n".join(lines)
