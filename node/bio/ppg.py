"""Pure PPG signal processing: finger check, heart rate, approximate SpO2 (fs = 100 Hz).

Called once per second on the last 8 s of IR and red samples. On the Pi this shares
the CPU with MediaPipe, so it does one sosfiltfilt per channel and nothing else heavy.
"""

from functools import lru_cache

import numpy as np
from scipy.signal import butter, find_peaks, sosfiltfilt

FS = 100
BAND_HZ = (0.7, 3.5)
MIN_INTERVAL_S = 0.33   # 180 bpm
MAX_INTERVAL_S = 1.5    # 40 bpm
MIN_INTERVALS = 4
MAX_CV = 0.25
SPO2_MIN, SPO2_MAX = 80, 100


@lru_cache(maxsize=4)
def _sos(fs: int):
    return butter(2, list(BAND_HZ), btype="band", fs=fs, output="sos")


def bandpass(x, fs: int = FS) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    return sosfiltfilt(_sos(fs), x - x.mean())


def detect_peaks(x_bp, fs: int = FS) -> np.ndarray:
    x_bp = np.asarray(x_bp, dtype=float)
    sd = float(np.std(x_bp))
    if sd == 0.0:
        return np.array([], dtype=int)
    peaks, _ = find_peaks(x_bp, distance=int(round(MIN_INTERVAL_S * fs)), prominence=0.4 * sd)
    return peaks


def _hr_from_bandpassed(ir_bp, fs):
    peaks = detect_peaks(ir_bp, fs)
    intervals = np.diff(peaks) / fs
    intervals = intervals[(intervals >= MIN_INTERVAL_S) & (intervals <= MAX_INTERVAL_S)]
    if len(intervals) < MIN_INTERVALS:
        return None, None
    cv = float(np.std(intervals) / np.mean(intervals))
    if cv > MAX_CV:
        return None, cv
    return int(round(60.0 / float(np.median(intervals)))), cv


def heart_rate(ir, fs: int = FS) -> tuple[int | None, float | None]:
    """(hr, cv): hr is None with too few beats or irregular intervals (cv > 0.25)."""
    return _hr_from_bandpassed(bandpass(ir, fs), fs)


def spo2_ratio(ir, red, ir_bp=None, red_bp=None, fs: int = FS) -> float:
    """R = (AC_red / DC_red) / (AC_ir / DC_ir); AC = std of band-passed, DC = mean of raw."""
    ir, red = np.asarray(ir, dtype=float), np.asarray(red, dtype=float)
    ir_bp = bandpass(ir, fs) if ir_bp is None else ir_bp
    red_bp = bandpass(red, fs) if red_bp is None else red_bp
    ac_ir, dc_ir = float(np.std(ir_bp)), float(np.mean(ir))
    ac_red, dc_red = float(np.std(red_bp)), float(np.mean(red))
    if min(ac_ir, dc_ir, dc_red) <= 0:
        raise ValueError("signal has no AC or DC component")
    return (ac_red / dc_red) / (ac_ir / dc_ir)


def spo2_from_ratio(r: float) -> int:
    """Common uncalibrated approximation: 110 - 25 R, clipped to 80..100 (approximate SpO2)."""
    return int(np.clip(round(110.0 - 25.0 * r), SPO2_MIN, SPO2_MAX))


def median_recent(values, n: int = 5) -> int | None:
    """Median of the last n valid values (used to smooth SpO2)."""
    valid = [v for v in values if v is not None][-n:]
    return int(round(float(np.median(valid)))) if valid else None


def analyse(ir, red, fs: int = FS, params: dict | None = None) -> dict:
    """{"hr", "spo2", "finger", "quality"} for one analysis window (SpO2 not yet smoothed)."""
    params = params or {}
    ir, red = np.asarray(ir, dtype=float), np.asarray(red, dtype=float)
    finger = bool(len(ir) and float(ir.mean()) > float(params.get("finger_ir_min", 0)))
    out = {"hr": None, "spo2": None, "finger": finger, "quality": 0.0}
    if not finger or len(ir) < MIN_INTERVALS * MAX_INTERVAL_S * fs / 2:
        return out
    ir_bp = bandpass(ir, fs)
    hr, cv = _hr_from_bandpassed(ir_bp, fs)
    if hr is None:
        return out
    out["hr"] = hr
    out["quality"] = float(min(1.0, max(0.0, 1.0 - cv / MAX_CV)))
    try:
        out["spo2"] = spo2_from_ratio(spo2_ratio(ir, red, ir_bp=ir_bp, red_bp=bandpass(red, fs), fs=fs))
    except ValueError:
        out["spo2"] = None
    return out
