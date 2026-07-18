"""
Member 3 — Checkpointing & Resume Module (starter skeleton)
=============================================================
This already speaks the exact HTTP contract Member 2's Orchestrator expects
(see MEMBER3_INTERFACE_SPEC.md). Everything marked TODO is where you plug in
your real training workload - the wiring/API around it is done.

Run:
    pip install fastapi uvicorn torch
    uvicorn app:app --port 8001

Then tell Member 2 (Aya) to set these two env vars before running the
Orchestrator, and the whole chain is live:
    CHECKPOINT_SERVICE_URL=http://localhost:8001/checkpoint
    RESUME_SERVICE_URL=http://localhost:8001/resume
"""

import os
import pickle
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI

try:
    import torch  # type: ignore
except Exception:  # pragma: no cover - exercised in lightweight environments
    torch = None

torch: Any

app = FastAPI(title="Checkpointing & Resume Module")

BASE_DIR = Path(__file__).resolve().parent
CHECKPOINT_PATH = str(BASE_DIR / "checkpoint.pt")

# ---------------------------------------------------------------------------
# Member 3 workload: lightweight training, checkpoint, resume.
# Replace this with the real task-specific model and dataset if needed.
# ---------------------------------------------------------------------------
state = {
    "epoch": 0,
    "step": 0,
    "running": True,
    "paused": False,
    "loss": None,
    "training_start_time": time.time(),
    "last_checkpoint_time": None,
    "work_saved_seconds": 0.0,
}

work_lock = threading.Lock()
pause_event = threading.Event()
pause_event.set()

model: Any = None
optimizer: Any = None
loss_fn: Any = None
train_loader: Any = None
train_iterator: Any = None

if torch is not None:
    from torch import nn
    from torch.utils.data import DataLoader, Dataset

    class SyntheticDataset(Dataset):
        def __init__(self, num_samples: int = 512, input_size: int = 10):
            self.num_samples = num_samples
            self.input_size = input_size
            self.data = torch.randn(num_samples, input_size)
            self.targets = self.data.sum(dim=1, keepdim=True) + 0.1 * torch.randn(num_samples, 1)

        def __len__(self):
            return self.num_samples

        def __getitem__(self, idx):
            return self.data[idx], self.targets[idx]

    class RegressionModel(nn.Module):
        def __init__(self, input_size: int = 10, hidden_size: int = 32):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(input_size, hidden_size),
                nn.ReLU(),
                nn.Linear(hidden_size, 1),
            )

        def forward(self, x):
            return self.net(x)

    model = RegressionModel()
    optimizer = torch.optim.SGD(model.parameters(), lr=1e-2, momentum=0.9)
    loss_fn = nn.MSELoss()
    train_loader = DataLoader(SyntheticDataset(), batch_size=32, shuffle=True)
    train_iterator = iter(train_loader)

    def _get_next_batch():
        global train_iterator
        try:
            batch = next(train_iterator)
        except StopIteration:
            state["epoch"] += 1
            train_iterator = iter(train_loader)
            batch = next(train_iterator)
        return batch

    def _training_step():
        inputs, targets = _get_next_batch()
        optimizer.zero_grad()
        predictions = model(inputs)
        loss = loss_fn(predictions, targets)
        loss.backward()
        optimizer.step()
        state["step"] += 1
        state["loss"] = float(loss.detach().item())
else:
    class ToyModel:
        def __init__(self):
            self.weights = [0.0, 0.0, 0.0]
            self.bias = 0.0

        def state_dict(self):
            return {"weights": list(self.weights), "bias": self.bias}

        def load_state_dict(self, state):
            self.weights = list(state.get("weights", self.weights))
            self.bias = state.get("bias", self.bias)

    class ToyOptimizer:
        def __init__(self, model):
            self.model = model
            self.lr = 0.01
            self.step = 0

        def zero_grad(self):
            pass

        def state_dict(self):
            return {"lr": self.lr, "step": self.step}

        def load_state_dict(self, state):
            self.lr = state.get("lr", self.lr)
            self.step = state.get("step", self.step)

    model = ToyModel()
    optimizer = ToyOptimizer(model)

    def _training_step():
        time.sleep(1)
        state["epoch"] += 1
        state["step"] += 1
        state["loss"] = 0.0


def _training_loop():
    while state["running"]:
        pause_event.wait()
        if not state["running"]:
            break
        with work_lock:
            _training_step()
        time.sleep(0.1)


threading.Thread(target=_training_loop, daemon=True).start()
# --- END TODO -----------------------------------------------------------


def _build_checkpoint_payload():
    payload = {
        "epoch": state["epoch"],
        "checkpoint_time": state["last_checkpoint_time"],
        "work_saved_seconds": state["work_saved_seconds"],
    }
    if torch is not None:
        payload.update(
            {
                "model_state": model.state_dict(),
                "optimizer_state": optimizer.state_dict(),
            }
        )
    else:
        payload.update(
            {
                "model_state": model.state_dict(),
                "optimizer_state": optimizer.state_dict(),
            }
        )
    return payload


def checkpoint_now():
    return checkpoint()


def resume_from_last():
    return resume()


@app.post("/checkpoint")
def checkpoint():
    """Called by the Orchestrator's checkpoint_now() the moment risk crosses
    the checkpoint threshold. MUST return {"done": true} once the state is
    safely written to disk - the Orchestrator waits for this before moving
    from Checkpointing -> Paused.
    """
    try:
        checkpoint_dir = os.path.dirname(CHECKPOINT_PATH)
        if checkpoint_dir:
            os.makedirs(checkpoint_dir, exist_ok=True)
        checkpoint_time = time.time()
        state["last_checkpoint_time"] = checkpoint_time
        state["work_saved_seconds"] = checkpoint_time - state["training_start_time"]
        with open(CHECKPOINT_PATH, "wb") as handle:
            pickle.dump(_build_checkpoint_payload(), handle)
        return {
            "done": True,
            "epoch_saved": state["epoch"],
            "checkpoint_path": CHECKPOINT_PATH,
            "checkpoint_time": checkpoint_time,
            "work_saved_seconds": state["work_saved_seconds"],
        }
    except Exception as exc:
        return {"done": False, "error": str(exc)}


@app.post("/resume")
def resume():
    """Called by the Orchestrator's resume_from_last() once risk clears.
    MUST return {"done": true} once training/processing can safely continue -
    the Orchestrator waits for this before moving from Resuming -> Normal.
    """
    try:
        with open(CHECKPOINT_PATH, "rb") as handle:
            ckpt = pickle.load(handle)
        model.load_state_dict(ckpt["model_state"])
        optimizer.load_state_dict(ckpt["optimizer_state"])
        state["epoch"] = ckpt["epoch"]
        state["training_start_time"] = time.time()
        state["last_checkpoint_time"] = ckpt.get("checkpoint_time")
        state["work_saved_seconds"] = ckpt.get("work_saved_seconds", 0.0)
        return {
            "done": True,
            "resumed_epoch": state["epoch"],
            "checkpoint_path": CHECKPOINT_PATH,
            "checkpoint_time": state["last_checkpoint_time"],
            "work_saved_seconds": state["work_saved_seconds"],
        }
    except FileNotFoundError:
        return {"done": False, "error": "no checkpoint found yet"}
    except Exception as exc:
        return {"done": False, "error": str(exc)}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "current_epoch": state["epoch"],
        "current_step": state["step"],
        "current_loss": state["loss"],
    }
