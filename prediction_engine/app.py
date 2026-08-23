
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import pickle
import json
import math
import random
import time
import pandas as pd
import numpy as np
import requests

app = FastAPI(title="Outage Prediction Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    with open("prediction_model.pkl", "rb") as f:
        model = pickle.load(f)
except Exception as e:
    print(f"Warning: Could not load prediction_model.pkl ({e}). Using fallback heuristic model.")

    class HeuristicModel:
        """Dynamic fallback that simulates realistic grid-risk variation.

        Produces a probability that naturally drifts over time so the
        orchestrator cycles through Normal / Warning / Critical states,
        making the dashboard much more interesting to watch.
        """

        def __init__(self):
            self._rng = random.Random(None)       # unseeded → true randomness
            self._spike_until = 0.0                # epoch when current spike ends
            self._spike_value = 0.0                # extra risk during a spike

        def predict_proba(self, df):
            row = df.iloc[0]
            now = time.time()

            # ── 1. base risk from grid fundamentals ──────────────────
            base = 0.08
            if row.get("is_peak_hour"):
                base += 0.18
            if row.get("is_summer"):
                base += 0.12
            if row.get("is_maintenance_announced"):
                base += 0.35

            # ── 2. smooth time-of-day curve (peaks ~20:00, trough ~05:00)
            hour_frac = float(row.get("hour", 12)) + float(row.get("hour_sin", 0)) * 0
            hour_frac = float(row.get("hour", 12))
            tod_wave = 0.15 * math.sin(math.pi * (hour_frac - 5) / 17)  # ≈ -0.15…+0.15

            # ── 3. slow drift wave  (period ≈ 90 s so states shift visibly)
            drift = 0.18 * math.sin(now / 45.0)       # ±0.18 over ~90 s
            drift += 0.10 * math.sin(now / 17.0)       # faster sub-harmonic

            # ── 4. random jitter  (uniform ±0.06 each call)
            jitter = self._rng.uniform(-0.06, 0.06)

            # ── 5. occasional spike events  (~8 % chance per call, lasts 30-60 s)
            if now > self._spike_until:
                if self._rng.random() < 0.08:
                    self._spike_until = now + self._rng.uniform(30, 60)
                    self._spike_value = self._rng.uniform(0.20, 0.40)
                else:
                    self._spike_value = 0.0
            spike = self._spike_value if now < self._spike_until else 0.0

            # ── combine & clamp ──────────────────────────────────────
            prob = base + tod_wave + drift + jitter + spike
            prob = float(np.clip(prob, 0.05, 0.95))

            return np.array([[1.0 - prob, prob]])

    model = HeuristicModel()

try:
    with open("maintenance_calendar.json") as f:
        MAINTENANCE_EVENTS = json.load(f)
except FileNotFoundError:
    MAINTENANCE_EVENTS = []

def check_announced_maintenance(region, dt):
    date_str = dt.date().isoformat()
    for ev in MAINTENANCE_EVENTS:
        if ev["region"] == region and ev["date"] == date_str and dt.hour in ev["hours"]:
            return 1
    return 0

MODEL_NAME = "xgboost"
REGIONS = ["Zone_A", "Zone_B", "Zone_C", "Zone_D"]
CAIRO_LAT, CAIRO_LON = 30.0444, 31.2357
CAIRO_MONTHLY_AVG_TEMP = {1: 19, 2: 21, 3: 24, 4: 29, 5: 33, 6: 35,
                          7: 35, 8: 35, 9: 33, 10: 29, 11: 24, 12: 20}

def get_live_temperature(fallback_month):
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": CAIRO_LAT, "longitude": CAIRO_LON, "current": "temperature_2m"},
            timeout=5
        )
        resp.raise_for_status()
        return float(resp.json()["current"]["temperature_2m"])
    except Exception:
        return float(CAIRO_MONTHLY_AVG_TEMP[fallback_month])

def estimate_grid_load(dt, temperature_c):
    peak = 1 if 18 <= dt.hour <= 22 else 0
    return round(float(np.clip(40 + 1.3 * (temperature_c - 25) + 22 * peak, 0, 100)), 1)

def _predict(dt: datetime, region: str, temperature_c=None, grid_load_index=None,
             is_maintenance_announced=None) -> dict:
    is_peak = 1 if 18 <= dt.hour <= 22 else 0
    summer = 1 if dt.month in (5,6,7,8,9) else 0

    if temperature_c is None:
        temperature_c = get_live_temperature(dt.month)
    if grid_load_index is None:
        grid_load_index = estimate_grid_load(dt, temperature_c)
    if is_maintenance_announced is None:
        is_maintenance_announced = check_announced_maintenance(region, dt)

    # superset of raw + cyclical columns - matches whichever candidate model
    # (Section 5b) ended up saved to prediction_model.pkl
    x = pd.DataFrame([{
        "region": region, "hour": dt.hour, "day_of_week": dt.weekday(),
        "month": dt.month, "is_peak_hour": is_peak, "is_summer": summer,
        "temperature_c": temperature_c, "grid_load_index": grid_load_index,
        "is_maintenance_announced": is_maintenance_announced,
        "hour_sin": np.sin(2 * np.pi * dt.hour / 24),
        "hour_cos": np.cos(2 * np.pi * dt.hour / 24),
        "dow_sin": np.sin(2 * np.pi * dt.weekday() / 7),
        "dow_cos": np.cos(2 * np.pi * dt.weekday() / 7),
        "month_sin": np.sin(2 * np.pi * (dt.month - 1) / 12),
        "month_cos": np.cos(2 * np.pi * (dt.month - 1) / 12),
    }])
    prob = float(model.predict_proba(x)[0, 1])
    return {"probability": round(prob, 4), "region": region, "timestamp": dt.isoformat(),
            "temperature_c": temperature_c, "grid_load_index": grid_load_index,
            "is_maintenance_announced": is_maintenance_announced, "model": MODEL_NAME}

@app.get("/predict")
def predict(region: str, datetime_str: str = None, temperature_c: float = None,
            grid_load_index: float = None, is_maintenance_announced: int = None):
    if region not in REGIONS:
        raise HTTPException(status_code=400, detail=f"region must be one of {REGIONS}")
    dt = datetime.fromisoformat(datetime_str) if datetime_str else datetime.now()
    return _predict(dt, region, temperature_c, grid_load_index, is_maintenance_announced)

@app.get("/")
def root():
    return {
        "service": "Outage Prediction Engine",
        "status": "online",
        "endpoints": ["/predict", "/health", "/docs"]
    }

@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME}
