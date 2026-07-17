"""
CostAwareScheduler — the core decision engine.

Design principles:
  • Open/Closed: new factors can be added as additional rule methods without
    modifying existing rule logic.
  • Single Responsibility: this class only scores and decides; it never
    fetches data or triggers side effects.
  • Dependency Inversion: callers provide a SchedulerInput; the scheduler
    never reaches out to sensors or APIs itself.

Decision matrix (priority-ordered):
  1. PAUSE  — extreme outage risk (≥ 90%) regardless of priority.
  2. CHECKPOINT — high outage risk (≥ 65%) + High/Medium priority.
  3. DELAY  — moderate risk, or high resource pressure, or high cost/carbon.
  4. RUN_NOW — everything looks safe and efficient.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

from .models import JobPriority, SchedulerAction, SchedulerDecision, SchedulerInput

logger = logging.getLogger("cost_aware_scheduler")


@dataclass
class SchedulerThresholds:
    """Tunable thresholds — can be overridden via env-vars or config."""
    # Outage probability
    outage_extreme: float = 0.90
    outage_high: float = 0.65
    outage_moderate: float = 0.40

    # Resource utilisation
    cpu_critical: float = 90.0
    cpu_high: float = 75.0
    memory_critical: float = 90.0
    memory_high: float = 75.0

    # Electricity cost ($/kWh)
    electricity_high: float = 0.30
    electricity_moderate: float = 0.20

    # Carbon intensity (gCO₂/kWh)
    carbon_high: float = 400.0
    carbon_moderate: float = 250.0


class CostAwareScheduler:
    """
    Evaluates system state and returns a SchedulerDecision.

    Usage
    -----
    >>> scheduler = CostAwareScheduler()
    >>> inp = SchedulerInput(
    ...     outage_probability=0.82,
    ...     cpu_percent=45.0,
    ...     memory_percent=60.0,
    ...     electricity_cost=0.28,
    ...     carbon_intensity=310.0,
    ...     job_priority=JobPriority.LOW,
    ... )
    >>> result = scheduler.evaluate(inp)
    >>> print(result.to_dict())
    {'decision': 'DELAY', 'reason': ['High outage probability (82%)', ...]}
    """

    def __init__(self, thresholds: SchedulerThresholds | None = None):
        self.thresholds = thresholds or SchedulerThresholds()

    # ── Public API ──────────────────────────────────────────────────────────

    def evaluate(self, inp: SchedulerInput) -> SchedulerDecision:
        """Run all rules against the input and produce a decision."""
        reasons: List[str] = []
        t = self.thresholds

        # ── Collect signals ─────────────────────────────────────────────────
        outage_pct = round(inp.outage_probability * 100)

        # 1. Extreme outage → PAUSE immediately
        if inp.outage_probability >= t.outage_extreme:
            reasons.append(f"Extreme outage probability ({outage_pct}%)")
            self._add_resource_reasons(inp, reasons)
            return SchedulerDecision(
                decision=SchedulerAction.PAUSE,
                reason=reasons,
                input_snapshot=inp,
            )

        # 2. High outage + High/Medium priority → CHECKPOINT
        if inp.outage_probability >= t.outage_high:
            reasons.append(f"High outage probability ({outage_pct}%)")
            if inp.job_priority in (JobPriority.HIGH, JobPriority.MEDIUM):
                reasons.append(f"Job priority is {inp.job_priority.value}")
                self._add_resource_reasons(inp, reasons)
                return SchedulerDecision(
                    decision=SchedulerAction.CHECKPOINT,
                    reason=reasons,
                    input_snapshot=inp,
                )
            # High outage + Low priority → DELAY
            reasons.append(f"Job priority is {inp.job_priority.value}")
            self._add_resource_reasons(inp, reasons)
            return SchedulerDecision(
                decision=SchedulerAction.DELAY,
                reason=reasons,
                input_snapshot=inp,
            )

        # 3. Moderate outage risk
        if inp.outage_probability >= t.outage_moderate:
            reasons.append(f"Moderate outage probability ({outage_pct}%)")

        # 4. Resource pressure
        delay_signals = 0

        if inp.cpu_percent >= t.cpu_critical:
            reasons.append(f"Critical CPU utilisation ({inp.cpu_percent:.0f}%)")
            delay_signals += 2
        elif inp.cpu_percent >= t.cpu_high:
            reasons.append(f"High CPU utilisation ({inp.cpu_percent:.0f}%)")
            delay_signals += 1

        if inp.memory_percent >= t.memory_critical:
            reasons.append(f"Critical memory utilisation ({inp.memory_percent:.0f}%)")
            delay_signals += 2
        elif inp.memory_percent >= t.memory_high:
            reasons.append(f"High memory utilisation ({inp.memory_percent:.0f}%)")
            delay_signals += 1

        # 5. Cost & carbon
        if inp.electricity_cost >= t.electricity_high:
            reasons.append(f"Electricity cost is high (${inp.electricity_cost:.2f}/kWh)")
            delay_signals += 1
        elif inp.electricity_cost >= t.electricity_moderate:
            reasons.append(f"Electricity cost is moderate (${inp.electricity_cost:.2f}/kWh)")

        if inp.carbon_intensity >= t.carbon_high:
            reasons.append(f"Carbon intensity is high ({inp.carbon_intensity:.0f} gCO₂/kWh)")
            delay_signals += 1
        elif inp.carbon_intensity >= t.carbon_moderate:
            reasons.append(f"Carbon intensity is moderate ({inp.carbon_intensity:.0f} gCO₂/kWh)")

        # 6. Priority amplifies or dampens the signal
        if inp.job_priority == JobPriority.LOW:
            reasons.append(f"Job priority is {inp.job_priority.value}")
            delay_signals += 1
        elif inp.job_priority == JobPriority.HIGH:
            reasons.append(f"Job priority is {inp.job_priority.value}")
            delay_signals -= 1  # high-priority jobs are more tolerant

        # ── Decision ────────────────────────────────────────────────────────
        if delay_signals >= 2 or inp.outage_probability >= t.outage_moderate:
            if not reasons:
                reasons.append("Multiple delay signals triggered")
            return SchedulerDecision(
                decision=SchedulerAction.DELAY,
                reason=reasons,
                input_snapshot=inp,
            )

        if delay_signals == 1 and inp.job_priority != JobPriority.HIGH:
            if not reasons:
                reasons.append("Minor delay signal with non-high priority")
            return SchedulerDecision(
                decision=SchedulerAction.DELAY,
                reason=reasons,
                input_snapshot=inp,
            )

        # All clear
        if not reasons:
            reasons.append("All metrics within safe thresholds")
        reasons.append("Conditions are favourable — proceed immediately")
        return SchedulerDecision(
            decision=SchedulerAction.RUN_NOW,
            reason=reasons,
            input_snapshot=inp,
        )

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _add_resource_reasons(self, inp: SchedulerInput, reasons: List[str]):
        """Append resource-utilisation context to the reason chain."""
        t = self.thresholds
        if inp.cpu_percent >= t.cpu_high:
            reasons.append(f"CPU utilisation is elevated ({inp.cpu_percent:.0f}%)")
        if inp.memory_percent >= t.memory_high:
            reasons.append(f"Memory utilisation is elevated ({inp.memory_percent:.0f}%)")
        if inp.electricity_cost >= t.electricity_moderate:
            reasons.append(f"Electricity cost: ${inp.electricity_cost:.2f}/kWh")
        if inp.carbon_intensity >= t.carbon_moderate:
            reasons.append(f"Carbon intensity: {inp.carbon_intensity:.0f} gCO₂/kWh")
