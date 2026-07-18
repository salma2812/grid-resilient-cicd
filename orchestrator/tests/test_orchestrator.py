"""
Test suite for Member 2 (Core Orchestrator).

Covers:
 - every state transition described in the task doc
 - the hysteresis "dead band" that prevents flapping
 - a randomized stress test with rapid, noisy risk changes (per the team's
   own Day 6-7 plan: "Stress-test with rapid simulated risk changes to make
   sure states don't get stuck")
"""

import random

import pytest

from orchestrator.state_machine import State, Thresholds, decide
from orchestrator.core import Orchestrator
from orchestrator import interfaces


@pytest.fixture
def thresholds():
    return Thresholds(warning_threshold=0.40, checkpoint_threshold=0.70, recovery_threshold=0.25)


# ---------------------------------------------------------------------------
# state_machine.decide() - pure function unit tests
# ---------------------------------------------------------------------------

def test_normal_stays_normal_when_risk_low(thresholds):
    d = decide(State.NORMAL, 0.10, thresholds)
    assert d.next_state == State.NORMAL
    assert d.actions == []


def test_normal_to_warning(thresholds):
    d = decide(State.NORMAL, 0.45, thresholds)
    assert d.next_state == State.WARNING
    assert d.actions == ["notify_warning"]


def test_normal_escalates_straight_to_checkpointing_on_high_risk(thresholds):
    d = decide(State.NORMAL, 0.85, thresholds)
    assert d.next_state == State.CHECKPOINTING
    assert d.actions == ["checkpoint_now"]


def test_warning_holds_in_hysteresis_band(thresholds):
    # between recovery_threshold (0.25) and warning_threshold (0.40): must hold
    d = decide(State.WARNING, 0.30, thresholds)
    assert d.next_state == State.WARNING
    assert d.actions == []


def test_warning_recovers_to_normal_below_recovery_threshold(thresholds):
    d = decide(State.WARNING, 0.20, thresholds)
    assert d.next_state == State.NORMAL
    assert d.actions == ["clear_warning"]


def test_warning_escalates_to_checkpointing(thresholds):
    d = decide(State.WARNING, 0.75, thresholds)
    assert d.next_state == State.CHECKPOINTING
    assert d.actions == ["checkpoint_now"]


def test_checkpointing_waits_without_confirmation(thresholds):
    d = decide(State.CHECKPOINTING, 0.90, thresholds, checkpoint_done=None)
    assert d.next_state == State.CHECKPOINTING
    assert d.actions == []

    d2 = decide(State.CHECKPOINTING, 0.90, thresholds, checkpoint_done=False)
    assert d2.next_state == State.CHECKPOINTING


def test_checkpointing_to_paused_on_confirmation(thresholds):
    d = decide(State.CHECKPOINTING, 0.90, thresholds, checkpoint_done=True)
    assert d.next_state == State.PAUSED
    assert d.actions == ["pause_pipeline"]


def test_paused_holds_while_risk_elevated(thresholds):
    d = decide(State.PAUSED, 0.50, thresholds)
    assert d.next_state == State.PAUSED
    assert d.actions == []


def test_paused_to_resuming_on_recovery(thresholds):
    d = decide(State.PAUSED, 0.10, thresholds)
    assert d.next_state == State.RESUMING
    assert d.actions == ["resume_from_last", "resume_pipeline"]


def test_resuming_waits_without_confirmation(thresholds):
    d = decide(State.RESUMING, 0.10, thresholds, resume_done=False)
    assert d.next_state == State.RESUMING


def test_resuming_to_normal_on_confirmation(thresholds):
    d = decide(State.RESUMING, 0.10, thresholds, resume_done=True)
    assert d.next_state == State.NORMAL
    assert d.actions == ["clear_all"]


def test_invalid_thresholds_raise():
    with pytest.raises(ValueError):
        Thresholds(warning_threshold=0.30, checkpoint_threshold=0.70, recovery_threshold=0.50)


# ---------------------------------------------------------------------------
# Hysteresis actually prevents flapping (quantitative, not just one sample)
# ---------------------------------------------------------------------------

def test_hysteresis_prevents_flapping_under_oscillation(thresholds):
    """Oscillate probability just above/below the warning line, entirely
    inside the recovery<->warning dead band once Warning has been entered.
    A naive single-threshold machine would flap every single step; ours
    should transition into WARNING once and then hold steady.
    """
    state = State.NORMAL
    transitions = 0
    # first push it into WARNING
    d = decide(state, 0.45, thresholds)
    state = d.next_state
    transitions += 1
    assert state == State.WARNING

    # now oscillate within the dead band (0.25 - 0.40) 200 times
    for i in range(200):
        prob = 0.30 if i % 2 == 0 else 0.35
        d = decide(state, prob, thresholds)
        if d.next_state != state:
            transitions += 1
        state = d.next_state

    assert state == State.WARNING
    assert transitions == 1, f"Expected exactly 1 transition (into Warning), got {transitions} - hysteresis failed"


# ---------------------------------------------------------------------------
# Orchestrator-level stress test with rapid, noisy, random risk changes
# ---------------------------------------------------------------------------

@pytest.fixture
def fast_orchestrator(monkeypatch):
    """An Orchestrator wired to instant mock actions (no time.sleep, no
    network) so the stress test can run thousands of ticks quickly."""
    monkeypatch.setattr(interfaces, "checkpoint_now", lambda: True)
    monkeypatch.setattr(interfaces, "resume_from_last", lambda: True)
    monkeypatch.setattr(interfaces, "pause_pipeline", lambda: True)
    monkeypatch.setattr(interfaces, "resume_pipeline", lambda: True)
    return Orchestrator()


def test_stress_rapid_random_risk_changes_never_crashes_or_gets_stuck(fast_orchestrator):
    """This is the notebook's own Day 6-7 requirement: 'stress-test with
    rapid simulated risk changes to make sure states don't get stuck.'
    """
    rng = random.Random(1234)
    valid_states = {s for s in State}

    for _ in range(5000):
        prob = rng.random()  # fully random 0-1 every tick, worst case churn
        event = fast_orchestrator.poll_once(probability=prob)
        assert State(event["new_state"]) in valid_states

    # Now feed a long calm tail (risk = 0). With confirmations mocked instant,
    # the machine MUST be able to fully unwind back to Normal - i.e. it must
    # not be able to get permanently stuck in any of the transient states.
    for _ in range(50):
        event = fast_orchestrator.poll_once(probability=0.0)

    assert fast_orchestrator.state == State.NORMAL, (
        f"Orchestrator got stuck in {fast_orchestrator.state} after a long calm period - "
        "this would mean a real outage recovery could be missed forever."
    )


def test_stress_rapid_alternating_extreme_risk(fast_orchestrator):
    """Alternate between 0.0 and 1.0 every single tick - the most violent
    input we could realistically be asked to handle."""
    rng_pattern = [0.0, 1.0] * 500
    for prob in rng_pattern:
        event = fast_orchestrator.poll_once(probability=prob)
        assert event["new_state"] in {s.value for s in State}

    # settle
    for _ in range(50):
        fast_orchestrator.poll_once(probability=0.0)
    assert fast_orchestrator.state == State.NORMAL


def test_mock_prediction_engine_fallback_used_when_unreachable():
    """get_current_probability() must never raise, even with no Member 1
    server running - it should fall back to the mock generator."""
    prob = interfaces.get_current_probability("Zone_A")
    assert 0.0 <= prob <= 1.0
