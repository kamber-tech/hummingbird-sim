"""
charts.py - Visualization and report generation
Hummingbird Sim | Charts & Reports Module
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import pandas as pd
import os
from typing import Optional, List
from pathlib import Path

# Color scheme
COLORS = {
    "clear":         "#2196F3",
    "haze":          "#FF9800",
    "smoke":         "#795548",
    "rain":          "#9C27B0",
    "light_rain":    "#9C27B0",
    "moderate_rain": "#673AB7",
    "heavy_rain":    "#311B92",
    "dust":          "#FF5722",
    "drizzle":       "#CE93D8",
    "fog":           "#90A4AE",
    "laser":         "#F44336",
    "microwave":     "#2196F3",
}

CHART_STYLE = {
    "figure.facecolor": "#0d1117",
    "axes.facecolor":   "#161b22",
    "axes.edgecolor":   "#30363d",
    "axes.labelcolor":  "#c9d1d9",
    "xtick.color":      "#8b949e",
    "ytick.color":      "#8b949e",
    "text.color":       "#c9d1d9",
    "grid.color":       "#21262d",
    "legend.facecolor": "#161b22",
    "legend.edgecolor": "#30363d",
}

def apply_style():
    plt.rcParams.update(CHART_STYLE)
    plt.rcParams["font.family"] = "monospace"


def plot_range_sweep(df_laser: pd.DataFrame, df_mw: pd.DataFrame,
                      output_dir: str = "charts") -> str:
    """
    Plot system efficiency vs. range for both modes and all conditions.
    Returns the filepath of saved PNG.
    """
    apply_style()
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("Hummingbird Sim — System Efficiency vs. Range", fontsize=14,
                  color="#c9d1d9", fontweight="bold")

    for ax, (df, mode_label) in zip(axes, [(df_laser, "LASER (1070 nm)"),
                                            (df_mw,   "MICROWAVE (5.8 GHz)")]):
        conditions = df["condition"].unique()
        for cond in conditions:
            sub = df[df["condition"] == cond].dropna(subset=["system_eff_pct"])
            if sub.empty:
                continue
            color = COLORS.get(cond, "#888888")
            ax.plot(sub["range_km"], sub["system_eff_pct"], "-o",
                    label=cond, color=color, linewidth=2, markersize=5)

        ax.set_xlabel("Range (km)")
        ax.set_ylabel("System Efficiency (%)")
        ax.set_title(mode_label, fontweight="bold")
        ax.legend(loc="upper right", fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(left=0)
        ax.set_ylim(bottom=0)
        ax.axhline(y=5, color="#F44336", linestyle="--", alpha=0.6, label="5% threshold")

    fig.tight_layout()
    out_path = Path(output_dir) / "range_sweep.png"
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ Saved: {out_path}")
    return str(out_path)


def plot_link_budget_waterfall(result_laser, result_mw: dict,
                                output_dir: str = "charts") -> str:
    """
    Waterfall / bar chart of efficiency chain for laser and microwave MVP.
    """
    apply_style()
    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    fig.suptitle("Hummingbird Sim — MVP Link Budget: 5 kW @ 2 km, Clear Sky",
                  fontsize=13, color="#c9d1d9", fontweight="bold")

    # Laser chain
    ax = axes[0]
    labels_l = ["Wall-plug\n→ Photon", "Atmo\nTransm.", "Geometric\nCapture",
                 "Turbulence\nStrehl", "Pointing\nLoss", "PV Conv.", "DC-DC\nCond."]
    vals_l = [
        result_laser.wall_plug_eff * 100,
        result_laser.atmospheric_transmittance * 100,
        result_laser.geometric_collection_eff * 100,
        result_laser.turbulence_strehl * 100,
        result_laser.pointing_loss * 100,
        result_laser.pv_efficiency * 100,
        result_laser.conditioning_eff * 100,
    ]
    bars = ax.bar(labels_l, vals_l, color=COLORS["laser"], alpha=0.85, edgecolor="#555")
    ax.set_title("LASER", fontweight="bold", color=COLORS["laser"])
    ax.set_ylabel("Stage Efficiency (%)")
    ax.set_ylim(0, 110)
    ax.axhline(y=result_laser.total_system_eff * 100, color="yellow",
                linestyle="--", linewidth=2, label=f"Total: {result_laser.total_system_eff*100:.1f}%")
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3, axis="y")
    for bar, val in zip(bars, vals_l):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                f"{val:.1f}%", ha="center", fontsize=8, color="#c9d1d9")

    # Microwave chain
    ax = axes[1]
    labels_m = ["Wall-plug\n→ RF", "TX Gain\n(norm)", "Path Loss\n(FSPL norm)",
                 "Atmo\nLoss norm", "RX Gain\n(norm)", "Rectenna\nConv.", "DC-DC\nCond."]
    # Normalize these to show relative efficiency steps
    wp_eff  = result_mw["wall_plug_eff"] * 100
    rect_eff = result_mw["rectenna_eff"] * 100
    cond_eff = 95.0  # DC-DC
    path_eff = 10**(-(result_mw["fspl_db"] + result_mw["atmo_loss_db"]) / 10) * 100
    path_eff = min(path_eff, 100)

    vals_m = [wp_eff, 100, path_eff, 100, 100, rect_eff, cond_eff]
    labels_m_clean = ["Wall-plug\n→ RF", "Beam Form.", "Path Loss",
                       "Atmo Loss", "RX Aperture", "Rectenna", "DC-DC"]
    bars = ax.bar(labels_m_clean, vals_m, color=COLORS["microwave"], alpha=0.85, edgecolor="#555")
    ax.set_title("MICROWAVE", fontweight="bold", color=COLORS["microwave"])
    ax.set_ylabel("Stage Efficiency (%)")
    ax.set_ylim(0, 110)
    total_mw = result_mw["total_system_eff"] * 100
    ax.axhline(y=total_mw, color="yellow",
                linestyle="--", linewidth=2, label=f"Total: {total_mw:.1f}%")
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3, axis="y")
    for bar, val in zip(bars, vals_m):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                f"{val:.1f}%", ha="center", fontsize=8, color="#c9d1d9")

    fig.tight_layout()
    out_path = Path(output_dir) / "link_budget_waterfall.png"
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ Saved: {out_path}")
    return str(out_path)


def plot_safety_zones(laser_safety, mw_safety,
                       output_dir: str = "charts") -> str:
    """
    Radial safety zone diagram for both systems.
    """
    apply_style()
    fig, axes = plt.subplots(1, 2, figsize=(12, 6), subplot_kw={"polar": False})
    fig.suptitle("Hummingbird Sim — Safety Exclusion Zones",
                  fontsize=13, color="#c9d1d9", fontweight="bold")

    # Laser irradiance profile
    ax = axes[0]
    ranges_m = np.logspace(0, 4, 500)  # 1 m to 10 km
    irradiances = [laser_safety.eye_mpe_w_cm2 * 1000] * len(ranges_m)  # placeholder

    # Use the compute function to get per-range irradiance
    # Import inline to avoid circular
    from .safety import laser_irradiance_at_range, MPE_EYE_1070NM_W_CM2, MPE_SKIN_1070NM_W_CM2
    irr_mw_cm2 = [laser_irradiance_at_range(10000.0, r, 0.075, 1.2) * 1000
                   for r in ranges_m]  # mW/cm²

    ax.loglog(ranges_m, irr_mw_cm2, color=COLORS["laser"], linewidth=2.5, label="Irradiance")
    ax.axhline(y=MPE_EYE_1070NM_W_CM2 * 1000, color="red", linestyle="--", linewidth=2,
                label=f"Eye MPE: {MPE_EYE_1070NM_W_CM2*1000:.1f} mW/cm²")
    ax.axhline(y=MPE_SKIN_1070NM_W_CM2 * 1000, color="orange", linestyle="--", linewidth=2,
                label=f"Skin MPE: {MPE_SKIN_1070NM_W_CM2*1000:.0f} mW/cm²")
    ax.axvline(x=laser_safety.nominal_hazard_distance_m, color="red", linestyle=":",
                alpha=0.8, label=f"Eye NOHD: {laser_safety.nominal_hazard_distance_m:.0f} m")
    ax.fill_between(ranges_m,
                     [MPE_EYE_1070NM_W_CM2 * 1000] * len(ranges_m),
                     [max(i, MPE_EYE_1070NM_W_CM2 * 1000) for i in irr_mw_cm2],
                     where=[i > MPE_EYE_1070NM_W_CM2 * 1000 for i in irr_mw_cm2],
                     alpha=0.2, color="red", label="Hazard zone")
    ax.set_xlabel("Range (m)")
    ax.set_ylabel("Irradiance (mW/cm²)")
    ax.set_title("Laser Safety Profile (10 kW, 15 cm beam)", fontweight="bold")
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(True, alpha=0.3, which="both")

    # Microwave power density profile
    ax = axes[1]
    from .safety import RF_LIMIT_OCCUPATIONAL_MW_CM2, RF_LIMIT_PUBLIC_MW_CM2
    from .microwave import array_gain_dbi, wavelength_m as mw_wl
    import sys

    G_lin = 10**(30.0 / 10)  # assume 30 dBi gain
    tx_rf = 10000.0           # 10 kW RF
    pd_w_m2 = [tx_rf * G_lin / (4 * np.pi * r**2) for r in ranges_m]
    pd_mw_cm2 = [p / 10 for p in pd_w_m2]

    ax.loglog(ranges_m, pd_mw_cm2, color=COLORS["microwave"], linewidth=2.5,
               label="Main beam PD")
    ax.axhline(y=RF_LIMIT_OCCUPATIONAL_MW_CM2, color="orange", linestyle="--", linewidth=2,
                label=f"Occ. limit: {RF_LIMIT_OCCUPATIONAL_MW_CM2} mW/cm²")
    ax.axhline(y=RF_LIMIT_PUBLIC_MW_CM2, color="red", linestyle="--", linewidth=2,
                label=f"Public limit: {RF_LIMIT_PUBLIC_MW_CM2} mW/cm²")
    ax.axvline(x=mw_safety.occupational_safe_distance_m, color="orange", linestyle=":",
                alpha=0.8, label=f"Occ. safe: {mw_safety.occupational_safe_distance_m:.0f} m")
    ax.axvline(x=mw_safety.public_safe_distance_m, color="red", linestyle=":",
                alpha=0.8, label=f"Public safe: {mw_safety.public_safe_distance_m:.0f} m")
    ax.set_xlabel("Range (m)")
    ax.set_ylabel("Power Density (mW/cm²)")
    ax.set_title("Microwave Safety Profile (10 kW RF, 30 dBi gain)", fontweight="bold")
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(True, alpha=0.3, which="both")

    fig.tight_layout()
    out_path = Path(output_dir) / "safety_zones.png"
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ Saved: {out_path}")
    return str(out_path)


def plot_financial_summary(roi: dict, scaling: pd.DataFrame,
                            output_dir: str = "charts") -> str:
    """
    Financial dashboard: NPV waterfall and production scaling curve.
    """
    apply_style()
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("Hummingbird Sim — Financial Model",
                  fontsize=13, color="#c9d1d9", fontweight="bold")

    # Cash flow / cumulative NPV
    ax = axes[0]
    years = list(range(roi["system_life_years"] + 1))
    cfs   = roi["cash_flows"]
    cum_npv = []
    running = 0
    for i, cf in enumerate(cfs):
        discounted = cf / (1.08**i)
        running += discounted
        cum_npv.append(running)

    colors_cf = ["#F44336" if cf < 0 else "#4CAF50" for cf in cfs]
    ax.bar(years, cfs, color=colors_cf, alpha=0.8, edgecolor="#555")
    ax2 = ax.twinx()
    ax2.plot(years, cum_npv, "y-o", linewidth=2, markersize=5, label="Cumulative NPV")
    ax2.axhline(y=0, color="white", linestyle="--", alpha=0.4)
    ax2.set_ylabel("Cumulative NPV ($)", color="yellow")
    ax2.tick_params(axis="y", colors="yellow")
    ax.set_xlabel("Year")
    ax.set_ylabel("Annual Cash Flow ($)")
    ax.set_title(f"NPV Analysis  (IRR: {roi['irr_pct']:.1f}%,  Payback: {roi['payback_years']:.1f} yr)",
                  fontweight="bold")
    ax.grid(True, alpha=0.3, axis="y")
    ax2.legend(loc="lower right")
    ax.set_xticks(years)

    # Production scaling curve
    ax = axes[1]
    ax.semilogy(scaling["units_produced"], scaling["unit_cost_usd"],
                 "o-", color="#4CAF50", linewidth=2.5, markersize=8)
    ax.fill_between(scaling["units_produced"], scaling["unit_cost_usd"],
                     color="#4CAF50", alpha=0.15)
    ax.set_xlabel("Units Produced (cumulative)")
    ax.set_ylabel("Unit Cost (USD, log scale)")
    ax.set_title("Production Scaling (Wright's Law, 18% learning rate)", fontweight="bold")
    ax.grid(True, alpha=0.3, which="both")
    for _, row in scaling.iterrows():
        ax.annotate(f"${row['unit_cost_usd']:,.0f}",
                     (row["units_produced"], row["unit_cost_usd"]),
                     textcoords="offset points", xytext=(5, 5), fontsize=8, color="#c9d1d9")

    fig.tight_layout()
    out_path = Path(output_dir) / "financial_summary.png"
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ Saved: {out_path}")
    return str(out_path)


def plot_beam_profile(beam, range_m: float = 2000.0,
                       output_dir: str = "charts") -> str:
    """
    2D Gaussian beam intensity profile at target range.
    """
    from .laser import beam_radius_at_range
    apply_style()
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle(f"Laser Beam Profile at {range_m/1000:.1f} km",
                  fontsize=13, color="#c9d1d9", fontweight="bold")

    w = beam_radius_at_range(range_m, beam)
    span = w * 3
    x = np.linspace(-span, span, 300)
    y = np.linspace(-span, span, 300)
    X, Y = np.meshgrid(x, y)
    I = beam.output_power_w * (2 / (np.pi * w**2)) * np.exp(-2 * (X**2 + Y**2) / w**2)
    I_kw_m2 = I / 1000

    ax = axes[0]
    c = ax.contourf(X * 100, Y * 100, I_kw_m2, levels=50, cmap="hot")
    plt.colorbar(c, ax=ax, label="Intensity (kW/m²)")
    circle = plt.Circle((0, 0), w * 100, fill=False, color="cyan", linewidth=2,
                          linestyle="--", label=f"1/e² radius: {w*100:.1f} cm")
    ax.add_patch(circle)
    ax.set_xlabel("x (cm)")
    ax.set_ylabel("y (cm)")
    ax.set_title("2D Intensity Map")
    ax.legend(fontsize=9)
    ax.set_aspect("equal")

    ax = axes[1]
    r = np.linspace(0, span * 100, 500)
    I_radial = (2 * beam.output_power_w / (np.pi * w**2)) * np.exp(-2 * (r/100)**2 / w**2) / 1000
    ax.plot(r, I_radial, color=COLORS["laser"], linewidth=2.5)
    ax.axvline(x=w * 100, color="cyan", linestyle="--", linewidth=1.5,
                label=f"w={w*100:.1f} cm")
    ax.set_xlabel("Radial distance (cm)")
    ax.set_ylabel("Intensity (kW/m²)")
    ax.set_title("Radial Intensity Profile")
    ax.legend()
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    out_path = Path(output_dir) / "beam_profile.png"
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ Saved: {out_path}")
    return str(out_path)


def generate_markdown_report(
    mode: str,
    laser_result=None,
    mw_result: dict = None,
    laser_safety=None,
    mw_safety=None,
    scenario_laser: dict = None,
    scenario_mw: dict = None,
    hw_laser=None,
    hw_mw=None,
    roi: dict = None,
    chart_paths: list = None,
) -> str:
    """Generate a full markdown simulation report."""
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

    md = [
        "# Hummingbird Sim — Simulation Report",
        f"*Generated: {now}*",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        "This report presents the end-to-end physics simulation, hardware sizing,",
        "safety assessment, and financial model for a **Wireless Power Transmission (WPT)**",
        "system delivering 5 kW to a remote FOB at 2 km range.",
        "",
        "Two technologies are evaluated:",
        "- **Laser**: 1070 nm Yb-fiber laser with GaAs photovoltaic receiver",
        "- **Microwave**: 5.8 GHz phased array with Schottky rectenna",
        "",
        "---",
        "",
        "## 1. Physics Results — MVP Scenario (5 kW @ 2 km, Clear Sky)",
        "",
    ]

    if laser_result is not None:
        md += [
            "### 1.1 Laser Link Budget",
            "",
            f"| Parameter | Value |",
            f"|-----------|-------|",
            f"| Wavelength | {1070} nm |",
            f"| Optical TX Power | {laser_result.optical_tx_power_w/1000:.1f} kW |",
            f"| Electrical Input | {laser_result.electrical_input_w/1000:.1f} kW |",
            f"| DC Output | {laser_result.dc_output_w/1000:.2f} kW |",
            f"| System Efficiency | {laser_result.total_system_eff*100:.1f}% |",
            f"| Beam radius @ 2 km | {laser_result.beam_radius_at_rx_m*100:.1f} cm |",
            f"| Atmospheric transmittance | {laser_result.atmospheric_transmittance*100:.1f}% |",
            f"| Turbulence Strehl | {laser_result.turbulence_strehl*100:.1f}% |",
            f"| Pointing loss | {(1-laser_result.pointing_loss)*100:.2f}% |",
            f"| PV efficiency (GaAs) | {laser_result.pv_efficiency*100:.0f}% |",
            f"| Rytov variance σ²R | {laser_result.rytov_variance:.4f} |",
            f"| Fried parameter r₀ | {laser_result.fried_r0_m*100:.1f} cm |",
            "",
        ]

    if mw_result is not None:
        md += [
            "### 1.2 Microwave Link Budget",
            "",
            f"| Parameter | Value |",
            f"|-----------|-------|",
            f"| Frequency | 5.8 GHz |",
            f"| TX RF Power | {mw_result['tx_rf_power_w']/1000:.2f} kW |",
            f"| Electrical Input | {mw_result['electrical_input_w']/1000:.2f} kW |",
            f"| DC Output | {mw_result['dc_output_w']/1000:.2f} kW |",
            f"| System Efficiency | {mw_result['total_system_eff']*100:.1f}% |",
            f"| TX Array Gain | {mw_result['array_gain_dbi']:.1f} dBi |",
            f"| Free-space Path Loss | {mw_result['fspl_db']:.1f} dB |",
            f"| Atmospheric Loss | {mw_result['atmo_loss_db']:.2f} dB |",
            f"| Rectenna Efficiency | {mw_result['rectenna_eff']*100:.0f}% |",
            f"| 3dB Beam Radius @ 2 km | {mw_result['beam_radius_m']:.1f} m |",
            "",
        ]

    md += [
        "---",
        "",
        "## 2. Safety Assessment",
        "",
    ]

    if laser_safety is not None:
        md += [
            "### 2.1 Laser Safety (ANSI Z136.1 / IEC 60825-1)",
            "",
            f"| Parameter | Value |",
            f"|-----------|-------|",
            f"| Eye MPE (1070 nm CW) | {laser_safety.eye_mpe_w_cm2*1000:.1f} mW/cm² |",
            f"| Skin MPE | {laser_safety.skin_mpe_w_cm2*1000:.0f} mW/cm² |",
            f"| Eye NOHD | {laser_safety.nominal_hazard_distance_m:.0f} m |",
            f"| Exclusion zone | {laser_safety.exclusion_zone_radius_m:.0f} m radius |",
            "",
            "**Warnings:**",
        ]
        for w in laser_safety.warnings:
            md.append(f"- {w}")
        md.append("")

    if mw_safety is not None:
        md += [
            "### 2.2 RF Safety (IEEE C95.1-2019 / ICNIRP)",
            "",
            f"| Parameter | Value |",
            f"|-----------|-------|",
            f"| Main beam power density | {mw_safety.main_beam_pd_at_range_mw_cm2:.3f} mW/cm² |",
            f"| Occupational safe distance | {mw_safety.occupational_safe_distance_m:.0f} m |",
            f"| Public safe distance | {mw_safety.public_safe_distance_m:.0f} m |",
            "",
            "**Warnings:**",
        ]
        for w in mw_safety.warnings:
            md.append(f"- {w}")
        md.append("")

    md += [
        "---",
        "",
        "## 3. Operational Scenarios",
        "",
    ]

    for s, label in [(scenario_laser, "Laser"), (scenario_mw, "Microwave")]:
        if s is not None:
            md += [
                f"### 3.{'1' if label == 'Laser' else '2'} {label} — Squad Outpost @ 2 km",
                "",
                f"| Metric | Value |",
                f"|--------|-------|",
                f"| DC delivered | {s['dc_power_delivered_kw']:.2f} kW |",
                f"| System efficiency | {s['system_efficiency_pct']:.1f}% |",
                f"| Fuel saved | {s['fuel_saved_l_day']:.1f} L/day |",
                f"| Annual fuel savings | ${s['fuel_cost_saved_yr_usd']:,.0f} |",
                f"| Convoys eliminated/yr | {s['convoys_eliminated_yr']:.0f} |",
                f"| Annual convoy savings | ${s['convoy_cost_saved_yr_usd']:,.0f} |",
                f"| Total annual value | ${s['total_value_yr_usd']:,.0f} |",
                "",
            ]

    if roi is not None:
        md += [
            "---",
            "",
            "## 4. Financial Model",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Annual diesel savings | ${roi['diesel_cost_yr_usd']:,.0f} |",
            f"| CAPEX | ${roi['capex_usd']:,.0f} |",
            f"| Simple payback | {roi['payback_years']:.1f} years |",
            f"| NPV (10yr @ 8%) | ${roi['npv_usd']:,.0f} |",
            f"| IRR | {roi['irr_pct']:.1f}% |",
            "",
        ]

    if chart_paths:
        md += ["---", "", "## 5. Charts", ""]
        for p in chart_paths:
            fname = Path(p).name
            md.append(f"![{fname}](charts/{fname})")
        md.append("")

    md += [
        "---",
        "",
        "## 6. Key References",
        "",
        "1. MDPI Photonics 2025: *55% Efficient High-Power Multijunction PV Laser Power Converters for 1070 nm*",
        "2. ResearchGate 2021: *Extendable Array Rectenna for Microwave WPT — 61.9% efficiency at 5.8 GHz*",
        "3. Andrews & Phillips: *Laser Beam Propagation Through Random Media*, 2nd ed., SPIE Press",
        "4. Balanis: *Antenna Theory*, 4th ed., Wiley",
        "5. ITU-R P.676-12: Attenuation by atmospheric gases",
        "6. ITU-R P.838-3: Rain attenuation model",
        "7. ANSI Z136.1-2022: *Safe Use of Lasers*",
        "8. IEEE C95.1-2019: *Safety Levels with Respect to Human Exposure to RF Fields*",
        "9. McMaster ECE / SPIE 2000: Atmospheric attenuation coefficients at 785/1550 nm",
        "10. RAND Corp: DoD convoy cost estimates ($400–$800/convoy-mile)",
        "",
        "---",
        "*Hummingbird Sim v0.1.0 — Defense WPT Engineering Platform*",
    ]

    return "\n".join(md)
