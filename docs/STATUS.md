# Project status

Progress view for the finish plan (`docs/FINISH_PLAN.md`). Updated at the end of every phase.
**Last update:** Thu 22 Oct 2026, Phase 0 (audit).

## Components

| Component | Status | Evidence | What's left |
| --- | --- | --- | --- |
| Broker (Mosquitto, auth, retain, LWT, WebSockets) | done | `tests/verify_steps_1_2.py` B1–B5 pass | — |
| Server (Flask + SQLite, ack, API) | done | `pytest server/tests` 22/22; `tests/verify_server.py` S1–S8 pass | — |
| Dashboard | partial | `npm test` 13/13, build OK, Playwright 1/1 pass | Redesign (FINISH Phase 4, Session B) |
| Fake node (`sim/fake_node.py`) | done | N1–N12 pass | — |
| Node runtime (`node/main.py`, settings, payload, MQTT, control, run log, fusion adapter) | missing | none of the files exist | Phase 1 |
| Vision (`node/vision/`: camera, hands, geometry, features, synthetic, tools) | missing | prototype only (`node/prototype/`) | Phase 1; **no webcam detected on this laptop** |
| Hardware lock (`node/hwlock.py`) | missing | `node/bio/hwlock_compat.py` stand-in exists | Phase 1 |
| `node/requirements.txt`, `-pi.txt` | missing | MediaPipe 1.1.1 dry-run installs into `.venv` with NumPy 2.5 | Phase 1 |
| OLED (`node/local_io/oled.py`) | missing | — | Phase 1 code + `--mock-io`; hardware-blocked for the real screen |
| Buzzer (`node/local_io/buzzer.py`) | missing | — | Phase 1 code + `--mock-io`; hardware-blocked for real beeps |
| Pi tooling (`pi_check`, `deploy`, `run_demo`, `kill_node`, `stop_node`, `set_broker`, `pi_bootstrap`) | missing | — | Phase 1 (scripts) and Phase 6 (bootstrap); running them is hardware-blocked |
| Bio driver (`node/bio/max30100.py`) | done (code) / hardware-blocked | `test_max30100_parse.py` 7 tests | Bring-up on the Pi |
| Sensor tools (`node/bio/tools/`) | partial | all 6 written, `--help` works | Clearer "no `/dev/i2c-1`" message (Phase 2); hardware runs |
| PPG maths (`node/bio/ppg.py`) | done | `test_ppg.py` 9 pass, 1 skipped (needs a real recording) | Real-recording check on hardware day |
| Bio sources (live, replay, manual) | partial | `test_live.py`, `test_sources.py` pass | `live` fake driver should replay at real 100 Hz (Phase 2) |
| Collector (`ml/collect/`) | partial | laptop dry run with stand-in vision passes | Webcam vision (needs Phase 1), R2 manual readings every 15 s (Phase 2) |
| Training / evaluation (`ml/train.py`, `validate_data.py`, rules, runtime) | done | `pytest ml/tests` 16 pass, 1 skipped (needs real model) | Run on real data |
| Export (`ml/export.py`, `ml/fusion_runtime.py`) | done | parity < 1e-9 on synthetic data | — |
| Replay files (`ml/replay/`) | partial (placeholder) | `"source": "synthetic-placeholder"` | Replay builder `ml/make_replay.py` (Phase 2); real recordings |
| Pipeline runner (`ml.run_all`) | missing | — | Phase 2 |
| Results docs (`ml.report` → `docs/ML_RESULTS.md`) | missing | — | Generator in Phase 2; document needs real data |
| Demo script / hardware checklist / report notes | missing | — | Phases 5, 6, 7 |

## Test results (Phase 0, 22 Oct 17:40, broker started for the run)

| Suite | Result |
| --- | --- |
| `tests/verify_steps_1_2.py` (B1–B5, N1–N12) | 17/17 PASS |
| `pytest server/tests` | 22 passed |
| `tests/verify_server.py` (S1–S8) | 8/8 PASS |
| `dashboard`: `npm test` | 13 passed |
| `dashboard`: `npm run build` | OK (JS 504 kB, 158 kB gzip) |
| Playwright (`tests/e2e/dashboard.spec.js`) | 1 passed |
| `pytest node/bio/tests` | 32 passed, 1 skipped (real sensor recording) |
| `pytest ml/tests` | 16 passed, 1 skipped (real model + data) |
| `node/tests` | does not exist yet |

## Target files vs repo

**Role A plan §4.1:** `docs/NODE_INTERFACES.md` exists and matches Appendix B exactly. `docs/ROLE_A_NOTES.md` was created in this audit. Every file under `node/` in §4.1 is **missing**: `__init__.py`, `README.md`, `requirements*.txt`, `settings.py`, `hwlock.py`, `main.py`, `payload.py`, `mqtt_pub.py`, `control.py`, `runlog.py`, `fusion_adapter.py`, `vision/*`, `local_io/*`, `tools/*`, `tests/*`. `bio_stub.py` isn't needed, because Role B's `node/bio/` exists.

**Role B plan §4.1:**
- **Exists:** `node/bio/*` (all files, incl. `tools/` and `tests/`), `ml/__init__.py`, `requirements.txt`, `schema.py`, `rule.py`, `fusion_runtime.py`, `synth.py`, `validate_data.py`, `train.py`, `export.py`, `collect/*`, `tests/test_rule.py`, `test_runtime_parity.py`, `test_pipeline_synth.py`, `replay/*` (placeholders), `docs/ROLE_B_NOTES.md`.
- **Missing:** `ml/make_replay.py`, `ml/models/model.*` (needs real data), `ml/results/*` (needs real data), `docs/ML_RESULTS.md` (needs real data).
- **Extra** (fine): `ml/dataset.py`, `ml/collect/synthetic_vision.py`, `ml/tests/test_collect.py`, `node/bio/hwlock_compat.py`, `node/bio/tests/test_live.py`.

**Added by FINISH_PLAN, missing:** `ml/report.py`, `ml/run_all`, `node/tools/pi_bootstrap.sh`, `node/tools/stop_node.sh`, `docs/HARDWARE_DAY.md`, `docs/DEMO_SCRIPT.md`, `docs/REPORT_NOTES.md`.

## Audit findings

- **Contract:** `docs/contracts.md` matches Role A Appendix A in substance (same topics, payloads, QoS, retain, rules).
- **Missing docs:** `docs/CONTEXT_FOR_ROLE_A.md` is listed in FINISH_PLAN but isn't in the repo or on this laptop. It is only a summary, so it isn't blocking.
- **Plan versions:** `docs/ROLE_A_IMPLEMENTATION_PLAN.md` is the updated Pi 3B+ version. (The PDF in `~/Downloads` is an older Pi 4B version.)
- **No webcam detected** (no `/dev/video*`, nothing in `lsusb`). Phase 1's webcam steps (fps test, calibration poses, `--vision camera` demo) need one.
- **Prototype review:** see `docs/ROLE_A_NOTES.md`. Reused: MediaPipe handling and the wrist-relative, size-normalised tremor. Superseded: `collect.py`, `train.py`. Wrong for the product: simulated vitals, binary labels, post-hoc relabelling, `imshow`, 0.5-s rows, `.pkl`.
- **Hardware lock:** Role A §4.5 asks for the message `HARDWARE BUSY: <name> (pid N) …` and exit code 3. Role B's stand-in switches to `node.hwlock` automatically once it exists.
- **Git:** no remote configured, so commits stay local.

## Decisions log

| When | Decision |
| --- | --- |
| Phase 0 | Pi model is the 3B+ (FINISH_PLAN wins over the older Pi 4B PDF). |
