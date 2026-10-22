#!/usr/bin/env bash
# Clean stop of the node (same as pressing q: publishes offline, then exits).
#   Pi: sends q to tmux session "icu", waits 3 s, closes the session.
#   Laptop: sends SIGTERM to the node process (the node treats it like q).
set -euo pipefail

NODE_PATTERN='^[^ ]*python[^ ]* (-u )?-m node\.main'

if command -v tmux >/dev/null && tmux has-session -t icu 2>/dev/null; then
    tmux send-keys -t icu q Enter
    sleep 3
    tmux kill-session -t icu 2>/dev/null || true
    echo "node stopped (tmux session icu closed)"
    exit 0
fi

pids="$(pgrep -f "$NODE_PATTERN" || true)"
if [ -z "$pids" ]; then
    echo "no node is running"
    exit 0
fi
# shellcheck disable=SC2086
kill -TERM $pids
for _ in $(seq 1 20); do
    pgrep -f "$NODE_PATTERN" >/dev/null || { echo "node stopped cleanly (offline published)"; exit 0; }
    sleep 0.25
done
echo "node did not stop within 5 s; use node/tools/kill_node.sh" >&2
exit 1
