# Report notes — facts for updating the course report

Facts only, taken from the code and docs in this repository (Sun 25 Oct 2026). Each section says where to check the details. **Results are pending**: see the clearly marked section below.

---

## 1. Final architecture

```
 bed1: Raspberry Pi 3B+                         Laptop (Ubuntu)
 ┌───────────────────────────────┐              ┌───────────────────────────────────────────────┐
 │ Pi camera → MediaPipe hands   │              │ Mosquitto broker  :1883 MQTT, :9001 WebSockets │
 │  → gesture_conf, tremor       │   MQTT       │   auth, retain, Last Will                      │
 │ Vitals: BIDMC replay          │ ───────────▶ │ Flask server :5050 (MQTT logger + SQLite + API)│
 │  → hr_delta, spo2             │   :1883      │ React dashboard :5173 (MQTT over WS + REST)    │
 │ Fusion (LogReg, NumPy) → level│              └───────────────────────────────────────────────┘
 │ OLED + buzzer (local alarm)   │
 └───────────────────────────────┘    bed2: fake node (sim/fake_node.py), same contract
```

| Component | Role | Where |
| --- | --- | --- |
| Bed node (Pi 3B+) | Every 3 s it computes gesture and tremor from the camera, gets HR/SpO₂ from the replay, runs the fusion model and publishes the level. Local OLED and buzzer. | `node/` |
| Vision | MediaPipe Tasks `HandLandmarker` (VIDEO mode, 320×240 inference), with a fallback to `mp.solutions.hands` | `node/vision/` |
| Biosignals | Replay of real ICU vitals (BIDMC) in the demo. Live MAX30100 and manual sources exist in code. | `node/bio/`, `ml/replay/` |
| Fusion | Logistic regression exported to JSON and evaluated with NumPy on the Pi. Fixed rule as a fallback. | `ml/fusion_runtime.py`, `node/fusion_adapter.py` |
| Broker | Mosquitto 2.x on the laptop. Anonymous access disabled. | `broker/` |
| Server | Flask + SQLite. An MQTT logger thread stores alerts, acks and connection events. REST API: `/api/health`, `/api/alerts`, `/api/nodes`, `/api/stats`, `/api/events`. | `server/` |
| Dashboard | React (Vite) nurse-station UI: live tiles from MQTT, history and statistics from Flask, Acknowledge | `dashboard/` |
| Fake node | Imitates a bed node for tests and the demo (`bed2`) | `sim/fake_node.py` |

Dashboard screenshots for the report (in `dashboard/design/after/`):
- `04-one-critical-1366x768.png` (critical alert)
- `05-acknowledged-1366x768.png` (response time)
- `07-one-offline-1366x768.png` (Last Will)
- `09-statistics-tab-1366x768.png`

## 2. MQTT design

Source: `docs/contracts.md` (contract v1, fixed).

| Topic | QoS | Retain | When |
| --- | --- | --- | --- |
| `icu/{node}/status/routine` | 0 | no | every 3-s window (live vitals and features) |
| `icu/{node}/status/urgent` | 1 | yes | when the level **rises** to urgent |
| `icu/{node}/status/critical` | 1 | yes | when the level **rises** to critical |
| `icu/{node}/heartbeat` | 0 | no | every 10 s |
| `icu/{node}/online` | 1 | yes | `online` on connect; the broker publishes `offline` as the Last Will |
| `icu/{node}/ack` | 1 | no | the nurse presses Acknowledge |

- **Severity topics:** one topic per level, so a subscriber can listen to alerts only. Routine messages are frequent but expendable (QoS 0). Alerts must arrive (QoS 1).
- **Retained alerts, cleared on acknowledge:** an alert stays until a nurse acknowledges it, so a dashboard that starts or reloads later still sees it. On ack, the server stores the response time (alert received → ack received) and publishes an **empty retained message** to `status/urgent` and `status/critical`, which clears them. Subscribers ignore empty payloads.
- **Rising-edge alerts:** urgent and critical are published only when the level rises compared with the previous window. Staying critical does not republish.
- **Liveness:** heartbeat every 10 s. Nodes connect with keepalive 5 s and a Last Will (`offline`, QoS 1, retained). A killed node shows **Offline** within about 10 s.
- **Authentication:** username and password per client (`bed1`, `bed2`, `logger`, `dashboard`); anonymous access disabled.
- **Payload:** `{"node","ts","level","p":{routine,urgent,critical},"features":{gesture_conf,tremor,hr_delta,spo2},"hr","bio_source"}`. `bio_source` is `replay` or `live`; the dashboard shows a REPLAY badge.

