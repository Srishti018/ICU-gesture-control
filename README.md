# ICU Fusion — Gesture + Biosignal Alert System

A patient's hand gesture (camera + MediaPipe) and vitals (heart rate, SpO₂) are fused on a Raspberry Pi into a level: `routine`, `urgent` or `critical`.
The Pi publishes the level over MQTT. A laptop runs the broker, a Flask + SQLite logger and a React nurse-station dashboard.
A fake node (`sim/fake_node.py`) imitates the Pi so everything can be run and tested without hardware.

```
 ┌──────────────────────────┐            ┌──────────────────────── Laptop (Ubuntu) ─────────────────────────┐
 │ bed1: Raspberry Pi 4B    │            │                                                                  │
 │ (Role A)                 │──MQTT────▶ │  ┌──────────────────────┐   MQTT :1883   ┌─────────────────────┐ │
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

The MQTT contract (topics, payloads, QoS, retain) is in [docs/contracts.md](docs/contracts.md).
The Pi-side guide for Role A is [docs/NODE_INTEGRATION.md](docs/NODE_INTEGRATION.md).

## Prerequisites

- Ubuntu with Mosquitto 2.x and Python 3.10+:
  ```bash
  sudo apt install mosquitto mosquitto-clients python3-venv
  ```
- The **system** Mosquitto service must be off (we run our own broker as a normal user):
  ```bash
  systemctl is-active mosquitto          # must print "inactive"
  sudo systemctl stop mosquitto && sudo systemctl disable mosquitto   # only if it printed "active"
  ```
- Node.js 20+ via [nvm](https://github.com/nvm-sh/nvm) (`nvm install --lts`). In scripts, `source ~/.nvm/nvm.sh` first.

## First-time setup

Run all commands from the repo root.

1. Passwords: copy the template and fill in every `*_PASS` (bed1, bed2, logger, dashboard):
   ```bash
   [ -f .env ] || cp .env.example .env
   ```
   `.env` is git-ignored. Never commit it.
2. Broker password file (prints usernames only):
   ```bash
   ./broker/make_passwd.sh
   ```
3. Python environment:
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r server/requirements.txt -r sim/requirements.txt
   ```
4. Dashboard:
   ```bash
   source ~/.nvm/nvm.sh && (cd dashboard && npm install)
   ```
   `./start_all.sh` creates `dashboard/.env` from `.env` if it is missing.

## Run

```bash
./start_all.sh
```

This opens a terminal window with three tabs (Broker, Server, Dashboard), waits for ports 1883/5050/5173, then prints the dashboard URL and the laptop's IP for the Pi.
Open http://localhost:5173. Stop everything with `./stop_all.sh`.

Each part can also be started on its own:

```bash
./broker/start.sh                          # broker, ports 1883 (MQTT) + 9001 (WebSockets)
.venv/bin/python -m server.app             # server, port 5050
source ~/.nvm/nvm.sh && cd dashboard && npm run dev   # dashboard, port 5173
```

## Fake node

```bash
.venv/bin/python sim/fake_node.py --node bed2
```

Options: `--node` (default `bed1`), `--host`, `--port`, `--user`, `--password` (defaults come from `.env`).
Type a command and press Enter:

| Key | Effect |
| --- | --- |
| `1` / `2` / `3` | level routine / urgent / critical (urgent and critical publish an alert when the level rises) |
| `r` | toggle `bio_source` between `live` and `replay` (REPLAY badge on the dashboard) |
| `q` | clean quit: publishes `offline` and disconnects |
| `k` | hard kill: no disconnect, so the broker sends the Last Will `offline` |

On demo day `bed1` is the real Pi, so run the fake node as `bed2`. Two clients with the same node id kick each other off.

## Tests

The broker must be running (`./broker/start.sh`). Stop the server before `verify_server.py`, because it starts its own server on port 5050 with a separate test database.

```bash
.venv/bin/python tests/verify_steps_1_2.py     # broker B1-B5 + fake node N1-N12
.venv/bin/python -m pytest server/tests -q     # server unit tests (no broker needed)
.venv/bin/python tests/verify_server.py        # server end-to-end S1-S8
source ~/.nvm/nvm.sh && cd dashboard && npm test && npm run build   # dashboard unit tests + build
```

Browser smoke test (needs broker, server and `npm run dev` running; first time: `npx playwright install chromium`):

```bash
source ~/.nvm/nvm.sh && cd dashboard && npx playwright test
```

It saves a screenshot to `test-results/dashboard.png`.

## Demo reset

For a clean start (empty alert log, no leftover alerts):

```bash
./stop_all.sh
./broker/start.sh          # in its own terminal, so retained messages can be cleared
./scripts/reset_demo.sh    # refuses to run while the server is up
```

Then stop that broker (Ctrl+C) and run `./start_all.sh`.
`reset_demo.sh` deletes `server/icu.db*` and clears the retained `status/urgent`, `status/critical` and `online` messages for `bed1` and `bed2`.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `broker/start.sh`: "port 1883 is already in use" | Run `systemctl is-active mosquitto`. If `active`, the system broker is running: `sudo systemctl stop mosquitto && sudo systemctl disable mosquitto`. Otherwise another copy of ours is running: `./stop_all.sh`. `ss -ltnp \| grep -E ':(1883\|9001)'` shows what holds the port. |
| Server or dashboard: port 5050 / 5173 in use | `./stop_all.sh`, then `ss -ltnp \| grep -E ':(5050\|5173)'` to see what else is using it. |
| Pi can't connect | Laptop and Pi must be on the same phone hotspot. Use the IP printed by `start_all.sh` (`hostname -I`). If the firewall is on, check with `sudo ufw status` and allow the port: `sudo ufw allow 1883/tcp`. Test from the Pi with `mosquitto_pub` (see `docs/NODE_INTEGRATION.md`). |
| Dashboard pill says "Reconnecting" / "Offline" | Broker not running, or wrong WebSocket port in `dashboard/.env` (`VITE_BROKER_WS_PORT=9001`). Restart the dashboard after editing `.env`. |
| Dashboard says "History unavailable" | The Flask server isn't running or can't be reached on port 5050. Live cards keep working without it. |
| "Not confirmed — is the server running?" after Acknowledge | The server clears alerts after an ack; start it (`.venv/bin/python -m server.app`) and press Retry. |
