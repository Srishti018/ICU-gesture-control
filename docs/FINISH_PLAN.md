# Finish Plan — Everything Except Hardware, Today

**Project:** ICU Gesture + Biosignal Fusion System (CBIT IIoT, Team 1)
**Written:** Thu 22 Oct 2026, 17:00. **Target:** all software finished by end of day today. **Demo:** Sun 25 Oct 2026.
**Machine:** the repo owner's Ubuntu laptop. One person now builds everything here; Role A's prototype has been imported into `node/prototype/`.

This file is the top-level instruction for Claude Code. It does **not** replace the detailed plans; it tells you what to finish, in what order, and what "finished" means:

| Detailed plan | Use it for |
| --- | --- |
| `docs/ROLE_A_IMPLEMENTATION_PLAN.md` | Node, vision, MQTT publishing, OLED/buzzer code, Pi tooling (Appendix A = MQTT contract, B = interfaces, C = wiring) |
| `docs/ROLE_B_IMPLEMENTATION_PLAN.md` | Sensor driver, HR/SpO₂ maths, bio sources, data collector, training, evaluation, export, replay files |
| `docs/ROLE_C_IMPLEMENTATION_PLAN.md` | Broker, server, existing dashboard (already done) |
| `docs/CONTEXT_FOR_ROLE_A.md` | Current-state summary (written before this plan) |

Where this file and a detailed plan disagree, **this file wins**. Where a detailed plan says "[PI]" or a hardware "[HUMAN]" step, skip it now and record it in `docs/HARDWARE_DAY.md` (Phase 6).

Hardware facts: **Raspberry Pi 3 Model B+** (1 GB RAM, Raspberry Pi OS Lite 64-bit). No working SD card yet. The MAX30100, OLED and buzzer have **not** been tested.

---

## 0. Rules for Claude Code

1. **Order:** Phase 0 → 7. Each phase ends with a Gate; pass it before moving on. Phase 4 (dashboard) may run in a **second Claude Code session in parallel** with Phases 1–3 (see §0.9).
2. **"Finished" means final product quality, not a first version:** complete error handling, clear log messages, tests, docs, no TODOs or placeholder text left in code or UI (except the placeholder replay files, which are explicitly labelled until real data replaces them).
3. **The MQTT contract (Role A plan, Appendix A; `docs/contracts.md`) and the interfaces (Appendix B; `docs/NODE_INTERFACES.md`) are fixed.** Never change topics, payload fields, types, QoS, retain, level names, feature order.
4. **Data honesty rules (from the Role B plan, non-negotiable):** labels come from the scenario, never from looking at the numbers; no relabelling or dropping data except the fixed exclusions; synthetic or simulated data never appears in results, charts or the report; `node/prototype/samples.csv` (simulated vitals, binary labels) is never used for results.
5. **Never print, log or commit secrets** (`.env`, `dashboard/.env`, `broker/passwd`). Never run `sudo` on the laptop; if something needs it, stop and tell the user the exact command.
6. **If a test fails, fix the code, never weaken the test.** Same failure after 3 attempts → stop and report.
7. **Commit at the end of every phase** (and after every major sub-step), only the files you changed: `git add <paths>`, never `git add -A` (the other session may have uncommitted work). If a remote exists, push; if not, commit only.
8. **Explain in plain language.** The user is a student under time pressure. At the end of each phase: 3–5 lines on what works, what was fixed, what the Gate showed, what the user must do (if anything).
9. **Two parallel sessions (recommended):** Session A runs Phases 0–3 and 5–7. Session B runs Phase 4 (dashboard) only and touches only `dashboard/` and `tests/e2e/`. Session B starts after Phase 0's audit is committed. If `.git/index.lock` exists when committing, wait a few seconds and retry; never delete it while the other session might be committing.
10. **Stop and ask the user when:** a contract conflict appears; something needs `sudo`; the webcam is needed for a [HUMAN] check (e.g. "hold your palm up"); data collection people/oximeter are needed (Phase 3); anything would delete data.

---

## 1. Definition of done for today

