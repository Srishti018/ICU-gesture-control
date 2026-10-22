# Role B Implementation Plan — Biosignal Sensor and ML Model

**Project:** ICU Gesture + Biosignal Fusion System (CBIT, IIoT course project, Team 1)
**Scope of this plan:** Role B only. Wiring and reading the MAX30100 pulse-oximeter on the Raspberry Pi, turning its signal into heart rate and SpO₂, the biosignal sources the node uses (live, replay, manual), the data collection session, training and evaluating the 3-class Logistic Regression model and the rule baseline, and exporting the model and replay files.
**Written:** Thu 22 Oct 2026. **Feature freeze:** Fri 23 Oct, night. **Demo:** Sun 25 Oct 2026.
**Companion plans:** Role A (Pi setup, camera, vision, node program) works in `node/` (except `node/bio/`). Role C (broker, server, dashboard) is finished.

---

## 0. Instructions for Claude Code (read first)

You are executing this plan end to end, together with a human teammate who has the hardware in front of them. Follow these rules for the whole plan.

1. **Work phase by phase, in order** (Phase 0 → Phase 10). Each phase ends with a **Gate**. Do not start the next phase until the Gate passes, except where a phase says it can run in parallel. Phase 1 needs no hardware and should start immediately.
2. **Three kinds of step are marked:**
   - **[LAPTOP]** — you run it on this computer.
   - **[PI]** — you run it on the Raspberry Pi through SSH: `ssh icu-pi '<command>'`. Anything that runs longer than a few seconds runs inside `tmux` (§4.4).
   - **[HUMAN]** — the teammate must do something physical (wire, place a finger, exercise, read a device). Print the instruction exactly as written in the plan as a numbered list, then **stop and wait** for their reply. Never assume a [HUMAN] step was done. Ask for the specific confirmation the step names.
3. **Hardware safety rules (never break these):**
   - Wiring is changed **only with the Pi powered off** (power cable unplugged). Ask the human to confirm "power is unplugged" before any wiring step and "wiring double-checked against the table" before power goes back on.
   - The MAX30100 gets **3.3 V from physical pin 1**. Never pin 2 or pin 4 (5 V).
   - No soldering instructions unless the human says someone experienced with soldering is present (§7.3).
