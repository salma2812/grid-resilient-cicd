"""
Central config so the whole team can tune behaviour from one place without
touching orchestrator logic. Env vars override defaults so this also works
cleanly inside a GitHub Actions runner (Member 4) without editing code.
"""

import os

from .state_machine import Thresholds

# --- Risk thresholds -------------------------------------------------------
THRESHOLDS = Thresholds(
    warning_threshold=float(os.getenv("ORCH_WARNING_THRESHOLD", 0.40)),
    checkpoint_threshold=float(os.getenv("ORCH_CHECKPOINT_THRESHOLD", 0.70)),
    recovery_threshold=float(os.getenv("ORCH_RECOVERY_THRESHOLD", 0.25)),
)

# --- Polling ----------------------------------------------------------------
POLL_INTERVAL_SECONDS = int(os.getenv("ORCH_POLL_INTERVAL_SECONDS", 15))

# --- Member 1 (Prediction Engine) integration ------------------------------
# Matches the FastAPI app Member 1 hands off (see app.py: GET /predict).
PREDICTION_ENGINE_URL = os.getenv(
    "PREDICTION_ENGINE_URL", "http://localhost:8000/predict"
)
PREDICTION_ENGINE_REGION = os.getenv("ORCH_REGION", "Zone_A")
PREDICTION_ENGINE_TIMEOUT_SECONDS = float(os.getenv("ORCH_PREDICT_TIMEOUT", 3.0))

# --- Member 3 (Checkpointing Module) integration ---------------------------
CHECKPOINT_SERVICE_URL = os.getenv("CHECKPOINT_SERVICE_URL", "")  # empty = use mock
RESUME_SERVICE_URL = os.getenv("RESUME_SERVICE_URL", "")          # empty = use mock

# --- Member 4 (CI/CD Integration) ------------------------------------------
GITHUB_REPO = os.getenv("GITHUB_REPO", "")           # e.g. "org/repo"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_DISPATCH_EVENT_PAUSE = os.getenv("GITHUB_DISPATCH_EVENT_PAUSE", "grid_risk_high")
GITHUB_DISPATCH_EVENT_RESUME = os.getenv("GITHUB_DISPATCH_EVENT_RESUME", "grid_risk_clear")

# --- Cost-Aware Scheduler ---------------------------------------------------
SCHEDULER_SERVICE_URL = os.getenv("SCHEDULER_SERVICE_URL", "")  # empty = use built-in
SCHEDULER_DEFAULT_PRIORITY = os.getenv("SCHEDULER_DEFAULT_PRIORITY", "Medium")

# --- Member 5 (Dashboard & Alerts) -----------------------------------------
EVENT_LOG_PATH = os.getenv("ORCH_EVENT_LOG_PATH", "orchestrator_events.jsonl")
