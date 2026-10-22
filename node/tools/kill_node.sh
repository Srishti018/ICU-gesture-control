#!/usr/bin/env bash
# Demo "device failure": kill the node with SIGKILL, so the broker publishes its Last Will (offline).
set -euo pipefail

NODE_PATTERN='^[^ ]*python[^ ]* (-u )?-m node\.main'
pids="$(pgrep -f "$NODE_PATTERN" || true)"
if [ -z "$pids" ]; then
    echo "no node is running" >&2
    exit 1
fi
# shellcheck disable=SC2086
kill -9 $pids
echo "node killed with SIGKILL (pid $(echo "$pids" | tr '\n' ',' | sed 's/,$//')); the dashboard should show OFFLINE within ~10 s"
