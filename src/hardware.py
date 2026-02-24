"""
hardware.py - Hardware design calculator and BOM estimator
Hummingbird Sim | Hardware Design Module

Sources & cost refs (2024 USD estimates):
  - Yb fiber laser (1070 nm, kW-class): ~$1,000–$2,000/W for CW fiber (IPG, nLIGHT)
  - GaAs laser PV arrays: ~$200–$500/cm² (AXT, Azur Space custom)
  - 5.8 GHz GaN PA modules: ~$100–300/element at qty 100, $20–50 at qty 1000
  - Phased array controller ASICs: $500–$2,000 each
  - Rectenna elements: $5–$20 each in qty, $50–$100 prototype
  - Diesel generator (10 kW): ~$5,000–$10,000 (mil-spec: ~$20,000)
  - Thermal management: ~10–15% of component cost
  - Structural/mechanical: ~5–10% of total hardware
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ── Thermal constants ─────────────────────────────────────────────────────
HEAT_SINK_SPECIFIC_POWER = 200.0    # W/kg — passive heat sink performance
LIQUID_COOLING_SPECIFIC  = 1000.0   # W/kg — liquid cooling system performance

# ── Cost tables (2024 USD) ────────────────────────────────────────────────
LASER_COST_PER_WATT_USD = {
    "prototype": 2000.0,   # prototype/off-the-shelf fiber laser
    "qty_10":    1000.0,
    "qty_100":    400.0,
    "qty_1000":   150.0,   # volume manufacturing estimate
}

PV_CELL_COST_PER_CM2_USD = {
    "gaas_prototype":       400.0,
    "gaas_qty_100":         200.0,
    "inp_multijunction":    600.0,   # state-of-art (MDPI 2025)
    "si_prototype":          10.0,
}

GAN_PA_COST_PER_ELEMENT_USD = {
    "prototype":  300.0,
    "qty_100":    150.0,
    "qty_1000":    40.0,
}

RECTENNA_COST_PER_ELEMENT_USD = {
    "prototype":  80.0,
    "qty_100":    20.0,
    "qty_1000":    5.0,
}


@dataclass
class BOMItem:
    """Bill of Materials line item."""
    name: str
    quantity: float
    unit: str
    unit_cost_usd: float
    total_cost_usd: float
    weight_kg: float = 0.0
    notes: str = ""

    def __str__(self):
        return (f"  {self.name:<35} | qty {self.quantity:>6.0f} {self.unit:<6} | "
                f"${self.unit_cost_usd:>8,.0f}/ea | ${self.total_cost_usd:>12,.0f} | "
                f"{self.weight_kg:.1f} kg")


@dataclass
class HardwareSpec:
    """Complete hardware specification and BOM for one WPT system."""
    mode: str                    # "laser" or "microwave"
    target_dc_power_w: float     # delivered DC power to FOB
    range_m: float
    system_efficiency: float     # overall wall-plug to DC
    bom: List[BOMItem] = field(default_factory=list)
    total_cost_usd: float = 0.0
    total_weight_kg: float = 0.0
    electrical_input_w: float = 0.0
    cooling_power_w: float = 0.0
    tx_aperture_m2: float = 0.0
    rx_aperture_m2: float = 0.0
    form_factor: str = ""


# ── Laser hardware calculator ─────────────────────────────────────────────

def design_laser_system(target_dc_w: float, range_m: float,
                          system_eff: float, pv_type: str = "gaas",
                          quantity_tier: str = "qty_100") -> HardwareSpec:
    """
    Size laser WPT hardware given a delivered power target and system efficiency.
    """
    # Power required at wall
    elec_input_w = target_dc_w / system_eff if system_eff > 0 else target_dc_w * 5

    # Laser power needed (assume 40% wall-plug eff for Yb fiber)
    laser_wall_plug = 0.40
    laser_optical_w = elec_input_w * laser_wall_plug

    # Thermal load
    waste_heat_laser_w = elec_input_w - laser_optical_w
    waste_heat_rx_w    = target_dc_w * (1 / 0.50 - 1)  # from PV conversion loss

    # Laser beam optics sizing (approximate)
    # Beam waist to achieve spot ≤ receiver aperture at range
    # Use diffraction limit: w0 ≈ λ*R / (π * w_rx) — solve for w0
    lambda_m = 1070e-9
    w_rx_target = 0.30  # target spot radius at receiver (m)
    w0 = lambda_m * range_m / (np.pi * w_rx_target)
    w0 = max(w0, 0.03)  # minimum 3 cm aperture

    aperture_diameter_m = 2 * w0
    tx_aperture_m2 = np.pi * w0**2

    # PV receiver area
    # GaAs PV at 1070nm: ~50% efficiency, PV area needed:
    pv_eff = {"gaas": 0.50, "inp_multijunction": 0.55, "si": 0.30}.get(pv_type, 0.50)
    # Power incident on PV: target_dc_w / (pv_eff * 0.95)
    power_incident_pv = target_dc_w / (pv_eff * 0.95)
    # Irradiance at receiver (W/m²) — optimal ~1000–5000 W/cm²... use 50 W/cm² = 500,000 W/m²
    optimal_irr_w_m2  = 50.0 * 1e4  # 50 W/cm² = 500 kW/m² (within GaAs linear range)
    pv_area_m2 = power_incident_pv / optimal_irr_w_m2
    rx_aperture_m2 = pv_area_m2 / 0.90  # 90% fill factor

    # Cooling
    tx_cooling_flow_lpm = waste_heat_laser_w / (4200 * 5 * 1000 / 60)  # ~5°C ΔT water
    rx_cooling_mass_kg  = waste_heat_rx_w / LIQUID_COOLING_SPECIFIC

    # Build BOM
    bom = []

    laser_cost_w = LASER_COST_PER_WATT_USD.get(quantity_tier, 400.0)
    bom.append(BOMItem(
        name="Yb fiber laser (1070 nm, CW)",
        quantity=1,
        unit="system",
        unit_cost_usd=laser_optical_w * laser_cost_w,
        total_cost_usd=laser_optical_w * laser_cost_w,
        weight_kg=laser_optical_w * 0.002,  # ~2 g/W for fiber laser
        notes=f"{laser_optical_w/1000:.1f} kW optical, Yb:fiber"
    ))

    beam_exp_cost = 15_000.0
    bom.append(BOMItem(
        name="Beam expander / collimator optics",
        quantity=1, unit="unit",
        unit_cost_usd=beam_exp_cost,
        total_cost_usd=beam_exp_cost,
        weight_kg=3.0,
        notes=f"ø{aperture_diameter_m*100:.1f} cm aperture"
    ))

    pointing_cost = 25_000.0
    bom.append(BOMItem(
        name="Fast-steering mirror + tracking system",
        quantity=1, unit="unit",
        unit_cost_usd=pointing_cost,
        total_cost_usd=pointing_cost,
        weight_kg=8.0,
        notes="Tip-tilt + azimuth/elevation gimbal, ±5 mrad"
    ))

    pv_cost_cm2 = PV_CELL_COST_PER_CM2_USD.get(f"{pv_type}_{quantity_tier}", 200.0)
    pv_area_cm2 = pv_area_m2 * 1e4
    pv_total_cost = pv_area_cm2 * pv_cost_cm2
    bom.append(BOMItem(
        name=f"Laser PV array ({pv_type.upper()})",
        quantity=pv_area_cm2,
        unit="cm²",
        unit_cost_usd=pv_cost_cm2,
        total_cost_usd=pv_total_cost,
        weight_kg=pv_area_m2 * 2.0,  # ~2 kg/m² for PV cells + substrate
        notes=f"{pv_eff*100:.0f}% eff @ 1070 nm"
    ))

    rx_struct_cost = max(5000.0, pv_area_m2 * 3000.0)
    bom.append(BOMItem(
        name="RX mechanical structure / tracker",
        quantity=1, unit="system",
        unit_cost_usd=rx_struct_cost,
        total_cost_usd=rx_struct_cost,
        weight_kg=pv_area_m2 * 5.0,
        notes="Aluminum frame, 2-axis sun-tracker style"
    ))

    tx_cooling_cost = waste_heat_laser_w * 2.0  # $2/W cooling estimate
    bom.append(BOMItem(
        name="TX liquid cooling system",
        quantity=1, unit="system",
        unit_cost_usd=tx_cooling_cost,
        total_cost_usd=tx_cooling_cost,
        weight_kg=waste_heat_laser_w / 200.0,
        notes=f"Water-cooled, {tx_cooling_flow_lpm:.1f} L/min flow"
    ))

    safety_cost = 30_000.0
    bom.append(BOMItem(
        name="Safety / interlock system (laser)",
        quantity=1, unit="system",
        unit_cost_usd=safety_cost,
        total_cost_usd=safety_cost,
        weight_kg=5.0,
        notes="Beam dump, mechanical shutter, tracking watchdog"
    ))

    dcdc_cost = max(2000.0, target_dc_w * 0.10)
    bom.append(BOMItem(
        name="DC-DC power conditioner",
        quantity=1, unit="unit",
        unit_cost_usd=dcdc_cost,
        total_cost_usd=dcdc_cost,
        weight_kg=target_dc_w / 1000.0,
        notes="Wide-input DC-DC, MIL-spec"
    ))

    total_cost = sum(item.total_cost_usd for item in bom)
    # Add system integration (15%) + contingency (20%)
    total_cost *= 1.35
    total_weight = sum(item.weight_kg for item in bom)

    form_factor = (f"TX: {aperture_diameter_m*100:.0f} cm aperture, "
                   f"RX: {rx_aperture_m2:.2f} m² array, "
                   f"Total weight: {total_weight:.0f} kg")

    return HardwareSpec(
        mode="laser",
        target_dc_power_w=target_dc_w,
        range_m=range_m,
        system_efficiency=system_eff,
        bom=bom,
        total_cost_usd=total_cost,
        total_weight_kg=total_weight,
        electrical_input_w=elec_input_w,
        cooling_power_w=waste_heat_laser_w + waste_heat_rx_w,
        tx_aperture_m2=tx_aperture_m2,
        rx_aperture_m2=rx_aperture_m2,
        form_factor=form_factor,
    )


# ── Microwave hardware calculator ─────────────────────────────────────────

def design_microwave_system(target_dc_w: float, range_m: float,
                             system_eff: float, freq_hz: float = 5.8e9,
                             quantity_tier: str = "qty_100") -> HardwareSpec:
    """
    Size microwave WPT hardware given a delivered power target and system efficiency.
    """
    elec_input_w = target_dc_w / system_eff if system_eff > 0 else target_dc_w * 5
    tx_rf_power_w = elec_input_w * 0.50  # 50% wall-plug to RF

    # GaN PA sizing: typical 5 W/element at 5.8 GHz
    pa_power_per_element = 5.0
    n_elements = int(np.ceil(tx_rf_power_w / pa_power_per_element))
    n_elements = max(n_elements, 16)  # min 4×4 array

    # Aperture size
    lam = 2.998e8 / freq_hz
    d_spacing = 0.5 * lam
    tx_area = n_elements * d_spacing**2
    tx_side  = np.sqrt(tx_area)

    # Receive aperture sizing
    rx_area = target_dc_w / (10e3 * 0.5 * 0.95)  # assume 10 kW/m² incident, 50% rect, 95% dcdc
    rx_area = max(rx_area, 0.5)
    n_rect_elements = int(np.ceil(rx_area / (d_spacing**2)))

    # Waste heat
    waste_heat_tx = elec_input_w - tx_rf_power_w
    waste_heat_rx = target_dc_w * (1 / 0.50 - 1)  # rectenna thermal

    bom = []

    pa_cost = GAN_PA_COST_PER_ELEMENT_USD.get(quantity_tier, 150.0)
    bom.append(BOMItem(
        name="GaN PA modules (5W @ 5.8 GHz)",
        quantity=n_elements,
        unit="elem",
        unit_cost_usd=pa_cost,
        total_cost_usd=n_elements * pa_cost,
        weight_kg=n_elements * 0.010,  # ~10 g/element incl. heat spreader
        notes=f"{n_elements} elements × {pa_power_per_element} W RF"
    ))

    beam_ctrl_cost = 5_000.0
    bom.append(BOMItem(
        name="Phased array beam controller",
        quantity=1, unit="unit",
        unit_cost_usd=beam_ctrl_cost,
        total_cost_usd=beam_ctrl_cost,
        weight_kg=2.0,
        notes="FPGA-based phase/amplitude control IC"
    ))

    antenna_cost = n_elements * 15.0
    bom.append(BOMItem(
        name="Patch antenna array (5.8 GHz)",
        quantity=n_elements,
        unit="elem",
        unit_cost_usd=15.0,
        total_cost_usd=antenna_cost,
        weight_kg=tx_area * 3.0,  # ~3 kg/m²
        notes=f"{tx_side:.2f} m × {tx_side:.2f} m aperture"
    ))

    rect_cost = RECTENNA_COST_PER_ELEMENT_USD.get(quantity_tier, 20.0)
    bom.append(BOMItem(
        name="Rectenna elements (Schottky, 5.8 GHz)",
        quantity=n_rect_elements,
        unit="elem",
        unit_cost_usd=rect_cost,
        total_cost_usd=n_rect_elements * rect_cost,
        weight_kg=rx_area * 2.0,
        notes=f"{rx_area:.2f} m² total aperture"
    ))

    rx_struct_cost = max(3000.0, rx_area * 2000.0)
    bom.append(BOMItem(
        name="RX structure / mounting",
        quantity=1, unit="system",
        unit_cost_usd=rx_struct_cost,
        total_cost_usd=rx_struct_cost,
        weight_kg=rx_area * 4.0,
        notes="Ground-mount or mast-mounted"
    ))

    tx_cooling_cost = waste_heat_tx * 1.5
    bom.append(BOMItem(
        name="TX thermal management",
        quantity=1, unit="system",
        unit_cost_usd=tx_cooling_cost,
        total_cost_usd=tx_cooling_cost,
        weight_kg=n_elements * 0.020,
        notes="Integrated heat sink + fan or liquid cooling"
    ))

    safety_cost = 15_000.0
    bom.append(BOMItem(
        name="RF safety / interlock system",
        quantity=1, unit="system",
        unit_cost_usd=safety_cost,
        total_cost_usd=safety_cost,
        weight_kg=3.0,
        notes="PA gate-kill, RF detector, watchdog"
    ))

    dcdc_cost = max(2000.0, target_dc_w * 0.08)
    bom.append(BOMItem(
        name="DC-DC power conditioner",
        quantity=1, unit="unit",
        unit_cost_usd=dcdc_cost,
        total_cost_usd=dcdc_cost,
        weight_kg=target_dc_w / 1500.0,
        notes="MIL-spec, wide Vout range"
    ))

    total_cost = sum(item.total_cost_usd for item in bom) * 1.35  # integration + contingency
    total_weight = sum(item.weight_kg for item in bom)

    form_factor = (f"TX: {tx_side:.1f} m × {tx_side:.1f} m array ({n_elements} elements), "
                   f"RX: {np.sqrt(rx_area):.1f} m × {np.sqrt(rx_area):.1f} m rectenna, "
                   f"Total weight: {total_weight:.0f} kg")

    return HardwareSpec(
        mode="microwave",
        target_dc_power_w=target_dc_w,
        range_m=range_m,
        system_efficiency=system_eff,
        bom=bom,
        total_cost_usd=total_cost,
        total_weight_kg=total_weight,
        electrical_input_w=elec_input_w,
        cooling_power_w=waste_heat_tx + waste_heat_rx,
        tx_aperture_m2=tx_area,
        rx_aperture_m2=rx_area,
        form_factor=form_factor,
    )


def print_hardware_report(spec: HardwareSpec) -> str:
    lines = [
        "=" * 70,
        f"  HARDWARE DESIGN SPECIFICATION — {spec.mode.upper()} WPT",
        "=" * 70,
        f"  Target delivered power:  {spec.target_dc_power_w/1000:.2f} kW DC",
        f"  Range:                   {spec.range_m/1000:.2f} km",
        f"  System efficiency:       {spec.system_efficiency*100:.1f}%",
        f"  Electrical input:        {spec.electrical_input_w/1000:.2f} kW (wall-plug)",
        f"  Cooling load:            {spec.cooling_power_w/1000:.2f} kW",
        f"  TX aperture:             {spec.tx_aperture_m2:.3f} m²",
        f"  RX aperture:             {spec.rx_aperture_m2:.3f} m²",
        f"  Form factor:             {spec.form_factor}",
        "",
        "  ── Bill of Materials ─────────────────────────────────────────────",
        f"  {'Component':<35} | {'Qty':>6} {'Unit':<6} | {'$/unit':>10} | {'Total $':>12} | Weight",
        "  " + "-" * 88,
    ]
    for item in spec.bom:
        lines.append(str(item))
    lines += [
        "  " + "-" * 88,
        f"  SUBTOTAL (hardware only):                                    ${sum(i.total_cost_usd for i in spec.bom):>12,.0f}",
        f"  Integration + contingency (35%):                             ${sum(i.total_cost_usd for i in spec.bom) * 0.35:>12,.0f}",
        f"  TOTAL SYSTEM COST:                                           ${spec.total_cost_usd:>12,.0f}",
        f"  TOTAL SYSTEM WEIGHT:                                         {spec.total_weight_kg:>10.1f} kg",
        "=" * 70,
    ]
    return "\n".join(lines)
