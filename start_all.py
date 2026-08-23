import subprocess
import sys
import time
import os
import signal

# Fix Windows console UTF-8 output encoding issues
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

processes = []

def start_service(name, command, cwd):
    print(f"🚀 Starting {name}...")
    if isinstance(command, list):
        command = " ".join(f'"{arg}"' if " " in arg else arg for arg in command)
    p = subprocess.Popen(command, cwd=cwd, shell=True)
    processes.append((name, p))

def cleanup(sig=None, frame=None):
    print("\n🛑 Stopping all Grid-Resilient CI/CD services...")
    for name, p in processes:
        try:
            print(f"   Terminating {name} (PID {p.pid})...")
            p.terminate()
        except Exception:
            pass
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

def free_ports():
    print("🧹 Clearing lingering service processes on ports 8000, 8001, 8002, 5173...")
    current_pid = os.getpid()
    if sys.platform == "win32":
        try:
            output = subprocess.check_output("netstat -ano", shell=True).decode("utf-8", errors="ignore")
            target_ports = {":8000", ":8001", ":8002", ":5173", ":5174", ":5175"}
            pids_to_kill = set()
            for line in output.splitlines():
                if "LISTENING" in line:
                    for port in target_ports:
                        if port in line:
                            parts = line.strip().split()
                            if parts:
                                try:
                                    pid = int(parts[-1])
                                    if pid != current_pid and pid > 0:
                                        pids_to_kill.add(pid)
                                except ValueError:
                                    pass
            for pid in pids_to_kill:
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
        except Exception:
            pass
    time.sleep(2.5)

def main():
    root_dir = os.path.abspath(os.path.dirname(__file__))

    print("==================================================")
    print("⚡ Starting Grid-Resilient CI/CD Multi-Service Suite")
    print("==================================================\n")

    free_ports()

    # 1. Prediction Engine (Port 8000)
    start_service(
        "Prediction Engine (Port 8000)",
        [sys.executable, "-m", "uvicorn", "app:app", "--port", "8000"],
        os.path.join(root_dir, "prediction_engine")
    )
    time.sleep(1.5)

    # 2. Checkpoint Service (Port 8001)
    start_service(
        "Checkpoint Service (Port 8001)",
        [sys.executable, "-m", "uvicorn", "app:app", "--port", "8001"],
        os.path.join(root_dir, "checkpointing_starter")
    )
    time.sleep(1.5)

    # 3. Cost-Aware Scheduler (Port 8002)
    start_service(
        "Cost-Aware Scheduler (Port 8002)",
        [sys.executable, "-m", "uvicorn", "api:app", "--port", "8002"],
        os.path.join(root_dir, "cost_aware_scheduler")
    )
    time.sleep(1.5)

    # 4. Core Orchestrator Live Loop
    start_service(
        "Orchestrator Live Loop",
        [sys.executable, "demo.py", "--live"],
        os.path.join(root_dir, "orchestrator")
    )
    time.sleep(1.0)

    # 5. UI Dashboard (Port 5173)
    start_service(
        "UI Dashboard (Port 5173)",
        "npm run dev",
        os.path.join(root_dir, "ui")
    )

    print("\n✨ All services launched and running!")
    print("📌 Press Ctrl+C at any time to stop all services cleanly.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()

if __name__ == "__main__":
    main()
