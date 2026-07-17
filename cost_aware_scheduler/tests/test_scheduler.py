"""
Unit tests for the CostAwareScheduler.

Covers the decision matrix:
  • Extreme outage → PAUSE
  • High outage + High priority → CHECKPOINT
  • High outage + Low priority → DELAY
  • Moderate outage → DELAY
  • Very high CPU → DELAY
  • Low risk + low cost → RUN_NOW
  • Low risk + High priority → RUN_NOW (overrides minor signals)
"""

import pytest

from cost_aware_scheduler.models import JobPriority, SchedulerAction, SchedulerInput
from cost_aware_scheduler.scheduler import CostAwareScheduler


@pytest.fixture
def scheduler():
    return CostAwareScheduler()


def _make_input(**overrides) -> SchedulerInput:
    """Helper to build SchedulerInput with safe defaults."""
    defaults = {
        "outage_probability": 0.10,
        "cpu_percent": 35.0,
        "memory_percent": 45.0,
        "electricity_cost": 0.10,
        "carbon_intensity": 180.0,
        "job_priority": JobPriority.MEDIUM,
    }
    defaults.update(overrides)
    return SchedulerInput(**defaults)


class TestSchedulerDecisions:
    """Core decision matrix tests."""

    def test_extreme_outage_pauses(self, scheduler):
        inp = _make_input(outage_probability=0.92, job_priority=JobPriority.HIGH)
        result = scheduler.evaluate(inp)
        assert result.decision == SchedulerAction.PAUSE
        assert any("Extreme" in r for r in result.reason)

    def test_high_outage_high_priority_checkpoints(self, scheduler):
        inp = _make_input(outage_probability=0.75, job_priority=JobPriority.HIGH)
        result = scheduler.evaluate(inp)
        assert result.decision == SchedulerAction.CHECKPOINT

    def test_high_outage_medium_priority_checkpoints(self, scheduler):
        inp = _make_input(outage_probability=0.70, job_priority=JobPriority.MEDIUM)
        result = scheduler.evaluate(inp)
        assert result.decision == SchedulerAction.CHECKPOINT

    def test_high_outage_low_priority_delays(self, scheduler):
        inp = _make_input(outage_probability=0.82, job_priority=JobPriority.LOW)
        result = scheduler.evaluate(inp)
        assert result.decision == SchedulerAction.DELAY
        assert any("Low" in r for r in result.reason)

    def test_moderate_outage_delays(self, scheduler):
        inp = _make_input(outage_probability=0.45)
        result = scheduler.evaluate(inp)
        assert result.decision == SchedulerAction.DELAY

    def test_very_high_cpu_delays(self, scheduler):
        inp = _make_input(cpu_percent=92.0, outage_probability=0.05)
        result = scheduler.evaluate(inp)
        assert result.decision == SchedulerAction.DELAY
        assert any("CPU" in r for r in result.reason)

    def test_low_risk_low_cost_runs_now(self, scheduler):
        inp = _make_input(
            outage_probability=0.05,
            cpu_percent=25.0,
            memory_percent=30.0,
            electricity_cost=0.08,
            carbon_intensity=150.0,
        )
        result = scheduler.evaluate(inp)
        assert result.decision == SchedulerAction.RUN_NOW

    def test_high_priority_overrides_minor_delay(self, scheduler):
        inp = _make_input(
            outage_probability=0.10,
            cpu_percent=78.0,  # high but not critical
            job_priority=JobPriority.HIGH,
        )
        result = scheduler.evaluate(inp)
        # HIGH priority subtracts from delay_signals, so 1-1=0 → RUN_NOW
        assert result.decision == SchedulerAction.RUN_NOW

    def test_high_electricity_and_carbon_delays(self, scheduler):
        inp = _make_input(
            electricity_cost=0.35,
            carbon_intensity=450.0,
            job_priority=JobPriority.MEDIUM,
        )
        result = scheduler.evaluate(inp)
        assert result.decision == SchedulerAction.DELAY

    def test_to_dict_format(self, scheduler):
        inp = _make_input(outage_probability=0.82, job_priority=JobPriority.LOW)
        result = scheduler.evaluate(inp)
        d = result.to_dict()
        assert "decision" in d
        assert "reason" in d
        assert isinstance(d["reason"], list)
        assert d["decision"] in ("RUN_NOW", "DELAY", "CHECKPOINT", "PAUSE")


class TestSchedulerReasonChain:
    """Verify that the reason chain captures multiple factors."""

    def test_multiple_reasons_collected(self, scheduler):
        inp = _make_input(
            outage_probability=0.50,
            cpu_percent=80.0,
            electricity_cost=0.32,
            carbon_intensity=420.0,
            job_priority=JobPriority.LOW,
        )
        result = scheduler.evaluate(inp)
        assert len(result.reason) >= 3

    def test_reason_always_non_empty(self, scheduler):
        inp = _make_input()
        result = scheduler.evaluate(inp)
        assert len(result.reason) >= 1

    def test_input_snapshot_preserved(self, scheduler):
        inp = _make_input(outage_probability=0.10)
        result = scheduler.evaluate(inp)
        assert result.input_snapshot is inp
