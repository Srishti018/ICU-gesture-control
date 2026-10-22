#!/usr/bin/env bash
# [PI] Set BROKER_HOST in ~/icu-fusion/.env to the laptop's IP. Never prints the password.
# Usage: node/tools/set_broker.sh 192.168.43.20
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT/.env"
ip="${1:-}"

if ! [[ "$ip" =~ ^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$ ]]; then
    echo "Usage: $0 <laptop IPv4 address>, e.g. $0 192.168.43.20" >&2
    exit 2
fi
for octet in "${BASH_REMATCH[@]:1}"; do
    if [ "$octet" -gt 255 ]; then echo "Not a valid IPv4 address: $ip" >&2; exit 2; fi
done
if [ ! -f "$ENV_FILE" ]; then
    echo "$ENV_FILE not found (run node/tools/pi_bootstrap.sh first)" >&2
    exit 1
fi

if grep -q '^BROKER_HOST=' "$ENV_FILE"; then
    sed -i "s/^BROKER_HOST=.*/BROKER_HOST=$ip/" "$ENV_FILE"
else
    echo "BROKER_HOST=$ip" >> "$ENV_FILE"
fi
grep '^BROKER_HOST=' "$ENV_FILE"
