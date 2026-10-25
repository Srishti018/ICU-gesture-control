"""Synthetic windows dataset for testing the pipeline ONLY.

Never write into ml/data/raw/, and never use these numbers in a result, chart or the report.
Rows are tagged bio_mode="synthetic" so the training script can refuse to publish them.

Usage: python -m ml.synth <out_dir> [--seed 0] [--gestures]   (--gestures: gesture-only protocol files)
"""

import argparse
import csv
from datetime import datetime, timedelta
from pathlib import Path
import random

from ml.schema import (GESTURE_SCENARIOS, GESTURE_WINDOW_COLUMNS, SCENARIOS, WINDOW_COLUMNS, is_exertion,
                       is_gesture, scenario_label, scenario_name)

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = (REPO_ROOT / "ml" / "data" / "raw").resolve()

PEOPLE = ["P1", "P2", "P3"]
TRIALS = 3
WINDOWS = 10
HARD_FRACTION = 0.05


def _refuse_raw(out_dir: Path) -> None:
    out = out_dir.resolve()
    if out == RAW_DIR or RAW_DIR in out.parents:
        raise ValueError("synthetic data must never be written into ml/data/raw/")


def _window(rng: random.Random, code: str, baseline: int, hard: bool) -> dict:
    gesture, exertion = is_gesture(code), is_exertion(code)
    if hard:
        # deliberately hard rows: the other side of the boundary for one feature
        if rng.random() < 0.5:
            gesture = not gesture
        else:
            exertion = not exertion
    gesture_conf = rng.uniform(0.85, 0.95) if gesture else rng.uniform(0.0, 0.25)
    gesture_conf = min(1.0, max(0.0, gesture_conf + rng.gauss(0, 0.03)))
    hr_delta = rng.randint(18, 30) if exertion else rng.randint(-3, 5)
    hr_delta += int(round(rng.gauss(0, 1.5)))
    spo2 = rng.randint(96, 99)
    tremor = rng.uniform(0.005, 0.05)
    hand_present = 1 if (gesture or rng.random() < 0.9) else 0
    n_frames = rng.randint(27, 33)
    return {
        "gesture_conf": round(gesture_conf, 3),
        "tremor": round(tremor, 3),
        "hand_present": hand_present,
        "n_frames": n_frames,
        "n_hand_frames": n_frames if hand_present else rng.randint(0, 5),
        "fps": round(n_frames / 3, 1),
        "hr": baseline + hr_delta,
        "spo2": spo2,
        "hr_delta": hr_delta,
        "finger": 1,
        "bio_quality": round(rng.uniform(0.7, 1.0), 2),
    }


def generate(out_dir, seed: int = 0) -> list[Path]:
    out_dir = Path(out_dir)
    _refuse_raw(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    start = datetime(2026, 10, 23, 8, 30, 0)
    paths = []
    for person in PEOPLE:
        baseline = rng.randint(65, 80)
        for code in SCENARIOS:
            for trial in range(1, TRIALS + 1):
                t0 = start + timedelta(minutes=len(paths))
                stem = f"{person}_{code}_T{trial}_{t0:%Y%m%d-%H%M%S}"
                path = out_dir / f"{stem}_windows.csv"
                with path.open("w", newline="", encoding="utf-8") as fh:
                    writer = csv.DictWriter(fh, fieldnames=WINDOW_COLUMNS)
                    writer.writeheader()
                    for w in range(WINDOWS):
                        row = _window(rng, code, baseline, rng.random() < HARD_FRACTION)
                        row.update({
                            "person": person, "scenario": code, "scenario_name": scenario_name(code),
                            "trial": trial, "label": scenario_label(code), "window_idx": w,
                            "ts": (t0 + timedelta(seconds=3 * (w + 1))).strftime("%Y-%m-%dT%H:%M:%S"),
                            "bio_mode": "synthetic", "baseline_hr": baseline,
                            "light": "dim" if code == "H1" else "normal",
                            "gesture_hand": "right", "discarded": 0,
                        })
                        writer.writerow(row)
                paths.append(path)
    return paths


def _gesture_window(rng: random.Random, code: str) -> dict:
    gesture = is_gesture(code)
    if rng.random() < HARD_FRACTION:
        gesture = not gesture
    if code == "N_NOHAND" and not gesture:
        hand = False
    else:
        hand = gesture or rng.random() < 0.9
    low = 0.6 if code == "G_WEAK" else 0.8
    conf = rng.uniform(low, 0.95) if gesture else rng.uniform(0.0, 0.35)
    shaky = code.endswith("SHAKY")
    n_frames = rng.randint(27, 33)
    return {
        "gesture_conf": round(conf if hand else 0.0, 3),
        "tremor": round(rng.uniform(0.03, 0.08) if shaky else rng.uniform(0.005, 0.03), 3),
        "hand_present": int(hand), "n_frames": n_frames, "n_hand_frames": n_frames if hand else 0,
        "fps": round(n_frames / 3, 1),
    }


def generate_gestures(out_dir, seed: int = 0, people=PEOPLE) -> list[Path]:
    """Synthetic gesture-only protocol files (same format as `ml.collect.session --bio none`)."""
    out_dir = Path(out_dir)
    _refuse_raw(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    start = datetime(2026, 10, 25, 20, 0, 0)
    paths = []
    for person in people:
        for code, (name, label, trials, light) in GESTURE_SCENARIOS.items():
            for trial in range(1, trials + 1):
                t0 = start + timedelta(minutes=len(paths))
                path = out_dir / f"{person}_{code}_T{trial}_{t0:%Y%m%d-%H%M%S}_windows.csv"
                with path.open("w", newline="", encoding="utf-8") as fh:
                    writer = csv.DictWriter(fh, fieldnames=GESTURE_WINDOW_COLUMNS)
                    writer.writeheader()
                    for w in range(WINDOWS):
                        row = _gesture_window(rng, code)
                        row.update({
                            "person": person, "scenario": code, "scenario_name": name, "trial": trial,
                            "label": label, "gesture": label, "window_idx": w,
                            "ts": (t0 + timedelta(seconds=3 * (w + 1))).strftime("%Y-%m-%dT%H:%M:%S"),
                            "bio_mode": "synthetic", "light": light, "gesture_hand": "right", "discarded": 0,
                        })
                        writer.writerow(row)
                paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out_dir")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--gestures", action="store_true", help="gesture-only protocol files")
    args = parser.parse_args()
    paths = (generate_gestures if args.gestures else generate)(args.out_dir, args.seed)
    print(f"wrote {len(paths)} synthetic trial files to {args.out_dir}")


if __name__ == "__main__":
    main()
