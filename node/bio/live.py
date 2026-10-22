"""LiveBio: reads the MAX30100 in a background thread and reports HR/SpO2 per 3-s window."""

from collections import deque
import csv
import json
import logging
from pathlib import Path
import threading
import time

import numpy as np

from node.bio import BioSource, BioUnavailable, empty_window, ppg

log = logging.getLogger("bio.live")

PARAMS_PATH = Path(__file__).resolve().parent / "sensor_params.json"
FS = ppg.FS
BUFFER_SECONDS = 8
POLL_S = 0.04
HISTORY_SECONDS = 120
WINDOW_SECONDS = 3
MAX_CONSECUTIVE_ERRORS = 10


def load_params(params=None) -> dict:
    if isinstance(params, dict):
        return params
    path = Path(params) if params else PARAMS_PATH
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


class LiveBio(BioSource):
    kind = "live"

    def __init__(self, settings=None, take_lock: bool = False, params=None, driver=None, log_path=None):
        self.settings = settings
        self.take_lock = take_lock
        self.params = load_params(params)
        self._driver = driver
        self.log_path = Path(log_path) if log_path else None
        self._n = BUFFER_SECONDS * FS
        self._ir = np.zeros(self._n)
        self._red = np.zeros(self._n)
        self._filled = 0
        self._history = deque(maxlen=HISTORY_SECONDS)
        self._spo2_recent = deque(maxlen=5)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._hw_lock = None
        self._baseline = None
        self.errors = 0
        self.failed = False

    # --- lifecycle --------------------------------------------------------------

    def start(self) -> None:
        if self.take_lock:
            from node.bio.hwlock_compat import HardwareBusy, HardwareLock
            lock = HardwareLock("bio.live")
            try:
                lock.__enter__()
            except HardwareBusy as e:
                raise BioUnavailable(str(e)) from e
            self._hw_lock = lock
        try:
            if self._driver is None:
                from node.bio.max30100 import MAX30100
                self._driver = MAX30100(red_code=int(self.params["red_code"]), ir_code=int(self.params["ir_code"]))
            self._driver.open()
            self._driver.configure()
        except Exception as e:
            self._release_lock()
            raise BioUnavailable(f"MAX30100 unavailable: {e}") from e
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="bio-live", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        try:
            if self._driver:
                self._driver.shutdown()
                self._driver.close()
        except Exception as e:  # never raise on shutdown
            log.warning("sensor shutdown failed: %s", e)
        self._release_lock()

    def _release_lock(self):
        if self._hw_lock:
            self._hw_lock.__exit__(None, None, None)
            self._hw_lock = None

    # --- worker thread ----------------------------------------------------------

    def _append(self, samples):
        if not samples:
            return
        arr = np.asarray(samples, dtype=float)
        k = min(len(arr), self._n)
        arr = arr[-k:]
        self._ir = np.roll(self._ir, -k)
        self._red = np.roll(self._red, -k)
        self._ir[-k:] = arr[:, 0]
        self._red[-k:] = arr[:, 1]
        self._filled = min(self._n, self._filled + k)

    def _analyse_now(self, t: float):
        ir, red = self._ir[-self._filled:], self._red[-self._filled:]
        rec = ppg.analyse(ir, red, FS, self.params) if self._filled else \
            {"hr": None, "spo2": None, "finger": False, "quality": 0.0}
        self._spo2_recent.append(rec["spo2"])
        rec["spo2"] = ppg.median_recent(self._spo2_recent) if rec["hr"] is not None else None
        rec["t"] = t
        with self._lock:
            self._history.append(rec)
        if self.log_path:
            self._log(rec)

    def _log(self, rec):
        new = not self.log_path.exists()
        with self.log_path.open("a", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["t_s", "hr", "spo2", "finger", "quality"])
            w.writerow([round(rec["t"], 2), rec["hr"], rec["spo2"], int(rec["finger"]), round(rec["quality"], 3)])

    def _run(self):
        next_analysis = time.monotonic() + 1.0
        while not self._stop.is_set():
            try:
                self._append(self._driver.read_samples())
                self.errors = 0
            except Exception as e:
                self.errors += 1
                log.warning("I2C read failed (%d in a row): %s", self.errors, e)
                if self.errors >= MAX_CONSECUTIVE_ERRORS:
                    self.failed = True
                    log.error("MAX30100 failed after %d consecutive errors; live values are now None", self.errors)
                    return
            now = time.monotonic()
            if now >= next_analysis:
                try:
                    self._analyse_now(now)
                except Exception as e:
                    log.warning("analysis failed: %s", e)
                next_analysis += 1.0
            self._stop.wait(POLL_S)

    # --- readings -----------------------------------------------------------------

    def records(self, seconds: float) -> list[dict]:
        cutoff = time.monotonic() - seconds
        with self._lock:
            return [r for r in self._history if r["t"] >= cutoff]

    def calibrate_baseline(self, seconds: int = 60) -> int:
        start = time.monotonic()
        self._stop.wait(seconds)
        with self._lock:
            recs = [r for r in self._history if r["t"] >= start]
        valid = [r["hr"] for r in recs if r["hr"] is not None]
        if not recs or len(valid) < 0.5 * max(len(recs), seconds):
            raise BioUnavailable(f"baseline failed: only {len(valid)} valid seconds out of {seconds}")
        self._baseline = int(round(float(np.median(valid))))
        return self._baseline

    def set_baseline(self, hr: int) -> None:
        self._baseline = int(hr)

    def baseline_hr(self) -> int | None:
        return self._baseline

    def window(self) -> dict:
        if self.failed:
            return empty_window("live")
        recs = self.records(WINDOW_SECONDS)
        if not recs:
            return empty_window("live")
        hrs = [r["hr"] for r in recs if r["hr"] is not None]
        spo2s = [r["spo2"] for r in recs if r["spo2"] is not None]
        hr = int(round(float(np.mean(hrs)))) if hrs else None
        spo2 = int(round(float(np.mean(spo2s)))) if spo2s else None
        return {
            "hr": hr,
            "spo2": spo2,
            "hr_delta": hr - self._baseline if hr is not None and self._baseline is not None else None,
            "finger": any(r["finger"] for r in recs),
            "source": "live",
            "quality": round(float(np.mean([r["quality"] for r in recs])), 3),
        }
