#!/usr/bin/env bash
# Start the bed node for the demo.
#   Pi:     runs pi_check.sh, then the node in tmux session "icu" (attach: tmux attach -t icu).
#   Laptop: the node in its own terminal window (webcam, replay, model), so you can type the keys there.
# Extra arguments go to node.main, e.g.: node/tools/run_demo.sh --fusion rule
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="$HOME/icu-data/logs"
NODE_PATTERN='^[^ ]*python[^ ]* (-u )?-m node\.main'
mkdir -p "$LOG_DIR"
cd "$ROOT"

if pgrep -f "$NODE_PATTERN" >/dev/null; then
    echo "A node is already running (pid $(pgrep -f "$NODE_PATTERN" | tr '\n' ' ')). Stop it with node/tools/stop_node.sh." >&2
    exit 1
fi

KEYS="Keys: r rest replay · x exertion replay · s status · q clean quit. Kill test: node/tools/kill_node.sh"

if grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
    if tmux has-session -t icu 2>/dev/null; then
        echo "tmux session 'icu' already exists. Stop it first: node/tools/stop_node.sh" >&2
        exit 1
    fi
    "$ROOT/node/tools/pi_check.sh" || { echo "pi_check failed; fix the FAIL lines above first." >&2; exit 1; }
    cmd=".venv/bin/python -m node.main --bio replay:rest --fusion model $* 2>&1 | tee -a $LOG_DIR/node.log"
    tmux new-session -d -s icu "cd '$ROOT' && $cmd"
    echo "Node started in tmux session 'icu'."
    echo "Attach: tmux attach -t icu   (detach with Ctrl-b then d)"
    echo "Send a key without attaching: tmux send-keys -t icu x Enter"
    echo "$KEYS"
    exit 0
fi

# Laptop fallback: bed1 with the laptop webcam.
cmd=".venv/bin/python -m node.main --vision camera --bio replay:rest --fusion model --mock-io --no-oled $*"
if command -v gnome-terminal >/dev/null && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    gnome-terminal --title="ICU node" --working-directory="$ROOT" \
        -- bash -c "printf '\033]0;ICU node\007'; $cmd 2>&1 | tee -a '$LOG_DIR/node.log'; echo; echo 'node exited'; exec bash"
    echo "Node started in a new terminal window titled 'ICU node' (type the keys there)."
    echo "$KEYS"
else
    echo "No graphical terminal; running the node here. $KEYS"
    exec bash -c "$cmd 2>&1 | tee -a '$LOG_DIR/node.log'"
fi
