# Member 2 — Core Orchestrator

The decision-making brain of Grid-Resilient CI/CD. Polls Member 1's outage
probability, decides Normal/Warning/Checkpointing/Paused/Resuming, triggers
Member 3 (checkpoint/resume) and Member 4 (pipeline pause/resume), and emits
a structured JSON event on every tick for Member 5's dashboard/alerts.

## Quick start

```bash
pip install -r requirements.txt
pytest tests/ -v          # 17 tests, incl. the 5000-tick stress test
python demo.py             # scripted walk through every state (no other member's code needed)
python demo.py --live      # real polling loop; auto-detects Member 1's API if it's running
```

## Project layout

```
orchestrator/
  state_machine.py   # pure decide() function + the 5 states + hysteresis thresholds
  config.py          # ALL tunable values (thresholds, poll interval, service URLs)
  interfaces.py       # calls to Member 1/3/4 - each falls back to a safe mock
  core.py             # Orchestrator class: ties it together + structured logging + APScheduler loop
  logging_setup.py
tests/
  test_orchestrator.py  # unit tests per transition + hysteresis + stress test
demo.py                  # standalone scripted + live demo
```

## How the state machine works

| State | Meaning | Leaves when |
|---|---|---|
| **Normal** | no elevated risk | probability ≥ `warning_threshold` (0.40) → Warning, or ≥ `checkpoint_threshold` (0.70) → straight to Checkpointing |
| **Warning** | elevated risk, watching | probability ≥ 0.70 → Checkpointing, or < `recovery_threshold` (0.25) → back to Normal |
| **Checkpointing** | `checkpoint_now()` fired, waiting for Member 3 to confirm | confirmed → Paused |
| **Paused** | job/deployment safely paused | probability < 0.25 → Resuming |
| **Resuming** | `resume_from_last()` fired, waiting for Member 3 to confirm | confirmed → Normal |

**Why two different thresholds for entering vs. leaving Warning (0.40 vs
0.25)?** This is a hysteresis "dead band." Without it, a probability
hovering right at 0.40 would flap the state back and forth every single
poll — which would spam Member 5's alerts and could rapid-fire
checkpoint/pause calls at Member 3/4. `tests/test_orchestrator.py::test_hysteresis_prevents_flapping_under_oscillation`
proves this quantitatively (200 oscillating ticks → exactly 1 real transition).

## Integration status (update as teammates hand off their pieces)

| Dependency | Status | How to wire in the real thing |
|---|---|---|
| Member 1 (Prediction Engine) | mocked by default | set `PREDICTION_ENGINE_URL` env var, or just run Member 1's `app.py` on `localhost:8000` — auto-detected |
| Member 3 (Checkpoint/Resume) | mocked by default | set `CHECKPOINT_SERVICE_URL` / `RESUME_SERVICE_URL` env vars |
| Member 4 (CI/CD) | mocked by default | set `GITHUB_REPO` + `GITHUB_TOKEN` env vars |
| Member 5 (Dashboard/Alerts) | reads `orchestrator_events.jsonl` (one JSON object per line) | no action needed - just tail/parse this file, or point Streamlit at it |

## Known limitations (documented honestly, same policy as Member 1)

- `checkpoint_now()` / `resume_from_last()` currently confirm instantly in
  the mock. Once Member 3's real service is wired in, if it's genuinely
  slow, the Orchestrator will correctly sit in Checkpointing/Resuming across
  multiple polls until confirmed — this is tested
  (`test_checkpointing_waits_without_confirmation`) but hasn't been proven
  against a *real* slow service yet, only the instant mock.
- Thresholds (0.40 / 0.70 / 0.25) are reasonable starting points, not
  calibrated against Member 1's actual precision/recall numbers yet. Once
  Member 1's real probabilities are flowing in, revisit these together -
  Member 1's threshold-tuning table (Section 5c) is a good reference point.
- GitHub dispatch auth (`GITHUB_TOKEN`) needs a real token with `repo` scope
  from whoever owns the hackathon repo - not generated here.
