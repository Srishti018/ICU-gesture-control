# Role C Implementation Plan — Broker, Server, Dashboard

**Project:** ICU Gesture + Biosignal Fusion System (CBIT, IIoT course project, Team 1)
**Scope of this plan:** Role C only — the MQTT broker, the fake node simulator, the Flask + SQLite server, the React dashboard, and the scripts to run them.
**Demo date:** Sunday 25 Oct 2026. Feature freeze: Friday 23 Oct, night.
**Machine:** Ubuntu Linux laptop. This laptop runs the broker, the server and the dashboard on demo day.

---

## 0. Instructions for Claude Code (read first)

You are executing this plan end to end. Follow these rules for the whole plan.

1. **Work phase by phase, in order** (Phase 0 → Phase 7). Each phase ends with a **Gate**: a command or checklist that must pass. Do not start the next phase until the Gate passes.
2. **The MQTT contract in Appendix A is fixed.** Never change topic names, payload fields, QoS or retain rules. If existing code disagrees with Appendix A, fix the code. If `docs/contracts.md` disagrees with Appendix A in substance (not just formatting), STOP and ask the user which is correct.
3. **Stay inside Role C folders:** `broker/`, `sim/`, `server/`, `dashboard/`, `tests/`, `scripts/`, `docs/`, plus root files (`README.md`, `.gitignore`, `.env.example`, `start_all.sh`, `stop_all.sh`). Never create or edit anything in `node/` or `ml/`; other teammates own them.
4. **Never run `sudo`.** If something needs it, stop and tell the user the exact command and why.
5. **Never print secrets.** Passwords live only in `.env` (repo root) and `dashboard/.env`. Never echo them, log them, or commit them. Read them in scripts via `source .env` or python-dotenv.
6. **If a test fails, fix the implementation, never weaken the test.** If the same failure survives 3 fix attempts, stop and report: the test, the error, what you tried.
7. **Commit at the end of each phase** with the commit message given in that phase, after checking `git status` shows no secrets or generated files staged.
8. **Keep the user informed in plain language.** The user is a student, not an expert in these tools. At the end of each phase, give a 3–5 line summary: what was done, what was fixed, what the Gate showed.
9. **When to stop and ask the user:** missing passwords in `.env`; any `sudo` need; a contract conflict; secrets found in Git history; a port already used by something you didn't start; anything that would touch `node/` or `ml/`.

---

## 1. What we are building (context)

A patient's hand gesture (camera + MediaPipe) and vitals (heart rate, SpO₂) are fused on a Raspberry Pi by a 3-class Logistic Regression model into a level: `routine`, `urgent` or `critical`. The Pi publishes the result over MQTT. **Role C builds everything that receives, stores and shows those messages**, plus a fake node that imitates the Pi so all of it can be built and tested without the Pi.

