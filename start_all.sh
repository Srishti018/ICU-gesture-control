#!/usr/bin/env bash
# Start broker, server and dashboard. Opens one gnome-terminal window with three
# tabs (Broker, Server, Dashboard); falls back to background processes with logs
# in /tmp/icu-*.log when gnome-terminal is not available.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

port_open() { ss -ltn "sport = :$1" | grep -q LISTEN; }

# --- checks ---------------------------------------------------------------------
if [ ! -f .env ]; then
    echo "Error: .env not found. Copy .env.example to .env and fill in the passwords." >&2
    exit 1
fi
if [ ! -f broker/passwd ]; then
    echo "broker/passwd missing; generating it from .env"
    ./broker/make_passwd.sh
fi
if [ ! -x .venv/bin/python ]; then
    echo "Error: .venv not found. Create it with:" >&2
    echo "  python3 -m venv .venv && .venv/bin/pip install -r server/requirements.txt -r sim/requirements.txt" >&2
    exit 1
fi
if [ ! -f dashboard/.env ]; then
    echo "dashboard/.env missing; creating it from .env"
    (
        set -a; source .env; set +a
        umask 077
        cat > dashboard/.env <<EOF
VITE_BROKER_HOST=${BROKER_HOST:-localhost}
VITE_BROKER_WS_PORT=${BROKER_WS_PORT:-9001}
VITE_DASHBOARD_USER=${DASHBOARD_USER:-dashboard}
VITE_DASHBOARD_PASS=${DASHBOARD_PASS}
VITE_API_BASE=http://localhost:${API_PORT:-5050}
EOF
    )
fi
if [ ! -d dashboard/node_modules ]; then
    echo "dashboard/node_modules missing; running npm install"
    (source ~/.nvm/nvm.sh && cd dashboard && npm install)
fi

# --- what to start ----------------------------------------------------------------
# name | port | command
NAMES=(Broker Server Dashboard)
PORTS=(1883 5050 5173)
CMDS=(
    "./broker/start.sh"
    ".venv/bin/python -m server.app"
    "source ~/.nvm/nvm.sh && cd dashboard && npm run dev"
)

to_start=()
for i in "${!NAMES[@]}"; do
    if port_open "${PORTS[$i]}"; then
        echo "${NAMES[$i]}: port ${PORTS[$i]} already in use; not starting another (run ./stop_all.sh first for a fresh start)"
    else
        to_start+=("$i")
    fi
done

if [ "${#to_start[@]}" -gt 0 ]; then
    if command -v gnome-terminal >/dev/null 2>&1 && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
        args=(--window)
        first=1
        for i in "${to_start[@]}"; do
            [ "$first" -eq 1 ] || args+=(--tab)
            first=0
            title="${NAMES[$i]}"
            # The trailing `exec bash` keeps the tab open so errors stay visible.
            args+=(--title="$title" --working-directory="$ROOT"
                   --command="bash -c 'printf \"\\033]0;$title\\007\"; ${CMDS[$i]}; exec bash'")
        done
        gnome-terminal "${args[@]}" 2>/dev/null
        echo "Opened gnome-terminal tabs: $(for i in "${to_start[@]}"; do printf '%s ' "${NAMES[$i]}"; done)"
    else
        echo "gnome-terminal not available; starting in the background (logs in /tmp/icu-*.log)"
        for i in "${to_start[@]}"; do
            log="/tmp/icu-$(echo "${NAMES[$i]}" | tr '[:upper:]' '[:lower:]').log"
            setsid nohup bash -c "cd '$ROOT' && ${CMDS[$i]}" > "$log" 2>&1 < /dev/null &
            echo "  ${NAMES[$i]} -> $log"
        done
    fi
fi

# --- wait for ports -------------------------------------------------------------
echo -n "Waiting for ports 1883, 5050, 5173 "
for _ in $(seq 1 30); do
    if port_open 1883 && port_open 5050 && port_open 5173; then
        break
    fi
    echo -n "."
    sleep 0.5
done
echo
for i in "${!NAMES[@]}"; do
    if port_open "${PORTS[$i]}"; then
        echo "  ${NAMES[$i]} is listening on ${PORTS[$i]}"
    else
        echo "  WARNING: ${NAMES[$i]} is NOT listening on ${PORTS[$i]} (check its tab or log)"
    fi
done

IP="$(hostname -I | awk '{print $1}')"
cat <<EOF

Dashboard:        http://localhost:5173   (other devices: http://${IP}:5173)
Pi broker address: ${IP}  port 1883  (user bed1)
Fake node:        .venv/bin/python sim/fake_node.py --node bed2
Stop everything:  ./stop_all.sh
EOF
