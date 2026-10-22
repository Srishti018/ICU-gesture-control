# Role A notes — node and vision

Working notes for the node (`node/`, except `node/bio/`). Plan: `docs/ROLE_A_IMPLEMENTATION_PLAN.md`; top-level instructions: `docs/FINISH_PLAN.md` (it takes precedence).

## Answers to 5.2

One person now builds everything on the repo owner's laptop (FINISH_PLAN). Known facts:
- Teammate's MediaPipe code: imported into `node/prototype/` (commit `fddd303`). It is laptop code (webcam window).
- Pi: Raspberry Pi 3 Model B+ (1 GB RAM), Raspberry Pi OS Lite 64-bit planned. No working SD card yet, so the Pi isn't set up.
- Camera, OLED model, buzzer type, power supply, GitHub repo URL: not known yet. Recorded as hardware-day questions in `docs/HARDWARE_DAY.md` (Phase 6).
- Laptop: Ubuntu, Python 3.12.3 (MediaPipe supports it). **No webcam detected on 22 Oct 17:30** (no `/dev/video*`, nothing in `lsusb`).

## Teammate code audit (`node/prototype/`)

| Aspect | What the prototype does | Verdict |
| --- | --- | --- |
| MediaPipe API | `mp.solutions.hands.Hands(max_num_hands=1, min_detection_confidence=0.6, min_tracking_confidence=0.6)`; mirrors the frame; converts BGR→RGB | **Reusable** as the `mp.solutions` path in `node/vision/hands.py` (the Tasks API is the plan's first choice) |
| Camera API | `cv2.VideoCapture(0)` | Reusable idea; `camera.py` adds V4L2, MJPG, buffer size 1, a 30-failure error |
| Gesture score | Per finger: (wrist→tip) / (wrist→PIP) distance ratio, ramped 1.0–1.3; thumb tip vs IP relative to the pinky base; mean of 5 | **Idea reusable, formula replaced** by the plan's §8.2 (PIP angle, thumb ratio, and an upright factor the prototype lacks: a flat open palm must not score high) |
| Tremor | Index fingertip relative to the wrist, normalised by hand size (wrist→middle MCP), over a rolling 2.5-s window; `sqrt(var x + var y)` | **Reusable**: the wrist-relative, size-normalised fingertip is kept. Computed per 3-s window with the plan's combination `(std x + std y) / 2` (recorded in Phase 1) |
| Train/test split | `GroupShuffleSplit` by trial | Right idea (no leakage between rows of one trial); the project uses leave-one-person-out (`ml/train.py`) |
| `collect.py` | Keyboard scenarios, 0.5-s rows | **Superseded** by `ml/collect/` |
| `train.py` | Binary Logistic Regression → `fusion_model.pkl` | **Superseded** by `ml/train.py` + `ml/fusion_runtime.py` |

Wrong for the final product (not carried over):
- `samples.csv` has **simulated** `hr_delta`/`spo2` (`fake_vitals()` random numbers) and **binary** labels, so it can never be used for results.
- `train.py` **relabels and drops trials after looking at the data** (`fix = [...]`, dropped trial IDs, `gesture_conf < 0.75` rows removed), which the data honesty rules forbid.
- `cv2.imshow` windows won't work on a headless Pi; the final code has no `imshow` outside `node/tools/`.
- Rows every 0.5 s instead of 3-s windows.
- A `.pkl` model instead of the NumPy JSON runtime.
- Labels {calm, gesture_only, hr_only → 0; combined → 1} don't match the project's three classes.

## Pi state

Not set up (no SD card). See `docs/HARDWARE_DAY.md`.

## Decisions

To be filled in Phase 1 (MediaPipe API, camera, OLED driver).

## Calibration

To be filled in Phase 1 (laptop calibration; re-check on the Pi).

## Performance

To be filled in Phase 1 (laptop fps) and on hardware day (Pi fps).
