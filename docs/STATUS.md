# Project status

Progress view for the finish plan (`docs/FINISH_PLAN.md`).
**Last update:** Sun 25 Oct 2026 (demo day). All test suites were re-run from a clean state for this update.
**Git:** `main` = `origin/main` (`82fd395`, GitHub `Medhachalla/icu-biosignal-fusion`). Nothing has been committed since Thu 22 Oct 17:46.

## Demo readiness at a glance

| Area | Ready for the demo? | Why |
| --- | --- | --- |
| Broker, server, dashboard, fake node | **Yes** | Built, redesigned, every test passes |
| Node software on the laptop (`bed1`) | **Yes, with caveats** | Real MediaPipe on the webcam publishes per the contract (C1–C10 pass). Gesture thresholds are uncalibrated defaults, and the real-hand check was never done |
| Biosignals in the demo | **Placeholder only** | Replay files are `synthetic-placeholder`; no real recording exists |
| Fusion model | **Rule fallback** | No trained model (`ml/models/model.json` missing, no data collected); the node logs `MODEL NOT FOUND, using rule fallback` |
| Raspberry Pi, MAX30100, OLED, buzzer | **No** | Never set up (no SD card); code exists, untested on hardware |
| Demo script, hardware checklist, report notes | **No** | `docs/DEMO_SCRIPT.md`, `docs/HARDWARE_DAY.md`, `docs/REPORT_NOTES.md` not written |

## Phase status (FINISH_PLAN)

| Phase | Status | Gate | Evidence / what's missing |
| --- | --- | --- | --- |
| 0 Audit | done | passed | `5b2066c` |
| 1 Role A software | mostly done | **not passed** | Code + unit tests + C1–C10 committed (`10dd006`). Missing: laptop calibration (P1–P9) and `gesture_params.json` tuning; the [HUMAN] real-hand check (palm → urgent once, `x` + palm → critical once, card on the dashboard); `node/README.md` |
| 2 Role B software | partial | **not passed** | Pipeline, driver, PPG, sources, collector exist and pass tests. Missing: `ml/make_replay.py` + four-case check, `ml.report`, `ml.run_all`, R2 manual readings every 15 s, collector dry run with webcam vision, a live-source test at real 100 Hz, a clearer laptop message for the sensor tools |
| 3 Real data (optional) | not started | n/a | No oximeter session was run; `ml/data/raw/` is empty. Decision never recorded |
| 4 Dashboard redesign (Session B) | done | passed | `82fd395`: redesigned UI, 14 before / 36 after screenshots, §6.7 self-review in `dashboard/design/README.md`, 37 unit tests, 5 Playwright e2e tests |
| 5 End-to-end on the laptop | not started | **not passed** | Full demo with the webcam node + fake node never run; `docs/DEMO_SCRIPT.md` missing |
| 6 Hardware-day kit | not started | **not passed** | `node/tools/pi_bootstrap.sh` and `docs/HARDWARE_DAY.md` missing (the other Pi scripts exist and pass `bash -n` + ShellCheck) |
| 7 Final docs | not started | **not passed** | Root `README.md` doesn't cover the node, webcam or new dashboard; `docs/REPORT_NOTES.md` missing |

## Components

| Component | Status | Evidence | What's left |
| --- | --- | --- | --- |
| Broker (Mosquitto, auth, retain, LWT, WebSockets) | done | B1–B5 pass | — |
| Server (Flask + SQLite, ack, API) | done | 22 unit tests; S1–S8 pass | — |
| Dashboard (redesigned nurse-station UI) | done | 37 unit tests, build OK, 5/5 Playwright; screenshots in `dashboard/design/after/` | — |
| Fake node (`sim/fake_node.py`) | done | N1–N12 pass | — |
| Run scripts (`start_all`, `stop_all`, `reset_demo`) | done | used in every test run | `start_all.sh` was not re-run against the redesigned dashboard (same `npm run dev`) |
| Node runtime (`node/main.py`, settings, payload, MQTT, control, run log, fusion adapter) | done | 42 `node/tests`; `verify_node_contract.py` C1–C10 pass | Real-hand gate (Phase 1) |
| Vision (camera, MediaPipe Tasks, geometry, features, synthetic) | done (code), **uncalibrated** | geometry tests; webcam 10 fps, 32 ms inference (22 Oct) | Calibration P1–P9 on the laptop; re-check on the Pi |
| Vision tools (`fps_test`, `vision_probe --calibrate`, `preview`) | done | all run on the laptop | Calibration run by a human |
| Hardware lock (`node/hwlock.py`) | done | unit test; Role B tools use it | — |
| `node/requirements.txt`, `-pi.txt` | done | install cleanly into `.venv` | Pi install untested (MediaPipe wheel for Python 3.11 aarch64) |
| OLED (`node/local_io/oled.py`) | done (code) / hardware-blocked | formatter tests; `--mock-io` shows the screen in the log | Real screen on the Pi |
| Buzzer (`node/local_io/buzzer.py`) | done (code) / hardware-blocked | pattern scheduler tests; mock beeps in the log | Real beeps on the Pi |
| Pi / demo scripts (`pi_check`, `deploy`, `set_broker`, `run_demo`, `kill_node`, `stop_node`) | done | `bash -n` + ShellCheck clean; `pi_check` on the laptop passes (Pi lines skipped) | Laptop `run_demo`/`kill_node`/`stop_node` not yet exercised in a demo run |
| Pi bootstrap (`node/tools/pi_bootstrap.sh`) | **missing** | — | Phase 6 |
| Bio driver (`node/bio/max30100.py`) | done (code) / hardware-blocked | 7 parse tests | Bring-up on the Pi |
| Sensor tools (`node/bio/tools/`) | partial | all 6 written | On this laptop they report `Permission denied: '/dev/i2c-1'` (the laptop has its own I2C bus); should say clearly "not a Pi / no MAX30100" |
| PPG maths (`node/bio/ppg.py`) | done | 9 tests, 1 skipped (needs a real recording) | Real-recording check on the Pi |
| Bio sources (live, replay, manual) | done | `test_live.py`, `test_sources.py` | Live test runs the fake sensor 4× faster than real time; FINISH asks for real 100 Hz |
| Collector (`ml/collect/`) | partial | laptop dry run with stand-in vision; can now load the real webcam vision | Webcam dry run; R2 manual readings every 15 s; delete PTEST files after |
| Training / evaluation / export / runtime | done | 16 `ml/tests`, 1 skipped (needs a real model); parity < 1e-9 | Run on real data |
| Replay files (`ml/replay/`) | **placeholder** | `"source": "synthetic-placeholder"`; the node warns at startup | `ml/make_replay.py` + real R1/R2 recordings |
| Replay builder `ml/make_replay.py` + four-case check | **missing** | — | Phase 2 |
| Pipeline runner `ml.run_all` | **missing** | — | Phase 2 |
| Results generator `ml.report` → `docs/ML_RESULTS.md` | **missing** | — | Generator in Phase 2; the document needs real data |
| `docs/DEMO_SCRIPT.md` | **missing** | — | Phase 5 |
| `docs/HARDWARE_DAY.md` | **missing** | — | Phase 6 |
| `docs/REPORT_NOTES.md`, root `README.md` update, `node/README.md` | **missing** | — | Phase 7 (`node/README.md`: Role A §14) |