## 3. Gesture and tremor definitions

Source: `node/vision/geometry.py`, `docs/ROLE_A_NOTES.md`. MediaPipe landmarks: 0 = wrist, 4 = thumb tip, 5/6/8 = index MCP/PIP/tip, 9 = middle MCP, 12 = middle tip.

- `ramp(v, lo, hi) = clamp((v − lo) / (hi − lo), 0, 1)`
- **Hand size:** `s = |wrist(0) → middle MCP(9)|` in pixels. The frame score is 0 if `s < 10 px`.
- **Finger straightness:** for each of the four fingers, the angle at the PIP joint between PIP→MCP and PIP→tip (180° = straight), then `ramp(angle, 120°, 165°)`.
- **Thumb:** `ramp(|thumb tip(4) − index MCP(5)| / s, 0.35, 0.70)`.
- **Openness:** `open = 0.8 · mean(four fingers) + 0.2 · thumb`.
- **Upright factor:** `u = (wrist.y − middle tip.y) / s`, and `up = ramp(u, 0.8, 1.5)`. A flat or sideways open hand scores low.
- **Frame gesture score:** `g = open · up`.
- **Window `gesture_conf`:** the mean of `g` over all frames in the 3-s window, with frames without a hand counting as 0.
- **Tremor (amplitude, not frequency):**
  - Per frame: index fingertip (8) relative to the wrist (0), divided by hand size.
  - Per 3-s window: `tremor = (std(x) + std(y)) / 2` over the frames with a hand. It needs at least 5 hand frames, otherwise 0.
  - Whole-hand movement and distance from the camera do not count as tremor.
- **Thresholds:** the parameters are still the plan defaults (`node/vision/gesture_params.json`: "not calibrated yet"). The rule and gesture-only baselines use `gesture_conf ≥ 0.8`.

## 4. The composed dataset

- **Why composed:** the MAX30100 sensor saturates in IR, so no usable vitals could be recorded together with the gestures. The dataset is therefore **composed from two independent sources that were not recorded at the same time**:
  1. **Gestures:** our Pi camera, 3 healthy team members (P1–P3). Gesture-only protocol (`python -m ml.collect.session --bio none`): 24 trials of 30 s per person in a fixed shuffled order seeded by the person code, with 10-s pauses. Each 30-s trial is cut into 3-s windows.
     - 12 `gesture` trials: G_PALM ×6, G_PALM_DIM ×2 (lights dimmed), G_WEAK ×2 (fingers half bent), G_PALM_SHAKY ×2.
     - 12 `no_gesture` trials: N_REST ×4, N_SCRATCH ×4, N_OTHER ×2 (fist, pointing, thumbs up), N_NOHAND ×1, N_REST_SHAKY ×1.
     - The label is fixed by the scenario before recording. No images or video are saved.
  2. **Vitals:** BIDMC PPG and Respiration Dataset (PhysioNet, ODC-By 1.0; Pimentel et al., IEEE TBME 64(8):1914–1923, 2016, doi:10.1109/TBME.2016.2613124). Real adult ICU patients, 53 recordings of 8 min. HR and SpO₂ at 1 Hz, cut into 3-s windows.
- **NEWS2 labels** (Royal College of Physicians, 2017), applied to the window means:
  - **abnormal:** SpO₂ ≤ 93 or HR ≥ 111
  - **normal:** SpO₂ ≥ 96 and 51 ≤ HR ≤ 90
  - **excluded:** HR ≤ 50 and the 1-point borderline bands
  - Result: 3,392 normal and 1,879 abnormal windows from 49 patients. ΔHR = HR − 75 (adult resting reference).
  - Details: `ml/data/public/README.md`.
- **Pairing rule:** gesture + normal → **urgent**; gesture + abnormal → **critical**; no_gesture + normal → **routine**; no_gesture + abnormal → **routine** (by default; alerts in this system are patient-initiated).
  - Each gesture window is used once with a normal and once with an abnormal vitals window, so urgent and critical differ only in the vitals.
  - Classes are balanced and the seed is fixed (42).
  - The first window of each trial and redone trials are dropped.
