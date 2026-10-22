# Role B notes — biosignal sensor and ML model

Working notes for Role B (`node/bio/`, `ml/`). Plan: `docs/ROLE_B_IMPLEMENTATION_PLAN.md`.

## Answers to 5.2

Asked: not yet. The team doesn't have the Raspberry Pi yet (no SD card), so on 22 Oct 2026 the user asked to skip the Pi and hardware questions and do the laptop-only work first. All six questions are still open:

1. Pi set up by Role A (`ssh icu-pi` works)? — **pending (no Pi yet)**
2. Which MAX30100 board (colour, printed text, labelled pins)? — pending
3. Commercial fingertip oximeter available? — pending
4. How many participants; anyone to avoid exercise? — pending
5. Session Fri 08:30–11:00 (or Thu evening)? — pending
6. Soldering experience and iron available? — pending

## Pi readiness

22 Oct 2026: no Pi (no SD card). Role A's files are not in the repo yet: `node/hwlock.py`, `node/settings.py`, `node/vision/features.py` and `node/requirements.txt` are all missing.
Consequences for the laptop work:
- Hardware lock: `node/bio/hwlock_compat.py` uses Role A's `node.hwlock` when it exists, otherwise a local fallback with the same behaviour (exclusive non-blocking `flock` on `/tmp/icu-hw.lock`). Switch-over is automatic.
- Vision: the collector is built and dry-run with a local stand-in (`ml/collect/synthetic_vision.py`) that has the `VisionFeatureExtractor` interface from Appendix B.
- Pi packages needed by Role B (to ask Role A to include in `node/requirements.txt`): `numpy<2`, `scipy`, `smbus2`.

## Sensor checks

Not done (no Pi). Phase 2 (`i2cdetect`, part ID `0x11`) is waiting for the Pi.

## Tuning values

Not tuned. `node/bio/sensor_params.json` holds the plan's defaults (`red_code` 8, `ir_code` 15) and a provisional `finger_ir_min`, marked `"tuned": false`. Replace them with the results of `finger_threshold.py` and `led_tune.py` on the Pi.

## HR/SpO₂ validation

Not done (no Pi). `validate_hr.py` is written; the table goes here.

| Check | Sensor HR | Reference HR | Difference | Sensor SpO₂ | Reference SpO₂ |
| --- | --- | --- | --- | --- | --- |
| Rest 1 | | | | | |
| Rest 2 | | | | | |
| Rest 3 | | | | | |
| After exercise | | | | | |

## Decision (live or manual)

Not made yet (needs the §8.6 validation on the Pi). The plan's deadline for it is Thu 22 Oct, 20:00.

## Data collection log summary

Not started (needs the Pi, Role A's camera code and the team).

Collector laptop dry run, 22 Oct 2026 (Phase 6, §10.4): `python -m ml.collect.session --person PTEST --bio manual --vision synthetic --quick --seconds 6 --out <temp>`, using `--only S1,S3` and then `--only S5 --resume`.
- Every prompt works when answers are piped in, including note, redo (discarded in the meta and the windows CSV), exertion delay, recovery and resume.
- `validate_data` read all 10 trial files with no format errors. Exit 1 ("not enough data") is expected for a one-person dry run.
- The Pi dry run (real camera, `--only S1,S3 --seconds 9`) is still to do.

Collector notes:
- `--vision synthetic` uses a local stand-in for Role A's `VisionFeatureExtractor`. It only works with `--person PTEST` and an `--out` folder other than `~/icu-data/raw`.
- PTEST or stand-in-vision data is treated as synthetic, so `ml.train` refuses to write it into `ml/results/` or `ml/models/`.
- Hidden flags for dry runs only: `--seconds N`, `--quick` (short baseline, pauses, exercise and recovery), `--out`, `--vision`.

## Model notes

- The training pipeline is tested on **synthetic data only** (`ml/synth.py`). Synthetic data is for testing code and must never appear in a result, chart or the report.
- `ml/replay/*.json` are **synthetic placeholders** (`"source": "synthetic-placeholder"`) so Role A can integrate. They must be replaced with real recordings in Phase 8 before the demo.
