#!/usr/bin/env bash
# Health check for the bed node. On the Pi: OS, temperature, throttling, groups, I2C, venv, .env,
# camera. On a laptop the Pi-only hardware lines are skipped.
# Exit code: non-zero if any FAIL (camera and broker lines are WARN only).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT/.env"
fails=0

pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; fails=$((fails + 1)); }
warn() { printf 'WARN  %s\n' "$1"; }
skip() { printf 'SKIP  %s\n' "$1"; }

env_value() {  # value of KEY in .env (never printed by callers for passwords)
    grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2-
}

on_pi=0
if grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then on_pi=1; fi

if [ "$on_pi" -eq 1 ]; then
    model="$(tr -d '\0' < /proc/device-tree/model)"
    pass "board: $model"
    arch="$(uname -m)"
    if [ "$arch" = "aarch64" ]; then pass "64-bit OS (aarch64)"; else fail "OS is $arch; MediaPipe needs 64-bit (reflash Raspberry Pi OS Lite 64-bit)"; fi
    if grep -q bookworm /etc/os-release; then pass "Raspberry Pi OS Bookworm"; else fail "not Bookworm: $(grep PRETTY /etc/os-release | cut -d= -f2)"; fi
    if command -v vcgencmd >/dev/null; then
        temp="$(vcgencmd measure_temp | sed 's/temp=//; s/.C//')"
        if awk "BEGIN{exit !($temp < 75)}"; then pass "temperature ${temp} C"; else fail "temperature ${temp} C (>= 75): add a heatsink/fan"; fi
        thr="$(vcgencmd get_throttled | cut -d= -f2)"
        if [ "$thr" = "0x0" ]; then pass "not throttled (0x0)"; else fail "throttled=$thr: under-voltage or overheating; use the official 5 V 2.5 A supply"; fi
    else
        fail "vcgencmd not found"
    fi
    for g in i2c video gpio; do
        if id -nG | tr ' ' '\n' | grep -qx "$g"; then pass "user in group $g"; else fail "user not in group $g (sudo usermod -aG i2c,video,gpio $USER, then log in again)"; fi
    done
    if [ -e /dev/i2c-1 ]; then pass "/dev/i2c-1 exists"; else fail "/dev/i2c-1 missing (sudo raspi-config nonint do_i2c 0)"; fi
else
    skip "not a Raspberry Pi: board, OS, temperature, throttling, groups and I2C checks skipped"
fi

if [ -x "$ROOT/.venv/bin/python" ]; then pass "venv $ROOT/.venv"; else fail "venv missing ($ROOT/.venv)"; fi

if [ -f "$ENV_FILE" ]; then
    pass ".env exists"
    if [ -n "$(env_value NODE_PASS)" ]; then pass "NODE_PASS is set"; else fail "NODE_PASS is empty in .env"; fi
    host="$(env_value BROKER_HOST)"
    if [ -z "$host" ] || [ "$host" = "CHANGE_ME" ]; then warn "BROKER_HOST not set (node/tools/set_broker.sh <laptop IP>)"; else pass "BROKER_HOST=$host"; fi
else
    fail ".env missing ($ENV_FILE)"
fi

videos=(/dev/video*)
if [ -e "${videos[0]}" ]; then
    pass "camera device: ${videos[*]}"
elif command -v rpicam-hello >/dev/null && rpicam-hello --list-cameras 2>/dev/null | grep -q '^[0-9]'; then
    pass "Pi Camera Module detected"
else
    warn "no camera found (USB webcam: ls /dev/video*; Pi camera: rpicam-hello --list-cameras)"
fi

if [ -f "$HOME/icu-data/models/hand_landmarker.task" ]; then
    pass "MediaPipe hand model in ~/icu-data/models"
else
    warn "hand model missing (the bootstrap downloads it to ~/icu-data/models/hand_landmarker.task)"
fi

if [ "$fails" -eq 0 ]; then echo "pi_check: all required checks passed"; else echo "pi_check: $fails FAIL line(s)"; fi
exit "$([ "$fails" -eq 0 ] && echo 0 || echo 1)"