By the end of today, on this laptop, **without any Raspberry Pi hardware**:

1. `./start_all.sh` starts broker, server and the redesigned dashboard.
2. `python -m node.main --node bed1 --vision camera --bio replay:rest` runs the **real node code with the laptop webcam** as `bed1`: real MediaPipe gesture and tremor, replayed biosignals, the fusion model (or the rule fallback until a real model exists), publishing to the broker exactly per the contract. The fake node runs as `bed2`.
3. The full demo script works on the laptop: calm → incidental movement → palm (urgent) → `x` + palm (critical) → acknowledge on the dashboard → kill the node (OFFLINE via Last Will) → restart.
4. Role B's software is complete and tested: driver + HR/SpO₂ maths (tested on synthetic signals), live/replay/manual sources, the guided data collector (runs on the laptop **and** the Pi), training/evaluation/export pipeline, replay builder, results write-up generator.
5. **If real data was collected today (Phase 3):** a real model and real replay files exist, and `docs/ML_RESULTS.md` is written from them. Otherwise: the pipeline is proven on synthetic data and runs in one command on Friday.
6. The dashboard is redesigned to the spec in Phase 4 and verified with screenshots.
7. The Pi is reduced to a checklist: `docs/HARDWARE_DAY.md` + a one-command Pi bootstrap script. Hardware day = flash card → run bootstrap → wire → run sensor/OLED/buzzer bring-up → calibrate camera → run demo.
8. All tests pass; docs and report material are written.

---

## 2. Phase 0 — Audit everything (≈ 30 min)

