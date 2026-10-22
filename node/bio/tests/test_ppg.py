from pathlib import Path

import numpy as np
import pytest

from node.bio import ppg

FS = 100
REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLES = REPO_ROOT / "ml" / "data" / "sensor_samples"
PARAMS = {"finger_ir_min": 20000}


def synth_ppg(bpm, seconds=8.0, dc=40000.0, amp=400.0, noise=20.0, seed=0, ac_dc_ratio=None):
    """DC + A sin(2 pi f t) + 0.3 A sin(4 pi f t + 0.5) + noise."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * FS)) / FS
    f = bpm / 60.0
    if ac_dc_ratio is not None:
        amp = ac_dc_ratio * dc
    return dc + amp * np.sin(2 * np.pi * f * t) + 0.3 * amp * np.sin(4 * np.pi * f * t + 0.5) \
        + rng.normal(0, noise, len(t))


def jittered_ppg(seconds=8.0, seed=3, mean_interval=0.8, rel_sd=0.4):
    """Pulse train with random beat-to-beat intervals (cv about 0.4)."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * FS)) / FS
    beats, x = [], 0.2
    while x < seconds:
        beats.append(x)
        x += float(np.clip(rng.normal(mean_interval, rel_sd * mean_interval), 0.34, 1.45))
    sig = sum(np.exp(-((t - b) ** 2) / (2 * 0.06 ** 2)) for b in beats)
    return 40000 + 400 * sig + rng.normal(0, 5, len(t))


@pytest.mark.parametrize("bpm", [60, 90, 120])
def test_heart_rate_within_2_bpm(bpm):
    hr, cv = ppg.heart_rate(synth_ppg(bpm), FS)
    assert hr is not None and abs(hr - bpm) <= 2, (hr, cv)
    assert cv < 0.05


def test_flat_signal_has_no_hr():
    flat = np.full(800, 40000.0) + np.random.default_rng(1).normal(0, 2, 800)
    hr, _ = ppg.heart_rate(flat, FS)
    assert hr is None


def test_no_finger_below_threshold():
    ir = synth_ppg(72, dc=1000.0, amp=10.0)
    out = ppg.analyse(ir, ir * 0.9, FS, PARAMS)
    assert out == {"hr": None, "spo2": None, "finger": False, "quality": 0.0}


def test_irregular_intervals_rejected():
    sig = jittered_ppg()
    hr, cv = ppg.heart_rate(sig, FS)
    assert hr is None
    assert cv is not None and cv > 0.25


def test_spo2_from_ratio():
    assert ppg.spo2_from_ratio(0.5) == 98
    assert ppg.spo2_from_ratio(0.0) == 100   # clipped at 100
    assert ppg.spo2_from_ratio(2.0) == 80    # clipped at 80
    assert ppg.spo2_from_ratio(1.0) == 85


def test_spo2_ratio_recovers_known_r():
    ir = synth_ppg(75, dc=40000, ac_dc_ratio=0.01, noise=0, seed=0)
    # R = 0.006 / 0.01 = 0.6 -> 110 - 15 = 95 (chosen away from a .5 rounding boundary)
    red = synth_ppg(75, dc=30000, ac_dc_ratio=0.006, noise=0, seed=0)
    r = ppg.spo2_ratio(ir, red)
    assert abs(r - 0.6) < 0.01
    out = ppg.analyse(ir, red, FS, PARAMS)
    assert out["finger"] and abs(out["hr"] - 75) <= 2
    assert out["spo2"] == 95
    assert 0.9 <= out["quality"] <= 1.0


def test_median_recent():
    assert ppg.median_recent([None, 95, 97, None, 99, 98, 96, 90], n=5) == 97
    assert ppg.median_recent([None, None]) is None


@pytest.mark.skipif(not list(SAMPLES.glob("sensor_rest_*.csv")), reason="no recorded sensor samples yet (Phase 3-4 on the Pi)")
def test_recorded_rest_file_gives_hr_most_seconds():
    import csv
    path = sorted(SAMPLES.glob("sensor_rest_*.csv"))[0]
    with path.open() as fh:
        rows = list(csv.DictReader(fh))
    ir = np.array([float(r["ir"]) for r in rows])
    red = np.array([float(r["red"]) for r in rows])
    seconds = range(8, len(ir) // FS)
    hrs = [ppg.analyse(ir[(s - 8) * FS:s * FS], red[(s - 8) * FS:s * FS], FS, {"finger_ir_min": 0})["hr"]
           for s in seconds]
    print(f"{path.name}: HR per second {hrs}")
    assert sum(h is not None for h in hrs) > 0.6 * len(hrs)
