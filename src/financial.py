"""
financial.py - Financial model for WPT system economics
Hummingbird Sim | Financial & ROI Module

Sources & assumptions:
  - DoD convoy cost: $400–$800/convoy-mile (RAND Corp, Army study 2009)
  - Diesel fuel DoD fully-burdened cost: ~$10–$20/liter in FOB logistics
  - Generator fuel consumption: ~0.3–0.4 L/kWh (diesel gen, 10 kW class)
  - SBIR Phase I: up to $250k; Phase II: up to $1.75M; Phase III: commercial
  - Military procurement typically 10–15 year system life
  - Discount rate: 8% (DoD standard for MILCON)
  - Cost per kWh at FOB (diesel): $5–$20/kWh fully burdened
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional, List

# ── Constants & defaults ──────────────────────────────────────────────────
DIESEL_ENERGY_DENSITY_KWH_L = 9.7          # kWh per liter of diesel
DIESEL_GEN_EFFICIENCY        = 0.30         # generator thermal efficiency
DIESEL_KWH_PER_LITER         = DIESEL_ENERGY_DENSITY_KWH_L * DIESEL_GEN_EFFICIENCY  # ~2.91 kWh/L
DIESEL_FUEL_CONSUMPTION_L_KWH = 1 / DIESEL_KWH_PER_LITER  # ~0.34 L/kWh

# Fully-burdened fuel cost at FOB (DoD, including logistics, not just pump price)
DIESEL_COST_PER_LITER_USD = 12.0          # $12/L at remote FOB (conservative estimate)
DIESEL_COST_PER_KWH_USD   = DIESEL_COST_PER_LITER_USD * DIESEL_FUEL_CONSUMPTION_L_KWH

# Convoy costs
CONVOY_COST_PER_MILE_USD = 600.0          # $600/convoy-mile (mid estimate)
CONVOY_SPEED_MPH         = 25.0           # avg convoy speed on rough terrain
RISK_PER_CONVOY_TRIP     = 0.005          # 0.5% fatality probability per trip (rough estimate)

# SBIR budget brackets
SBIR_PHASE_I_USD  = 250_000
SBIR_PHASE_II_USD = 1_750_000
SBIR_PHASE_III_USD = 10_000_000  # production contract target


@dataclass
class FinancialAssumptions:
    """Adjustable financial model inputs."""
    system_cost_usd: float       = 500_000.0    # unit system cost
    install_cost_pct: float      = 0.15         # % of system cost
    annual_maintenance_pct: float = 0.05        # % of system cost/year
    system_life_years: int       = 10
    discount_rate: float         = 0.08         # 8% DoD discount rate
    diesel_cost_per_liter_usd: float = DIESEL_COST_PER_LITER_USD
    diesel_l_per_kwh: float      = DIESEL_FUEL_CONSUMPTION_L_KWH
    convoy_cost_per_mile_usd: float = CONVOY_COST_PER_MILE_USD
    hours_operation_per_year: float = 8760.0    # 24/7 = 8760 h/yr
    delivered_power_kw: float    = 5.0          # kW delivered to FOB
    wpt_electricity_cost_usd_kwh: float = 0.0   # marginal cost of WPT electricity (if solar/grid at TX)


@dataclass
class SBIRBudget:
    """SBIR development cost model."""
    phase_i_months: int      = 6
    phase_i_budget_usd: float = SBIR_PHASE_I_USD
    phase_ii_months: int     = 24
    phase_ii_budget_usd: float = SBIR_PHASE_II_USD
    phase_iii_target_usd: float = SBIR_PHASE_III_USD
    team_size_phase_i: int   = 3
    team_size_phase_ii: int  = 8
    avg_salary_usd_yr: float = 140_000.0   # fully-burdened labor
    hardware_bom_phase_i: float  = 80_000.0
    hardware_bom_phase_ii: float = 600_000.0
    test_range_cost: float   = 50_000.0
    safety_validation_usd: float = 100_000.0


def compute_sbir_budget(sbir: SBIRBudget) -> dict:
    """Compute SBIR phase costs and feasibility check."""
    # Phase I
    p1_labor   = sbir.team_size_phase_i * sbir.avg_salary_usd_yr * (sbir.phase_i_months / 12)
    p1_overhead = p1_labor * 0.50  # F&A overhead
    p1_hw      = sbir.hardware_bom_phase_i
    p1_total   = p1_labor + p1_overhead + p1_hw
    p1_feasible = p1_total <= sbir.phase_i_budget_usd

    # Phase II
    p2_labor   = sbir.team_size_phase_ii * sbir.avg_salary_usd_yr * (sbir.phase_ii_months / 12)
    p2_overhead = p2_labor * 0.50
    p2_hw      = sbir.hardware_bom_phase_ii
    p2_test    = sbir.test_range_cost
    p2_safety  = sbir.safety_validation_usd
    p2_total   = p2_labor + p2_overhead + p2_hw + p2_test + p2_safety
    p2_feasible = p2_total <= sbir.phase_ii_budget_usd

    return {
        "phase_i": {
            "months": sbir.phase_i_months,
            "budget_usd": sbir.phase_i_budget_usd,
            "estimated_cost_usd": p1_total,
            "labor_usd": p1_labor,
            "overhead_usd": p1_overhead,
            "hardware_usd": p1_hw,
            "feasible": p1_feasible,
            "surplus_deficit_usd": sbir.phase_i_budget_usd - p1_total,
        },
        "phase_ii": {
            "months": sbir.phase_ii_months,
            "budget_usd": sbir.phase_ii_budget_usd,
            "estimated_cost_usd": p2_total,
            "labor_usd": p2_labor,
            "overhead_usd": p2_overhead,
            "hardware_usd": p2_hw,
            "test_range_usd": p2_test,
            "safety_validation_usd": p2_safety,
            "feasible": p2_feasible,
            "surplus_deficit_usd": sbir.phase_ii_budget_usd - p2_total,
        },
        "phase_iii_target": sbir.phase_iii_target_usd,
    }


def compute_roi(fa: FinancialAssumptions) -> dict:
    """
    Compute ROI, payback period, NPV, IRR for WPT system vs. diesel generator.
    """
    # Annual energy delivered (kWh/yr)
    kwh_per_year = fa.delivered_power_kw * fa.hours_operation_per_year

    # Diesel baseline cost
    diesel_liters_yr = kwh_per_year * fa.diesel_l_per_kwh
    diesel_cost_yr   = diesel_liters_yr * fa.diesel_cost_per_liter_usd

    # WPT operating cost (electricity at TX end — if solar or grid: near zero)
    wpt_elec_cost_yr = kwh_per_year * fa.wpt_electricity_cost_usd_kwh
    wpt_maintenance_yr = fa.system_cost_usd * fa.annual_maintenance_pct

    # Annual savings vs. diesel
    annual_savings = diesel_cost_yr - wpt_elec_cost_yr - wpt_maintenance_yr

    # Capital cost
    capex = fa.system_cost_usd * (1 + fa.install_cost_pct)

    # Simple payback
    payback_years = capex / annual_savings if annual_savings > 0 else np.inf

    # NPV / IRR
    cash_flows = [-capex]  # year 0
    for yr in range(1, fa.system_life_years + 1):
        salvage = capex * 0.1 if yr == fa.system_life_years else 0
        cash_flows.append(annual_savings + salvage)

    npv = sum(cf / (1 + fa.discount_rate)**i for i, cf in enumerate(cash_flows))

    # IRR (binary search)
    def npv_at_rate(r):
        return sum(cf / (1 + r)**i for i, cf in enumerate(cash_flows))

    irr = None
    try:
        r_lo, r_hi = -0.99, 10.0
        for _ in range(100):
            r_mid = (r_lo + r_hi) / 2
            if npv_at_rate(r_mid) > 0:
                r_lo = r_mid
            else:
                r_hi = r_mid
        irr = (r_lo + r_hi) / 2
    except Exception:
        irr = None

    return {
        "kwh_per_year":           kwh_per_year,
        "diesel_liters_yr":       diesel_liters_yr,
        "diesel_cost_yr_usd":     diesel_cost_yr,
        "diesel_cost_per_kwh":    DIESEL_COST_PER_KWH_USD,
        "wpt_elec_cost_yr_usd":   wpt_elec_cost_yr,
        "wpt_maintenance_yr_usd": wpt_maintenance_yr,
        "annual_savings_usd":     annual_savings,
        "capex_usd":              capex,
        "payback_years":          payback_years,
        "npv_usd":                npv,
        "irr_pct":                irr * 100 if irr else None,
        "system_life_years":      fa.system_life_years,
        "cash_flows":             cash_flows,
    }


def compute_convoy_economics(fa: FinancialAssumptions,
                              convoy_distance_km: float = 50.0,
                              convoy_trips_per_month: float = 4.0,
                              fraction_eliminated: float = 0.80) -> dict:
    """
    Compute value of convoy elimination.
    WPT reduces fuel convoys → fewer trips → lower cost + risk.
    """
    convoy_distance_miles = convoy_distance_km * 0.621371
    cost_per_trip = convoy_distance_miles * fa.convoy_cost_per_mile_usd
    trips_per_year = convoy_trips_per_month * 12
    current_cost_yr = trips_per_trip = cost_per_trip * trips_per_year

    trips_eliminated_yr = trips_per_year * fraction_eliminated
    cost_saved_yr       = trips_eliminated_yr * cost_per_trip
    risk_reduction_yr   = trips_eliminated_yr * RISK_PER_CONVOY_TRIP  # expected lives saved

    # Also account for fuel weight reduction
    diesel_liters_yr = fa.delivered_power_kw * fa.hours_operation_per_year * fa.diesel_l_per_kwh
    fuel_weight_saved_kg = diesel_liters_yr * 0.84 * fraction_eliminated  # diesel density ~0.84 kg/L

    return {
        "convoy_distance_km":      convoy_distance_km,
        "trips_per_year":          trips_per_year,
        "cost_per_trip_usd":       cost_per_trip,
        "current_convoy_cost_yr":  current_cost_yr,
        "fraction_eliminated":     fraction_eliminated,
        "trips_eliminated_yr":     trips_eliminated_yr,
        "convoy_cost_saved_yr_usd": cost_saved_yr,
        "expected_risk_reduction": risk_reduction_yr,
        "fuel_weight_saved_kg_yr": fuel_weight_saved_kg,
    }


def scaling_analysis(base_system_cost: float, volumes: List[int] = None) -> pd.DataFrame:
    """
    Learning curve analysis for production scaling.
    Uses Wright's Law: unit cost reduces by ~15–20% per doubling of cumulative units.
    """
    if volumes is None:
        volumes = [1, 10, 50, 100, 500, 1000, 5000]
    learning_rate = 0.82  # 18% reduction per doubling (typical electronics)
    rows = []
    for qty in volumes:
        # Wright's law: C_n = C_1 * n^(log(L)/log(2))
        exponent = np.log(learning_rate) / np.log(2)
        unit_cost = base_system_cost * qty**exponent
        total_cost = unit_cost * qty
        rows.append({
            "units_produced": qty,
            "unit_cost_usd":  unit_cost,
            "total_rev_usd":  total_cost,
            "cost_reduction_pct": (1 - unit_cost / base_system_cost) * 100,
        })
    return pd.DataFrame(rows)


def print_financial_report(roi: dict, convoy: dict, sbir: dict,
                            scaling: pd.DataFrame) -> str:
    lines = [
        "=" * 65,
        "  FINANCIAL MODEL REPORT",
        "=" * 65,
        "",
        "  ── ROI Analysis ─────────────────────────────────────────",
        f"  Annual energy delivered:    {roi['kwh_per_year']:,.0f} kWh/yr",
        f"  Diesel fuel saved:          {roi['diesel_liters_yr']:,.0f} L/yr",
        f"  Diesel cost avoided:        ${roi['diesel_cost_yr_usd']:,.0f}/yr",
        f"  Diesel cost per kWh:        ${roi['diesel_cost_per_kwh']:.2f}/kWh",
        f"  WPT maintenance cost:       ${roi['wpt_maintenance_yr_usd']:,.0f}/yr",
        f"  Net annual savings:         ${roi['annual_savings_usd']:,.0f}/yr",
        f"  CAPEX (incl. install):      ${roi['capex_usd']:,.0f}",
        f"  Simple payback:             {roi['payback_years']:.1f} years",
        f"  NPV ({roi['system_life_years']}yr @ 8%):              ${roi['npv_usd']:,.0f}",
        f"  IRR:                        {roi['irr_pct']:.1f}%",
        "",
        "  ── Convoy Elimination Value ─────────────────────────────",
        f"  Convoy distance:            {convoy['convoy_distance_km']:.0f} km",
        f"  Annual convoy trips:        {convoy['trips_per_year']:.0f}",
        f"  Cost per trip:              ${convoy['cost_per_trip_usd']:,.0f}",
        f"  Convoys eliminated/yr:      {convoy['trips_eliminated_yr']:.0f} ({convoy['fraction_eliminated']*100:.0f}%)",
        f"  Convoy cost saved/yr:       ${convoy['convoy_cost_saved_yr_usd']:,.0f}",
        f"  Expected risk reduction:    {convoy['expected_risk_reduction']:.3f} lives/yr",
        f"  Fuel weight saved:          {convoy['fuel_weight_saved_kg_yr']:,.0f} kg/yr",
        "",
        "  ── SBIR Budget Alignment ────────────────────────────────",
        f"  Phase I  (${sbir['phase_i']['budget_usd']:,.0f}):   est. ${sbir['phase_i']['estimated_cost_usd']:,.0f}  "
        f"{'✓ FITS' if sbir['phase_i']['feasible'] else '✗ OVER BUDGET'}",
        f"  Phase II (${sbir['phase_ii']['budget_usd']:,.0f}): est. ${sbir['phase_ii']['estimated_cost_usd']:,.0f}  "
        f"{'✓ FITS' if sbir['phase_ii']['feasible'] else '✗ OVER BUDGET'}",
        f"  Phase III target:           ${sbir['phase_iii_target']:,.0f}",
        "",
        "  ── Production Scaling (Wright's Law, 18% learning) ──────",
        f"  {'Units':>8} | {'Unit Cost':>12} | {'Cost Reduction':>16}",
        "  " + "-" * 42,
    ]
    for _, row in scaling.iterrows():
        lines.append(
            f"  {int(row['units_produced']):>8} | ${row['unit_cost_usd']:>10,.0f} | "
            f"{row['cost_reduction_pct']:>14.1f}%"
        )
    lines.append("=" * 65)
    return "\n".join(lines)
