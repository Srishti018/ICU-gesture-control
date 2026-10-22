# Role A prototype (reference only)

This is Role A's first prototype (October 2026), imported from https://github.com/Srishti018/ICU-gesture-control (commit `9e987e9`). It is kept here for reference. Nothing in the project imports or runs it.

## Files

| File | What it is |
| --- | --- |
| `hand_landmarks.py` | Webcam + MediaPipe hand tracking demo (draws landmarks, prints wrist and index-tip positions) |
| `test_webcam.py` | Checks that the camera opens |
| `collect.py` | Prototype data collector (keyboard-driven scenarios, writes `samples.csv`) |
| `train.py` | Prototype binary Logistic Regression training |
| `samples.csv` | Data recorded with `collect.py` |

## `samples.csv` must never be used as project results

- `hr_delta` and `spo2` are **simulated**: random numbers from `fake_vitals()` in `collect.py`, not from a sensor.
- Labels are **binary** (0/1), not the project's three classes (`routine`, `urgent`, `critical`).

Don't use it for training, evaluation, charts or the report.

## What replaces what

- `collect.py` and `train.py` are **superseded** by `ml/collect/` (guided session runner) and `ml/train.py` (3-class model, leave-one-person-out evaluation).
- The gesture and tremor code in `collect.py` (`gesture_confidence()`, `tremor_value()`) is the **starting point for `node/vision/`**.
