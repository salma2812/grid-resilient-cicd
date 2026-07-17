"""
Data models for the Cost-Aware Scheduler.

Follows the Single Responsibility Principle — this module only defines
the input/output contracts; no business logic lives here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class JobPriority(str, Enum):
    """Tri-level priority classification for queued pipeline jobs."""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class SchedulerAction(str, Enum):
    """The four possible scheduling decisions."""
    RUN_NOW = "RUN_NOW"
    DELAY = "DELAY"
    CHECKPOINT = "CHECKPOINT"
    PAUSE = "PAUSE"


@dataclass
class SchedulerInput:
    """
    All inputs the scheduler evaluates before making a decision.

    Attributes
    ----------
    outage_probability : float
        Probability of an outage (0.0 – 1.0) from the Prediction Engine.
    cpu_percent : float
        Current CPU utilisation (0 – 100).
    memory_percent : float
        Current memory utilisation (0 – 100).
    electricity_cost : float
        Estimated electricity cost in $/kWh.
    carbon_intensity : float
        Estimated carbon intensity in gCO₂/kWh.
    job_priority : JobPriority
        Priority classification of the pipeline job.
    """
    outage_probability: float
    cpu_percent: float
    memory_percent: float
    electricity_cost: float
    carbon_intensity: float
    job_priority: JobPriority = JobPriority.MEDIUM


@dataclass
class SchedulerDecision:
    """
    The scheduler's output: a decision plus the reasoning chain.

    Attributes
    ----------
    decision : SchedulerAction
        One of RUN_NOW, DELAY, CHECKPOINT, PAUSE.
    reason : list[str]
        Human-readable list explaining each factor that influenced the decision.
    input_snapshot : SchedulerInput | None
        Optional: the input state at the time the decision was made.
    """
    decision: SchedulerAction
    reason: List[str] = field(default_factory=list)
    input_snapshot: SchedulerInput | None = None

    def to_dict(self) -> dict:
        """Serialise to the JSON-friendly format specified in the requirements."""
        return {
            "decision": self.decision.value,
            "reason": list(self.reason),
        }
