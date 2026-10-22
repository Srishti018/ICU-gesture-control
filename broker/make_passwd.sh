#!/usr/bin/env bash
# Generate broker/passwd from the repo-root .env. Prints usernames only, never passwords.
set -euo pipefail

BROKER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$BROKER_DIR/.." && pwd)"
PASSWD_FILE="$BROKER_DIR/passwd"

if ! command -v mosquitto_passwd >/dev/null 2>&1; then
    echo "Error: mosquitto_passwd not found. Install it with: sudo apt install mosquitto mosquitto-clients" >&2
    exit 1
fi

if [ ! -f "$ROOT/.env" ]; then
    echo "Error: $ROOT/.env not found. Copy .env.example to .env and fill in the passwords." >&2
    exit 1
fi

set -a
# shellcheck disable=SC1091
source "$ROOT/.env"
set +a

missing=""
for var in NODE_PASS BED2_PASS LOGGER_PASS DASHBOARD_PASS; do
    if [ -z "${!var:-}" ]; then
        missing="$missing $var"
    fi
done
if [ -n "$missing" ]; then
    echo "Error: empty or missing in .env:$missing" >&2
    exit 1
fi

rm -f "$PASSWD_FILE"
mosquitto_passwd -b -c "$PASSWD_FILE" bed1 "$NODE_PASS"
mosquitto_passwd -b "$PASSWD_FILE" bed2 "$BED2_PASS"
mosquitto_passwd -b "$PASSWD_FILE" logger "$LOGGER_PASS"
mosquitto_passwd -b "$PASSWD_FILE" dashboard "$DASHBOARD_PASS"
chmod 600 "$PASSWD_FILE"

echo "Created $PASSWD_FILE with users: bed1 bed2 logger dashboard"
