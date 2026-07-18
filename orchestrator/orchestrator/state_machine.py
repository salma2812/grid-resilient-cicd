"""
Core Orchestrator - State Machine
=================================
Member 2 track: Grid-Resilient CI/CD (DevOpsDays Cairo 2026 Hackathon)

This module defines the 5 system states and the pure decision function that
maps (current_state, outage_probability, time) -> (next_state, actions).

Design choices (explained so the team / judges can follow the logic):

1. Two risk thresholds, not one -> hysteresis.
   `checkpoint_threshold` (high) escalates straight to CHECKPOINTING even
   from NORMAL - if risk is already very high we don't waste time sitting
   in WARNING first.
   `warning_threshold` (medium) escalates NORMAL -> WARNING.
   `recovery_threshold` (low, LOWER than warning_threshold) is required to
   fully stand down back to NORMAL. Having recovery_threshold < warning_threshold
   creates a "dead band" between the two: once we've raised the alarm, small
   fluctuations around the warning line don't cause rapid Warning<->Normal
   flapping. This is the fix validated by the stress test in
   tests/test_orchestrator.py.

2. CHECKPOINTING and RESUMING are "action in progress" states, not purely
   risk-driven. They only advance once the corresponding action is confirmed
   done (via `checkpoint_done` / `resume_done` flags passed in), so a slow or
   failed checkpoint can't be silently skipped just because risk fluctuated.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class State(str, Enum):
    NORMAL = "Normal"
    WARNING = "Warning"
    CHECKPOINTING = "Checkpointing"
    PAUSED = "Paused"
    RESUMING = "Resuming"


@dataclass
class Thresholds:
    warning_threshold: float = 0.40     # Normal -> Warning
    checkpoint_threshold: float = 0.70  # (Normal|Warning) -> Checkpointing
    recovery_threshold: float = 0.25    # (Warning|Paused) -> stand down
    # recovery_threshold MUST be < warning_threshold, or there's no hysteresis
    # band and the state machine can flap. Enforced in __post_init__.

    def __post_init__(self):
        if not (self.recovery_threshold < self.warning_threshold <= self.checkpoint_threshold):
            raise ValueError(
                "Thresholds must satisfy: recovery_threshold < warning_threshold "
                f"<= checkpoint_threshold. Got recovery={self.recovery_threshold}, "
                f"warning={self.warning_threshold}, checkpoint={self.checkpoint_threshold}"
            )


@dataclass
class Decision:
    next_state: State
    actions: list = field(default_factory=list)
    reason: str = ""


def decide(
    current_state: State,
    probability: float,
    thresholds: Thresholds,
    checkpoint_done: Optional[bool] = None,
    resume_done: Optional[bool] = None,
) -> Decision:
    """Pure decision function - no I/O, no side effects, fully unit-testable.

    Parameters
    ----------
    current_state: the state the orchestrator is currently in
    probability: latest outage probability from Member 1's Prediction Engine (0-1)
    thresholds: the Thresholds config in effect
    checkpoint_done: only relevant while in CHECKPOINTING - has Member 3's
        checkpoint_now() call been confirmed complete?
    resume_done: only relevant while in RESUMING - has Member 3's
        resume_from_last() call been confirmed complete?

    Returns
    -------
    Decision(next_state, actions, reason)
    """
    t = thresholds

    if current_state == State.NORMAL:
        if probability >= t.checkpoint_threshold:
            return Decision(State.CHECKPOINTING, ["checkpoint_now"],
                             f"probability {probability:.2f} >= checkpoint_threshold {t.checkpoint_threshold}")
        if probability >= t.warning_threshold:
            return Decision(State.WARNING, ["notify_warning"],
                             f"probability {probability:.2f} >= warning_threshold {t.warning_threshold}")
        return Decision(State.NORMAL, [], "probability below warning_threshold")

    if current_state == State.WARNING:
        if probability >= t.checkpoint_threshold:
            return Decision(State.CHECKPOINTING, ["checkpoint_now"],
                             f"probability {probability:.2f} >= checkpoint_threshold {t.checkpoint_threshold}")
        if probability < t.recovery_threshold:
            return Decision(State.NORMAL, ["clear_warning"],
                             f"probability {probability:.2f} < recovery_threshold {t.recovery_threshold}")
        return Decision(State.WARNING, [], "probability in hysteresis band, holding Warning")

    if current_state == State.CHECKPOINTING:
        if checkpoint_done:
            return Decision(State.PAUSED, ["pause_pipeline"],
                             "checkpoint confirmed complete")
        return Decision(State.CHECKPOINTING, [], "waiting for checkpoint confirmation")

    if current_state == State.PAUSED:
        if probability < t.recovery_threshold:
            return Decision(State.RESUMING, ["resume_from_last", "resume_pipeline"],
                             f"probability {probability:.2f} < recovery_threshold {t.recovery_threshold}, safe to resume")
        return Decision(State.PAUSED, [], "risk still elevated, staying paused")

    if current_state == State.RESUMING:
        if resume_done:
            return Decision(State.NORMAL, ["clear_all"],
                             "resume confirmed complete")
        return Decision(State.RESUMING, [], "waiting for resume confirmation")

    raise ValueError(f"Unhandled state: {current_state}")
