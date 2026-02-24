"""
Hummingbird Sim — FastAPI Backend
Wireless Power Transmission simulator for defense logistics.
"""

import sys
import os

# Add project root to path so we can import src.*
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
import math
import dataclasses
import numpy as np
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ── Import simulation modules ─────────────────────────────────────────────
from src.scenarios import (
    compute_scenario,
    sweep_range_and_conditions,
    run_mvp_scenario,
)
from src.financial import (
    FinancialAssumptions,
    SBIRBudget,
    compute_roi,
    compute_sbir_budget,
    compute_convoy_economics,
    scaling_analysis,
)
from src.safety import (
    compute_laser_safety,
    compute_microwave_safety,
    model_interlock_scenario,
)
from src.hardware import design_laser_system, design_microwave_system


# ── JSON serializer for numpy / dataclasses ───────────────────────────────

def make_serializable(obj: Any) -> Any:
    """Recursively convert numpy types, dataclasses, etc. to JSON-safe types."""
    if isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [make_serializable(v) for v in obj]
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return make_serializable(dataclasses.asdict(obj))
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else obj
    if isinstance(obj, bool):
        return obj
    # pandas DataFrame
    try:
        import pandas as pd
        if isinstance(obj, pd.DataFrame):
            return make_serializable(obj.to_dict(orient="records"))
    except ImportError:
        pass
    return obj


# ── App setup ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Hummingbird Sim API",
    description="Wireless Power Transmission simulation for defense logistics",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response models ───────────────────────────────────────────────

class SimulateRequest(BaseModel):
    mode: str = Field(..., description="laser | microwave | compare")
    range_m: float = Field(2000.0, ge=100, le=50000)
    power_kw: float = Field(5.0, ge=0.1, le=500)
    condition: str = Field("clear", description="clear | haze | smoke | rain")


class FinancialRequest(BaseModel):
    system_cost_usd: float = Field(500000.0, ge=10000)
    power_kw: float = Field(5.0, ge=0.1)
    convoy_distance_km: float = Field(50.0, ge=1)
    convoy_trips_month: float = Field(4.0, ge=0)


# ── Endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/simulate")
def simulate(req: SimulateRequest):
    """Run a single operational scenario and return full result JSON."""
    try:
        if req.mode in ("laser", "microwave"):
            result = compute_scenario(
                mode=req.mode,
                range_m=req.range_m,
                target_power_kw=req.power_kw,
                condition=req.condition,
            )
        elif req.mode == "compare":
            laser_result = compute_scenario(
                mode="laser",
                range_m=req.range_m,
                target_power_kw=req.power_kw,
                condition=req.condition,
            )
            mw_result = compute_scenario(
                mode="microwave",
                range_m=req.range_m,
                target_power_kw=req.power_kw,
                condition=req.condition if req.condition not in ["smoke"] else "clear",
            )
            result = {
                "mode": "compare",
                "laser": laser_result,
                "microwave": mw_result,
            }
        else:
            raise HTTPException(status_code=400, detail=f"Unknown mode: {req.mode}")

        return make_serializable(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sweep")
def sweep(
    mode: str = Query("laser", description="laser | microwave"),
    power_kw: float = Query(5.0, ge=0.1, le=500),
):
    """Return range sweep data as JSON array (efficiency vs range for all conditions)."""
    try:
        df = sweep_range_and_conditions(
            mode=mode,
            target_power_kw=power_kw,
        )
        return make_serializable(df)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/safety")
def safety(
    mode: str = Query("laser", description="laser | microwave"),
    power_kw: float = Query(15.0, ge=0.1),
    range_m: float = Query(2000.0, ge=100),
):
    """Return safety analysis JSON."""
    try:
        if mode == "laser":
            result = compute_laser_safety(
                power_w=power_kw * 1000,
                range_m=range_m,
                waist_m=0.075,
            )
            interlocks = [
                model_interlock_scenario(trigger, power_kw * 1000)
                for trigger in ["beam_block", "tracking_lost", "power_down_full"]
            ]
            return make_serializable({
                "mode": "laser",
                "laser_safety": result,
                "interlocks": interlocks,
            })
        elif mode == "microwave":
            # Need to compute scenario first for actual PD at range
            scenario = compute_scenario(
                mode="microwave",
                range_m=range_m,
                target_power_kw=power_kw,
                condition="clear",
            )
            # Estimate gain from scenario physics dict
            physics = scenario.get("physics", {})
            gain_dbi = physics.get("array_gain_dbi", 43.0)
            total_rf_w = physics.get("total_rf_power_w", power_kw * 1000 * 0.5)
            pd_at_range = physics.get("power_density_mw_cm2", 0.1)

            result = compute_microwave_safety(
                total_tx_rf_w=total_rf_w,
                gain_dbi=gain_dbi,
                range_m=range_m,
                pd_at_range_mw_cm2=pd_at_range,
            )
            interlocks = [
                model_interlock_scenario(trigger, total_rf_w)
                for trigger in ["rf_kill", "tracking_lost", "power_down_full"]
            ]
            return make_serializable({
                "mode": "microwave",
                "mw_safety": result,
                "interlocks": interlocks,
            })
        else:
            raise HTTPException(status_code=400, detail=f"Unknown mode: {mode}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/hardware")
def hardware(
    mode: str = Query("laser", description="laser | microwave"),
    power_kw: float = Query(5.0, ge=0.1),
    range_m: float = Query(2000.0, ge=100),
):
    """Return hardware BOM JSON."""
    try:
        if mode == "laser":
            spec = design_laser_system(
                target_dc_w=power_kw * 1000,
                range_m=range_m,
                system_eff=0.08,
            )
        elif mode == "microwave":
            spec = design_microwave_system(
                target_dc_w=power_kw * 1000,
                range_m=range_m,
                system_eff=0.15,
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown mode: {mode}")

        return make_serializable(spec)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/financial")
def financial(req: FinancialRequest):
    """Return financial model JSON."""
    try:
        fa = FinancialAssumptions(
            system_cost_usd=req.system_cost_usd,
            delivered_power_kw=req.power_kw,
        )
        roi = compute_roi(fa)
        convoy = compute_convoy_economics(
            fa,
            convoy_distance_km=req.convoy_distance_km,
            convoy_trips_per_month=req.convoy_trips_month,
        )
        sbir = compute_sbir_budget(SBIRBudget())
        scaling = scaling_analysis(req.system_cost_usd)

        return make_serializable({
            "roi": roi,
            "convoy": convoy,
            "sbir": sbir,
            "scaling": scaling,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
