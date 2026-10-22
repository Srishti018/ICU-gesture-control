#!/usr/bin/env bash
# Stop this project's broker, server and dashboard. Matches processes by their
# command line, so unrelated programs on the same ports are never touched.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

NAMES=(Broker Server Dashboard)
PATTERNS=(
    "^mosquitto -c /tmp/icu-mosquitto.conf"
    "^[^ ]*python[^ ]* (-u )?-m server\.app"
    "^node $ROOT/dashboard/node_modules/\.bin/vite"
)

for i in "${!NAMES[@]}"; do
    pids="$(pgrep -f "${PATTERNS[$i]}" || true)"
    if [ -z "$pids" ]; then
        echo "${NAMES[$i]}: not running"
        continue
    fi
    # Server: only stop copies started from this repo.
    if [ "${NAMES[$i]}" = "Server" ]; then
        mine=""
        for pid in $pids; do
            [ "$(readlink -f "/proc/$pid/cwd" 2>/dev/null)" = "$ROOT" ] && mine="$mine $pid"
        done
        pids="${mine# }"
        if [ -z "$pids" ]; then
            echo "${NAMES[$i]}: not running"
            continue
        fi
    fi
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    for _ in $(seq 1 20); do
        alive=""
        for pid in $pids; do kill -0 "$pid" 2>/dev/null && alive="$alive $pid"; done
        [ -z "$alive" ] && break
        sleep 0.25
    done
    if [ -n "${alive:-}" ]; then
        # shellcheck disable=SC2086
        kill -9 $alive 2>/dev/null || true
    fi
    echo "${NAMES[$i]}: stopped (pid $(echo $pids | tr ' ' ','))"
done
