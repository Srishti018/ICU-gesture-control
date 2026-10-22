#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"
PASSWD_FILE="$SCRIPT_DIR/passwd"

if ! command -v mosquitto_passwd >/dev/null 2>&1; then
    echo "Error: mosquitto_passwd binary not found in PATH." >&2
    echo "Install it using: sudo apt install mosquitto mosquitto-clients" >&2
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env file not found at $ENV_FILE" >&2
    echo "Copy .env.example to .env and configure the passwords first." >&2
    exit 1
fi

# Load variables from .env
# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

# Node passwords: allow BED1_PASS/BED2_PASS or fallback to NODE_PASS
BED1_PASSWORD="${BED1_PASS:-$NODE_PASS}"
BED2_PASSWORD="${BED2_PASS:-$NODE_PASS}"
LOGGER_PASSWORD="${LOGGER_PASS}"
DASHBOARD_PASSWORD="${DASHBOARD_PASS}"

# Validate passwords are not empty
missing=""
[ -z "$BED1_PASSWORD" ] && missing="$missing bed1 (BED1_PASS or NODE_PASS)"
[ -z "$BED2_PASSWORD" ] && missing="$missing bed2 (BED2_PASS or NODE_PASS)"
[ -z "$LOGGER_PASSWORD" ] && missing="$missing logger (LOGGER_PASS)"
[ -z "$DASHBOARD_PASSWORD" ] && missing="$missing dashboard (DASHBOARD_PASS)"

if [ -n "$missing" ]; then
    echo "Error: Missing password in .env for:$missing" >&2
    exit 1
fi

echo "Generating broker password file at $PASSWD_FILE..."

# -c creates/overwrites the file for the first user, -b passes password via CLI
mosquitto_passwd -c -b "$PASSWD_FILE" "bed1" "$BED1_PASSWORD"
mosquitto_passwd -b "$PASSWD_FILE" "bed2" "$BED2_PASSWORD"
mosquitto_passwd -b "$PASSWD_FILE" "logger" "$LOGGER_PASSWORD"
mosquitto_passwd -b "$PASSWD_FILE" "dashboard" "$DASHBOARD_PASSWORD"

chmod 600 "$PASSWD_FILE"

echo "Successfully created $PASSWD_FILE with permissions 600 for users: bed1, bed2, logger, dashboard."

