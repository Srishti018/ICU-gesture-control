# Audit of Steps 0–2 (Role C)

**Date:** 2026-10-22
**Audited against:** `docs/ROLE_C_IMPLEMENTATION_PLAN.md`

## Summary

The broker, fake node and test script exist and all 17 existing tests (B1–B5, N1–N12) pass; no secrets are in Git.
The main gaps are details: the fake node uses the wrong client ID and value ranges, the broker scripts lack the port check and fixed paths, and `make_passwd.sh` reuses the bed1 password for bed2.
`.env` is missing `BED2_PASS` and `API_PORT`; `.gitignore` had a `lib/` rule that would have hidden `dashboard/src/lib/` (fixed in this phase).

## Secrets check

- `git ls-files | grep -E '(^|/)\.env$|broker/passwd|\.db$'` → nothing.
- `git log --all --oneline -- .env broker/passwd` → nothing.
- `docs/contracts.md` vs Appendix A: same topics, payloads, QoS, retain and rules. Only formatting differs, plus Appendix A's note on per-node acks. No conflict.

## Checklist

| # | Item | Status | Note |
| --- | --- | --- | --- |
| A1 | `.gitignore` | WRONG → fixed | Missing `dashboard/.env`, `server/*.db-*`, `test-results/`, `playwright-report/`; had `lib/`, which would hide `dashboard/src/lib/`. Rewritten in Phase 0. |
| A2 | `.env.example` | WRONG → fixed | Missing `BED2_PASS` and `API_PORT`. Added in Phase 0. |
| A3 | `.env` exists | WRONG | Present; all passwords that exist are non-empty, but `BED2_PASS` and `API_PORT` are missing. User must add them. |
| A4 | System Mosquitto service | OK | `systemctl is-active mosquitto` → `inactive`. |
| A5 | `broker/mosquitto.conf` | WRONG | Relative paths (works only because `start.sh` does `cd`); missing `per_listener_settings false`, `protocol mqtt`, log types, `connection_messages`, timestamps. |
| A6 | `broker/start.sh` | WRONG | Executable. Uses `set -e` only, no port-in-use check, no rendered `/tmp/icu-mosquitto.conf`, runs with `-v`. |
| A7 | `broker/make_passwd.sh` | WRONG | Executable, creates 4 users, chmod 600. But bed2 falls back to `NODE_PASS` instead of requiring `BED2_PASS`, and it accepts a `BED1_PASS` key not in the plan. |
| A8 | `.venv/` | OK | Python 3.12.3; paho-mqtt 2.1.0, python-dotenv 1.2.4. |
| A9 | `sim/fake_node.py` | WRONG | Client ID is `sim_{node}_{pid}_{time}` (should be `node-{node}`, clean session explicit); tremor ranges wrong for all levels; gesture_conf rounded to 2 decimals (should be 3); `p` uses 0.80–0.95 for the top class (should be 0.70–0.90) and the sum is not forced to exactly 1.00; bed2 password falls back to `NODE_PASS`; threads reversed (stdin in a thread, timer in main); publish log lines lack time/QoS/retain; prints not flushed. Correct: keepalive 5, Will before connect, `online` on connect, level-rise rule, heartbeat, stdin commands, EOF keeps running, `q` exits 0, `k` is `os._exit(1)`. |
| A10 | `sim/requirements.txt` | OK | `paho-mqtt>=2.0.0`, `python-dotenv>=1.0.0`. |
| A11 | `tests/verify_steps_1_2.py` | WRONG (minor) | Covers B1–B5 and N1–N12. Gaps: client IDs not `test-` + random; N3 sum tolerance 0.05 (plan: 0.01) and no exact top-level key / type / 3-decimal checks; N5/N6 do not check all value ranges; N12 does not check for disconnects; uses `sys.executable` rather than `.venv/bin/python`. |
| A12 | README | OK | Has Broker and Fake Node sections. |

## Test results (run 2026-10-22, broker already running from `broker/start.sh`)

`.venv/bin/python tests/verify_steps_1_2.py` → **17/17 PASS** (B1–B5, N1–N12).

## Fixes for Phases 1–2

Phase 1 (broker):
1. Rewrite `broker/mosquitto.conf` to §6.1 with `__BROKER_DIR__` placeholders.
2. Rewrite `broker/start.sh` to §6.2: `set -euo pipefail`, passwd check, port check, render to `/tmp/icu-mosquitto.conf`, `exec mosquitto -c`.
3. Rewrite `broker/make_passwd.sh` to §6.3: require all four passwords incl. `BED2_PASS`; print only usernames.
4. Regenerate `broker/passwd` after the user adds `BED2_PASS`; restart the broker; B1–B5 pass.

Phase 2 (fake node):
1. Client ID `node-{node}`, `clean_session=True`; password defaults `NODE_PASS`/`BED2_PASS`.
2. Value ranges and rounding per §7.1; `p` top class 0.70–0.90, sum exactly 1.00.
3. Timer loop in a thread, stdin in main thread; flushed publish lines with time, topic, level, QoS, retain.
4. Tighten `tests/verify_steps_1_2.py` (client IDs, N3/N5/N6 checks, N12 disconnect check, `.venv/bin/python`); 17/17 pass.
