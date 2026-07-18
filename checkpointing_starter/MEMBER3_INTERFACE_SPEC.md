# Interface Spec — what Member 3 needs to build

Member 2's Orchestrator is already tested and waiting for these 2 endpoints.
Build `app.py` exposing exactly this (a working starter is in
`member3_skeleton/app.py` - just fill in the TODOs with your real training
workload):

## `POST /checkpoint`
Called the instant risk crosses the checkpoint threshold. Save whatever
state means "no work lost" for your workload (model weights, optimizer,
epoch/step - matches the task doc's PyTorch `.pt` file approach).

**Must return:** `{"done": true}` once the save is actually complete.
(`{"done": false}` if it failed - the Orchestrator will just keep waiting/retrying.)

## `POST /resume`
Called once risk clears. Reload your saved state and continue.

**Must return:** `{"done": true}` once processing can safely continue.

## That's the entire contract.
No request body needed for either endpoint (the Orchestrator sends none).
Any other fields you add to the response (`epoch_saved`, timestamps, etc.)
are ignored by the Orchestrator but fine to include for your own logging/demo.

## How to go live (2 steps, no code changes on Orchestrator side)

1. Run your service, e.g. `uvicorn app:app --port 8001`
2. Tell Aya to set these two env vars before running the Orchestrator:
   ```bash
   export CHECKPOINT_SERVICE_URL="http://localhost:8001/checkpoint"
   export RESUME_SERVICE_URL="http://localhost:8001/resume"
   ```
   That's it - `interfaces.py` switches from mock to your real service
   automatically the moment these are set.

## Already verified working (2026-07-13)
Ran a full 3-service test: Member 1's real `app.py` (port 8000) + a
test-double matching this exact contract (port 8001) + the real
Orchestrator. Forced a full risk cycle (0.85 -> checkpoint -> pause -> 0.10
-> resume -> normal) - every HTTP call fired correctly and a real checkpoint
file was written to disk and read back. The wiring works; only your
real training logic needs to go in.
