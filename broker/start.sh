#!/usr/bin/env bash
# Start the ICU Fusion Mosquitto broker in the foreground (no sudo).
set -euo pipefail

BROKER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RENDERED_CONF="/tmp/icu-mosquitto.conf"

if ! command -v mosquitto >/dev/null 2>&1; then
    echo "Error: mosquitto not found. Install it with: sudo apt install mosquitto mosquitto-clients" >&2
    exit 1
fi

if [ ! -f "$BROKER_DIR/passwd" ]; then
    echo "Error: $BROKER_DIR/passwd not found. Run broker/make_passwd.sh first." >&2
    exit 1
fi

for port in 1883 9001; do
    if ss -ltn "sport = :$port" | grep -q LISTEN; then
        echo "Error: port $port is already in use." >&2
        echo "Check whether the system broker is running: systemctl is-active mosquitto" >&2
        echo "(or another copy of this broker; stop it with ./stop_all.sh)" >&2
        exit 1
    fi
done

mkdir -p "$BROKER_DIR/data"

sed "s|__BROKER_DIR__|$BROKER_DIR|g" "$BROKER_DIR/mosquitto.conf" > "$RENDERED_CONF"

echo "Starting Mosquitto (config: $RENDERED_CONF)"
exec mosquitto -c "$RENDERED_CONF"
