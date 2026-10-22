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

| Topic | Decision | Why |
| --- | --- | --- |
| MediaPipe API | **Tasks `HandLandmarker`**, VIDEO mode, 320×240 inference; model `~/icu-data/models/hand_landmarker.task` (float16). `node/vision/hands.py` falls back to `mp.solutions.hands` (`model_complexity=0`) automatically if the Tasks API is unavailable. | The laptop's MediaPipe 1.1.1 has no `mp.solutions` (removed in 1.x). The Pi may get a different wheel, hence the fallback. |
| NumPy | `node/requirements.txt` pins `numpy<2` only on `aarch64` (Pi); the laptop keeps NumPy 2.x | The laptop `.venv` is shared with the ML stack (SciPy 1.18, pandas 3, scikit-learn 1.9), which needs NumPy 2. MediaPipe 1.1.1 works with NumPy 2. |
| OpenCV | `opencv-python-headless` (ours) + `opencv-contrib-python` (pulled in by MediaPipe) both installed; `cv2` 5.0 imports fine | No `imshow` is used anywhere outside `node/tools/`. |
| Camera | USB webcam via OpenCV V4L2, MJPG, 640×480, buffer 1 | Laptop: HP Wide Vision HD (`/dev/video0`). |
| Tremor | Index fingertip (8) **relative to the wrist (0)**, divided by the hand size (wrist→middle MCP) per frame; per 3-s window `tremor = (std(x) + std(y)) / 2` over hand frames; ≥ 5 hand frames, else 0 | The prototype's wrist-relative, size-normalised fingertip (whole-hand movement and camera distance don't count as tremor), combined as the plan's §8.2 formula. It is tremor **amplitude**, not frequency. |
| OLED line 3 | `Bio: REPLAY rest` / `Bio: REPLAY exertion` / `Bio: LIVE` | The plan's `Model bio: REPLAY exertion` is 26 characters; a 128-px OLED shows 21 in the default font. |
| Hardware lock | `node/hwlock.py`: `HARDWARE BUSY: <name> (pid N) is using the camera/sensors`, exit code 3 | Role B's `node/bio/hwlock_compat.py` now uses this module automatically. |
| Laptop demo scripts | No tmux on the laptop: `run_demo.sh` opens a terminal window titled "ICU node"; `stop_node.sh` sends SIGTERM (same as `q`); `kill_node.sh` sends SIGKILL | Lets the laptop run as `bed1` if the Pi fails. Scripts match only the real `python -m node.main` process. |

## Calibration

To be filled in Phase 1 (laptop calibration; re-check on the Pi).

## Performance

| Where | Camera | fps | Inference | API | Temperature |
| --- | --- | --- | --- | --- | --- |
| Laptop (22 Oct) | HP Wide Vision HD, 640×480 MJPG | 10.0 | 31.6 ms (320×240) | Tasks | 47 °C |
| Pi 3B+ | — | hardware day | — | — | — |
