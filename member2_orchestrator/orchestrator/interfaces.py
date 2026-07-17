"""
Integration adapters - one function per external dependency.

Every function here has the SAME shape regardless of whether the real
service is up yet: it tries the real call first, and falls back to a mock
with a logged warning if the real service isn't reachable. This means:
  - Day 1-4: you can develop/demo the orchestrator alone, no other member's
    code needs to exist yet.
  - Day 4-7: as each teammate's service comes online, these functions start
    hitting the real thing automatically - nobody has to change orchestrator
    logic, only these adapter functions (and most of them not even that).
"""

import logging
import random
import time
from datetime import datetime
from typing import Optional

import requests

from . import config

logger = logging.getLogger("orchestrator.interfaces")


# ---------------------------------------------------------------------------
# Member 1: Prediction Engine
# ---------------------------------------------------------------------------
def get_current_probability(region: str = None) -> float:
    """Calls Member 1's FastAPI /predict endpoint. Falls back to a mock
    probability generator if the service isn't reachable yet (e.g. during
    early development before Member 1 hands off app.py)."""
    region = region or config.PREDICTION_ENGINE_REGION
    params = {"region": region, "datetime_str": datetime.now().isoformat(timespec="seconds")}
    try:
        resp = requests.get(
            config.PREDICTION_ENGINE_URL,
            params=params,
            timeout=config.PREDICTION_ENGINE_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        # app.py's response is expected to include an outage probability field
        prob = data.get("outage_probability", data.get("probability"))
        if prob is None:
            raise ValueError(f"Unexpected response shape from Prediction Engine: {data}")
        return float(prob)
    except Exception as e:
        mock_prob = _mock_probability()
        logger.warning(
            "Prediction Engine unreachable (%s) - using MOCK probability %.2f. "
            "This is expected until Member 1's app.py is running.",
            e, mock_prob,
        )
        return mock_prob


def _mock_probability() -> float:
    """A simple mock: mostly low risk, with occasional spikes - just enough
    to exercise every state transition during standalone development/demo."""
    if random.random() < 0.08:
        return round(random.uniform(0.65, 0.95), 2)
    return round(random.uniform(0.0, 0.35), 2)


# ---------------------------------------------------------------------------
# Member 3: Checkpointing & Resume Module
# ---------------------------------------------------------------------------
def checkpoint_now() -> bool:
    """Triggers Member 3's checkpoint. Returns True once confirmed complete."""
    if config.CHECKPOINT_SERVICE_URL:
        try:
            resp = requests.post(config.CHECKPOINT_SERVICE_URL, timeout=10)
            resp.raise_for_status()
            return bool(resp.json().get("done", True))
        except Exception as e:
            logger.error("checkpoint_now() call failed: %s", e)
            return False
    logger.info("[MOCK] checkpoint_now() - Member 3 not wired up yet, simulating success.")
    time.sleep(0.2)  # simulate the call taking a moment
    return True


def resume_from_last() -> bool:
    """Triggers Member 3's resume. Returns True once confirmed complete."""
    if config.RESUME_SERVICE_URL:
        try:
            resp = requests.post(config.RESUME_SERVICE_URL, timeout=10)
            resp.raise_for_status()
            return bool(resp.json().get("done", True))
        except Exception as e:
            logger.error("resume_from_last() call failed: %s", e)
            return False
    logger.info("[MOCK] resume_from_last() - Member 3 not wired up yet, simulating success.")
    time.sleep(0.2)
    return True


# ---------------------------------------------------------------------------
# Member 4: CI/CD Pipeline Integration (GitHub Actions)
# ---------------------------------------------------------------------------
def pause_pipeline() -> bool:
    """Fires a repository_dispatch event Member 4's workflow listens for."""
    return _send_github_dispatch(config.GITHUB_DISPATCH_EVENT_PAUSE)


def resume_pipeline() -> bool:
    """Fires a repository_dispatch event Member 4's workflow listens for."""
    return _send_github_dispatch(config.GITHUB_DISPATCH_EVENT_RESUME)


def _send_github_dispatch(event_type: str) -> bool:
    if config.GITHUB_REPO and config.GITHUB_TOKEN:
        try:
            url = f"https://api.github.com/repos/{config.GITHUB_REPO}/dispatches"
            headers = {
                "Authorization": f"Bearer {config.GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
            }
            resp = requests.post(url, headers=headers, json={"event_type": event_type}, timeout=10)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error("GitHub dispatch '%s' failed: %s", event_type, e)
            return False
    logger.info("[MOCK] repository_dispatch('%s') - Member 4's workflow not wired up yet.", event_type)
    return True