1. `git status`, `git log --oneline -30`, tree (excluding `.git`, `.venv`, `node_modules`).
2. Run every existing test suite and record results: `tests/verify_steps_1_2.py`, `pytest server/tests`, `tests/verify_server.py`, `npm test` + `npm run build` in `dashboard/`, Playwright if configured, and anything already in `node/`, `node/bio/`, `ml/`. (Start the broker first if needed.)
3. Compare the repo against the target file lists in the Role A plan §4.1 and Role B plan §4.1. For each target file: exists / partial / missing.
4. **Review `node/prototype/`** (Role A's first prototype) and list, concretely:
   - what is reusable (MediaPipe handling, gesture score idea, tremor relative to the wrist, train/test split by trial)
   - what is superseded (its `collect.py`/`train.py` → `ml/collect/`, `ml/train.py`)
   - what is wrong for the final product: simulated vitals in `samples.csv`; binary labels; post-hoc relabelling/dropping in `train.py`; `cv2.imshow` (won't work on a headless Pi); per-row 0.5-s samples instead of 3-s windows; `.pkl` model instead of the JSON runtime.
5. Check `docs/NODE_INTERFACES.md` exists and matches Role A plan Appendix B (create it from Appendix B if missing).
6. Write **`docs/STATUS.md`**: one table, rows = every component (broker, server, dashboard, fake node, node runtime, vision, OLED, buzzer, Pi tooling, bio driver, PPG maths, bio sources, collector, training, export, replay files, results docs), columns = status (done / partial / missing / hardware-blocked), evidence (test or file), what's left. This file is updated at the end of every phase and is the user's progress view.

**Gate 0:** `docs/STATUS.md` committed; all existing tests' results recorded. Commit: `docs: full audit and status table`.

---

## 3. Phase 1 — Role A software, finished on the laptop (≈ 2–3 h)

Follow the Role A plan for everything below, building on the prototype where §2.4 found it reusable.

| Role A plan section | Do now | Notes |
| --- | --- | --- |
| §7.1 requirements | ✅ | `node/requirements.txt` + `node/requirements-pi.txt`. Must install cleanly into the repo `.venv` on this laptop. |
| §4.5 / Appendix B.5 `hwlock.py` | ✅ | |
| §7.3–7.5 `camera.py`, `hands.py`, `fps_test.py` | ✅ with the **laptop webcam** | Support both `mp.solutions.hands` and Tasks API; prefer what works with the installed MediaPipe. No `imshow` anywhere outside `tools/`. |
| §8 vision features + unit tests | ✅ | `geometry.py`, `features.py`, `synthetic.py`. Tremor: use the prototype's **fingertip relative to the wrist, normalised by hand size**, computed per 3-s window (std of x and y, combined as in the plan). Record the choice in `docs/ROLE_A_NOTES.md`. |
| §8.4 `vision_probe.py`, `preview.py` | ✅ | `preview.py` must work on the laptop too (`http://localhost:8080`). |
| §9 calibration | ✅ **laptop calibration** | [HUMAN] poses P1–P9 in front of the laptop webcam via `vision_probe.py`. Save `gesture_params.json`. Mark in notes: "laptop calibration; re-check on the Pi". |
| §10 node runtime, MQTT, control, run log, unit tests, `verify_node_contract.py` | ✅ | Test against the local broker. |
| §11 OLED + buzzer code | ✅ code only | Must import lazily and degrade gracefully; add `--mock-io` that prints what the OLED would show and the beep patterns to the log, so the code path is exercised on the laptop. Unit-test the OLED line formatter and buzzer pattern scheduler. |
| §13.1 Pi scripts (`deploy.sh`, `run_demo.sh`, `kill_node.sh`, `stop_node.sh`, `set_broker.sh`, `pi_check.sh`) | ✅ written + `bash -n` + `shellcheck` if installed | Also make `run_demo.sh` / `kill_node.sh` / `stop_node.sh` work **on the laptop** (detect non-Pi: skip `pi_check.sh` hardware lines), so the demo can fall back to the laptop as `bed1`. |
| §6 Pi setup, §7.6 Pi fps, §11 wiring, §12–13 Pi runs | ❌ hardware | Record in `docs/HARDWARE_DAY.md`. |

Additional requirements for "final product":
- `python -m node.main --help` documents every option; startup prints a clear one-screen summary (node id, broker, vision mode, bio mode, fusion mode, OLED/buzzer state).
- Clean shutdown on Ctrl-C (same as `q`).
- If the webcam can't be opened, exit with a clear message naming the camera index tried and how to list cameras.

**Gate 1:** all `node/tests` pass; `verify_node_contract.py` C1–C10 pass (synthetic vision); [HUMAN] with the real laptop webcam: palm held 6 s → `urgent` published once, `x` + palm → `critical` published once, card shown on the existing dashboard. Commit: `node: final node runtime and vision (laptop-verified)`.

---

## 4. Phase 2 — Role B software, finished (≈ 2–3 h)

Follow the Role B plan; everything that doesn't need the sensor.

| Role B plan section | Do now | Notes |
| --- | --- | --- |
| §6 pipeline (schema, rules, runtime, export, synth, validate, train) + tests | ✅ | |
| §8.1 driver (`max30100.py`) + parse tests | ✅ code + tests | No hardware run. |
| §8.2 tools | ✅ written | Each must fail with a clear message on a machine without `/dev/i2c-1`. |
| §8.4 `ppg.py` + tests with synthetic PPG | ✅ | |
| §8.5 `live.py` | ✅ code; test with a fake driver that replays a synthetic PPG at 100 Hz | |
| §9 bio package (replay, manual) + placeholder replay files | ✅ | Placeholder JSONs say `"source": "synthetic-placeholder"`. |
| §10 collector + guided session | ✅ | **Must run on the laptop** with the webcam (`VisionFeatureExtractor`) and `--bio manual`, and on the Pi with `--bio live`. Data folder: `--out` option, default `~/icu-data/raw/`. Add to manual mode for the R2 exertion recording: prompt for a reference reading every 15 s (interpolate between them). |
| §12 replay builder, four-case check | ✅ code; tested on synthetic | |
| §13.1 `ML_RESULTS.md` | ✅ **generator**: `python -m ml.report` builds the document from `metrics.json`, `data_report.md` and notes, with the honest-discussion section written from the actual numbers | Run only on real data. |
| §7 wiring, §8.3 raw checks, §8.6 validation | ❌ hardware | Record in `docs/HARDWARE_DAY.md`. |

Add `ml/run_all.sh` (or `python -m ml.run_all`): validate → train → export → replay files → parity tests → report, in one command, stopping at the first failure. This is what Friday (or tonight) runs after collection.

**Gate 2:** `pytest ml/tests node/bio/tests -q` passes; `ml.run_all` succeeds end-to-end on a synthetic folder (outputs written to a temp folder, never into `ml/results/` or `ml/models/`); a laptop dry run of the collector (`--seconds 6`, person `PTEST`, synthetic or webcam vision, manual bio) produces files that `validate_data` reads. Delete the `PTEST` files. Commit: `ml: final pipeline, bio sources, collector (laptop-verified)`.

---

## 5. Phase 3 — Real data today, on the laptop (optional, ≈ 1.5–2 h with people)

The Pi isn't needed to collect training data: the **laptop webcam** gives real `gesture_conf` and `tremor`, and a **commercial fingertip oximeter** gives real HR/SpO₂ through `--bio manual`. This is honest real data (state in the report: "vision from a webcam, vitals from a commercial pulse oximeter entered by the operator").

1. **Ask the user** (one message): "Do you have a commercial fingertip oximeter, and can 2–3 team members do the guided session today (about 40 minutes each)? Anyone who should skip exercise?"
2. If **yes**: run the Role B plan §10–§12 session on the laptop: `python -m ml.collect.session --person P1 --bio manual --out ml/data/raw/` (the user runs it in a terminal; it is interactive). The laptop webcam must stay in the same position for everyone. Then `ml.run_all` on the real data → real `model.json`, real replay files (from the R1/R2 recordings), `docs/ML_RESULTS.md`.
3. If **no**: skip. Everything stays ready for Friday on the Pi (or on the laptop, if an oximeter turns up).
4. Either way, record the decision in `docs/STATUS.md`.

**Gate 3 (only if collected):** `validate_data` exits 0; `ml.run_all` succeeds; the four-case check (Role B §12.4) is reported; replay JSONs no longer say `synthetic-placeholder`. Commit: `ml: real dataset, model, replay files and results`.

---

## 6. Phase 4 — Dashboard redesign (Session B, ≈ 3 h)

The current dashboard works and is tested; its look and flow need a major upgrade. Redesign the UI **without changing its data behaviour**: same MQTT subscriptions, same ack payload, same Flask API, the live view still works when Flask is down.

### 6.1 Process
1. Load the `frontend-design` skill if your environment offers it.
2. **Before screenshots:** with broker + server + `npm run dev` + fake nodes `bed1` and `bed2`, use Playwright to capture the current UI at **1366×768** and **1920×1080** in these states: empty (no nodes), all routine, one urgent, one critical, one offline, replay badge, Flask down. Save to `dashboard/design/before/`.
3. Build the redesign (§6.2–6.6).
4. **After screenshots**, same states and sizes, to `dashboard/design/after/`. Review them yourself against the checklist in §6.7, fix what fails, re-shoot.
5. Update the Playwright e2e test for the new UI (use `data-testid` attributes so tests don't depend on text or CSS) and extend it with the new flows (§6.8).

### 6.2 Who it's for and what it must do at a glance
- A nurse 2 m away must answer in under 2 seconds: **Is anyone in trouble? Which bed? How bad? Since when?**
- An examiner watching the demo must understand without explanation: what the levels mean, that biosignals are replayed, that a device went offline, that the alert was acknowledged and how fast.

### 6.3 Layout
```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Top bar: product name · ward "ICU · Demo ward" · live status (broker/server)  │
│          · REPLAY disclosure chip · clock · sound toggle · theme toggle       │
├──────────────────────────────────────────────────────────────────────────────┤
│ Alert strip (only when an alert is active): highest-severity first, one row   │
│ per active alert: bed · level · "for 00:42" · [Acknowledge]                   │
├───────────────────────────────────────────────────┬──────────────────────────┤
│ Bed grid (main area)                               │ Side panel (tabs)        │
│  bed tiles, sorted: critical → urgent → offline →  │  • Activity: live event  │
│  routine, then by bed id                           │    feed (alerts, acks,   │
│                                                    │    online/offline)       │
│                                                    │  • Statistics            │
│                                                    │  • Legend / About        │
├───────────────────────────────────────────────────┴──────────────────────────┤
│ History (collapsible or its own tab/page): full alert log with filters         │
└──────────────────────────────────────────────────────────────────────────────┘
```
At widths below 1100 px the side panel moves under the grid. No horizontal scrolling at 1366×768 or 768 px wide.

### 6.4 Bed tile (the core component)
- **Header:** bed name ("Bed 1" from `bed1`), connection state (dot + word: Online / No heartbeat / Offline), "updated 2 s ago".
- **Severity block:** large level word (ROUTINE / URGENT / CRITICAL) with an **icon and colour** (never colour alone), and when an alert is active, the elapsed time since the alert ("Critical for 00:42"), ticking every second.
- **Vitals:** HR (large, bpm), SpO₂ (%), ΔHR vs baseline (signed, e.g. +24), each with a label and unit. A **sparkline of HR over the last 2 minutes** from routine messages (kept in memory per bed; custom SVG, no chart library).
- **Gesture:** a labelled meter for gesture confidence (0–100%) with the 80% mark shown; tremor as a small number with a label.
- **Model output:** a single horizontal stacked bar of p(routine/urgent/critical) with the percentage of the winning class labelled.
- **Badges:** "Biosignals: replay" (clear, not alarming), "Rule fallback" if the probabilities look one-hot (optional).
- **Actions:** a large **Acknowledge** button when an alert is active; after clicking, "Acknowledging…" then "Acknowledged · response 8.2 s" (from the server) or the existing "Not confirmed — is the server running?" + retry.
- **States:** routine (calm, low visual weight), urgent (amber border/accent), critical (red, stronger, a pulse animation for the first 10 s only), offline (desaturated, "No signal since 10:02:11 · device disconnected"), no heartbeat (warning row), waiting for first data (skeleton).

### 6.5 Visual system
- Two themes: **dark** (default on the laptop) and **light / high-contrast** (for a projector, where dark UIs wash out). Toggle in the top bar; remember the choice in `localStorage` (wrapped in try/catch); respect `prefers-color-scheme` on first load.
- Colour tokens as CSS variables; severity colours that pass WCAG AA contrast for text in both themes. Routine must not be bright green everywhere; keep the screen calm when nothing is wrong so alerts stand out.
- Typography: one sans-serif family bundled locally (e.g. `@fontsource/inter` or `@fontsource/ibm-plex-sans`; **no internet fonts**, the demo network may be offline); tabular numbers for vitals and timers; clear size hierarchy (level word ≫ HR ≫ other vitals ≫ labels).
- Icons: `lucide-react` (small, tree-shaken). No UI framework, no Tailwind; plain CSS (CSS modules or one well-organised stylesheet with tokens).
- Motion: subtle, purposeful (new-alert pulse, value transitions); fully disabled under `prefers-reduced-motion`.
- Spacing on an 8-px grid; consistent radii; no clutter, no decorative gradients.

### 6.6 Behaviour additions
- **Sound:** an "Enable sound" toggle (browsers block audio until the user interacts). When on, a short tone via Web Audio for a new urgent alert and a more insistent pattern for critical; never loops.
- **Keyboard:** Tab reaches every Acknowledge button; Enter/Space acknowledges; visible focus rings.
- **Screen readers:** new alerts announced through an `aria-live="assertive"` region; tiles have accessible names ("Bed 1, critical, heart rate 99").
- **Activity feed:** client-side list of the last 50 events (alert raised, acknowledged with response time, online, offline, heartbeat lost), newest first, with time.
- **Statistics tab:** from `/api/stats` and `/api/alerts`: alerts per level, acknowledged count, mean and max response time per level, offline events; a small SVG bar chart of response times (custom, no chart library).
- **History:** alert log with filters (bed, level, acknowledged/open) and readable times; "History unavailable" state when Flask is down (live tiles keep working).
- **Legend / About:** what routine/urgent/critical mean in this system; "Biosignals in this demo are replayed from real recordings; gesture detection is live"; the four inputs to the model.
- **Connection banner:** if the broker connection drops, a top banner "Live data paused — reconnecting…" and tiles show "stale" timers.
- **Empty state:** "Waiting for bed devices… Start a node or the fake node." with the command.

### 6.7 Self-review checklist (all must be true in the after-screenshots)
- From the 1366×768 screenshot with one critical bed: the critical bed, its level and its alert age are the most prominent things on screen.
- Every state from §6.1 looks intentional (no broken layout, no overlapping text, no empty boxes).
- Nothing relies on colour alone; text contrast AA in both themes.
- No placeholder text, lorem ipsum, or debug output.
- Works at 768, 1366 and 1920 px wide without horizontal scroll.
- Light theme is readable on a projector (high contrast, no thin grey text).

### 6.8 Tests
- Keep and update `nodesReducer` tests; add tests for: severity sort order, alert-age formatting, HR history buffer (max 2 min), activity-feed reducer, rule-fallback detection.
- Playwright e2e: critical → banner/alert strip → acknowledge → "Acknowledged · response N s" → reload shows no active alert; offline via fake node `k` → tile shows Offline; Flask stopped → "History unavailable" while live tiles still update; theme toggle persists after reload.
- `npm run build` with no warnings that indicate errors; bundle size reported in the summary.

**Gate 4:** unit tests, build and Playwright pass; before/after screenshots committed; checklist §6.7 all true. Commit: `dashboard: redesigned nurse-station UI`.

---

## 7. Phase 5 — End-to-end on the laptop (≈ 45 min)

1. `./stop_all.sh` → `./scripts/reset_demo.sh` (broker running first, per Role C's README) → `./start_all.sh`.
2. Start the node as `bed1` with the **laptop webcam** (`node/tools/run_demo.sh` on the laptop, or `python -m node.main --node bed1 --vision camera --bio replay:rest`), and the fake node as `bed2`.
3. [HUMAN] Run the full demo script with the user, watching the redesigned dashboard: calm → scratch face (stays routine) → palm 6 s (urgent) → `x` + palm (critical) → Acknowledge (response time shown) → `r` → kill the node (`kill_node.sh`) → Offline within ~10 s → restart → Online.
4. Record a short table of what happened at each step in `docs/STATUS.md`, plus any problems fixed.
5. Write `docs/DEMO_SCRIPT.md`: the exact on-stage sequence (who presses what, what to say in one sentence per step), for both the Pi (`bed1` on the Pi) and the laptop fallback (`bed1` on the laptop).

**Gate 5:** the full demo works end to end twice in a row on the laptop. Commit: `docs: demo script; e2e verified on laptop`.

---

## 8. Phase 6 — Make hardware day a checklist (≈ 45 min)

1. **`node/tools/pi_bootstrap.sh`** — run once on a freshly flashed Pi (over SSH, from the repo cloned there, or piped from the laptop). It does everything in Role A plan §6.3–6.8 and §7.1 that can be automated, with clear PASS/FAIL output: checks `aarch64` and Bookworm; enables I2C; installs the apt packages; creates the venv with `--system-site-packages`; installs `node/requirements.txt` + `-pi.txt` (with the 3B+ swap fallback); creates `~/icu-data/{logs,raw,models}`; creates `.env` with placeholders and `chmod 600`; runs `pi_check.sh`. It may only use the `sudo` commands listed in the Role A plan. It must be safe to run twice.
2. **`docs/HARDWARE_DAY.md`** — the complete, ordered checklist for when the new SD card arrives, written for a student, with the exact commands and the expected output for each step:
   1. Test the new card with `f3probe` before flashing (expected: "Good news … the real thing").
   2. Flash Raspberry Pi OS Lite (64-bit) with the Imager settings (hostname `icu-pi`, user `pi`, hotspot Wi-Fi, country IN, Asia/Kolkata, SSH on).
   3. SSH key setup; GitHub repo + deploy key, or `scp`/`rsync` from the laptop if there's still no remote (give both).
   4. `pi_bootstrap.sh`.
   5. Camera check + `fps_test.py` on the 3B+ (targets: ≥5 good, 3–5 acceptable, <3 → laptop fallback).
   6. Wiring (power off), with the Appendix C table and a text diagram of the breadboard rails.
   7. MAX30100 bring-up: `i2cdetect`, part ID `0x11`, `finger_threshold.py`, `led_tune.py`, `capture_raw.py`, `validate_hr.py`, and the live/manual decision rule.
   8. OLED and buzzer tests.
   9. Camera placement + calibration re-check (P1, P4, P5, P9).
   10. If no real data yet: data collection on the Pi (or the laptop) → `ml.run_all`.
   11. Full demo run over the hotspot.
   Every step lists: time estimate, what "pass" looks like, and the fallback if it fails.
3. Collect every skipped [PI]/[HUMAN] hardware step from the Role A and Role B plans into `HARDWARE_DAY.md` so nothing is lost.

**Gate 6:** `bash -n` (and `shellcheck` if available) on all scripts; `HARDWARE_DAY.md` covers every skipped hardware step (list them and tick them off against both plans). Commit: `node: pi bootstrap and hardware-day checklist`.

---

## 9. Phase 7 — Final verification, docs and report material (≈ 45 min)

1. From a clean state, run **every** test suite (Role C's 4 suites + Playwright, `node/tests`, `node/bio/tests`, `ml/tests`, `verify_node_contract.py`) and put one results table in `docs/STATUS.md`.
2. `README.md` (root): rewrite as the single entry point: what the system is (with the architecture diagram), quick start on the laptop, how to run the node with the webcam, the fake node, tests, demo reset, where each doc is, hardware status.
3. **`docs/REPORT_NOTES.md`** — material for updating the course report, facts only:
   - final architecture and the role of each component
   - gesture definition and formulas; tremor definition (relative to the wrist; "tremor amplitude", not frequency)
   - MQTT design: severity topics, QoS 0/1, retained alerts and clearing on acknowledge, heartbeat + Last Will, authentication
   - ML: 3 classes, features, leave-one-person-out, rule and gesture-only baselines, results (if real data exists) or "pending data collection"
   - the dashboard's features (with 2–3 after-screenshots referenced by path)
   - honest limitations: no TLS, no topic ACLs, dashboard password in browser JS, Flask dev server, small simulated-distress dataset from healthy students, approximate SpO₂, replayed biosignals in the demo, Pi 3B+ frame rate
   - the list of report corrections from the original implementation plan (Pi model, topic names, retain, Firebase → Flask + SQLite, 3 classes, Drawbacks §8–9 now outdated, "tremor frequency" → "tremor amplitude")
4. `docs/STATUS.md` final: every row done or hardware-blocked, with the reason.
5. `git status` clean; commit `docs: final status, readme and report notes`; push if a remote exists.

Final message to the user: the results table, what's left (hardware only, pointing at `HARDWARE_DAY.md`), and anything they must do personally (e.g. data collection, creating the GitHub repo, buying the oximeter).

---

## 10. Suggested time plan (today)

| Time | Session A | Session B |
| --- | --- | --- |
| 17:15–17:45 | Phase 0 audit | — |
| 17:45–20:30 | Phase 1 (node + vision), then Phase 2 (ML/bio) | Phase 4 dashboard redesign |
| 20:30–22:30 | Phase 3 data collection (if oximeter + people) | Phase 4 finishing, screenshots |
| 22:30–23:15 | Phase 5 end-to-end, Phase 6 hardware kit | — |
| 23:15–24:00 | Phase 7 final verification and docs | — |

If time runs short, cut in this order: Phase 3 (move to Friday) → dashboard statistics chart → activity feed → sound. Never cut: the contract tests, the end-to-end demo run, `HARDWARE_DAY.md`.