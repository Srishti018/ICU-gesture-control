"""Load windows CSVs and apply the fixed exclusions of plan §12.1 (laptop only, uses pandas)."""

import json
from pathlib import Path

import pandas as pd

from ml.schema import FEATURES, WINDOW_COLUMNS


class DataFormatError(Exception):
    """A windows file is unreadable or doesn't have the expected columns."""


def load_windows(folder) -> pd.DataFrame:
    folder = Path(folder)
    files = sorted(folder.glob("*_windows.csv"))
    if not files:
        raise DataFormatError(f"no *_windows.csv files in {folder}")
    frames = []
    gesture_files = 0
    for f in files:
        try:
            df = pd.read_csv(f)
        except Exception as e:
            raise DataFormatError(f"{f.name}: cannot read ({e})") from e
        missing = [c for c in WINDOW_COLUMNS if c not in df.columns]
        if missing:
            raise DataFormatError(f"{f.name}: missing columns {missing}")
        has_gesture = "gesture" in df.columns
        gesture_files += has_gesture
        df = df[WINDOW_COLUMNS + (["gesture"] if has_gesture else [])].copy()
        df["trial_id"] = f.name[: -len("_windows.csv")]
        frames.append(df)
    if 0 < gesture_files < len(files):
        raise DataFormatError(f"{folder}: mixes gesture-only files (with a 'gesture' column) and fusion files; "
                              "keep them in separate folders")
    data = pd.concat(frames, ignore_index=True)
    for col in FEATURES + ["hr", "baseline_hr", "hand_present", "finger", "bio_quality", "window_idx", "discarded"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data["discarded"] = data["discarded"].fillna(0).astype(int)
    data["person"] = data["person"].astype(str)
    data.attrs["synthetic_vision"] = _any_synthetic_vision(folder)
    return data


def _any_synthetic_vision(folder: Path) -> bool:
    for meta in folder.glob("*_meta.json"):
        try:
            if json.loads(meta.read_text(encoding="utf-8")).get("vision") == "synthetic":
                return True
        except (OSError, ValueError):
            continue
    return False


def is_gesture_only(data: pd.DataFrame) -> bool:
    """Files from the gesture-only protocol (--bio none): label is gesture / no_gesture, no bio."""
    return "gesture" in data.columns


def apply_exclusions(data: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """The only data removed: first window of each trial, discarded trials, missing hr_delta/spo2
    (the last one not for gesture-only data, which has no bio by design)."""
    first = data["window_idx"] == 0
    discarded = data["discarded"] == 1
    base = data[~first & ~discarded]
    if is_gesture_only(data):
        missing_bio = pd.Series(False, index=base.index)
    else:
        missing_bio = base["hr_delta"].isna() | base["spo2"].isna()
    kept = base[~missing_bio].copy()
    counts = {
        "first_window": int(first.sum()),
        "discarded_trials": int(data.loc[discarded, "trial_id"].nunique()),
        "discarded_windows": int((discarded & ~first).sum()),
        "missing_bio": int(missing_bio.sum()),
        "missing_bio_by_scenario": {str(k): int(v) for k, v in base[missing_bio].groupby("scenario").size().items()},
        "kept": int(len(kept)),
    }
    return kept, counts


DRY_RUN_PERSON = "PTEST"


def is_synthetic(data: pd.DataFrame) -> bool:
    """Synthetic or dry-run data (ml.synth, PTEST, or recorded with the stand-in vision)."""
    if (data["bio_mode"].astype(str) == "synthetic").any() or (data["person"] == DRY_RUN_PERSON).any():
        return True
    return bool(data.attrs.get("synthetic_vision"))
