#!/usr/bin/env bash
# Reset to a clean demo state: empty database and no retained alerts/online flags.
# Refuses to run while the server is running.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

port_open() { ss -ltn "sport = :$1" | grep -q LISTEN; }

if port_open 5050; then
    echo "Error: the server is running (port 5050). Stop it first (./stop_all.sh), then rerun." >&2
    exit 1
fi

shopt -s nullglob
dbs=(server/icu.db*)
if [ "${#dbs[@]}" -gt 0 ]; then
    rm -f "${dbs[@]}"
    echo "Deleted: ${dbs[*]}"
else
    echo "No database to delete"
fi

if port_open 1883; then
    # Clear retained messages as the logger user; the password is read from .env, never printed.
    .venv/bin/python - <<'EOF'
import os
from pathlib import Path

from dotenv import load_dotenv
import paho.mqtt.client as mqtt

load_dotenv(Path.cwd() / ".env")
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="reset-demo", clean_session=True)
client.username_pw_set(os.getenv("LOGGER_USER", "logger"), os.getenv("LOGGER_PASS", ""))
client.connect(os.getenv("BROKER_HOST", "localhost"), int(os.getenv("BROKER_PORT", "1883")), keepalive=10)
client.loop_start()
topics = [f"icu/{node}/{suffix}" for node in ("bed1", "bed2")
          for suffix in ("status/urgent", "status/critical", "online")]
for topic in topics:
    client.publish(topic, payload=b"", qos=1, retain=True).wait_for_publish(timeout=5)
client.disconnect()
client.loop_stop()
print("Cleared retained messages:", ", ".join(topics))
EOF
else
    echo "Broker not running; retained messages not cleared (run this again with the broker up if needed)"
fi
