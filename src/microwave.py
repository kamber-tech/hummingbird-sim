"""
microwave.py - Microwave/RF beam physics engine
Hummingbird Sim | Microwave Wireless Power Transmission Module

Sources:
  - Friis transmission: Friis 1946 Proc. IRE + Balanis "Antenna Theory" 4th ed.
  - Phased array gain: Balanis Ch. 6 (G = 4π*Ae/λ²)
  - ITU-R P.676-12: atmospheric gaseous absorption
  - Rectenna efficiency: ResearchGate 2021 (61.9% at 5.8 GHz, Schottky diodes)
  - Practical system efficiency: ~30–50% end-to-end for 5.8 GHz WPT
  - Rain attenuation: ITU-R P.838-3
  - Power density limits: IEEE C95.1-2019 / ICNIRP
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional

# ── Physical constants ─────────────────────────────────────────────────────
C_LIGHT = 2.998e8       # m/s

# ── Frequency bands for WPT ───────────────────────────────────────────────
WPT_FREQUENCIES = {
    "2.45_GHz": 2.45e9,   # ISM band, legacy SPS studies
    "5.8_GHz":  5.80e9,   # ISM, preferred for WPT (smaller apertures, better rectenna efficiency)
    "24_GHz":   24.0e9,   # mm-wave (smaller aperture but higher rain loss)
}

# ── Atmospheric gaseous absorption @ key frequencies (dB/km) ─────────────
# Ref: ITU-R P.676-12 (Table 1, sea-level, standard atmosphere)
GASEOUS_ABS_DB_KM = {
    "2.45_GHz":  0.006,   # O2 + H2O absorption, near-negligible
    "5.8_GHz":   0.008,   # slightly higher H2O component
    "24_GHz":    0.10,    # water vapor resonance nearby (22.235 GHz)
}

# ── Rain attenuation coefficients (ITU-R P.838-3) ─────────────────────────
# γ_R = k * R^α  [dB/km] where R = rain rate mm/hr
# Values for linear polarization (average of H and V), 5.8 GHz approx.
RAIN_K    = {  "2.45_GHz": 0.0000847, "5.8_GHz": 0.000354, "24_GHz": 0.00488  }
RAIN_ALPHA= {  "2.45_GHz": 1.528,     "5.8_GHz": 1.451,    "24_GHz": 1.195   }

# Rain rates (mm/hr) by condition
RAIN_RATE_MM_HR = {
    "clear":     0.0,
    "drizzle":   0.5,
    "light_rain": 2.5,
    "moderate_rain": 12.5,
    "heavy_rain": 50.0,
    "fog":        0.1,    # liquid water path, not rain per se
}

# ── Rectenna efficiency at 5.8 GHz by technology ─────────────────────────
# Ref: ResearchGate 2021 (61.9%), practical system 30-50%
RECTENNA_EFF = {
    "schottky_class_A": 0.62,   # Best lab: 61.9% (ResearchGate 2021)
    "schottky_class_E": 0.50,   # Class-E rectifier, practical systems
    "greinacher":       0.40,   # Voltage doubler, simpler
    "cmos":             0.30,   # CMOS integrated, low power
}


@dataclass
class MicrowaveTransmitter:
    """Phased array transmitter parameters."""
    frequency_hz: float = 5.80e9           # operating frequency
    n_elements: int = 1024                 # number of array elements (e.g. 32×32)
    element_spacing_lambda: float = 0.5    # element spacing in wavelengths (0.5λ standard)
    tx_power_per_element_w: float = 5.0    # power per PA element (W)
    pa_efficiency: float = 0.60            # power amplifier efficiency (DC → RF)
    aperture_efficiency: float = 0.70      # accounts for taper, losses, feed network
    wall_plug_efficiency: float = 0.50     # total DC→RF wall-plug (incl. control, cooling)
    side_lobe_level_db: float = -20.0      # first sidelobe relative to main beam (dB)
    frequency_key: str = "5.8_GHz"        # key for atmospheric lookups


@dataclass
class MicrowaveReceiver:
    """Rectenna array receiver parameters."""
    aperture_area_m2: float = 3.0          # physical receiving aperture area (m²)
    aperture_efficiency: float = 0.85      # effective aperture fraction (incl. fill)
    rectenna_type: str = "schottky_class_E" # rectenna technology
    dc_dc_efficiency: float = 0.95         # output conditioning
    frequency_key: str = "5.8_GHz"


@dataclass
class AtmosphericConditions:
    """Atmospheric conditions for microwave link."""
    condition: str = "clear"               # from RAIN_RATE_MM_HR keys
    custom_rain_rate_mm_hr: Optional[float] = None
    relative_humidity: float = 50.0        # % (affects water vapor absorption)


# ── Core physics ──────────────────────────────────────────────────────────

def wavelength_m(freq_hz: float) -> float:
    """λ = c / f"""
    return C_LIGHT / freq_hz


def array_aperture_area(tx: MicrowaveTransmitter) -> float:
    """
    Physical aperture area of a uniformly-spaced planar array.
    A_phys = N * (d_spacing)²  where d = 0.5λ typical
    """
    lam = wavelength_m(tx.frequency_hz)
    d = tx.element_spacing_lambda * lam
    return tx.n_elements * d**2


def array_gain_dbi(tx: MicrowaveTransmitter) -> float:
    """
    Array directivity/gain (dBi).
    G = 4π * η_ap * A_phys / λ²
    Ref: Balanis Eq. 2-21, aperture antenna theory
    """
    lam = wavelength_m(tx.frequency_hz)
    A = array_aperture_area(tx)
    G_linear = 4 * np.pi * tx.aperture_efficiency * A / lam**2
    return 10 * np.log10(G_linear)


def beam_half_angle_deg(tx: MicrowaveTransmitter) -> float:
    """
    3dB half-beamwidth of a uniform aperture (radians → degrees).
    θ_3dB ≈ 0.886 * λ / D    (for square aperture side D)
    """
    lam = wavelength_m(tx.frequency_hz)
    D = np.sqrt(array_aperture_area(tx))  # side of equivalent square aperture
    theta_rad = 0.886 * lam / D
    return np.degrees(theta_rad)


def spot_radius_at_range(tx: MicrowaveTransmitter, range_m: float) -> float:
    """
    Approximate 3dB beam radius at range z (m).
    r_3dB = tan(θ_3dB) * range ≈ θ_3dB * range  (small angle)
    """
    theta_rad = np.radians(beam_half_angle_deg(tx))
    return theta_rad * range_m


def friis_path_loss_db(range_m: float, freq_hz: float) -> float:
    """
    Free-space path loss (FSPL) in dB.
    FSPL = 20*log10(4π*R/λ)
    Ref: Friis 1946 Proc. IRE
    """
    lam = wavelength_m(freq_hz)
    return 20 * np.log10(4 * np.pi * range_m / lam)


def atmospheric_abs_db(range_km: float, frequency_key: str) -> float:
    """
    Gaseous atmospheric absorption (dB).
    Ref: ITU-R P.676-12 Table 1 at sea level
    """
    alpha = GASEOUS_ABS_DB_KM.get(frequency_key, 0.008)
    return alpha * range_km


def rain_attenuation_db(range_km: float, frequency_key: str, condition: str,
                        custom_rate: Optional[float] = None) -> float:
    """
    Rain attenuation per ITU-R P.838-3.
    γ_R = k * R^α  (dB/km)
    """
    if custom_rate is not None:
        R = custom_rate
    else:
        R = RAIN_RATE_MM_HR.get(condition, 0.0)
    if R <= 0:
        return 0.0
    k = RAIN_K.get(frequency_key, 0.000354)
    a = RAIN_ALPHA.get(frequency_key, 1.451)
    gamma = k * R**a
    return gamma * range_km


def received_power_friis(tx: MicrowaveTransmitter, rx: MicrowaveReceiver,
                         range_m: float, atmosphere: AtmosphericConditions) -> dict:
    """
    Full Friis-based received power calculation.
    P_r = P_t * G_t * G_r * (λ/4πR)²  *  T_atmo
    where G_r = 4π * η_ap * A_rx / λ²

    Returns dict with all intermediate quantities.
    """
    freq = tx.frequency_hz
    lam = wavelength_m(freq)
    range_km = range_m / 1000.0

    # TX side
    total_tx_rf_power = tx.n_elements * tx.tx_power_per_element_w  # RF watts
    G_t = 10**(array_gain_dbi(tx) / 10)

    # RX aperture gain
    A_rx_eff = rx.aperture_area_m2 * rx.aperture_efficiency
    G_r = 4 * np.pi * A_rx_eff / lam**2

    # Free-space path loss
    fspl_db = friis_path_loss_db(range_m, freq)
    fspl_linear = 10**(fspl_db / 10)

    # Atmospheric losses
    atmo_loss_db = (atmospheric_abs_db(range_km, tx.frequency_key) +
                    rain_attenuation_db(range_km, tx.frequency_key,
                                        atmosphere.condition,
                                        atmosphere.custom_rain_rate_mm_hr))
    atmo_loss_linear = 10**(atmo_loss_db / 10)

    # Received RF power (Friis)
    P_rf_rx = total_tx_rf_power * G_t * G_r / (fspl_linear * atmo_loss_linear)

    # Clip at total TX RF (energy conservation — Friis can be >1 at very short range with huge gain)
    P_rf_rx = min(P_rf_rx, total_tx_rf_power * 0.999)

    # Rectenna conversion
    rect_eff = RECTENNA_EFF.get(rx.rectenna_type, 0.50)
    P_dc_raw = P_rf_rx * rect_eff
    P_dc_out = P_dc_raw * rx.dc_dc_efficiency

    # Electrical input (wall-plug)
    elec_input = total_tx_rf_power / tx.wall_plug_efficiency

    # System efficiency
    sys_eff = P_dc_out / elec_input if elec_input > 0 else 0.0

    # Link budget
    link_db = 10 * np.log10(sys_eff) if sys_eff > 0 else -999.0

    # Power density at range (main beam center, W/m²)
    spot_area = np.pi * spot_radius_at_range(tx, range_m)**2
    power_density_w_m2 = P_rf_rx / spot_area if spot_area > 0 else 0.0

    return {
        "range_m":               range_m,
        "condition":             atmosphere.condition,
        "electrical_input_w":    elec_input,
        "tx_rf_power_w":         total_tx_rf_power,
        "array_gain_dbi":        array_gain_dbi(tx),
        "rx_gain_dbi":           10 * np.log10(G_r),
        "fspl_db":               fspl_db,
        "atmo_loss_db":          atmo_loss_db,
        "received_rf_power_w":   P_rf_rx,
        "rectenna_eff":          rect_eff,
        "dc_output_w":           P_dc_out,
        "wall_plug_eff":         tx.wall_plug_efficiency,
        "total_system_eff":      sys_eff,
        "link_budget_db":        link_db,
        "beam_radius_m":         spot_radius_at_range(tx, range_m),
        "power_density_w_m2":    power_density_w_m2,
        "power_density_mw_cm2":  power_density_w_m2 / 10,  # convert W/m² → mW/cm²
        "beam_halfangle_deg":    beam_half_angle_deg(tx),
    }


def sidelobe_power_density(tx: MicrowaveTransmitter, range_m: float,
                            total_tx_rf_power_w: float) -> float:
    """
    Approximate sidelobe power density at range (W/m²).
    First sidelobe ~ SLL below main beam.
    """
    sl_linear = 10**(tx.side_lobe_level_db / 10)
    G_t_main = 10**(array_gain_dbi(tx) / 10)
    G_sl = G_t_main * sl_linear
    lam = wavelength_m(tx.frequency_hz)
    fspl = (4 * np.pi * range_m / lam)**2
    P_sl = total_tx_rf_power_w * G_sl / fspl
    # Power density (approximate uniform distribution over hemisphere)
    area = 2 * np.pi * range_m**2
    return P_sl / area


def print_microwave_report(result: dict) -> str:
    """Format a readable microwave link budget report."""
    lines = [
        "=" * 65,
        "  MICROWAVE WPT LINK BUDGET REPORT",
        "=" * 65,
        f"  Range:              {result['range_m']/1000:.2f} km",
        f"  Condition:          {result['condition']}",
        "",
        "  ── Power Chain ──────────────────────────────────────────",
        f"  Electrical input:   {result['electrical_input_w']/1000:.2f} kW",
        f"  TX RF power:        {result['tx_rf_power_w']/1000:.2f} kW",
        f"  Received RF power:  {result['received_rf_power_w']/1000:.3f} kW",
        f"  DC output:          {result['dc_output_w']/1000:.3f} kW",
        "",
        "  ── Efficiency Breakdown ─────────────────────────────────",
        f"  Wall-plug → RF:     {result['wall_plug_eff']*100:.1f}%",
        f"  TX array gain:      {result['array_gain_dbi']:.1f} dBi",
        f"  Free-space path:   -{result['fspl_db']:.1f} dB",
        f"  Atmo loss:         -{result['atmo_loss_db']:.2f} dB",
        f"  RX gain:            {result['rx_gain_dbi']:.1f} dBi",
        f"  Rectenna eff:       {result['rectenna_eff']*100:.1f}%",
        f"  TOTAL system eff:   {result['total_system_eff']*100:.2f}%",
        "",
        "  ── Beam Properties ──────────────────────────────────────",
        f"  3dB beam radius:    {result['beam_radius_m']:.1f} m",
        f"  Beam half-angle:    {result['beam_halfangle_deg']:.3f}°",
        f"  Link budget:        {result['link_budget_db']:.1f} dB",
        "",
        "  ── Safety ───────────────────────────────────────────────",
        f"  Main-beam PD:       {result['power_density_mw_cm2']:.3f} mW/cm²",
        f"  (IEEE C95.1 occ):   10 mW/cm²  (at 5.8 GHz)",
        "=" * 65,
    ]
    return "\n".join(lines)