4. **People safety rules for data collection (never break these):** only team members who agree take part; anyone with a heart, lung or blood-pressure condition, or who feels unwell, skips the exercise trials; exercise stops immediately on dizziness, chest pain or unusual breathlessness; water is available. No camera images or video are ever saved. People are recorded as `P1`, `P2`, `P3` only; the name mapping is never written to the repo.
5. **The interfaces in Appendix B are fixed** between Role A and Role B. You own `node/bio/`, `ml/` and `docs/ROLE_B_NOTES.md`, `docs/ML_RESULTS.md`. You use Role A's `node/vision/features.py`, `node/settings.py` and `node/hwlock.py`; never edit them or anything else in `node/` outside `node/bio/`. If you need a package added to `node/requirements.txt`, ask the user to pass the request to Role A.
6. **The MQTT contract (Appendix A of Role A's plan / `docs/contracts.md`) is not yours to change.** What matters to you from it: the level names are exactly `routine`, `urgent`, `critical`; probabilities `p` must sum to 1; the features are `gesture_conf`, `tremor`, `hr_delta`, `spo2` (integers for `hr_delta` and `spo2`).
7. **`sudo`:** never on the laptop. On the Pi only the `sudo` commands written in this plan, exactly as written; anything else → stop and ask.
8. **Labels are decided by the scenario before recording, never after looking at the numbers.** Never relabel, drop or "clean" data to improve results, except by the fixed rules in §12.1. Report what the data shows, including if the rule baseline ties or beats the model.
9. **If a check fails, fix the cause, never weaken the check.** If the same failure survives 3 fix attempts, stop and report: the check, the exact error, what you tried.
10. **Commit at the end of each phase** with the message given, after `git status` shows no secrets or `.env` staged. Then `git pull --rebase` and `git push`. If a rebase conflict touches a file outside your folders, stop and ask.
11. **Explain in plain language.** At the end of each phase, give a 3–5 line summary: what works now, what was fixed, what the Gate showed, what the human must do next.
12. **Stop and ask the user when:** a [HUMAN] step is pending; the Pi is not ready (Role A's Phase 1); the sensor is not detected after §7.2; a decision point in §8.6 is reached; Role A's vision code is missing at the collector gate; anything would change the contract or Role A's files.

---

## 1. What Role B builds (context)

1. **A working MAX30100 reading on the Pi:** a small driver that talks to the chip over I2C and gives raw infrared (IR) and red light samples at 100 per second.
2. **Heart rate and SpO₂ from that signal**, checked against a reference (a commercial fingertip oximeter or a manual pulse count).
3. **The `node/bio/` package** the node uses: `live` (the sensor), `replay:rest` / `replay:exertion` (recorded files played back in real time, used in the demo), `manual` (values typed from a reference device, used only for data collection if the sensor is unreliable).
4. **The data collection session:** about 57 trials of 30 seconds with all three team members, recording the four features every 3 seconds with a label decided by the scenario.
5. **The model:** a 3-class Logistic Regression (`routine`, `urgent`, `critical`) on `gesture_conf`, `tremor`, `hr_delta`, `spo2`, evaluated leave-one-person-out against a fixed rule and a gesture-only rule, exported as a small JSON file that the Pi runs with NumPy only.
6. **Replay files** from real recordings, so the demo can show a rest and an exertion scenario on stage.
7. **The results write-up** for the report.

Why replay in the demo: heart rate can't be raised on demand on stage. The report already commits to disclosing this; the node publishes `"bio_source": "replay"` and the dashboard shows a REPLAY badge.

---

## 2. Environment facts and questions to settle in Phase 0

| Item | Value |
| --- | --- |
| Pi | Raspberry Pi 3 Model B+ (1 GB RAM), Raspberry Pi OS Lite 64-bit (Bookworm), set up by Role A (their Phase 1): hostname `icu-pi`, user `pi`, repo at `~/icu-fusion`, venv at `~/icu-fusion/.venv`, I2C enabled, `i2c-tools` installed |
| Sensor | MAX30100 module, I2C bus 1, address `0x57`, part ID register `0xFF` reads `0x11` |
| Shared I2C bus | Role A's OLED at `0x3C` is on the same SDA/SCL wires |
| Pi Python packages | Installed by Role A from `node/requirements.txt` (includes `numpy<2`, `scipy`, `smbus2`) |
| Laptop (where you run) | Detect the OS. Linux/macOS: commands as written. Windows: PowerShell; `ssh`/`scp` are built in; venv Python is `.venv\Scripts\python` |
| Training | Runs on the laptop (scikit-learn), never on the Pi |
| Pi data folder | `~/icu-data/raw/` (outside the repo, so `git pull` on the Pi never conflicts with data) |
| Laptop data folder | `ml/data/raw/` (committed; CSV/JSON only, no images) |

---

## 3. Architecture

### 3.1 Where Role B sits

```
 Raspberry Pi                                                    Laptop
 ┌──────────────────────────────────────────────────────┐        ┌────────────────────────────────────────┐
 │ MAX30100 ─I2C 0x57─▶ node/bio/max30100.py (driver)    │        │ ml/data/raw/*.csv  (copied from the Pi) │
 │                      node/bio/ppg.py (HR, SpO2)       │        │ ml/validate_data.py → data report       │
 │                      node/bio/live.py  ─┐             │        │ ml/train.py  (LOPO, rule baselines)     │
 │ ml/replay/*.csv ───▶ node/bio/replay.py ├─ BioSource  │        │ ml/export.py → ml/models/model.json     │
 │ operator input ───▶ node/bio/manual.py ─┘   (App. B)  │        │ ml/make_replay.py → ml/replay/*.csv     │
 │                                                      │        │ docs/ML_RESULTS.md                      │
 │ ml/collect/session.py  ◀── Role A's VisionFeatureExtractor     └───────────────────┬────────────────────┘
 │   writes ~/icu-data/raw/  (data collection)          │                            │ git push
 │                                                      │◀───────── git pull ─────────┘
 │ node/main.py (Role A) uses: make_bio_source(), ml/fusion_runtime.FusionModel + model.json
 └──────────────────────────────────────────────────────┘
```

### 3.2 Signal path (live sensor)

```
MAX30100 FIFO (100 samples/s, 16 deep) ─▶ poll every 40 ms ─▶ ring buffer (8 s of IR + red)
   ─▶ every 1 s: finger check (IR DC level) ─▶ band-pass 0.7–3.5 Hz ─▶ peak detection ─▶ HR
                                            ─▶ AC/DC of red and IR ─▶ ratio R ─▶ SpO₂
   ─▶ per-second record {hr, spo2, finger, quality}
   ─▶ window(): mean of valid seconds in the last 3 s; hr_delta = hr − baseline
```

---

## 4. Repository layout and conventions

### 4.1 Files Role B creates (target)

```
icu-fusion/
├── docs/
│   ├── ROLE_B_NOTES.md            # sensor checks, tuning values, validation, decisions
│   └── ML_RESULTS.md              # results write-up for the report (Phase 9)
├── node/bio/                      # runs on the Pi (and replay/manual also on the laptop)
│   ├── __init__.py                # make_bio_source(), BioUnavailable, BioSource base
│   ├── max30100.py                # I2C driver (smbus2)
│   ├── ppg.py                     # PURE signal processing: HR, SpO2, finger, quality
│   ├── live.py                    # LiveBio: thread + ring buffer + baseline
│   ├── replay.py                  # ReplayBio
│   ├── manual.py                  # ManualBio (interpolated operator values)
│   ├── sensor_params.json         # LED currents, finger threshold (tuned in Phase 4)
│   ├── tools/
│   │   ├── i2c_probe.py           # part ID and register check
│   │   ├── capture_raw.py         # save raw 100 Hz IR/red to CSV
│   │   ├── led_tune.py            # balance red vs IR
│   │   ├── finger_threshold.py
│   │   ├── live_monitor.py        # prints HR/SpO2/quality every second
│   │   └── validate_hr.py         # guided comparison with a reference device
│   └── tests/
│       ├── __init__.py
│       ├── test_max30100_parse.py
│       ├── test_ppg.py
│       └── test_sources.py
└── ml/
    ├── __init__.py                # empty (must not import scikit-learn)
    ├── requirements.txt           # laptop only
    ├── schema.py                  # column names, scenario table, label map (single source of truth)
    ├── rule.py                    # fixed rule baseline + gesture-only baseline
    ├── fusion_runtime.py          # NumPy-only FusionModel (Appendix B)
    ├── synth.py                   # synthetic dataset for testing the pipeline ONLY
    ├── validate_data.py
    ├── train.py
    ├── export.py
    ├── make_replay.py
    ├── collect/
    │   ├── __init__.py
    │   ├── session.py             # guided session runner (runs on the Pi, interactive)
    │   ├── trial.py               # records one trial
    │   └── recorder.py            # writes CSV + JSON
    ├── data/
    │   ├── raw/                   # copied from the Pi after collection
    │   └── sensor_samples/        # raw IR/red captures for algorithm tests
    ├── models/
    │   ├── model.joblib
    │   └── model.json
    ├── replay/
    │   ├── rest.csv, rest.json
    │   └── exertion.csv, exertion.json
    ├── results/                   # metrics.json, metrics.md, PNG charts, data_report.md
    └── tests/
        ├── test_rule.py
        ├── test_runtime_parity.py
        └── test_pipeline_synth.py
```

### 4.2 Requirements

`ml/requirements.txt` (laptop only):
```
numpy>=1.24
scipy>=1.10
pandas>=2.0
scikit-learn>=1.3
matplotlib>=3.7
joblib>=1.3
pytest>=8.0
```
On the Pi, everything `node/bio/` and `ml/collect/` need (`numpy`, `scipy`, `smbus2`) is already in Role A's `node/requirements.txt`. **Do not use pandas, scikit-learn or matplotlib in `node/bio/`, `ml/collect/` or `ml/fusion_runtime.py`**; those run on the Pi.

### 4.3 Getting code onto the Pi
Role A's setup: the Pi pulls the repo from GitHub with a read-only deploy key. To update the Pi after pushing: `ssh icu-pi 'cd ~/icu-fusion && git pull --ff-only'`. Never edit files on the Pi directly.

### 4.4 Long-running programs on the Pi
Run in `tmux` so a dropped connection doesn't kill them:
- Start: `ssh icu-pi 'tmux new-session -d -s bio "cd ~/icu-fusion && .venv/bin/python -m node.bio.tools.live_monitor"'`
- Read output: `ssh icu-pi 'tmux capture-pane -pt bio | tail -30'`
- Stop: `ssh icu-pi 'tmux kill-session -t bio'`
- Interactive programs (the data collection session) are run by the human: `ssh -t icu-pi`, then `tmux new -s collect`, then the command. Detach with **Ctrl-b then d**; reattach with `tmux attach -t collect`.

### 4.5 Hardware lock
Every Role B program that opens I2C (all of `node/bio/tools/` and `ml/collect/session.py`) wraps its work in Role A's `with HardwareLock("<program name>"):` from `node/hwlock.py`. If the lock is busy, print the message and exit; do not retry in a loop. If `node/hwlock.py` doesn't exist yet, ask the user to check Role A's progress; meanwhile implement the same behaviour locally in your tool (exclusive non-blocking `fcntl.flock` on `/tmp/icu-hw.lock`) and switch to Role A's module once it exists.

Inside `node.main`, Role A already holds the lock, so `LiveBio` must **not** take it again (a second `flock` in the same process on a new file handle would fail). `LiveBio(take_lock=False)` is the default; tools pass `take_lock=True`.

---

## 5. Phase 0 — Audit and questions (≈ 20 min)

### 5.1 [LAPTOP] Inspect
1. `git pull`, `git log --oneline -15`, print the tree (excluding `.git`, `.venv`, `node_modules`).
2. Read `docs/contracts.md`, `docs/NODE_INTEGRATION.md`, and `docs/NODE_INTERFACES.md` if present. Compare `NODE_INTERFACES.md` with Appendix B: if it exists and differs in substance → STOP and ask; if it doesn't exist, create it from Appendix B verbatim (Role A does the same; whoever is first creates it, the other checks it).
3. Check what exists in `node/bio/`, `ml/`, and Role A's `node/` (`hwlock.py`, `settings.py`, `vision/features.py`).
4. Detect the laptop OS and Python version.

### 5.2 [HUMAN] Ask these, all in one message, and wait
1. "Is the Pi set up yet by Role A (can you or they run `ssh icu-pi` without a password)? If not, roughly when?"
2. "Which MAX30100 board do you have? What colour is it, and what text is printed on it (for example 'MAX30100', 'RCWL-0530', 'GY-MAX30100')? Which pins are labelled on its edge?"
3. "Is there a **commercial fingertip pulse oximeter** available to borrow for Thursday and Friday? (It is the reference to check our readings.)"
4. "Who will take part in data collection (just say how many of the three), and is anyone advised to avoid exercise? You don't need to say why."
5. "Can the session happen Friday 08:30–11:00 (about 2–2.5 hours, all three people)? If someone is free Thursday evening, we can start then."
6. "Is anyone on the team experienced with soldering, and is a soldering iron available? (Only needed if the sensor has a known board problem.)"

### 5.3 `docs/ROLE_B_NOTES.md`
Create with sections: Answers to 5.2 · Pi readiness · Sensor checks · Tuning values · HR/SpO₂ validation · Decision (live or manual) · Data collection log summary · Model notes.

### Gate 0
Answers recorded; interface doc exists and matches. Commit: `ml: role B audit`.

---

## 6. Phase 1 — ML pipeline on the laptop, before any data (≈ 2–3 h, no hardware; start now)

Build and test the whole training pipeline with **synthetic** data, so that on Friday real data only has to be dropped in. Synthetic data is for testing code only: it must never appear in any result, chart or the report.

### 6.1 `ml/schema.py` (single source of truth)
```python
FEATURES = ["gesture_conf", "tremor", "hr_delta", "spo2"]
CLASSES  = ["routine", "urgent", "critical"]
SCENARIOS = {
  # code: (name, label, exertion, gesture, notes)
  "S1": ("calm",                     "routine",  False, False, "hand resting in view"),
  "S2": ("incidental_movement",      "routine",  False, False, "scratch face, adjust sleeve/blanket, shift hand"),
  "S3": ("gesture_only",             "urgent",   False, True,  "open palm held up for the whole trial"),
  "S4": ("exertion_only",            "routine",  True,  False, "after exercise, hand resting in view"),
  "S5": ("exertion_gesture",         "critical", True,  True,  "after exercise, open palm held up"),
  "H1": ("gesture_dim_light",        "urgent",   False, True,  "S3 with room lights dimmed"),
  "H2": ("weak_gesture",             "urgent",   False, True,  "palm up, fingers half-bent (weak patient)"),
  "H3": ("mild_exertion_gesture",    "critical", True,  True,  "after 60 s brisk walking only, open palm"),
  "H4": ("exertion_incidental",      "routine",  True,  False, "after exercise, scratching/adjusting"),
}
WINDOW_COLUMNS = ["person","scenario","scenario_name","trial","label","window_idx","ts",
  "gesture_conf","tremor","hand_present","n_frames","n_hand_frames","fps",
  "hr","spo2","hr_delta","finger","bio_quality","bio_mode","baseline_hr",
  "light","gesture_hand","discarded"]
```

### 6.2 `ml/rule.py`
- `rule_level(f)`: `critical` if `gesture_conf >= 0.8 and hr_delta >= 15`; `urgent` if `gesture_conf >= 0.8`; else `routine`. **Fixed now; never tuned on data.**
- `gesture_only_level(f)`: `urgent` if `gesture_conf >= 0.8` else `routine` (models a gesture-only system like the 2019-era systems in the report; it can never output `critical`).
- `test_rule.py`: boundary cases (0.79/0.80, 14/15).

### 6.3 `ml/fusion_runtime.py` (NumPy only — runs on the Pi)
Implements Appendix B §B.4 exactly:
- `FusionModel.load(path)`: read JSON; check `features == FEATURES` and `classes == CLASSES` (raise `ValueError` otherwise); store arrays.
- `predict_proba(features: dict) -> dict`: `x` in FEATURES order (float); `z = (x − mean) / scale`; `logits = coef @ z + intercept`; stable softmax (subtract max); return `{class: float}` in CLASSES order. No rounding here (Role A rounds for publishing).
- Missing or non-numeric feature → `ValueError` naming the feature.

### 6.4 `ml/export.py`
`export(pipeline, path, n_train)`: take the `StandardScaler` (`mean_`, `scale_`) and `LogisticRegression` (`coef_`, `intercept_`, `classes_`). **scikit-learn orders `classes_` alphabetically (`critical, routine, urgent`)**; reorder the rows of `coef_` and `intercept_` into CLASSES order by name. Write `{"version": 1, "trained_at", "features", "classes", "mean", "scale", "coef", "intercept", "n_train", "sklearn_version"}` with lists of floats.

### 6.5 `ml/synth.py`
Generates a fake windows dataset in the exact `WINDOW_COLUMNS` format for 3 people × all scenarios × 3 trials × 10 windows, with plausible values (gesture 0.85–0.95 when gesture, 0–0.25 otherwise; hr_delta 18–30 after exertion, −3..5 otherwise; spo2 96–99; tremor 0.005–0.05) plus noise and 5% deliberately hard rows. Writes to a temp folder given as an argument, never into `ml/data/raw/`.

### 6.6 `ml/validate_data.py`
Input: a folder of `*_windows.csv` files. Output: `data_report.md` (and printed summary) with:
- files read, rows, people, trials per person × scenario (table), discarded trials
- windows per label after the §12.1 exclusions
- per trial: mean `gesture_conf`, mean `hand_present`, mean `hr_delta`, `finger` rate, `bio_mode`
- **flags** (never auto-fixes): gesture scenarios with mean `hand_present < 0.8`; S5/H3 trials with mean `hr_delta < 15`; S3/H1 trials with mean `gesture_conf < 0.6`; any `hr` missing in > 20% of a trial's windows
- exit code 1 if: any label has < 60 windows, or fewer than 2 people, or a person is missing S1–S5

### 6.7 `ml/train.py`
CLI: `python -m ml.train --data ml/data/raw --out ml/results [--models ml/models]`.

1. Load all windows; apply §12.1 exclusions; print counts.
2. `X` = FEATURES (float), `y` = label, `groups` = person.
3. Model: `Pipeline([("scale", StandardScaler()), ("lr", LogisticRegression(C=1.0, class_weight="balanced", max_iter=2000))])`. No hyper-parameter tuning (too little data; say so in the results). `random_state=42` wherever applicable.
4. **Leave-one-person-out** (`LeaveOneGroupOut`): for each person, fit on the others, predict the held-out person. Collect predictions for all rows.
5. On the same held-out rows, compute `rule_level` and `gesture_only_level`.
6. For each method (model, rule, gesture-only):
   - accuracy, macro-F1, per-class precision/recall/F1, 3×3 confusion matrix (rows = true, columns = predicted, order CLASSES)
   - **alert view** (alert = not routine): precision, recall, false-positive rate = routine windows predicted as alert ÷ all routine windows
   - critical precision and recall
   - per-person accuracy (to show variation)
7. **For comparison only:** a stratified 5-fold random split of windows for the model (`StratifiedKFold(5, shuffle=True, random_state=42)`), reported next to LOPO with one sentence explaining why it looks better (windows from the same trial are near-copies, so the test set leaks). This answers the teacher's question.
8. Fit the final model on **all** data; save `ml/models/model.joblib`; export `ml/models/model.json` via `export.py`.
9. Coefficients of the final model (standardised features): table (class × feature) to `coefficients.csv` and a grouped bar chart `coefficients.png`.
10. Charts: confusion matrices for the three methods side by side (`confusion.png`), with counts in the cells.
11. Write `metrics.json` (all numbers) and `metrics.md` (tables in Markdown).

### 6.8 Tests (synthetic)
- `test_runtime_parity.py`: train on synthetic data, export, then for every row `FusionModel.predict_proba` vs the pipeline's `predict_proba` (columns reordered to CLASSES) → max absolute difference < 1e-9; each output sums to 1 within 1e-9; loading a JSON with wrong `classes` raises.
- `test_pipeline_synth.py`: run `validate_data` and `train` on a synthetic folder in `tmp_path`; check all output files exist and `metrics.json` has the three methods with the documented keys.

### Gate 1
`pytest ml/tests -q` passes on the laptop. Commit: `ml: training pipeline, rule baselines, numpy runtime (tested on synthetic data)`.

---

## 7. Phase 2 — Wire the MAX30100 and detect it (≈ 30–60 min)

**Dependency:** Role A's Phase 1 is done (`ssh icu-pi 'echo ok'` works; `i2cdetect` installed; I2C enabled). If not, keep working on Phase 1 and tell the user.

### 7.1 [HUMAN] Wiring (Pi powered OFF)
Show Appendix C, then:
1. "Unplug the Pi's power cable. Reply 'power off'."
2. "If the board has no header pins soldered, it needs them before it can go in the breadboard; tell me if so."
3. "Put the MAX30100 board on the breadboard. Connect, using the labels printed on the board:
   - **VIN** → breadboard **+ rail**; + rail → **Pi pin 1 (3.3 V)**
   - **GND** → breadboard **− rail**; − rail → **Pi pin 6 (GND)**
   - **SDA** → a free breadboard row (the SDA row) → **Pi pin 3**
   - **SCL** → another free row (the SCL row) → **Pi pin 5**
   - Leave **INT**, **IRD** and **RD** unconnected.
   If Role A's OLED is already wired, the sensor shares the same + rail, − rail, SDA row and SCL row."
4. "Check each wire against Appendix C. Make sure nothing goes to pin 2 or pin 4 (5 V). Reply 'checked'. Then plug the power in and reply 'powered on'."

### 7.2 [PI] Detect
1. `i2cdetect -y 1` → must show `57` (and `3c` if the OLED is connected). Paste the grid into `ROLE_B_NOTES.md`.
2. `i2cget -y 1 0x57 0xff` → must print `0x11` (MAX30100 part ID). `i2cget -y 1 0x57 0xfe` → revision ID; record it.

Troubleshooting, in order (stop at the first that fixes it; record what happened):
| Symptom | Action |
| --- | --- |
| `i2cdetect` shows nothing at all, not even `3c` | [HUMAN] power off; re-seat all four wires; confirm SDA→pin 3, SCL→pin 5 (swapped SDA/SCL is the most common mistake). Power on, retry. Check `ls /dev/i2c-1` exists (else Role A's I2C enable step failed). |
| `3c` shows but `57` doesn't | [HUMAN] power off; re-seat the sensor's wires; check VIN goes to pin 1 and GND to the − rail. Retry once. |
| `57` shows but `0xff` reads an error or not `0x11` | Retry 3 times. Then go to §7.3. |
| Still failing | §7.3 |

### 7.3 Known board problem and the time-box
Many cheap MAX30100 modules (often the green "RCWL-0530" and some purple boards) pull the I2C lines up to **1.8 V** through resistors on the module, which the Pi (3.3 V logic) often can't read reliably. The documented fix is to remove those pull-up resistors from the module so the Pi's own pull-ups are used, which requires desoldering small surface-mount parts.

Decision rule:
- Total time spent on detection problems > **60 minutes**, or the reading in Phase 4 stays garbage (IR always 0, always 65535, or random jumps with a still finger) → **switch to manual mode** (§8.6): the data collection uses a reference oximeter typed in by the operator, the replay files come from those values, and the live sensor on the OLED is dropped. Tell the user clearly.
- Only if the human said an experienced person and a soldering iron are available: tell them to search for a photo guide for their exact board ("MAX30100 module pull-up resistor fix") and follow it with the Pi powered off. Do not give resistor locations yourself; they differ between boards. Re-run §7.2 afterwards.

### Gate 2
`i2cget -y 1 0x57 0xff` prints `0x11` reliably (5 out of 5 tries), or the manual-mode decision is recorded. Commit (notes only): `ml: sensor wiring checks`.

---

## 8. Phase 3–4 — Driver, signal tuning and HR/SpO₂ (≈ 3–4 h)

### 8.1 `node/bio/max30100.py` — driver (smbus2)
Register map (MAX30100 datasheet):

| Register | Address | Use |
| --- | --- | --- |
| INT_STATUS | `0x00` | read to clear |
| FIFO_WR_PTR | `0x02` | write pointer (4 bits) |
| OVF_COUNTER | `0x03` | overflow count |
| FIFO_RD_PTR | `0x04` | read pointer (4 bits) |
| FIFO_DATA | `0x05` | 4 bytes per sample: IR high, IR low, RED high, RED low |
| MODE_CONFIG | `0x06` | bit 6 = reset; mode bits: `0x02` HR only, `0x03` SpO₂ |
| SPO2_CONFIG | `0x07` | bit 6 = high-resolution; bits 4:2 = sample rate (`001` = 100 Hz); bits 1:0 = pulse width (`11` = 1600 µs, 16-bit) |
| LED_CONFIG | `0x09` | bits 7:4 = red current code, bits 3:0 = IR current code |
| REV_ID / PART_ID | `0xFE` / `0xFF` | part ID must be `0x11` |

Class `MAX30100(bus=1, address=0x57, red_code=8, ir_code=15)`:
- `open()`: `SMBus(1)`; read PART_ID, raise `SensorError("MAX30100 not found or wrong part ID: 0x..")` if not `0x11`.
- `configure()`:
  1. write `MODE_CONFIG = 0x40` (reset); poll until bit 6 clears (max 100 ms; else error)
  2. write `SPO2_CONFIG = 0x47` (high-res, 100 Hz, 1600 µs)
  3. write `LED_CONFIG = (red_code << 4) | ir_code` (default `0x8F`: red ≈ 27 mA, IR ≈ 50 mA)
  4. write `FIFO_WR_PTR`, `OVF_COUNTER`, `FIFO_RD_PTR` = 0
  5. write `MODE_CONFIG = 0x03` (SpO₂ mode, both LEDs)
- `read_samples() -> list[(ir, red)]`: `wr = read(0x02) & 0x0F`, `rd = read(0x04) & 0x0F`, `ovf = read(0x03)`; `n = (wr − rd) & 0x0F`, or 16 if `n == 0 and ovf > 0`. Read `4·n` bytes from `0x05` in chunks of at most 32 bytes (`read_i2c_block_data(addr, 0x05, k)`; the FIFO register does not auto-increment, so consecutive reads return consecutive samples). Parse big-endian 16-bit pairs. Count overflows in `self.dropped`.
- `set_led(red_code, ir_code)`, `shutdown()` (MODE_CONFIG bit 7 = shutdown), `close()`.
- Pure helpers for testing: `parse_fifo(bytes) -> list[(ir, red)]`, `fifo_count(wr, rd, ovf) -> int`.

LED current codes (mA): `0:0, 1:4.4, 2:7.6, 3:11.0, 4:14.2, 5:17.4, 6:20.8, 7:24.0, 8:27.1, 9:30.6, 10:33.8, 11:37.0, 12:40.2, 13:43.6, 14:46.8, 15:50.0`.

`test_max30100_parse.py`: byte parsing; `fifo_count` with wrap-around (wr=2, rd=14 → 4), full FIFO with overflow → 16, empty → 0.

### 8.2 Tools (all take the hardware lock, all print and write to `~/icu-data/raw/`)
- `i2c_probe.py`: part ID, revision, register dump of 0x00–0x09.
- `capture_raw.py --seconds 30 --tag rest_P1`: polls `read_samples()` every 40 ms; writes `sensor_<tag>.csv` with `t_s, ir, red` (t_s = sample index / 100); prints dropped samples and mean IR/red.
- `finger_threshold.py`: [HUMAN] prompts "Keep your finger OFF the sensor" (5 s), then "Rest your left index fingertip lightly on the sensor and keep still" (10 s); reports mean IR DC without and with finger; proposes `finger_ir_min = (off + on) / 2`. If the "on" level is above 60,000 (near the 65,535 limit), lower `ir_code` by 2 and repeat (saturation ruins the pulse signal).
- `led_tune.py`: with a finger on, tries `red_code` 5…11 (2 s each) with the chosen `ir_code`; prints IR DC and red DC; picks the code where red DC is closest to IR DC (aim within ±25%).
- Save the chosen `red_code`, `ir_code`, `finger_ir_min` to `node/bio/sensor_params.json` and `ROLE_B_NOTES.md`.

### 8.3 [HUMAN] + [PI] Raw signal checks
For each step, give the human the instruction, run the tool in tmux, report the numbers.
1. `i2c_probe.py` → part ID `0x11`.
2. `finger_threshold.py` (human follows the prompts).
3. `led_tune.py` ("finger on, keep still, about 15 seconds").
4. `capture_raw.py --seconds 30 --tag rest_P1` ("finger resting lightly, other hand on the table, sit still, breathe normally"). Then `--tag move_P1` ("finger on, but gently wiggle the finger for 30 s").
5. [LAPTOP] `scp 'icu-pi:~/icu-data/raw/sensor_*.csv' ml/data/sensor_samples/`. Plot IR for both files (save `ml/results/raw_ir_rest.png`, `raw_ir_move.png`). In the rest file you should see a regular pulse wave (about 1 per second). If no pulse is visible: [HUMAN] "press slightly lighter or slightly firmer, and shade the sensor from room light with your other hand", then recapture once.

### 8.4 `node/bio/ppg.py` — signal processing (pure functions, fs = 100 Hz)
Applied every second to the last **8 s** (800 samples) of IR and red: (on the 3B+ this shares the CPU with MediaPipe during data collection and the demo; keep it to one `sosfiltfilt` per channel per second and no plotting on the Pi).
1. **Finger:** `finger = mean(IR) > finger_ir_min`. No finger → `hr = spo2 = None`, `quality = 0`.
2. **Band-pass:** `scipy.signal.butter(2, [0.7, 3.5], btype="band", fs=100, output="sos")`, apply with `sosfiltfilt` to IR and red (after subtracting each channel's mean).
3. **Peaks:** `find_peaks(ir_bp, distance=33, prominence=0.4 * std(ir_bp))` (33 samples = 0.33 s = max 180 bpm). Use only the peaks themselves; polarity doesn't matter for intervals.
4. **HR:** intervals between consecutive peaks in seconds; keep those in 0.33–1.5 s. Need ≥ 4 kept intervals. `cv = std/mean`. If `cv > 0.25` → `hr = None` (irregular or motion). Else `hr = round(60 / median(intervals))`.
5. **Quality:** `quality = clamp(1 − cv / 0.25, 0, 1)` if `hr` is not None, else 0.
6. **SpO₂** (only if `hr` is not None): `AC = std(band-passed)`, `DC = mean(raw)` per channel; `R = (AC_red / DC_red) / (AC_ir / DC_ir)`; `spo2 = clip(round(110 − 25·R), 80, 100)`. This is the common uncalibrated approximation; say "approximate SpO₂" in the report. Smooth: report the median of the last 5 valid values.
7. Functions: `bandpass`, `detect_peaks`, `heart_rate(ir, fs) -> (hr, cv)`, `spo2_ratio(ir, red) -> R`, `spo2_from_ratio(R)`, `analyse(ir, red, fs, params) -> {"hr","spo2","finger","quality"}`.

`test_ppg.py` with a synthetic PPG generator (`DC + A·sin(2πf t) + 0.3A·sin(4πf t + 0.5) + noise`, red with a different AC/DC ratio):
- 60, 90, 120 bpm → estimated HR within ±2 bpm
- flat signal (no pulse) → `hr is None`
- DC below threshold → `finger False`
- random interval jitter (cv ≈ 0.4) → `hr is None`
- a known R → expected SpO₂ (e.g. R = 0.5 → 98 after rounding; clip at 100 and 80)
- the two recorded files from §8.3 (if present in `ml/data/sensor_samples/`): rest file gives HR values for > 60% of seconds; print them (no fixed expected value).

### 8.5 `node/bio/live.py` — `LiveBio`
- `__init__(settings, take_lock=False, params=sensor_params.json)`
- `start()`: open + configure the driver (raises `BioUnavailable` with the reason if the sensor is missing), start a thread that every 40 ms appends samples to an 8-s ring buffer (NumPy arrays), and once per second runs `ppg.analyse` and appends `{t, hr, spo2, finger, quality}` to a per-second history (last 120 s). Optionally also writes each per-second record to a CSV if `log_path` is set.
- `calibrate_baseline(seconds=60) -> int`: waits and returns `round(median(valid hr))` over that period; raises `BioUnavailable` if fewer than 50% of seconds were valid. Stores it.
- `window()`: per-second records from the last 3 s; `hr` = rounded mean of valid ones (None if none), `spo2` likewise, `hr_delta = hr − baseline` (None if either is None), `finger` = any finger, `quality` = mean quality, `source = "live"`.
- `stop()`: stop thread, `shutdown()` the sensor, close the bus.
- Never raises from the thread; errors are logged and counted; after 10 consecutive I2C errors, mark `self.failed = True` and return `None` values.

### 8.6 HR validation and the live/manual decision
`node/bio/tools/validate_hr.py`, run on the Pi, guided:
1. [HUMAN] "Finger on the MAX30100. If you have the commercial oximeter, put it on a finger of the **other** hand. Sit still." (No oximeter: "Another person will count your pulse at the wrist for 30 seconds when I say go, and multiply by 2.")
2. Tool runs 30 s, prints the sensor's median HR for those 30 s and its SpO₂.
3. [HUMAN] "Type the oximeter's heart rate and SpO₂ (or the counted pulse)."
4. Repeat 3 times at rest. Then [HUMAN] "Do 60 seconds of spot jogging, sit, put the finger back", and run 1 more check straight away.

Record the table in `ROLE_B_NOTES.md`: sensor HR, reference HR, difference, sensor SpO₂, reference SpO₂.

**Decision (latest Thu 22 Oct, 20:00):**
| Result | Decision |
| --- | --- |
| Rest: |difference| ≤ 8 bpm in ≥ 2 of 3 checks, **and** after exercise the sensor shows HR ≥ baseline + 15 when the reference does | **LIVE**: collect data with the sensor; OLED shows live readings in the demo |
| Otherwise | **MANUAL**: collect data with the reference values typed in (`--bio manual`); replay files come from those values; the live sensor on the OLED is dropped or shown as "experimental". Tell Role A. |

Ask the human to confirm the decision before continuing. Record it.

### Gate 3–4
Driver tests and `test_ppg.py` pass; tuning values saved; validation table recorded; decision made and confirmed. Commit: `bio: max30100 driver, ppg processing, live source`.

---

## 9. Phase 5 — The `node/bio` package (replay and manual) (≈ 1–1.5 h; can run in parallel with Phase 3–4)

### 9.1 `node/bio/__init__.py`
Exactly Appendix B §B.3:
- `class BioUnavailable(Exception)`
- `class BioSource` (base with `kind`, `start`, `window`, `baseline_hr`, `stop`)
- `make_bio_source(mode, settings, **kw)`: `"live"` → `LiveBio`; `"replay:rest"` / `"replay:exertion"` → `ReplayBio(name)`; `"manual"` → `ManualBio`; anything else → `ValueError`.
- Import `live.py` lazily inside `make_bio_source`, so the laptop (no `smbus2` I2C device) can use replay and manual.

### 9.2 `node/bio/replay.py` — `ReplayBio`
- Files: `ml/replay/{name}.csv` (`t_s,hr,spo2`, one row per second, integers, no gaps) and `{name}.json` (`{"kind", "person", "baseline_hr", "source": "MAX30100"|"manual", "recorded_at", "seconds"}`); paths resolved from the repo root.
- `start()` records the start time; position = `int(elapsed_seconds) % n_rows`.
- `window()`: the 3 rows ending at the current position (wrapping); `hr`, `spo2` = rounded means; `hr_delta = hr − baseline_hr`; `finger=True`; `quality=1.0`; `source="replay"`.
- `restart()` and creating a new instance both start from row 0 (Role A's `r`/`x` keys rely on this).
- `baseline_hr()` returns the JSON value.
- Missing file → `BioUnavailable("replay file ml/replay/<name>.csv not found")`.

### 9.3 `node/bio/manual.py` — `ManualBio`
Used only by the data collector.
- `set_start(hr, spo2)` before a trial and `set_end(hr, spo2)` after it; values per second are linearly interpolated between start and end over the trial length.
- `window_for(t_start, t_end)`: mean of the interpolated values; `hr_delta = hr − baseline`; `source = "manual"`; `quality = 1.0`.
- `set_baseline(hr)`.

### 9.4 Tests — `test_sources.py`
Replay: loops correctly; `hr_delta` uses the JSON baseline; restart goes back to row 0; missing file raises `BioUnavailable`. Manual: interpolation midpoint; baseline delta. `make_bio_source` returns the right types; unknown mode raises.

### 9.5 Provisional replay files (so Role A can integrate before real data)
Write `ml/replay/rest.csv` + `.json` and `ml/replay/exertion.csv` + `.json` with **clearly synthetic** values (rest: hr 72–76, spo2 97–98, baseline 74; exertion: hr starting at 108 and decaying to 92 over 90 s, spo2 96–98, baseline 74) and `"source": "synthetic-placeholder"` in the JSON. They are replaced by real recordings in Phase 8. Never use the placeholders in the demo; Phase 10 checks this.

### Gate 5
`pytest node/bio/tests -q` passes on the laptop and on the Pi. Commit: `bio: replay and manual sources, placeholder replay files`. Tell the human: "Role A can now integrate `node.bio` with `--bio replay:rest`."

---

## 10. Phase 6 — Data collector (≈ 2 h)

**Dependency:** Role A's `node/vision/features.py` (`VisionFeatureExtractor`) exists and works on the Pi, and their gesture calibration is committed (`node/vision/gesture_params.json`). Check with `git pull` and `ssh icu-pi '... python -c "from node.vision.features import VisionFeatureExtractor"'`. If missing: build and test the collector with Role A's `SyntheticVision` (or a local stand-in with the same interface) and tell the user what is blocking the real session.

### 10.1 Output files (all on the Pi in `~/icu-data/raw/`)
Per trial, base name `{person}_{scenario}_T{trial}_{YYYYmmdd-HHMMSS}`:
- `..._windows.csv` — one row per 3-s window, columns `WINDOW_COLUMNS` (§6.1)
- `..._bio.csv` — one row per second: `t_s, hr, spo2, finger, quality` (live) or the interpolated values (manual)
- `..._meta.json` — person, scenario, label, trial, bio_mode, baseline_hr, light, gesture_hand, start/end time, `delay_s` (seconds between finishing exercise and starting the trial, exertion scenarios only), operator notes, `discarded` flag, software git commit hash
Per person: `{person}_baseline.json` (baseline HR, method, 60-s per-second values) and `{person}_session_log.txt` (every prompt and answer with timestamps, including the consent confirmation).
Special recordings for replay: `{person}_R1_rest_...` (the 60-s baseline, saved as a `_bio.csv`) and `{person}_R2_exertion_...` (90 s straight after exercise).

### 10.2 `ml/collect/trial.py` and `recorder.py`
`run_trial(vision, bio, person, scenario, trial, seconds=30, ...)`:
1. Call `vision.window()` once and discard it (clears frames from before the trial).
2. For `seconds / 3` windows: sleep until the next 3-s mark (monotonic schedule), call `vision.window()` and (live) `bio.window()`; build the row. Print one line per window: `w3 g=0.91 tr=0.012 hand=1.0 hr=96 Δ22 spo2=98`.
3. Manual mode: windows are buffered; bio values are filled in after the trial when the end values are known.
4. Write the three files. `window_idx` starts at 0.

### 10.3 `ml/collect/session.py` — guided runner (interactive, run by the human)
CLI: `python -m ml.collect.session --person P1 --bio live|manual [--resume] [--only S3,S5]`.
Takes the hardware lock for the whole session; starts `VisionFeatureExtractor` and the bio source once.

Flow, with a clear prompt and "press Enter to start" before every step:
1. **Consent and safety:** print the safety rules (§0.4) and ask: "Does P1 agree to take part, and is P1 fine to do light exercise? (y/n/no-exercise)". With `no-exercise`, all exertion scenarios are skipped for that person.
2. **Setup check (20 s):** live view of `gesture_conf`, `hand_present`, HR. Prompts the participant to hold the palm up for a few seconds and rest it; continue only when hand detection works.
3. **Baseline (60 s):** seated, sensor finger on, other hand resting in view. Live: `calibrate_baseline(60)`. Manual: reference reading typed at the start and end; baseline = mean. Saves `{person}_baseline.json` and the `R1_rest` recording.
4. **Rest block:** S1, S2, S3 × 3 trials each, in a fixed shuffled order per person (seeded by the person code, printed at the start), then H1 (dim the lights — prompt), H2. Between trials: 15 s pause.
5. **Exertion block:** for each of S4 × 3, S5 × 3, H4 × 1, H3 × 1 (alternating S4/S5):
   - "Do 60 seconds of spot jogging (or jumping jacks) now. **Stop at once if you feel dizzy or unwell.**" (H3: "Walk briskly on the spot for 60 seconds.") A 60-s countdown is shown.
   - "Sit, put the sensor finger back, raise / rest the other hand as instructed, then press Enter." `delay_s` is recorded; if > 20 s, print a warning.
   - Run the trial.
   - **Recovery:** wait at least 2 minutes and until live HR (or the reference reading) is within baseline + 10 bpm before the next exercise.
6. **Replay recording R2:** a final 60 s of exercise, then a 90-s recording seated, finger on, no gesture (bio only).
7. After every trial, show the summary (mean gesture, hand %, mean hr_delta, finger %) and ask: `k` keep / `r` redo (marks this one `discarded` in its meta and repeats it) / `n` add a note.
8. `--resume` reads the person's existing `_meta.json` files and skips completed (non-discarded) trials.

Scenario instructions printed to the participant (exact text):
| Code | Instruction |
| --- | --- |
| S1 | "Rest your gesture hand in view of the camera. Stay relaxed." |
| S2 | "For 30 seconds, move naturally: scratch your face, adjust your sleeve, shift your hand, touch your hair. Do NOT hold the palm up." |
| S3 | "Hold your open palm up towards the camera, fingers spread, for the whole 30 seconds. You may rest your elbow on the table." |
| S4 | "Rest your gesture hand in view of the camera. Do not make the gesture." |
| S5 | "Hold your open palm up towards the camera for the whole 30 seconds." |
| H1 | Same as S3 (lights dimmed). |
| H2 | "Hold your hand up towards the camera with the fingers half bent, as if you were weak, for 30 seconds." |
| H3 | Same as S5 (after brisk walking only). |
| H4 | Same as S2 (after exercise). |

Sensor rules printed at the start: "Left index finger rests lightly on the sensor (don't press). Keep that hand still on the table. Use your right hand for gestures (left-handed people may swap; tell the operator)." `gesture_hand` is recorded.

### 10.4 Dry run
[LAPTOP] run `session.py` with `SyntheticVision` and `--bio manual` for one short scenario (seconds reduced via a hidden `--seconds 6` flag) into a temp folder; then run `ml/validate_data.py` on that folder to prove the formats match. [PI] run it once with the real camera and live/manual bio for S1 and S3 only (`--only S1,S3 --seconds 9`, person `PTEST`), then delete `PTEST` files on the Pi.

### Gate 6
Dry run on the laptop and on the Pi produce files that `validate_data.py` reads without errors. Commit: `ml: data collector and guided session`.

---

## 11. Phase 7 — [HUMAN] Data collection session (Fri 08:30–11:00, or start Thu evening)

### 11.1 Before starting (checklist to give the human)
- Pi powered with the official supply, cool; camera placed as in Role A's calibration; lights on; plain background.
- Nothing else running on the Pi (`cat /tmp/icu-hw.lock` shows no holder; Role A's node stopped).
- Reference oximeter charged (if used). Water. Space to jog on the spot. A chair.
- Everyone has read the safety rules.
- Time per person ≈ 40–45 minutes (rest block ~10 min, exertion block ~25–30 min with recovery, R2 ~3 min).

### 11.2 Running it
For each person (P1, then P2, then P3):
1. [HUMAN] `ssh -t icu-pi`, `tmux new -s collect` (or `tmux attach -t collect`), `cd ~/icu-fusion && .venv/bin/python -m ml.collect.session --person P1 --bio <live|manual>` (decision from §8.6).
2. Follow the prompts. If the connection drops, reconnect and `tmux attach -t collect`; if the program stopped, rerun with `--resume`.
3. Between people, you (Claude Code) check progress: `ssh icu-pi 'ls ~/icu-data/raw | wc -l'` and run a quick count of `_windows.csv` per person.

### 11.3 After the session
1. [LAPTOP] `scp 'icu-pi:~/icu-data/raw/P*' ml/data/raw/` (P1, P2, P3 files only; no `PTEST`).
2. `python -m ml.validate_data ml/data/raw` → `ml/results/data_report.md`. Show the human the flags.
3. If a flagged trial looks like an operator mistake (e.g. hand out of frame for most of an S3 trial), ask the human whether to re-record it **now** (they're still together). Never drop or relabel it on your own.
4. Commit the data: `git add ml/data/raw ml/results/data_report.md`; message `ml: collected dataset (P1-P3)`. Confirm there are no names, no images.

### Gate 7
`validate_data.py` exits 0 (every label ≥ 60 windows; ≥ 2 people with S1–S5). Flags reviewed with the human.

---

## 12. Phase 8 — Train, evaluate, export, replay files (Fri 11:00–14:00)

### 12.1 Fixed exclusions (the only data removed)
1. `window_idx == 0` of every trial (the participant is settling in).
2. Trials marked `discarded` (redone during the session).
3. Windows where `hr_delta` or `spo2` is missing (live mode, no valid reading). Count and report them per scenario.
Nothing else is removed, including flagged trials.

### 12.2 Run
1. `python -m ml.train --data ml/data/raw --out ml/results --models ml/models`.
2. `pytest ml/tests -q` again, now including a parity check against the **real** exported model on the real data (add a test that runs only if `ml/models/model.json` exists and `ml/data/raw` has files).
3. Sanity checks (report each, don't "fix" by tuning):
   - The model's critical recall on held-out people.
   - Whether `hr_delta` has a large positive coefficient for `critical` and `gesture_conf` large for `urgent` and `critical` (expected); state what was actually found.
   - The SpO₂ coefficient (expected near zero, because healthy volunteers stay at 96–99%).
   - Model vs rule vs gesture-only: accuracy, macro-F1, alert false-positive rate, critical recall.

### 12.3 Replay files from real recordings — `ml/make_replay.py`
CLI: `python -m ml.make_replay --rest <person>_R1 --exertion <person>_R2`.
- Pick the person whose R2 recording has the highest valid-HR coverage and an initial `hr − baseline ≥ 20` (print the candidates and let the human choose if more than one qualifies).
- Rest file: their 60-s R1 `_bio.csv`; exertion file: their 90-s R2 `_bio.csv`.
- Fill gaps of up to 3 s by linear interpolation; if more than 20% of seconds are missing, refuse and pick another person.
- Write `ml/replay/rest.csv/.json` and `exertion.csv/.json` with the real `baseline_hr`, `"source": "MAX30100"` or `"manual"`, the person code and the recording time. This overwrites the placeholders.
- Check with `ReplayBio`: rest windows give `hr_delta` within ±5; the first 30 s of exertion give `hr_delta ≥ 15`. If the exertion file doesn't reach +15 in its first 30 s, tell the human (the demo's critical step would then depend on gesture alone) and ask whether to record a new R2.

### 12.4 Integration check with the real model
[LAPTOP] Simulate the demo moves through the runtime: for each pair (gesture 0.05 / 0.9) × (rest / exertion replay first 30 s), compute `predict_proba`. Expected: rest + no gesture → routine; rest + gesture → urgent; exertion + gesture → critical; exertion + no gesture → routine. Report the table. If any of the four disagrees, tell the user plainly; this matters for the demo script. Do not adjust the model to force it.

### Gate 8
`metrics.md`, charts, `model.json`, `model.joblib`, real replay files exist; parity tests pass; the four-case table is reported. Commit: `ml: trained model, evaluation, real replay files`. Push, then tell the human: "Tell Role A the model and replay files are pushed (`ml/models/model.json`, `ml/replay/`)."

---

## 13. Phase 9 — Results write-up and handoff

### 13.1 `docs/ML_RESULTS.md` (for the report)
Write only facts from `metrics.json` and the notes; no invented numbers.
1. **Data:** participants (count, P-codes only), scenarios with labels (§6.1 table), trial counts, windows per label after exclusions, exclusions and why, bio mode (live/manual), reference device used.
2. **Sensor:** MAX30100 settings, validation table (§8.6), statement that SpO₂ is approximate/uncalibrated.
3. **Features:** definitions (gesture_conf and tremor from Role A's notes; hr_delta = HR − personal resting baseline; SpO₂).
4. **Method:** 3-class multinomial Logistic Regression, standardised features, `class_weight="balanced"`, `C=1.0`, no tuning; leave-one-person-out; the fixed rule and the gesture-only rule.
5. **Results:** the comparison table (model / rule / gesture-only: accuracy, macro-F1, alert precision/recall/FPR, critical precision/recall); confusion matrices; per-person accuracy; random-split vs LOPO with the one-sentence explanation; coefficients table and chart with a plain reading of each.
6. **Honest discussion:** small simulated dataset from healthy students; exercise as a stand-in for distress; SpO₂ barely varies; the rule baseline's performance (whatever it is); what the model adds (graded probabilities, learned weights) and does not (clinical validity).
7. **Demo note:** biosignals are replayed from the recordings named in the replay JSONs; gesture is live.

### 13.2 Message for Role A (print it for the human to send)
"Model and replay files are pushed. `ml/models/model.json` (classes routine/urgent/critical, features gesture_conf, tremor, hr_delta, spo2). Replay: rest baseline X bpm, exertion starts at +Y bpm. Live sensor: <works / doesn't>; use `--display-bio <live|none>`. Four-case check: <table>."

### Gate 9
`docs/ML_RESULTS.md` complete; `ROLE_B_NOTES.md` complete. Commit: `docs: ML results and role B notes`.

---

## 14. Phase 10 — Final verification

1. [LAPTOP] `pytest ml/tests node/bio/tests -q` → all pass.
2. [PI] `git pull`; `.venv/bin/python -m pytest node/bio/tests -q` → all pass.
3. [PI] `python -c "from ml.fusion_runtime import FusionModel; m=FusionModel.load('ml/models/model.json'); print(m.predict_proba({'gesture_conf':0.9,'tremor':0.02,'hr_delta':25,'spo2':98}))"` prints probabilities with `critical` highest (or report what it shows).
4. Check the replay JSONs do **not** say `synthetic-placeholder`.
5. If live mode: [PI] `live_monitor.py` for 20 s with a finger on → HR values appear.
6. `git status` clean; pushed.

Final message to the user: results table (model vs rule vs gesture-only), the four-case demo table, live/manual decision, anything cut, and what Role A and the report writers need.

---

## 15. Schedule (Role B)

| When | Phases | Done when |
| --- | --- | --- |
| Thu 22 Oct, morning | 0, 1 (laptop) | Pipeline tested on synthetic data |
| Thu 22 Oct, late morning (after Role A's Pi setup) | 2 | Sensor detected (`0x11`) |
| Thu 22 Oct, afternoon | 3–4, 5 in parallel | HR working or manual decision; placeholder replay files pushed |
| Thu 22 Oct, evening (≤ 20:00 decision) | 6 | Collector dry run passes on the Pi |
| Fri 23 Oct, 08:30–11:00 | 7 | All three people recorded; data validated |
| Fri 23 Oct, 11:00–14:00 | 8 | Model + real replay files pushed for Role A |
| Fri 23 Oct, evening | Full demo run with A and C | Freeze at night |
| Sat 24 Oct | 9, 10 | Results in the report |

Cut order if behind: H1–H4 trials → the random-split comparison → live sensor on the OLED → third participant (two people still allows leave-one-person-out with 2 folds; say so). Never cut: the fixed rule comparison, leave-one-person-out evaluation, real (non-placeholder) replay files.

---

## Appendix B — Node interfaces between Role A and Role B (fixed; identical copy in Role A's plan and `docs/NODE_INTERFACES.md`)

### B.1 Ownership
| Path | Owner |
| --- | --- |
| `node/` (except `node/bio/`), `docs/ROLE_A_NOTES.md` | Role A |
| `node/bio/`, `ml/` (including `ml/fusion_runtime.py`, `ml/models/`, `ml/replay/`, `ml/collect/`), `docs/ROLE_B_NOTES.md`, `docs/ML_RESULTS.md` | Role B |
| `node/requirements*.txt`, `node/hwlock.py` | Role A (Role B asks for additions) |

### B.2 Vision (Role A provides) — `node/vision/features.py`
```python
class VisionFeatureExtractor:
    def __init__(self, settings) -> None: ...
    def start(self) -> None: ...          # opens the camera, starts the capture thread
    def window(self) -> dict: ...         # features over all frames since the previous call
    def stop(self) -> None: ...
# window() returns:
# {"hand_present": bool, "gesture_conf": float 0..1 (3 dp), "tremor": float >= 0 (3 dp),
#  "n_frames": int, "n_hand_frames": int, "fps": float}
```
`node.settings.Settings.load()` returns default settings that work for this class.

### B.3 Biosignals (Role B provides) — package `node/bio/`
```python
# node/bio/__init__.py
def make_bio_source(mode: str, settings) -> "BioSource": ...
#   mode: "live" | "replay:rest" | "replay:exertion" | "manual"
class BioUnavailable(Exception): ...      # raised by make_bio_source/start() if the mode can't run

class BioSource:
    kind: str                             # "live" | "replay" | "manual"
    def start(self) -> None: ...
    def window(self) -> dict: ...         # values over the last ~3 s
    def baseline_hr(self) -> int | None: ...
    def stop(self) -> None: ...
# window() returns:
# {"hr": int | None, "spo2": int | None, "hr_delta": int | None,
#  "finger": bool, "source": "live" | "replay" | "manual", "quality": float 0..1}
```
- `live`: reads the MAX30100 (I2C bus 1, `0x57`) through `smbus2`; takes the hardware lock only when run standalone (inside `node.main` the node already holds it); `calibrate_baseline(seconds=60)` sets the baseline. `hr_delta = hr − baseline`.
- `replay:*`: plays `ml/replay/{rest|exertion}.csv` (columns `t_s,hr,spo2`, 1 row per second) in real time, looping; `hr_delta = hr − baseline_hr` from the matching `.json`; restarting the source restarts the file from row 0.
- `manual`: values typed by the operator (used only by the data collector).
- Values are `None` when there is no valid reading (no finger, poor signal).

### B.4 Fusion model (Role B provides) — `ml/fusion_runtime.py` + `ml/models/model.json`
```python
class FusionModel:
    FEATURES = ["gesture_conf", "tremor", "hr_delta", "spo2"]   # fixed order
    CLASSES  = ["routine", "urgent", "critical"]
    @classmethod
    def load(cls, path) -> "FusionModel": ...
    def predict_proba(self, features: dict) -> dict: ...  # {"routine": p, "urgent": p, "critical": p}, sums to 1
```
- NumPy only (no scikit-learn needed on the Pi): `z = (x − mean) / scale`, `logits = W·z + b`, softmax.
- `model.json`: `{"version", "trained_at", "features", "classes", "mean", "scale", "coef" (3×4, rows in "classes" order), "intercept" (3), "n_train", "sklearn_version"}`.
- **Rule baseline** (fixed before data collection, used by both roles): `critical` if `gesture_conf ≥ 0.8 and hr_delta ≥ 15`; `urgent` if `gesture_conf ≥ 0.8`; else `routine`.

### B.5 Hardware lock
`node/hwlock.py`: `with HardwareLock("name"):` takes an exclusive non-blocking `flock` on `/tmp/icu-hw.lock`; raises `HardwareBusy` with the holder's name and PID. Every program that opens the camera or I2C devices uses it.

---

## Appendix C — Wiring and pin map (Raspberry Pi 3 Model B+, 40-pin header; same layout as every 40-pin Pi)

Hold the Pi with the USB/Ethernet ports facing down, the 40-pin header on the right. **Pin 1** is the top-left pin of the header (square solder pad), nearest the corner with the SD card slot on the underside; odd pins are the inner (left) column, even pins the outer (right) column.

| Physical pin | Name | Used for |
| --- | --- | --- |
| 1 | 3.3 V | Breadboard **+ rail** → MAX30100 VIN, OLED VCC |
| 2 | 5 V | Buzzer + (only with the transistor circuit; Role A) |
| 3 | GPIO2 / SDA | Breadboard **SDA row** → MAX30100 SDA, OLED SDA |
| 5 | GPIO3 / SCL | Breadboard **SCL row** → MAX30100 SCL, OLED SCL |
| 6 | GND | Breadboard **− rail** → MAX30100 GND, OLED GND, transistor emitter |
| 9 | GND | Buzzer − (only without the transistor; Role A) |
| 11 | GPIO17 | Buzzer control (Role A) |

MAX30100 board pins `INT`, `IRD`, `RD` stay **unconnected**. Expected `i2cdetect -y 1` with everything attached: `3c` (OLED) and `57` (MAX30100).

Rules: wire only with the power unplugged; never connect 5 V (pins 2, 4) to the sensor or OLED; keep wires short; rest the sensor finger lightly (pressing hard stops blood flow and ruins the reading); shade the sensor from strong room light.