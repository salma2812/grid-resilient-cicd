@echo off
echo Starting Grid-Resilient CI/CD services...

start "Prediction Engine (8000)" cmd /k "cd /d %~dp0prediction_engine && python -m uvicorn app:app --port 8000"
start "Checkpoint Service (8001)" cmd /k "cd /d %~dp0checkpointing_starter && python -m uvicorn app:app --port 8001"
start "Cost-Aware Scheduler (8002)" cmd /k "cd /d %~dp0cost_aware_scheduler && python -m uvicorn api:app --port 8002"
start "Orchestrator" cmd /k "cd /d %~dp0orchestrator && python demo.py --live"
start "UI Dashboard (5173)" cmd /k "cd /d %~dp0ui && npm run dev"

echo All 5 services launched in separate windows!
