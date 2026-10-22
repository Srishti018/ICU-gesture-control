"""Shared helpers for the sensor tools (run on the Pi)."""

import json
from pathlib import Path
import sys
import time

import numpy as np

from node.bio.hwlock_compat import HardwareBusy, HardwareLock
from node.bio.live import PARAMS_PATH, load_params
from node.bio.max30100 import MAX30100, SensorError

DATA_DIR = Path.home() / "icu-data" / "raw"
POLL_S = 0.04


def data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def run_locked(name: str, fn) -> int:
    """Run fn() holding the hardware lock; print and exit 1 if it is busy (no retry loop)."""
    try:
        with HardwareLock(name):
            return fn() or 0
    except HardwareBusy as e:
        print(f"{e}. Stop that program first, then rerun.", file=sys.stderr)
        return 1
    except SensorError as e:
        print(f"Sensor error: {e}", file=sys.stderr)
        return 1


def open_sensor(params: dict | None = None) -> MAX30100:
    params = params or load_params()
    s = MAX30100(red_code=int(params["red_code"]), ir_code=int(params["ir_code"]))
    s.open()
    s.configure()
    return s


def collect(sensor: MAX30100, seconds: float) -> tuple[np.ndarray, np.ndarray]:
    """Poll the FIFO every 40 ms for `seconds`; returns (ir, red) arrays."""
    samples = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        samples += sensor.read_samples()
        time.sleep(POLL_S)
    samples += sensor.read_samples()
    arr = np.asarray(samples, dtype=float).reshape(-1, 2)
    return arr[:, 0], arr[:, 1]


def save_params(updates: dict) -> dict:
    params = load_params()
    params.update(updates)
    params["tuned"] = True
    params.pop("note", None)
    PARAMS_PATH.write_text(json.dumps(params, indent=2) + "\n", encoding="utf-8")
    return params


def prompt(text: str) -> str:
    return input(f"\n>>> {text}\n    (press Enter when ready) ")
