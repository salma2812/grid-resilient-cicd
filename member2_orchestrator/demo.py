"""
Standalone demo for Member 2 (Core Orchestrator).

Run this to see the state machine react to a scripted risk scenario, printing
every transition. Works completely standalone - no other member's code needs
to exist yet (Member 3/4 calls are mocked, Member 1 predictions are mocked
if app.py isn't running on localhost:8000).

Usage:
    python demo.py            # scripted scenario (deterministic, good for judges)
    python demo.py --live     # real polling loop hitting Member 1's API / mocks
"""

import sys
import time

from orchestrator.core import Orchestrator
from orchestrator.logging_setup import setup_logging

setup_logging()


def run_scripted_scenario():
    """A hand-picked probability sequence that walks through every state:
    Normal -> Warning -> Checkpointing -> Paused -> Resuming -> Normal,
    plus a spell in the hysteresis dead band to prove no flapping.
    """
    orch = Orchestrator()
    scenario = [
        (0.10, "calm morning"),
        (0.15, "still calm"),
        (0.45, "risk climbing -> should enter WARNING"),
        (0.32, "dips into dead band -> should HOLD Warning, not bounce to Normal"),
        (0.38, "still in dead band -> should HOLD Warning"),
        (0.80, "spike! -> jumps to CHECKPOINTING and fires checkpoint_now()"),
        (0.80, "checkpoint confirmed (mock is instant here) -> moves to PAUSED"),
        (0.60, "still risky -> stays PAUSED"),
        (0.55, "still risky -> stays PAUSED"),
        (0.20, "risk clears -> enters RESUMING and fires resume_from_last()"),
        (0.15, "resume confirmed (mock is instant here) -> returns to NORMAL"),
        (0.10, "back to calm"),
    ]

    print("\n=== Grid-Resilient CI/CD — Orchestrator scripted demo ===\n")
    for probability, note in scenario:
        event = orch.poll_once(probability=probability)
        print(f"[{note}]")
        print(f"  probability={probability:.2f}  "
              f"{event['previous_state']} -> {event['new_state']}  "
              f"({event['reason']})")
        if event["actions"]:
            print(f"  actions fired: {event['actions']} -> {event['action_results']}")
        print()
        time.sleep(0.3)

    print(f"Final state: {orch.state.value}")
    print(f"Full structured event log written to: orchestrator_events.jsonl")


def run_live_loop():
    orch = Orchestrator()
    print("Starting live polling loop (Ctrl+C to stop)...")
    print("Trying Member 1's API at http://localhost:8000/predict - "
          "falls back to mock risk if it's not running yet.\n")
    orch.run_forever()


if __name__ == "__main__":
    if "--live" in sys.argv:
        run_live_loop()
    else:
        run_scripted_scenario()
