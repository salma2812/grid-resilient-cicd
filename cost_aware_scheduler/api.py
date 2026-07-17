"""
FastAPI service for the Cost-Aware Scheduler.

Endpoints
---------
POST /schedule   — Evaluate a scheduling decision from explicit inputs.
GET  /schedule   — Evaluate using live/simulated metrics + prediction engine.
GET  /metrics    — Return current simulated system metrics.
GET  /health     — Health check.

Run:
    uvicorn cost_aware_scheduler.api:app --port 8002
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import requests
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .models import JobPriority, SchedulerInput
from .scheduler import CostAwareScheduler
from .simulators import get_all_simulated_metrics

logger = logging.getLogger("cost_aware_scheduler.api")

app = FastAPI(
    title="Cost-Aware Scheduler",
    description="Decides whether a pipeline should execute immediately or be delayed based on outage risk, resource utilisation, electricity cost, and carbon intensity.",
    version="1.0.0",
)

# Allow the UI dashboard to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

scheduler = CostAwareScheduler()

# ── Prediction Engine config ────────────────────────────────────────────────
PREDICTION_ENGINE_URL = "http://localhost:8000/predict"
DEFAULT_REGION = "Zone_A"


# ── Request/response schemas ────────────────────────────────────────────────

class ScheduleRequest(BaseModel):
    """Explicit input for POST /schedule."""
    outage_probability: float = Field(..., ge=0.0, le=1.0, description="Outage probability (0-1)")
    cpu_percent: float = Field(..., ge=0.0, le=100.0, description="CPU utilisation %")
    memory_percent: float = Field(..., ge=0.0, le=100.0, description="Memory utilisation %")
    electricity_cost: float = Field(..., ge=0.0, description="$/kWh")
    carbon_intensity: float = Field(..., ge=0.0, description="gCO₂/kWh")
    job_priority: str = Field("Medium", description="High, Medium, or Low")


class ScheduleResponse(BaseModel):
    """The scheduler's output."""
    decision: str
    reason: list[str]
    metrics: dict = {}


# ── Endpoints ───────────────────────────────────────────────────────────────

@app.post("/schedule", response_model=ScheduleResponse)
def schedule_explicit(req: ScheduleRequest):
    """Evaluate a scheduling decision from explicitly provided inputs."""
    try:
        priority = JobPriority(req.job_priority)
    except ValueError:
        priority = JobPriority.MEDIUM

    inp = SchedulerInput(
        outage_probability=req.outage_probability,
        cpu_percent=req.cpu_percent,
        memory_percent=req.memory_percent,
        electricity_cost=req.electricity_cost,
        carbon_intensity=req.carbon_intensity,
        job_priority=priority,
    )
    result = scheduler.evaluate(inp)
    return ScheduleResponse(
        decision=result.decision.value,
        reason=result.reason,
        metrics={
            "outage_probability": req.outage_probability,
            "cpu_percent": req.cpu_percent,
            "memory_percent": req.memory_percent,
            "electricity_cost": req.electricity_cost,
            "carbon_intensity": req.carbon_intensity,
            "job_priority": req.job_priority,
        },
    )


@app.get("/schedule", response_model=ScheduleResponse)
def schedule_auto(
    region: str = Query(DEFAULT_REGION, description="Grid region"),
    job_priority: str = Query("Medium", description="High, Medium, or Low"),
):
    """
    Evaluate using the Prediction Engine for outage probability and
    simulated values for CPU, memory, electricity, and carbon.
    """
    # Get outage probability from Prediction Engine (with mock fallback)
    outage_prob = _get_outage_probability(region)
    metrics = get_all_simulated_metrics()

    try:
        priority = JobPriority(job_priority)
    except ValueError:
        priority = JobPriority.MEDIUM

    inp = SchedulerInput(
        outage_probability=outage_prob,
        cpu_percent=metrics["cpu_percent"],
        memory_percent=metrics["memory_percent"],
        electricity_cost=metrics["electricity_cost"],
        carbon_intensity=metrics["carbon_intensity"],
        job_priority=priority,
    )
    result = scheduler.evaluate(inp)
    return ScheduleResponse(
        decision=result.decision.value,
        reason=result.reason,
        metrics={
            "outage_probability": outage_prob,
            **metrics,
            "job_priority": job_priority,
        },
    )


@app.get("/metrics")
def get_metrics():
    """Return current simulated system metrics (for the dashboard)."""
    metrics = get_all_simulated_metrics()
    return {
        **metrics,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/health")
def health():
    """Health check."""
    return {"status": "ok", "service": "cost-aware-scheduler"}


# ── Internal helpers ────────────────────────────────────────────────────────

def _get_outage_probability(region: str) -> float:
    """Try the Prediction Engine; fall back to a mock on failure."""
    try:
        resp = requests.get(
            PREDICTION_ENGINE_URL,
            params={
                "region": region,
                "datetime_str": datetime.now().isoformat(timespec="seconds"),
            },
            timeout=3,
        )
        resp.raise_for_status()
        data = resp.json()
        prob = data.get("probability", data.get("outage_probability"))
        if prob is not None:
            return float(prob)
    except Exception as e:
        logger.warning("Prediction Engine unreachable (%s) — using mock", e)

    # Mock fallback: mostly low risk
    import random
    if random.random() < 0.08:
        return round(random.uniform(0.65, 0.95), 3)
    return round(random.uniform(0.05, 0.30), 3)
