#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v mosquitto >/dev/null 2>&1; then
    echo "Error: mosquitto binary not found in PATH." >&2
    echo "Install it using: sudo apt install mosquitto" >&2
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/passwd" ]; then
    echo "Error: Password file '$SCRIPT_DIR/passwd' not found." >&2
    echo "Run '$SCRIPT_DIR/make_passwd.sh' first to generate credentials from .env." >&2
    exit 1
fi

mkdir -p "$SCRIPT_DIR/data"

# Mosquitto resolves relative paths (like passwd and data/) from the working directory where it is launched.
# Changing into SCRIPT_DIR ensures paths resolve correctly regardless of where start.sh was called from.
cd "$SCRIPT_DIR"

echo "Starting Mosquitto broker from $SCRIPT_DIR..."
exec mosquitto -v -c "$SCRIPT_DIR/mosquitto.conf"

