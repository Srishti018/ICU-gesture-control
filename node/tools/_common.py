"""Shared helpers for node tools: logging, hardware lock, CPU temperature."""

import logging
from pathlib import Path
import subprocess
import sys

from node.hwlock import EXIT_BUSY, HardwareBusy, HardwareLock


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("absl").setLevel(logging.WARNING)


def run_locked(name: str, fn) -> int:
    """Run fn() holding the hardware lock; print the holder and exit 3 if it's busy."""
    try:
        with HardwareLock(name):
            return fn() or 0
    except HardwareBusy as e:
        print(f"{e}. Stop that program first (cat /tmp/icu-hw.lock).", file=sys.stderr)
        return EXIT_BUSY


def cpu_temp() -> str:
    try:
        out = subprocess.run(["vcgencmd", "measure_temp"], capture_output=True, text=True, timeout=3)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip().replace("temp=", "")
    except (OSError, subprocess.TimeoutExpired):
        pass
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*/temp")):
        try:
            return f"{int(zone.read_text()) / 1000:.1f}'C ({zone.parent.name})"
        except (OSError, ValueError):
            continue
    return "n/a"