On demo day:
- `bed1` = the real Raspberry Pi (Role A's code, not part of this plan).
- `bed2` = the fake node from this plan, running on a laptop.
- Biosignals on the Pi are replayed from recorded data; messages say so with `bio_source: "replay"`, and the dashboard must show a clear REPLAY badge.

### Features the demo depends on (must work)
| Feature | Why it matters for the demo |
| --- | --- |
| Severity topics with QoS 0 (routine) / QoS 1 (urgent, critical) | Core IoT design argument in the report |
| Retained alerts | Refreshing the dashboard still shows the active alert |
| Heartbeat + Last Will (LWT) | Killing the Pi shows the node OFFLINE |
| Username/password authentication | Claimed in the report |
| Acknowledge button with response time | Report promises response-time data |
| REPLAY badge | Honest disclosure of replayed biosignals |

---

## 2. Environment facts (assume exactly this)

| Item | Value |
| --- | --- |
| OS | Ubuntu Linux |
| Mosquitto | 2.x installed from apt (`mosquitto`, `mosquitto-clients`). The **system service must be stopped and disabled**; we run our own broker as the normal user. |
| Python | System `python3` (3.10+). All Python runs in **one virtual env at the repo root: `.venv/`**. Use `.venv/bin/python` and `.venv/bin/pip` explicitly in scripts. |
| Node.js | LTS (20+) installed via **nvm**. In non-interactive shells, run `source ~/.nvm/nvm.sh` before `npm`/`node`. |
| Ports | 1883 MQTT TCP · 9001 MQTT WebSockets · 5050 Flask API · 5173 Vite dev server |
| Network on demo day | Phone hotspot. The Pi connects to the laptop's IP on port 1883. |

---

## 3. Architecture

### 3.1 Component diagram

```
 ┌──────────────────────────┐            ┌──────────────────────── Laptop (Ubuntu) ─────────────────────────┐
 │ bed1: Raspberry Pi 4B    │            │                                                                  │
 │ (Role A — not this plan) │──MQTT────▶ │  ┌──────────────────────┐   MQTT :1883   ┌─────────────────────┐ │
 └──────────────────────────┘   :1883    │  │ Mosquitto broker     │◀─────────────▶│ Flask server :5050  │ │
                                         │  │ broker/              │                │ server/             │ │
 ┌──────────────────────────┐            │  │ auth · retain · LWT  │                │ MQTT logger thread  │ │
 │ bed2: fake node          │──MQTT────▶ │  │ :1883 TCP            │                │ + SQLite (icu.db)   │ │
 │ sim/fake_node.py         │   :1883    │  │ :9001 WebSockets     │                │ + REST API          │ │
 └──────────────────────────┘            │  └──────────┬───────────┘                └──────────┬──────────┘ │
                                         │             │ MQTT over WS :9001                    │ HTTP :5050 │
                                         │             ▼                                       ▼            │
                                         │  ┌──────────────────────────────────────────────────────────────┐ │
                                         │  │ React dashboard (Vite :5173) dashboard/                      │ │
                                         │  │ live cards from MQTT · alert log + stats from Flask · Ack    │ │
                                         │  └──────────────────────────────────────────────────────────────┘ │
                                         └──────────────────────────────────────────────────────────────────┘
```

### 3.2 Responsibilities

| Component | Does | Does NOT |
| --- | --- | --- |
| Mosquitto | Authenticates clients, routes messages, stores retained messages, fires Last Will | Any logic |
| Fake node | Publishes exactly what the Pi will publish; controlled from stdin | ML, real sensors |
| Flask server | Subscribes to everything; stores alerts, acks, node state; computes response time; clears retained alerts after ack; serves history over HTTP | Live display; it is not on the live path |
| Dashboard | Live state straight from MQTT; history/stats from Flask; publishes acks | Stores nothing permanently |

**Key design rule:** the live view never depends on Flask. If Flask is down, cards still update; only the log and stats show "History unavailable".

### 3.3 Message flows

1. **Live status:** node → `icu/{node}/status/routine` (every 3 s, QoS 0) → dashboard updates the card; Flask updates `node_state`.
2. **Alert:** node → `icu/{node}/status/urgent|critical` (on level rise, QoS 1, retained) → dashboard shows the alert + banner; Flask inserts into `alerts`.
3. **Acknowledge:** dashboard → `icu/{node}/ack` (QoS 1) → Flask marks all open alerts for that node acknowledged, computes response time, then publishes an **empty retained** message to `icu/{node}/status/urgent` and `icu/{node}/status/critical` → broker deletes the retained alerts → dashboard receives the empty payloads and clears the alert.
4. **Liveness:** node → `icu/{node}/heartbeat` every 10 s; node → `icu/{node}/online` = `online` (retained) on connect; on an unclean disconnect the broker publishes the node's Last Will `offline` (retained).

### 3.4 MQTT client IDs and users

| Client | Username | Client ID | Clean session |
| --- | --- | --- | --- |
| Pi | `bed1` | `node-bed1` | true |
| Fake node | `bed1` or `bed2` | `node-{node}` | true |
| Flask logger | `logger` | `logger-server` | true |
| Dashboard (each browser tab) | `dashboard` | `dashboard-` + 8 random hex chars | true |
| Test scripts | any | `test-` + random | true |

Client IDs must be unique. Two clients with the same ID disconnect each other.

---

## 4. Final repository structure (target)

```
icu-fusion/
├── .env                      # secrets, NOT committed
├── .env.example              # committed, no real passwords
├── .gitignore
├── README.md
├── start_all.sh              # opens broker, server, dashboard in gnome-terminal tabs
├── stop_all.sh
├── docs/
│   ├── contracts.md          # MQTT contract (must match Appendix A)
│   ├── AUDIT.md              # written in Phase 0
│   ├── NODE_INTEGRATION.md   # handoff for Role A (Phase 6)
│   └── ROLE_C_IMPLEMENTATION_PLAN.md   # this file
├── broker/
│   ├── mosquitto.conf
│   ├── start.sh
│   ├── make_passwd.sh
│   ├── passwd                # generated, NOT committed
│   └── data/                 # generated, NOT committed
├── sim/
│   ├── fake_node.py
│   └── requirements.txt
├── server/
│   ├── __init__.py
│   ├── app.py                # Flask app + entry point
│   ├── config.py
│   ├── db.py
│   ├── mqtt_worker.py
│   ├── timeutil.py
│   ├── requirements.txt
│   ├── icu.db                # generated, NOT committed
│   └── tests/
│       ├── __init__.py
│       └── test_handlers.py
├── dashboard/
│   ├── .env                  # NOT committed
│   ├── .env.example
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/ … (see Phase 4)
├── scripts/
│   └── reset_demo.sh
├── tests/
│   ├── verify_steps_1_2.py   # broker + fake node checks
│   ├── verify_server.py      # Flask end-to-end checks
│   └── e2e/                  # optional Playwright UI test (Phase 4C)
├── node/                     # Role A — do not touch
└── ml/                       # Role B — do not touch
```

### 4.1 `.env` keys (repo root) — final set

```
BROKER_HOST=localhost
BROKER_PORT=1883
BROKER_WS_PORT=9001
NODE_USER=bed1
NODE_PASS=
BED2_PASS=
LOGGER_USER=logger
LOGGER_PASS=
DASHBOARD_USER=dashboard
DASHBOARD_PASS=
API_PORT=5050
```

`.env.example` has exactly these keys with empty passwords. `NODE_USER/NODE_PASS` are the `bed1` credentials (Role A's Pi uses them too). If any key is missing from the user's `.env`, add it to `.env.example`, then STOP and ask the user to fill in `.env`.

### 4.2 `.gitignore` must contain

```
.env
dashboard/.env
.venv/
__pycache__/
*.pyc
node_modules/
dist/
broker/passwd
broker/data/
server/*.db
server/*.db-*
test-results/
playwright-report/
```

---

## 5. Phase 0 — Audit what exists (do this first)

**Goal:** find out what Steps 0–2 (repo skeleton, broker, fake node) already contain, compare it with this plan, and record the result. Fix nothing in this phase except obvious `.gitignore`/secret problems; fixes happen in Phases 1–2.

### 5.1 Inspect

1. `git status`, `git log --oneline -20`, and print the tree (excluding `.venv`, `node_modules`, `.git`).
2. **Secrets check:** `git ls-files | grep -E '(^|/)\.env$|broker/passwd|\.db$'` must print nothing. Also `git log --all --oneline -- .env broker/passwd` must print nothing. If either prints something, STOP and tell the user: those passwords have been committed and should be changed after cleanup.
3. Compare `docs/contracts.md` with Appendix A. Formatting differences are fine; substantive differences (topics, fields, QoS, retain, rules) → STOP and ask.
4. Check each item in the table below and mark it OK / WRONG / MISSING.

| # | Item | Expected |
| --- | --- | --- |
| A1 | `.gitignore` | Contains every line from §4.2 |
| A2 | `.env.example` | Exactly the keys in §4.1 |
| A3 | `.env` exists | All §4.1 keys present with non-empty passwords (check presence and non-emptiness only; never print values) |
| A4 | System Mosquitto service | `systemctl is-active mosquitto` prints `inactive` (if `active`, ask user to run `sudo systemctl stop mosquitto && sudo systemctl disable mosquitto`) |
| A5 | `broker/mosquitto.conf` | Matches §6.1 in substance |
| A6 | `broker/start.sh` | Matches §6.2 in substance; executable |
| A7 | `broker/make_passwd.sh` | Matches §6.3; creates all 4 users; executable |
| A8 | `.venv/` | Exists at repo root |
| A9 | `sim/fake_node.py` | Behaviour matches §7 (read the code and check every bullet) |
| A10 | `sim/requirements.txt` | Contains `paho-mqtt>=2.0` and `python-dotenv` |
| A11 | `tests/verify_steps_1_2.py` | Exists and covers tests B1–B5 and N1–N12 in §7.3 |
| A12 | README | Has Broker and Fake node sections |

5. If `tests/verify_steps_1_2.py` exists, start the broker (if not running) and run it. Record the results.

### 5.2 Write `docs/AUDIT.md`

Contents: date; summary in 3 lines; the table above with status and a one-line note per row; test results if run; list of fixes to be made in Phases 1–2.

### Gate 0
`docs/AUDIT.md` exists and every row has a status. Show the user the summary and the WRONG/MISSING rows. Then continue with Phase 1 without waiting, unless a STOP condition was hit.

Commit: `docs: audit of steps 0-2` (plus any `.gitignore` fix).

---

## 6. Phase 1 — Broker (fix or confirm)

### 6.1 `broker/mosquitto.conf` (target content)

Paths in this file are placeholders; `start.sh` generates the real config with absolute paths (see 6.2). Either approach is acceptable as long as the broker never depends on the current working directory.

```
per_listener_settings false
allow_anonymous false
password_file __BROKER_DIR__/passwd

persistence true
persistence_location __BROKER_DIR__/data/
autosave_interval 30

listener 1883 0.0.0.0
protocol mqtt

listener 9001 0.0.0.0
protocol websockets

log_dest stdout
log_type error
log_type warning
log_type notice
log_type information
connection_messages true
log_timestamp true
log_timestamp_format %H:%M:%S
```

### 6.2 `broker/start.sh`

- `#!/usr/bin/env bash`, `set -euo pipefail`.
- `BROKER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"`.
- Fails with a clear message if `broker/passwd` doesn't exist ("run broker/make_passwd.sh first").
- Fails with a clear message if port 1883 or 9001 is already in use (`ss -ltn`), naming the port and suggesting `systemctl is-active mosquitto`.
- Creates `broker/data/`.
- Renders `mosquitto.conf` into `/tmp/icu-mosquitto.conf`, replacing `__BROKER_DIR__` with `$BROKER_DIR`.
- `exec mosquitto -c /tmp/icu-mosquitto.conf` (foreground, so the terminal shows the log). No `sudo`.

### 6.3 `broker/make_passwd.sh`

- Loads the repo-root `.env` (`set -a; source "$ROOT/.env"; set +a`).
- Fails clearly if any of `NODE_PASS`, `BED2_PASS`, `LOGGER_PASS`, `DASHBOARD_PASS` is empty.
- Deletes and recreates `broker/passwd` with `mosquitto_passwd -b -c` for the first user and `mosquitto_passwd -b` for the rest: `bed1` (NODE_PASS), `bed2` (BED2_PASS), `logger` (LOGGER_PASS), `dashboard` (DASHBOARD_PASS).
- `chmod 600 broker/passwd`.
- Prints only usernames created.

### Gate 1
Run the broker tests B1–B5 from §7.3 (they live in `tests/verify_steps_1_2.py`; write that file now if it doesn't exist, starting with B1–B5). All pass.

Commit: `broker: align with plan and verify`.

---

## 7. Phase 2 — Fake node (fix or confirm)

### 7.1 Behaviour of `sim/fake_node.py`

- Python, `paho-mqtt>=2.0` (`mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=f"node-{node}", clean_session=True)`), `python-dotenv` loading the repo-root `.env` (resolve the path from `__file__`, not the CWD).
- CLI: `--node` (default `bed1`), `--host`, `--port`, `--user`, `--password`; defaults from `.env`. Password default: `NODE_PASS` for `bed1`, `BED2_PASS` for `bed2`. User default: the node name.
- Connect with keepalive **5 s**. Set the Will **before** connecting: topic `icu/{node}/online`, payload `offline`, QoS 1, retain True.
- In `on_connect` (success only): publish `online` to `icu/{node}/online`, QoS 1, retain True.
- **Status loop every 3 s:** build a status payload (Appendix A) for the current level with these value ranges:

| Level | gesture_conf | tremor | hr_delta | spo2 |
| --- | --- | --- | --- | --- |
| routine | 0.00–0.20 | 0.002–0.008 | −3…5 | 96–99 |
| urgent | 0.80–0.95 | 0.004–0.012 | −3…5 | 96–99 |
| critical | 0.80–0.95 | 0.008–0.020 | 18…30 | 96–99 |

  `hr = 75 + hr_delta` (integers for hr, hr_delta, spo2; gesture_conf and tremor rounded to 3 decimals). `p`: give the current level a random value in 0.70–0.90, split the remainder randomly between the other two, round to 2 decimals, and make the sum exactly 1.00. `ts` = local time `YYYY-MM-DDTHH:MM:SS`. `bio_source` = current toggle (`live` at start).
  - Always publish it to `icu/{node}/status/routine`, QoS 0, retain False.
  - **Level-rise rule:** rank routine=0, urgent=1, critical=2. If the current rank is higher than the previous window's rank, ALSO publish the same payload to `icu/{node}/status/{level}`, QoS 1, retain True. The first window counts as previous = routine.
- **Heartbeat every 10 s:** `{"node", "ts", "uptime_s"}` to `icu/{node}/heartbeat`, QoS 0, retain False.
- **Stdin control**, one line per command (works by pipe as well as by keyboard): `1` routine, `2` urgent, `3` critical, `r` toggle bio_source, `q` clean quit (publish `offline` retained QoS 1, wait for it to be sent, then disconnect, exit 0), `k` hard kill (`os._exit(1)` immediately, no disconnect). EOF on stdin = keep running (so it can run in the background); unknown input prints help.
- Print one short line per publish: time, topic, level, QoS, retain.
- Use `loop_start()`; the timer loop runs in a thread; the main thread reads stdin. Flush output (`print(..., flush=True)`).

### 7.2 `sim/requirements.txt`
```
paho-mqtt>=2.0
python-dotenv>=1.0
```

### 7.3 `tests/verify_steps_1_2.py`

Uses `paho-mqtt` and `python-dotenv`. Starts fake nodes with `subprocess.Popen([".venv/bin/python", "-u", "sim/fake_node.py", "--node", X], stdin=PIPE, stdout=PIPE, text=True)` and sends commands with `proc.stdin.write("3\n"); proc.stdin.flush()`. A recorder client subscribes to `icu/#` at QoS 1 and stores topic, payload, qos, retain, arrival time. Each test prints `PASS`/`FAIL <reason>`; exit code non-zero if any fail. Always runs cleanup in `finally`.

Broker tests:
- **B1** `logger` subscribes and `bed1` publishes on 1883 → received.
- **B2** Anonymous connect is refused.
- **B3** Wrong password is refused.
- **B4** Retained publish → a new subscriber receives it with `retain=True`; empty retained publish clears it; a new subscriber then gets nothing within 2 s.
- **B5** `transport="websockets"` connection to 9001 as `dashboard` receives a message published on 1883.

Fake node tests (node `bed1` unless stated):
- **N1** `icu/bed1/online` = `online` after start.
- **N2** 3–4 routine messages in 10 s; QoS 0; not retained.
- **N3** Payload shape matches Appendix A exactly (all keys, types, `ts` format, `p` sums to 1.00 ± 0.01 and highest on `level`).
- **N4** Heartbeat within 12 s with `node`, `ts`, `uptime_s`.
- **N5** `2` → exactly one `status/urgent` message, QoS 1, values in range; none in the next 7 s.
- **N6** `3` → exactly one `status/critical`, QoS 1, `hr_delta` 18–30; none in the next 7 s.
- **N7** A new subscriber receives the critical message with `retain=True`.
- **N8** `1`, wait 4 s, `3` → a new critical message.
- **N9** `r` → next routine has `bio_source = "replay"`.
- **N10** `k` → `online` becomes `offline` within 10 s.
- **N11** restart, `q` → `online` becomes `offline`; process exits 0.
- **N12** `bed1` and `bed2` together for 10 s: both publish; neither sees a disconnect.

Cleanup: terminate fake nodes; publish empty retained messages to `icu/bed1/` and `icu/bed2/` × (`status/urgent`, `status/critical`, `online`).

### Gate 2
`.venv/bin/python tests/verify_steps_1_2.py` → all 17 tests PASS.

Commit: `sim: fake node aligned with contract; tests B1-B5, N1-N12 pass`.

---

## 8. Phase 3 — Flask + SQLite server

### 8.1 Files and responsibilities

| File | Contents |
| --- | --- |
| `server/__init__.py` | empty |
| `server/config.py` | Loads repo-root `.env`; exposes `BROKER_HOST`, `BROKER_PORT`, `LOGGER_USER`, `LOGGER_PASS`, `API_PORT` (default 5050), `DB_PATH` (default `server/icu.db`, absolute), `CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]` |
| `server/timeutil.py` | `now_local_iso()` → `YYYY-MM-DDTHH:MM:SS`; `parse_local_iso(s)`; `seconds_between(a, b)` |
| `server/db.py` | Schema creation, a module-level `threading.Lock`, `connect()` (new `sqlite3` connection per call, `check_same_thread=False`, `row_factory=sqlite3.Row`, `PRAGMA journal_mode=WAL`), and all query functions below |
| `server/mqtt_worker.py` | The paho client, subscriptions, and one handler function per topic type. Handlers take `(node, payload_bytes, retain)` and call `db.py`; they are pure enough to unit test without a broker |
| `server/app.py` | Flask app factory `create_app(start_mqtt=True)`, the routes, and `if __name__ == "__main__":` that runs on `0.0.0.0:API_PORT` with `debug=False, use_reloader=False` |
| `server/requirements.txt` | `flask>=3.0`, `flask-cors>=4.0`, `paho-mqtt>=2.0`, `python-dotenv>=1.0`, `pytest>=8.0` |

Run command (from repo root): `.venv/bin/python -m server.app`.

**Important:** `use_reloader=False` is mandatory. The Flask reloader starts the app twice, which would start two MQTT clients with the same client ID that kick each other off.

### 8.2 Database schema (exact)

```sql
CREATE TABLE IF NOT EXISTS alerts (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  node             TEXT NOT NULL,
  level            TEXT NOT NULL CHECK (level IN ('urgent','critical')),
  alert_ts         TEXT NOT NULL,      -- ts from the node's payload
  received_at      TEXT NOT NULL,      -- server clock when first received
  payload_json     TEXT NOT NULL,
  ack_ts           TEXT,               -- ack_ts from the dashboard's payload
  ack_received_at  TEXT,               -- server clock when the ack arrived
  response_s       REAL,               -- ack_received_at - received_at, seconds
  UNIQUE (node, level, alert_ts)
);

CREATE TABLE IF NOT EXISTS node_state (
  node              TEXT PRIMARY KEY,
  online            INTEGER,           -- 1, 0 or NULL (unknown)
  online_changed_at TEXT,
  last_heartbeat_at TEXT,              -- server clock
  last_status_json  TEXT,
  last_status_at    TEXT,              -- server clock
  updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS connection_events (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  node   TEXT NOT NULL,
  state  TEXT NOT NULL CHECK (state IN ('online','offline')),
  at     TEXT NOT NULL                 -- server clock
);
```

**Why response time uses server-clock fields:** the Pi's clock and the laptop's clock can differ. `received_at` and `ack_received_at` are both measured on the laptop, so `response_s` is always correct and never negative.

### 8.3 MQTT worker behaviour (exact)

- Client: `client_id="logger-server"`, user `LOGGER_USER`, keepalive 30, `reconnect_delay_set(1, 10)`, `connect_async` + `loop_start()` so Flask starts even if the broker is down.
- Track `connected: bool` (set in `on_connect` / `on_disconnect`) for `/api/health`.
- In `on_connect`, subscribe (QoS 1) to: `icu/+/status/routine`, `icu/+/status/urgent`, `icu/+/status/critical`, `icu/+/heartbeat`, `icu/+/online`, `icu/+/ack`. (Subscribing in `on_connect` re-subscribes after a reconnect.)
- Parse the node id from the topic (`icu/{node}/...`). The topic is the source of truth; if the payload's `node` differs, log a warning and use the topic's.
- **Empty payload → ignore** (log at debug level). This includes the clears the server itself publishes.
- Invalid JSON where JSON is expected → log a warning and ignore. Never crash the worker thread; wrap each handler in try/except and log the exception.

| Topic | Handler logic |
| --- | --- |
| `status/routine` | Upsert `node_state`: `last_status_json`, `last_status_at = now`, `updated_at = now`. Do not insert into alerts. |
| `status/urgent`, `status/critical` | `INSERT OR IGNORE INTO alerts (node, level, alert_ts, received_at, payload_json)` with `alert_ts = payload.ts`, `received_at = now`. Retained re-deliveries after a server restart are ignored by the UNIQUE constraint, so `received_at` keeps its original value. Log `ALERT bed1 critical` only when a row was actually inserted. |
| `heartbeat` | Upsert `node_state.last_heartbeat_at = now`. |
| `online` | Payload is plain text `online`/`offline`. Upsert `node_state.online` (1/0). If the value changed from the stored one (or there was none), set `online_changed_at = now` and insert a `connection_events` row. Log `NODE bed1 offline`. |
| `ack` | See below. |

**Ack logic (decision: one ack acknowledges the node, not a single alert):**
1. Parse the JSON; `ack_received_at = now`.
2. Select all rows in `alerts` where `node = ?` and `ack_ts IS NULL`.
3. For each: set `ack_ts = payload.ack_ts` (fallback to `now` if missing), `ack_received_at`, `response_s = seconds_between(received_at, ack_received_at)` rounded to 1 decimal.
4. Publish an empty payload with QoS 1, retain True, to `icu/{node}/status/urgent` and `icu/{node}/status/critical`.
5. Log `ACK bed1: 2 alert(s) acknowledged`. If zero rows were open, still do step 4 (idempotent) and log a warning.

Rationale: when a nurse attends the bed, every open alert for that bed is handled. The dashboard shows only the highest alert, so acknowledging per node matches what the nurse sees. This satisfies contract rule 5.

### 8.4 HTTP API (exact)

All responses are JSON. CORS allowed for `CORS_ORIGINS`. Errors return `{"error": "<message>"}` with a 4xx/5xx status. Timestamps are `YYYY-MM-DDTHH:MM:SS` strings.

**`GET /api/health`**
```json
{"ok": true, "mqtt_connected": true, "db": "ok", "server_time": "2026-10-25T10:02:11"}
```

**`GET /api/alerts?limit=50&node=bed1`** — `limit` default 50, max 500; `node` optional. Newest first by `received_at`.
```json
{"alerts": [
  {"id": 7, "node": "bed1", "level": "critical",
   "alert_ts": "2026-10-25T10:02:11", "received_at": "2026-10-25T10:02:11",
   "ack_ts": "2026-10-25T10:02:19", "ack_received_at": "2026-10-25T10:02:19", "response_s": 8.0,
   "hr": 99, "spo2": 98, "hr_delta": 24, "gesture_conf": 0.91, "tremor": 0.01,
   "bio_source": "replay", "p": {"routine": 0.04, "urgent": 0.11, "critical": 0.85}}
]}
```
(The flattened fields come from `payload_json`; missing fields become `null`.)

**`GET /api/nodes`**
```json
{"nodes": [
  {"node": "bed1", "online": true, "online_changed_at": "...", "last_heartbeat_at": "...",
   "heartbeat_age_s": 4.2, "last_status": { /* last routine payload */ }, "last_status_at": "..."}
]}
```

**`GET /api/stats`**
```json
{"total_alerts": 5, "open_alerts": 1,
 "by_level": {
   "urgent":   {"count": 3, "acknowledged": 3, "mean_response_s": 6.4, "max_response_s": 9.1},
   "critical": {"count": 2, "acknowledged": 1, "mean_response_s": 8.0, "max_response_s": 8.0}},
 "offline_events": 1}
```
Means/maxes are `null` when there are no acknowledged alerts at that level.

**`GET /api/events?limit=50`** — `connection_events`, newest first: `{"events": [{"node", "state", "at"}]}`.

### 8.5 Tests

**Unit tests — `server/tests/test_handlers.py` (pytest, no broker needed).** Use a temporary DB file (`tmp_path`) and call handler functions directly; mock the publish function.
- routine updates `node_state`, inserts no alert
- urgent inserts one alert; the same payload again inserts nothing (UNIQUE)
- empty payload is ignored on every topic
- invalid JSON is ignored without raising
- `online` → `offline` → `offline` creates exactly 2 connection events
- ack with two open alerts acknowledges both, `response_s >= 0`, and calls publish exactly twice with empty payload, QoS 1, retain True on the two alert topics
- ack with no open alerts still publishes the two clears
- `/api/stats` and `/api/alerts` return the documented shapes (use `create_app(start_mqtt=False)` and Flask's test client)

**End-to-end — `tests/verify_server.py`** (broker must be running; this script starts and stops the server and a fake node itself):
- **S1** server starts; `/api/health` within 10 s shows `mqtt_connected: true`
- **S2** fake node `bed1`: send `2`, then `3` → `/api/alerts?node=bed1` has an urgent and a critical alert
- **S3** restart the server → still exactly those 2 alerts (no duplicates from retained re-delivery)
- **S4** `/api/nodes` shows `bed1` online with `heartbeat_age_s < 15`
- **S5** publish an ack as user `dashboard` (Appendix A shape) → within 3 s both alerts have `ack_ts` and `response_s >= 0`
- **S6** a new MQTT subscriber to `icu/bed1/status/#` receives no retained alert
- **S7** `/api/stats` counts match (2 alerts, 2 acknowledged, means not null)
- **S8** fake node `k` → within 10 s `/api/nodes` shows `bed1` offline and `/api/events` has an `offline` event
- Cleanup in `finally`: stop processes, clear retained topics, delete the test DB. Use a separate DB path for the test (`DB_PATH` env override → e.g. `/tmp/icu-test.db`); never touch `server/icu.db`.

### Gate 3
`.venv/bin/python -m pytest server/tests -q` passes and `.venv/bin/python tests/verify_server.py` shows S1–S8 PASS.

Commit: `server: flask + sqlite logger, ack handling, API; tests pass`.

---

## 9. Phase 4 — React dashboard

### 9.1 Stack and setup

- Vite + React, **JavaScript** (no TypeScript), **plain CSS** (no Tailwind, no UI library).
- Create in `dashboard/` with `npm create vite@latest dashboard -- --template react` (run from the repo root, after `source ~/.nvm/nvm.sh`). If `dashboard/` already contains files, inspect them first and keep what works.
- Dependencies: `mqtt` (v5). Dev: `vitest`.
- `mqtt` v5 import: `import mqtt from "mqtt"`. If Vite fails to bundle it, use `import mqtt from "mqtt/dist/mqtt.esm.js"`.
- `dashboard/.env.example` (and `dashboard/.env`, values copied from the root `.env` — create `.env` yourself, never print the password):
```
VITE_BROKER_HOST=localhost
VITE_BROKER_WS_PORT=9001
VITE_DASHBOARD_USER=dashboard
VITE_DASHBOARD_PASS=
VITE_API_BASE=http://localhost:5050
```
- Scripts in `package.json`: `dev` (vite, port 5173, `--host` so other devices can open it), `build`, `test` (vitest run).
- The dashboard password ends up in browser JavaScript. That's acceptable for a local prototype; it is listed in the report's limitations.

### 9.2 Source layout

```
dashboard/src/
├── main.jsx               # renders <App/>, imports styles.css
├── App.jsx                # layout + wiring
├── config.js              # reads import.meta.env.VITE_*
├── styles.css
├── lib/
│   ├── time.js            # nowLocalIso(), secondsSince(), formatClock()
│   ├── api.js             # fetchAlerts(), fetchStats(), fetchHealth() with 4 s timeout
│   └── topics.js          # parseTopic(topic) -> {node, kind, level} ; ackTopic(node)
├── state/
│   ├── nodesReducer.js    # pure reducer (unit tested)
│   └── nodesReducer.test.js
├── hooks/
│   ├── useMqtt.js         # connection, subscription, dispatch, publishAck
│   ├── useNow.js          # re-render every 1 s for ages and clocks
│   └── usePolling.js      # fetch every N ms + manual refresh()
└── components/
    ├── TopBar.jsx
    ├── AlertBanner.jsx
    ├── StatsStrip.jsx
    ├── NodeGrid.jsx
    ├── NodeCard.jsx
    ├── ProbabilityBars.jsx
    └── AlertLog.jsx
```

### 9.3 State model (`nodesReducer.js`)

```js
// state: { nodes: { [nodeId]: NodeState }, lastAlertEvent: null | {node, level, at} }
// NodeState:
{
  id: "bed1",
  online: null | true | false,
  lastHeartbeatAt: null | number,     // Date.now() ms when received
  firstSeenAt: number,
  status: null | StatusPayload,       // latest routine payload
  statusAt: null | number,
  alerts: { urgent: null | StatusPayload, critical: null | StatusPayload },
  ackPendingSince: null | number      // ms; set when Ack clicked
}
```

Actions:
| Action | Effect |
| --- | --- |
| `{type: "MESSAGE", topic, payload: string, retain: bool, at}` | Create the node on first message. Route by topic kind: `status/routine` → `status`; `status/urgent|critical` → if payload empty, set that alert to null, else set it to the parsed payload, and if `!retain` set `lastAlertEvent = {node, level, at}`; `heartbeat` → `lastHeartbeatAt = at`; `online` → `online = payload === "online"`; `ack` → ignore. Invalid JSON → return state unchanged. When both alerts become null, set `ackPendingSince = null`. |
| `{type: "ACK_SENT", node, at}` | `ackPendingSince = at` |
| `{type: "DISMISS_BANNER"}` | `lastAlertEvent = null` |

Selectors (exported, pure, take `(nodeState, now)`):
- `activeAlert(n)` → `n.alerts.critical ?? n.alerts.urgent ?? null`
- `displayLevel(n)` → `activeAlert(n)?.level ?? n.status?.level ?? "routine"`
- `heartbeatStale(n, now)` → `n.online === true && now - (n.lastHeartbeatAt ?? n.firstSeenAt) > 25000`
- `ackUnconfirmed(n, now)` → `n.ackPendingSince !== null && activeAlert(n) && now - n.ackPendingSince > 5000`

### 9.4 `useMqtt` hook

- One `useEffect` creates the client: `mqtt.connect(\`ws://${host}:${port}\`, { username, password, clientId: "dashboard-" + random8hex, clean: true, reconnectPeriod: 2000, connectTimeout: 5000 })`.
- **Cleanup must call `client.end(true)`.** React StrictMode runs effects twice in development; without cleanup there would be two connections.
- Connection status state: `"connecting" | "connected" | "reconnecting" | "offline"` from `connect`, `reconnect`, `close`, `offline` events.
- On `connect`: subscribe `icu/+/#` at QoS 1.
- On `message (topic, buf, packet)`: dispatch `MESSAGE` with `payload: buf.toString()`, `retain: packet.retain`, `at: Date.now()`.
- `publishAck(node, alert)`: publish to `icu/{node}/ack`, QoS 1, retain false, payload `{"node", "level": alert.level, "alert_ts": alert.ts, "ack_ts": nowLocalIso(), "by": "dashboard"}`; then dispatch `ACK_SENT`.

### 9.5 Components and behaviour

**Visual style:** dark background (`#0f1419`), cards `#1a2129`, text `#e6edf3`. Level colours: routine `#2ea043`, urgent `#d29922`, critical `#f85149`, offline `#6e7681`, replay badge `#fb8500`. System font stack. Base font 16 px; level label 32 px bold; vitals 28 px. Must be readable from 2 m on a laptop screen. Responsive grid: `repeat(auto-fill, minmax(320px, 1fr))`; works at 1366×768 without horizontal scroll.

| Component | Shows / does |
| --- | --- |
| `TopBar` | Title "ICU Gesture + Biosignal Fusion — Nurse Station"; broker pill (green Connected / amber Reconnecting / red Offline); history pill (green when `/api/health` ok, grey "History unavailable" otherwise); live clock (HH:MM:SS). |
| `AlertBanner` | When `lastAlertEvent` is set and that alert is still active: full-width bar in the level colour, "CRITICAL — bed1" / "URGENT — bed2", with a Dismiss ×. Auto-hides when the alert clears. |
| `StatsStrip` | From `/api/stats`: Urgent count, Critical count, Acknowledged, Average response time (s), Offline events. Hidden if history is unavailable. |
| `NodeGrid` | Cards sorted by node id. Empty state: "Waiting for nodes…" |
| `NodeCard` | Header: node id, online dot + "Online"/"OFFLINE", "heartbeat Ns ago". Big level label in the level colour from `displayLevel`; if an alert is active, the label says the alert level and the card border is 3 px in that colour and pulses for 10 s after a new (non-retained) alert. Vitals row: HR (bpm), SpO₂ (%), ΔHR (bpm, with sign). Feature row: gesture confidence (%), tremor (3 decimals). `ProbabilityBars`. REPLAY badge "BIOSIGNAL: REPLAY" when `status.bio_source === "replay"` (or the alert's). Warnings: "No heartbeat for 25 s" when `heartbeatStale`; whole card greyed with "OFFLINE" when `online === false`. **Acknowledge** button only when an alert is active; disabled while `ackPendingSince` is set; if `ackUnconfirmed`, show "Not confirmed — is the server running?" |
| `ProbabilityBars` | Three horizontal bars (routine, urgent, critical) with percentage labels, coloured by level. |
| `AlertLog` | Table from `/api/alerts?limit=50`: Time (received_at, HH:MM:SS), Bed, Level (coloured chip), HR, Gesture %, Source (live/replay), Acknowledged (HH:MM:SS or "—"), Response (s). Shows "History unavailable" instead of the table when Flask can't be reached. |

**Data refresh:** `usePolling` fetches alerts and stats every 10 s, and immediately when `lastAlertEvent` changes or an alert clears. Health every 5 s.

### 9.6 Tests and checks

- `nodesReducer.test.js` (vitest): routine sets status; retained critical sets alert without `lastAlertEvent`; non-retained critical sets `lastAlertEvent`; empty payload clears; both cleared resets `ackPendingSince`; invalid JSON leaves state unchanged; `displayLevel`, `heartbeatStale`, `ackUnconfirmed` boundaries.
- `npm run build` succeeds with no errors.
- `npm test` passes.

### 9.7 Phase 4C — Automated UI smoke test (optional, try it)

- Install `@playwright/test` as a dev dependency in `dashboard/` and run `npx playwright install chromium`. **If this needs `sudo` (missing system libraries), skip Phase 4C**, tell the user, and give them the manual checklist below instead.
- `tests/e2e/dashboard.spec.js` (config in `dashboard/playwright.config.js`): with broker, server and `npm run dev` running and a fake node `bed2` started by the test: page loads → card `bed2` visible within 10 s → send `3` to the fake node → card shows "CRITICAL" and the Acknowledge button → click it → within 5 s the card no longer shows the Acknowledge button and the alert log has a row with a response time → reload the page → no active alert. Save a screenshot to `test-results/dashboard.png`.

**Manual checklist for the user** (always include it in the final summary, in plain words):
1. Run `./start_all.sh`, open http://localhost:5173.
2. In the fake node terminal, type `3` and Enter → a red CRITICAL card and a banner appear.
3. Click Acknowledge → the card goes back to normal; the log shows a response time.
4. Type `r` → the orange REPLAY badge appears.
5. Type `k` → the card turns grey and says OFFLINE.

### Gate 4
`npm run build` and `npm test` pass in `dashboard/`; Phase 4C passes or was skipped with a reason.

Commit: `dashboard: live cards, alerts, ack, log, stats`.

---

## 10. Phase 5 — Run scripts and demo reset

### 10.1 `start_all.sh` (repo root, executable)
- Checks: `.env` exists; `broker/passwd` exists (else runs `broker/make_passwd.sh`); `.venv` exists; `dashboard/node_modules` exists (else `npm install`).
- Opens one `gnome-terminal` window with three tabs titled Broker, Server, Dashboard:
  - Broker: `./broker/start.sh`
  - Server: `.venv/bin/python -m server.app`
  - Dashboard: `source ~/.nvm/nvm.sh && cd dashboard && npm run dev`
  Each tab keeps the shell open after the command exits (`bash -c "...; exec bash"`), so errors stay visible.
- Waits up to 15 s for ports 1883, 5050, 5173, then prints: the dashboard URL, the laptop's Wi-Fi IP (`hostname -I | awk '{print $1}'`) for the Pi, and how to start the fake node (`.venv/bin/python sim/fake_node.py --node bed2`).
- If `gnome-terminal` isn't installed, fall back to starting the three as background processes logging to `/tmp/icu-*.log` and say so.

### 10.2 `stop_all.sh`
Stops the processes listening on 1883/9001, 5050 and 5173 that belong to this project (match by command line: `mosquitto -c /tmp/icu-mosquitto.conf`, `server.app`, `vite`). Never kills unrelated processes.

### 10.3 `scripts/reset_demo.sh`
For a clean demo start. Refuses to run if the server is running (port 5050 open). Deletes `server/icu.db*`. If the broker is running, publishes empty retained messages to `icu/bed1/` and `icu/bed2/` × (`status/urgent`, `status/critical`, `online`) as user `logger`. Prints what it did.

### Gate 5
`./stop_all.sh` → `./scripts/reset_demo.sh` → `./start_all.sh` works; all three ports listen; the dashboard loads (`curl -s localhost:5173` returns HTML; `curl -s localhost:5050/api/health` returns `ok: true`).

Commit: `scripts: start_all, stop_all, reset_demo`.

---

## 11. Phase 6 — Documentation and Pi handoff

### 11.1 `README.md`
Sections: Overview (3 lines + the diagram from §3.1) · Prerequisites (Ubuntu packages, nvm, system Mosquitto disabled) · First-time setup (`.env`, `make_passwd.sh`, venv + `pip install -r server/requirements.txt -r sim/requirements.txt`, `npm install`) · Run (`start_all.sh`) · Fake node commands · Tests (all commands) · Demo reset · Troubleshooting (port in use; system Mosquitto running; Pi can't connect → same hotspot, laptop IP, `ufw status`; dashboard "Reconnecting" → broker not running or wrong WS port; "History unavailable" → server not running).

### 11.2 `docs/NODE_INTEGRATION.md` (for Role A)
- Broker address: laptop IP on the hotspot, port 1883, user `bed1`, password from the team (not written in the file).
- The exact Pi responsibilities from Appendix A rules 1–4 and 7, with the status payload example.
- A minimal paho-mqtt 2.x Python snippet: connect with Will + keepalive 5, publish `online`, publish one routine status, heartbeat thread, level-rise publish.
- How to test from the Pi before running project code: `mosquitto_pub -h <laptop IP> -u bed1 -P <pass> -t icu/bed1/heartbeat -m test` (needs `sudo apt install mosquitto-clients` on the Pi).
- "How you know it works": the bed1 card appears on the dashboard and `tests/verify_steps_1_2.py`-style checks pass.

### Gate 6
Both files exist and every command in them has been run at least once successfully on this machine (except the Pi-side ones).

Commit: `docs: README and node integration guide`.

---

## 12. Phase 7 — Final verification

Run everything from a clean state, in this order, and report a single table to the user:

1. `./stop_all.sh`, `./scripts/reset_demo.sh`
2. Start the broker; `.venv/bin/python tests/verify_steps_1_2.py` → 17/17
3. `.venv/bin/python -m pytest server/tests -q` → all pass
4. `.venv/bin/python tests/verify_server.py` → S1–S8
5. `cd dashboard && npm test && npm run build`
6. Phase 4C Playwright test (if not skipped)
7. `./scripts/reset_demo.sh` again so the demo database starts empty
8. `git status` clean except ignored files; `git log --oneline` shows one commit per phase

Then give the user:
- the results table
- the manual 5-step checklist from §9.7
- anything skipped, and why
- what Role A needs from them (send `docs/NODE_INTEGRATION.md`, the laptop IP on the day, and the `bed1` password)

Commit (if anything changed): `chore: final verification`. Push to the remote if one is configured (`git remote -v`); if not, tell the user.

---

## 13. Definition of done (Role C)

- [ ] Broker: auth on, anonymous refused, 1883 + 9001, retained messages persist across broker restarts
- [ ] Fake node passes N1–N12 and can run as `bed1` or `bed2`
- [ ] Server stores alerts once, acknowledges per node, measures response time on the server clock, clears retained alerts, exposes the documented API, passes unit + end-to-end tests
- [ ] Dashboard: live cards, level colours, REPLAY badge, OFFLINE + stale heartbeat, banner, Acknowledge with confirmation, alert log, stats; survives Flask being down; build + tests pass
- [ ] `start_all.sh`, `stop_all.sh`, `reset_demo.sh` work
- [ ] README and `docs/NODE_INTEGRATION.md` written
- [ ] No secrets in Git; one commit per phase

---

## Appendix A — MQTT contract v1 (authoritative)

### Broker
- Mosquitto 2.x on the laptop. Anonymous access disabled.
- Port 1883: MQTT (Pi nodes, fake node, Flask logger). Port 9001: MQTT over WebSockets (browser dashboard).
- Users: `bed1`, `bed2` (nodes), `logger` (Flask), `dashboard` (browser).
- Node ids: `bed1`, `bed2`. Timestamps: ISO 8601 local time, seconds precision, no timezone, e.g. `2026-10-25T10:02:11`.

### Topics
| Topic | Publisher | QoS | Retain | When |
| --- | --- | --- | --- | --- |
| `icu/{node}/status/routine` | node | 0 | no | every 3 s window |
| `icu/{node}/status/urgent` | node | 1 | yes | when level rises to urgent |
| `icu/{node}/status/critical` | node | 1 | yes | when level rises to critical |
| `icu/{node}/heartbeat` | node | 0 | no | every 10 s |
| `icu/{node}/online` | node / broker (LWT) | 1 | yes | `online` on connect; broker sends `offline` via LWT |
| `icu/{node}/ack` | dashboard | 1 | no | nurse presses Acknowledge |

### Payloads
Status (same shape on routine, urgent, critical):
```json
{"node": "bed1", "ts": "2026-10-25T10:02:11", "level": "critical",
 "p": {"routine": 0.04, "urgent": 0.11, "critical": 0.85},
 "features": {"gesture_conf": 0.91, "tremor": 0.010, "hr_delta": 24, "spo2": 98},
 "hr": 99, "bio_source": "replay"}
```
Heartbeat: `{"node": "bed1", "ts": "2026-10-25T10:02:11", "uptime_s": 312}`
Online: plain text `online` or `offline` (not JSON).
Ack: `{"node": "bed1", "level": "critical", "alert_ts": "2026-10-25T10:02:11", "ack_ts": "2026-10-25T10:02:19", "by": "dashboard"}`

### Rules
1. Nodes connect with keepalive 5 s and a Last Will: topic `icu/{node}/online`, payload `offline`, QoS 1, retain.
2. On connect, a node publishes `online` (QoS 1, retain) to `icu/{node}/online`.
3. Urgent/critical are published only when the level rises compared with the previous window. Staying critical does not republish.
4. Routine messages carry the live vitals; the dashboard uses them for the live view.
5. An alert stays until acknowledged. On ack, the logger stores it and publishes an EMPTY retained message to `icu/{node}/status/urgent` and `/critical` to clear them. (Implementation decision: one ack acknowledges all open alerts for that node; see §8.3.)
6. Every subscriber ignores empty payloads (they are clears, not data).
7. `bio_source` is `live` or `replay`; the dashboard shows a REPLAY badge when it is `replay`.