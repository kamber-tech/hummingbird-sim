#!/usr/bin/env python3
"""
hummingbird.py — Hummingbird Sim CLI
Wireless Power Transmission simulation platform (defense logistics)

Usage:
  python hummingbird.py                          # default: compare laser vs microwave @ 2 km
  python hummingbird.py --mode laser             # single laser scenario
  python hummingbird.py --mode microwave         # single microwave scenario
  python hummingbird.py --mode sweep             # range sweep 0.5–10 km
  python hummingbird.py --mode financial         # financial + SBIR model
  python hummingbird.py --mode all --charts      # everything + save charts
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from src.scenarios import (
    run_mvp_scenario, compute_scenario,
    sweep_range_and_conditions, print_scenario_report
)
from src.financial import (
    FinancialAssumptions, SBIRBudget,
    compute_roi, compute_convoy_economics, compute_sbir_budget,
    scaling_analysis, print_financial_report
)
from src.safety import (
    compute_laser_safety, compute_microwave_safety,
    model_interlock_scenario, print_safety_report
)
from src.hardware import design_laser_system, design_microwave_system, print_hardware_report
from src.charts import (
    plot_range_sweep, plot_link_budget_waterfall,
    plot_safety_zones, plot_financial_summary,
    generate_markdown_report
)

import pandas as pd
import numpy as np


def run_scenario_block(mode: str, charts: bool = False, output_dir: str = "output"):
    """Run a single mode scenario (laser or microwave) with full report."""
    s = run_mvp_scenario(mode)
    print(print_scenario_report(s))
    return s


def run_compare(charts: bool = False, output_dir: str = "output"):
    """Laser vs microwave side-by-side at MVP conditions (5 kW @ 2 km, clear)."""
    laser = run_mvp_scenario("laser")
    mw    = run_mvp_scenario("microwave")

    print("\n" + "=" * 65)
    print("  HUMMINGBIRD SIM — LASER vs MICROWAVE @ 2 km (clear sky)")
    print("=" * 65)
    print(print_scenario_report(laser))
    print()
    print(print_scenario_report(mw))

    # Side-by-side comparison table
    print("\n── Head-to-Head Summary ─────────────────────────────────────────")
    rows = [
        ("System efficiency (%)",   f"{laser['system_efficiency_pct']:.1f}",   f"{mw['system_efficiency_pct']:.1f}"),
        ("DC delivered (kW)",       f"{laser['dc_power_delivered_kw']:.2f}",    f"{mw['dc_power_delivered_kw']:.2f}"),
        ("Electrical input (kW)",   f"{laser['electrical_input_kw']:.1f}",      f"{mw['electrical_input_kw']:.1f}"),
        ("FOB load covered (%)",    f"{laser['wpt_coverage_pct']:.0f}",         f"{mw['wpt_coverage_pct']:.0f}"),
        ("Fuel saved (L/day)",      f"{laser['fuel_saved_l_day']:.0f}",         f"{mw['fuel_saved_l_day']:.0f}"),
        ("Convoys eliminated/yr",   f"{laser['convoys_eliminated_yr']:.0f}",    f"{mw['convoys_eliminated_yr']:.0f}"),
        ("Total operational value", f"${laser['total_value_yr_usd']:,.0f}/yr",  f"${mw['total_value_yr_usd']:,.0f}/yr"),
    ]
    print(f"  {'Metric':<30} {'Laser (1070 nm)':>16} {'Microwave (5.8 GHz)':>20}")
    print("  " + "-" * 70)
    for metric, lv, mv in rows:
        print(f"  {metric:<30} {lv:>16} {mv:>20}")

    if charts:
        try:
            os.makedirs(output_dir, exist_ok=True)
            df_laser = sweep_range_and_conditions("laser")
            df_mw    = sweep_range_and_conditions("microwave")
            plot_range_sweep(df_laser, df_mw, output_dir=output_dir)
            plot_link_budget_waterfall(laser, mw, output_dir=output_dir)
        except Exception as e:
            print(f"  [Chart error: {e}]")

    return laser, mw


def run_sweep(mode: str = "laser", charts: bool = False, output_dir: str = "output"):
    """Sweep range from 0.5–10 km across atmospheric conditions."""
    print(f"\n── RANGE SWEEP ({mode.upper()}) ──────────────────────────────────────")
    df = sweep_range_and_conditions(mode)
    print(df.to_string(index=False))

    if charts:
        try:
            os.makedirs(output_dir, exist_ok=True)
            df_other = sweep_range_and_conditions("microwave" if mode == "laser" else "laser")
            df_laser = df if mode == "laser" else df_other
            df_mw    = df_other if mode == "laser" else df
            plot_range_sweep(df_laser, df_mw, output_dir=output_dir)
        except Exception as e:
            print(f"  [Chart error: {e}]")
    return df


def run_safety(laser_scenario: dict, mw_scenario: dict, charts: bool = False, output_dir: str = "output"):
    """Run safety analysis for both modalities."""
    print("\n── SAFETY ANALYSIS ──────────────────────────────────────────────")

    # Laser safety (15 kW optical, 7.5 cm waist)
    laser_safety = compute_laser_safety(
        power_w=15_000,
        range_m=2000,
        waist_m=0.075,
        m_squared=1.2,
    )

    # Microwave safety (1024 × 10 W = 10.24 kW RF)
    from src.microwave import MicrowaveTransmitter, array_gain_dbi
    tx = MicrowaveTransmitter(n_elements=1024, tx_power_per_element_w=10.0)
    gain = array_gain_dbi(tx)
    mw_safety = compute_microwave_safety(
        total_tx_rf_w=1024 * 10.0,
        gain_dbi=gain,
        range_m=2000,
        pd_at_range_mw_cm2=0.01,  # will be computed inside
        n_elements=1024,
    )

    print(print_safety_report(laser_safety=laser_safety, mw_safety=mw_safety))

    # Interlock modeling
    print("\n── INTERLOCK SCENARIOS ───────────────────────────────────────────")
    for trigger in ["tracking_loss", "obstruction", "power_surge"]:
        interlock = model_interlock_scenario(trigger, tx_power_w=15_000)
        print(f"  [{trigger}] response: {interlock.response_time_ms:.1f} ms | "
              f"safe: {'✓' if interlock.safe else '✗'} | "
              f"energy deposited: {interlock.energy_deposited_j:.1f} J | "
              f"{interlock.mitigation}")

    if charts:
        try:
            os.makedirs(output_dir, exist_ok=True)
            plot_safety_zones(laser_safety, mw_safety, output_dir=output_dir)
        except Exception as e:
            print(f"  [Chart error: {e}]")

    return laser_safety, mw_safety


def run_financial(laser_scenario: dict, system_cost_usd: float = 500_000,
                  charts: bool = False, output_dir: str = "output"):
    """Run full financial model."""
    print("\n── FINANCIAL MODEL ───────────────────────────────────────────────")

    fa = FinancialAssumptions(
        system_cost_usd=system_cost_usd,
        delivered_power_kw=laser_scenario["dc_power_delivered_kw"],
        hours_operation_per_year=8760,
    )

    roi    = compute_roi(fa)
    convoy = compute_convoy_economics(fa, convoy_distance_km=50, fraction_eliminated=0.80)
    sbir   = compute_sbir_budget(SBIRBudget())
    scale  = scaling_analysis(system_cost_usd)

    print(print_financial_report(roi, convoy, sbir, scale))

    if charts:
        try:
            os.makedirs(output_dir, exist_ok=True)
            plot_financial_summary(roi, scale, output_dir=output_dir)
        except Exception as e:
            print(f"  [Chart error: {e}]")

    return roi, convoy, sbir, scale


def run_hardware(charts: bool = False):
    """Show hardware design specs for both modalities."""
    print("\n── HARDWARE DESIGN ───────────────────────────────────────────────")

    laser_hw = design_laser_system(target_dc_w=5000, range_m=2000, system_eff=0.06)
    mw_hw    = design_microwave_system(target_dc_w=5000, range_m=2000, system_eff=0.004)

    print("\n  [LASER SYSTEM]")
    print(print_hardware_report(laser_hw))
    print("\n  [MICROWAVE SYSTEM]")
    print(print_hardware_report(mw_hw))

    return laser_hw, mw_hw


def run_all(system_cost: float = 500_000, charts: bool = False, output_dir: str = "output"):
    """Run full simulation suite."""
    print("\n" + "🦅 " * 20)
    print("  HUMMINGBIRD SIM — FULL SIMULATION SUITE")
    print("  Wireless Power Transmission | Defense Logistics | MVP: 5 kW @ 2 km")
    print("🦅 " * 20)

    laser, mw = run_compare(charts=charts, output_dir=output_dir)
    run_sweep(mode="laser", charts=charts, output_dir=output_dir)
    run_sweep(mode="microwave", charts=charts, output_dir=output_dir)
    run_safety(laser, mw, charts=charts, output_dir=output_dir)
    run_hardware()
    roi, convoy, sbir, scale = run_financial(laser, system_cost_usd=system_cost,
                                              charts=charts, output_dir=output_dir)

    # Generate markdown report
    if charts:
        try:
            report_path = os.path.join(output_dir, "SIMULATION_REPORT.md")
            report = generate_markdown_report(
                mode="both",
                scenario_laser=laser,
                scenario_mw=mw,
                roi=roi,
            )
            with open(report_path, "w") as f:
                f.write(report)
            print(f"\n  Full report: {report_path}")
        except Exception as e:
            print(f"  [Report error: {e}]")


def main():
    parser = argparse.ArgumentParser(
        description="Hummingbird Sim — Wireless Power Transmission platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--mode", default="compare",
                        choices=["laser", "microwave", "compare", "sweep", "safety",
                                 "hardware", "financial", "all"],
                        help="Simulation mode (default: compare)")
    parser.add_argument("--charts", action="store_true",
                        help="Generate and save charts to output/")
    parser.add_argument("--output", default="output",
                        help="Output directory for charts/reports")
    parser.add_argument("--system-cost", type=float, default=500_000,
                        help="Unit system cost in USD (default: $500k)")

    args = parser.parse_args()

    if args.mode == "laser":
        run_scenario_block("laser", charts=args.charts, output_dir=args.output)
    elif args.mode == "microwave":
        run_scenario_block("microwave", charts=args.charts, output_dir=args.output)
    elif args.mode == "compare":
        run_compare(charts=args.charts, output_dir=args.output)
    elif args.mode == "sweep":
        run_sweep(mode="laser", charts=args.charts, output_dir=args.output)
        run_sweep(mode="microwave", charts=args.charts, output_dir=args.output)
    elif args.mode == "safety":
        laser = run_mvp_scenario("laser")
        mw    = run_mvp_scenario("microwave")
        run_safety(laser, mw, charts=args.charts, output_dir=args.output)
    elif args.mode == "hardware":
        run_hardware()
    elif args.mode == "financial":
        laser = run_mvp_scenario("laser")
        run_financial(laser, system_cost_usd=args.system_cost,
                      charts=args.charts, output_dir=args.output)
    elif args.mode == "all":
        run_all(system_cost=args.system_cost, charts=args.charts, output_dir=args.output)


if __name__ == "__main__":
    main()
