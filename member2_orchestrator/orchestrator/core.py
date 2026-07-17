import json
import logging
import sys
import os
from datetime import datetime, timezone
from typing import Optional

from . import config, interfaces
from .state_machine import State, decide

# Add the project root to sys.path so the cost_aware_scheduler package is importable
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from cost_aware_scheduler import CostAwareScheduler, SchedulerInput, JobPriority
from cost_aware_scheduler.models import SchedulerAction
from cost_aware_scheduler.simulators import get_all_simulated_metrics

logger = logging.getLogger("orchestrator.core")


class Orchestrator:
    """The Member 2 'brain': polls Member 1's risk prediction, decides what
    to do using the pure state machine in state_machine.py, executes the
    resulting actions against Member 3/4's services (or mocks), and emits a
    structured JSON event for every poll for Member 5's dashboard to consume.
    """

    def __init__(self, thresholds=None, region: str = None, job_priority: str = None):
        self.thresholds = thresholds or config.THRESHOLDS
        self.region = region or config.PREDICTION_ENGINE_REGION
        self.state = State.NORMAL
        self._checkpoint_done: Optional[bool] = None
        self._resume_done: Optional[bool] = None
        self.history = []  # in-memory event history, handy for tests/demo/notebook display
        self._scheduler = CostAwareScheduler()
        self._job_priority = job_priority or config.SCHEDULER_DEFAULT_PRIORITY
        self._last_scheduler_result = None

    def poll_once(self, probability: Optional[float] = None) -> dict:
        """Runs exactly one decision cycle. If `probability` is not given,
        fetches it live from Member 1's Prediction Engine (with mock
        fallback). Passing `probability` explicitly is how tests and demos
        drive the state machine deterministically without waiting on a
        real/mock random feed.
        """
        if probability is None:
            probability = interfaces.get_current_probability(self.region)

        # ── Cost-Aware Scheduler evaluation ─────────────────────────────────
        scheduler_result = self._evaluate_scheduler(probability)
        self._last_scheduler_result = scheduler_result

        decision = decide(
            self.state,
            probability,
            self.thresholds,
            checkpoint_done=self._checkpoint_done,
            resume_done=self._resume_done,
        )

        previous_state = self.state
        self.state = decision.next_state

        action_results = {action: self._execute_action(action) for action in decision.actions}

        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "previous_state": previous_state.value,
            "new_state": self.state.value,
            "probability": probability,
            "reason": decision.reason,
            "actions": decision.actions,
            "action_results": action_results,
            "scheduler": scheduler_result,
        }
        self._emit_event(event)
        self.history.append(event)
        return event

    def _evaluate_scheduler(self, outage_probability: float) -> dict:
        """Run the Cost-Aware Scheduler and return its decision + metrics."""
        try:
            metrics = get_all_simulated_metrics()
            try:
                priority = JobPriority(self._job_priority)
            except ValueError:
                priority = JobPriority.MEDIUM

            inp = SchedulerInput(
                outage_probability=outage_probability,
                cpu_percent=metrics["cpu_percent"],
                memory_percent=metrics["memory_percent"],
                electricity_cost=metrics["electricity_cost"],
                carbon_intensity=metrics["carbon_intensity"],
                job_priority=priority,
            )
            result = self._scheduler.evaluate(inp)
            return {
                "decision": result.decision.value,
                "reason": result.reason,
                "metrics": {
                    "outage_probability": outage_probability,
                    "cpu_percent": metrics["cpu_percent"],
                    "memory_percent": metrics["memory_percent"],
                    "electricity_cost": metrics["electricity_cost"],
                    "carbon_intensity": metrics["carbon_intensity"],
                    "job_priority": self._job_priority,
                },
            }
        except Exception as e:
            logger.warning("Scheduler evaluation failed: %s — continuing with state machine only", e)
            return {
                "decision": "UNKNOWN",
                "reason": [f"Scheduler error: {e}"],
                "metrics": {},
            }

    def _execute_action(self, action: str):
        if action == "checkpoint_now":
            result = interfaces.checkpoint_now()
            self._checkpoint_done = result
            return result
        if action == "pause_pipeline":
            result = interfaces.pause_pipeline()
            self._checkpoint_done = None  # reset ready for the next risk cycle
            return result
        if action == "resume_from_last":
            result = interfaces.resume_from_last()
            self._resume_done = result
            return result
        if action == "resume_pipeline":
            return interfaces.resume_pipeline()
        if action == "clear_all":
            self._resume_done = None
            return True
        if action in ("notify_warning", "clear_warning"):
            # Purely informational - Member 5's dashboard/alert bot subscribes
            # to the emitted event itself rather than a separate call here.
            return True
        logger.warning("Unknown action requested: %s", action)
        return None

    def _emit_event(self, event: dict):
        line = json.dumps(event)
        logger.info(line)
        try:
            with open(config.EVENT_LOG_PATH, "a") as f:
                f.write(line + "\n")
        except OSError as e:
            logger.error("Could not write to event log %s: %s", config.EVENT_LOG_PATH, e)

    def run_forever(self, poll_interval: Optional[int] = None):
        """Blocking background loop using APScheduler, as recommended by the
        team task doc. Ctrl+C to stop cleanly.
        """
        from apscheduler.schedulers.blocking import BlockingScheduler

        interval = poll_interval or config.POLL_INTERVAL_SECONDS
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.poll_once, "interval", seconds=interval,
            next_run_time=datetime.now(),  # fire immediately, then every `interval`s
        )
        logger.info("Orchestrator starting - polling every %ss (region=%s)", interval, self.region)
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Orchestrator stopped.")
