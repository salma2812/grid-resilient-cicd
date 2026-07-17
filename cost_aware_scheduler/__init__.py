"""
Cost-Aware Scheduler Module
============================
Sits between the Prediction Engine and the Core Orchestrator in the
Grid-Resilient CI/CD architecture. Evaluates outage probability,
system resource utilisation, electricity cost, carbon intensity,
and job priority to decide whether a pipeline should RUN_NOW, be
DELAYED, CHECKPOINTED, or PAUSED.

Architecture flow:
    Prediction Engine → Cost-Aware Scheduler → Core Orchestrator
"""

from .models import JobPriority, SchedulerDecision, SchedulerInput  # noqa: F401
from .scheduler import CostAwareScheduler  # noqa: F401

__all__ = [
    "CostAwareScheduler",
    "SchedulerDecision",
    "SchedulerInput",
    "JobPriority",
]