## Definition of done (FINISH_PLAN §1)

| # | Item | Status |
| --- | --- | --- |
| 1 | `./start_all.sh` starts broker, server and the redesigned dashboard | Yes (same scripts; dashboard served by `npm run dev`) |
| 2 | `python -m node.main --node bed1 --vision camera --bio replay:rest` runs real node code on the webcam; fake node as `bed2` | Code works (camera run on 22 Oct, C1–C10). Not run together with the fake node and dashboard |
| 3 | Full demo script works on the laptop | **Not done** (Phase 5) |
| 4 | Role B software complete and tested | **Partial**: replay builder, `ml.run_all`, `ml.report` and collector extras missing |
| 5 | Real data → real model, replay files, `ML_RESULTS.md`; otherwise pipeline proven on synthetic data and runnable in one command | **Not met**: no real data, and no one-command runner yet |
| 6 | Dashboard redesigned and verified with screenshots | **Yes** |
| 7 | Pi reduced to a checklist (`HARDWARE_DAY.md` + bootstrap script) | **Not done** |
| 8 | All tests pass; docs and report material written | Tests: **yes**. Docs and report material: **no** |

## Test results (Sun 25 Oct, clean state, broker started for the run)

| Suite | Result |
| --- | --- |
| `tests/verify_steps_1_2.py` (B1–B5, N1–N12) | 17/17 PASS |
| `pytest server/tests` | 22 passed |
| `tests/verify_server.py` (S1–S8) | 8/8 PASS |
| `pytest node/tests` | 42 passed |
| `node/tests/verify_node_contract.py` (C1–C10, synthetic vision, rule fusion) | 10/10 PASS |
| `pytest node/bio/tests` | 31 passed, 2 skipped (real sensor recording; Role B's lock stand-in, now replaced by `node/hwlock.py`) |
| `pytest ml/tests` | 16 passed, 1 skipped (real model + data) |
| `dashboard`: `npm test` | 37 passed (3 files) |
| `dashboard`: `npm run build` | OK (JS 537 kB, 167 kB gzip; CSS 18 kB; Inter font bundled locally) |
| Playwright (`tests/e2e/dashboard.spec.js`) | 5/5 passed (theme persists; critical → keyboard ack → response time → gone after reload; server down; broker unreachable banner; Last Will offline) |

## Open problems found in this update

- **Webcam is off again:** `/dev/video0` is missing. Press the laptop's camera key before any camera run.
- **Gesture thresholds are uncalibrated:** `node/vision/gesture_params.json` still says "plan defaults; not calibrated yet". No calibration file exists in `~/icu-data/logs/`. The rule (and the demo's urgent step) depends on an open palm scoring ≥ 0.8.
- **The demo runs on the rule, not a model:** there's no `ml/models/model.json`, so the node uses the fixed rule. The dashboard may show its "Rule fallback" badge.
- **Replayed biosignals are synthetic:** the dashboard's "Biosignals replayed" disclosure is true, but the plan (Role B §9.5) says the placeholders must never be used in the demo. For today, either state clearly that the replayed vitals are synthetic placeholders, or skip the exertion story.
- **The Pi was never set up:** the demo has to use the laptop as `bed1` (the fallback in Role A §15).

## Decisions log

| When | Decision |
| --- | --- |
| Phase 0 | Pi model is the 3B+ (FINISH_PLAN wins over the older Pi 4B PDF). |
| Phase 1 | MediaPipe Tasks API (1.1.1 has no `mp.solutions`); `numpy<2` only on the Pi; tremor = wrist-relative, size-normalised fingertip, `(std x + std y)/2` per window; OLED line `Bio: REPLAY …` to fit 21 characters. Details in `docs/ROLE_A_NOTES.md`. |
| Phase 3 | Not run: no data collection session took place. |