- **Evaluation:** leave-one-participant-out × BIDMC patient-grouped split. Patients are split into 3 groups, each containing both normal and abnormal patients, giving 9 folds. In every fold the test pairs share neither a participant nor an ICU patient with the training pairs.
  - The model, the fixed rule and the gesture-only baseline are scored on the same test pairs.
  - A random split is reported for comparison only.
  - No hyper-parameter tuning: StandardScaler + LogisticRegression (C = 1, balanced).
  - Code: `ml/train_composed.py`; write-up generator: `ml/report.py`.
- **Demo replay files** (`ml/replay/`, built by `ml/make_replay.py`; baseline 75):
  - **rest** = `bidmc_39` s 198–258: 60 s, NEWS2-normal every second, HR 73–79, SpO₂ 97.
  - **exertion** = `bidmc_52` s 129–219: 90 s, HR ≥ 111 and SpO₂ ≤ 93 every second (HR 115, SpO₂ 92–93).
  - Both are real ICU recordings. Note that the final model is trained on all BIDMC patients, including these two.

## 5. Limitations (state them honestly)

- **Composed data:** gestures and vitals come from different people and different times, and the pairing rule creates the labels. The results measure how well the model combines the two signals, not real patient behaviour.
- **3 healthy participants** acted out the gestures. Real ICU patients move differently (weakness, sedation, lines, dressings, lying down).
- **NEWS2 as ground truth:** an early-warning score, not a diagnosis. Excluding the borderline 1-point bands makes the classes easier to separate than in practice.
- **Low HR excluded** (HR ≤ 50): with a linear ΔHR feature, logistic regression cannot treat both low and high HR as abnormal. Bradycardia is therefore not detected.
- **ΔHR uses a fixed 75 bpm reference**, not each patient's own baseline.
- **No vitals-only alarm:** abnormal vitals without a gesture stay routine by design; this relies on the bedside monitor.
- **MAX30100 IR saturation:** the bed's own sensor could not give usable HR/SpO₂, so the demo **replays** recorded ICU vitals (the dashboard shows "Biosignals: replay").
- **Security:**
  - no TLS (MQTT and HTTP in plain text on the hotspot)
  - no per-topic ACLs (any authenticated client could publish to any topic)
  - the dashboard's MQTT password is built into the browser JavaScript (`VITE_DASHBOARD_PASS`)
  - Flask runs on its development server
- **Pi 3B+ frame rate:** MediaPipe on the 3B+ gives far fewer frames per 3-s window than the laptop (10 fps). Measure it on hardware day. Fewer frames make gesture_conf and tremor noisier.
- **Gesture thresholds are uncalibrated** (plan defaults). One camera position and one room.

## 6. Report corrections (changes from the original implementation plan)

| Original report / plan | Now |
| --- | --- |
| Raspberry Pi 4B | **Raspberry Pi 3 Model B+** (1 GB) |
| Old topic names | `icu/{node}/status/{routine,urgent,critical}`, `icu/{node}/heartbeat`, `icu/{node}/online`, `icu/{node}/ack` (contract v1) |
| Retain | Only urgent and critical (and `online`) are retained; alerts are cleared by an empty retained message on acknowledge |
| Firebase | **Flask + SQLite** server on the laptop, with an MQTT logger and REST API |
| Binary alert / no alert | **3 classes:** routine, urgent, critical |
| "Tremor frequency" | **Tremor amplitude** (wrist-relative, size-normalised fingertip spread per 3-s window) |
| Vitals measured live by the MAX30100 | **Replayed real ICU vitals (BIDMC)** in the demo; the MAX30100 saturates in IR |
| Training data recorded simultaneously (gesture + vitals) | **Composed dataset:** Pi-camera gestures + BIDMC vitals with NEWS2 labels, paired by a fixed rule |
| Drawbacks §8–9 | Outdated: replace with the limitations in §5 above |

---

## ⚠️ RESULTS: pending

**Not filled in yet.** The gesture recordings for P1–P3 have not arrived. When they do:

```
python -m ml.train_composed --gestures ml/data/raw --vitals ml/data/public/bidmc_news2_windows.csv
python -m ml.report
```

Then copy the numbers from `docs/ML_RESULTS.md` (generated from `ml/results/metrics.json`) into the report:
- mean ± SD accuracy, macro-F1, alert recall and FPR, and critical recall for the model, the rule and gesture-only
- the per-fold table
- the pooled confusion matrices (`ml/results/confusion.png`)
- the random-split comparison
- the coefficients (`ml/results/coefficients.png`)
- the four-case check on the demo replay inputs

Do not quote any number from a synthetic or test run.
