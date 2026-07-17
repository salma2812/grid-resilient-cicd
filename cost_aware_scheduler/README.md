# 💰 Cost-Aware Scheduler

Optimises CI/CD pipeline execution timing based on outage probability, resource utilisation, electricity cost, carbon intensity, and job priority.

## How it works

The scheduler uses a **severity-ordered rule chain** to evaluate 6 input metrics and output one of 4 decisions:

```
   ┌─────────────────────────────────────────────────────────┐
   │                  SchedulerInput                         │
   │  outage_probability, cpu, memory, electricity,          │
   │  carbon_intensity, job_priority                         │
   └───────────────────────┬─────────────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │  Extreme outage (≥90%)? │──── YES ──▶ PAUSE
              └────────────┬────────────┘
                           │ NO
              ┌────────────▼────────────┐
              │  High outage (≥65%)?    │
              │  + High/Med priority?   │──── YES ──▶ CHECKPOINT
              └────────────┬────────────┘
                           │ NO (or Low priority → DELAY)
              ┌────────────▼────────────┐
              │  Moderate outage (≥40%) │
              │  OR high CPU/Memory     │
              │  OR high cost + carbon  │──── YES ──▶ DELAY
              └────────────┬────────────┘
                           │ NO
                           ▼
                        RUN_NOW
```

Every decision includes a **reasoning chain** — a list of human-readable explanations for why each factor contributed to the final decision.

## Quick start

```bash
# Install
pip install -r requirements.txt

# Run tests (13/13)
python -m pytest tests/ -v

# Start API
uvicorn api:app --port 8002
```

## API

### `POST /schedule`

Evaluate a scheduling decision with custom inputs:

```bash
curl -X POST http://localhost:8002/schedule \
  -H "Content-Type: application/json" \
  -d '{
    "outage_probability": 0.72,
    "cpu_percent": 88,
    "memory_percent": 81,
    "electricity_cost": 0.34,
    "carbon_intensity": 420,
    "job_priority": "High"
  }'
```

Response:
```json
{
  "decision": "CHECKPOINT",
  "reason": [
    "High outage probability (72%)",
    "Job priority is High",
    "CPU utilisation is elevated (88%)",
    "Memory utilisation is elevated (81%)",
    "Electricity cost: $0.34/kWh",
    "Carbon intensity: 420 gCO₂/kWh"
  ],
  "input": { ... }
}
```

### `GET /schedule`

Auto-evaluate using simulated metrics + live prediction engine data:

```bash
curl http://localhost:8002/schedule
```

### `GET /metrics`

Current simulated resource/cost metrics:

```bash
curl http://localhost:8002/metrics
```

### `GET /health`

```bash
curl http://localhost:8002/health
```

## Decision Matrix

| Condition | Decision |
|-----------|----------|
| Extreme outage risk (≥90%) | **PAUSE** |
| High outage (≥65%) + High/Medium priority | **CHECKPOINT** |
| High outage (≥65%) + Low priority | **DELAY** |
| Moderate outage (≥40%) | **DELAY** |
| Very high CPU (≥90%) or Memory (≥90%) | **DELAY** |
| High electricity (≥$0.25/kWh) + High carbon (≥400 gCO₂/kWh) | **DELAY** |
| High priority overrides 1 minor delay signal | **RUN_NOW** |
| All conditions favourable | **RUN_NOW** |

## Files

| File | Purpose |
|------|---------|
| `models.py` | `JobPriority`, `SchedulerAction`, `SchedulerInput`, `SchedulerDecision` |
| `scheduler.py` | `CostAwareScheduler` class — the core rule-chain decision engine |
| `simulators.py` | Time-varying sinusoidal simulators for CPU, memory, electricity, carbon |
| `api.py` | FastAPI service with CORS, auto-integration with Prediction Engine |
| `tests/test_scheduler.py` | 13 unit tests covering every path in the decision matrix |

## Integration with the Orchestrator

The scheduler is called automatically by `member2_orchestrator/orchestrator/core.py` on every polling cycle:

1. Orchestrator fetches outage probability from Prediction Engine
2. Orchestrator calls `_evaluate_scheduler()` with the probability + simulated metrics
3. Scheduler returns decision + reasoning chain
4. Both the state machine decision AND scheduler result are emitted in the event JSON
5. Dashboard reads the `scheduler` field to render the Cost-Aware Scheduler panel

If the scheduler fails for any reason, the orchestrator continues with its state machine alone — graceful degradation.

## Simulators

The simulators produce realistic day-cycle patterns using sinusoidal functions with noise:

- **CPU**: Peaks mid-day (50–80%), low overnight (15–30%)
- **Memory**: Follows CPU with slight lag and offset
- **Electricity cost**: Peaks during afternoon demand ($0.08–$0.35/kWh)
- **Carbon intensity**: Inverse of solar generation (80–500 gCO₂/kWh)

All simulators are stateless pure functions keyed on `time.time()`, making them deterministic for a given timestamp.
