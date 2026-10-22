#!/usr/bin/env python3
"""
tests/verify_server.py - End-to-end checks for the Flask + SQLite server (S1-S8).

Needs the broker running (./broker/start.sh). Starts and stops the server and a
fake node itself, using a separate test database; never touches server/icu.db.
"""

from datetime import datetime
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request

import dotenv
import paho.mqtt.client as mqtt

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PY = str(REPO_ROOT / ".venv" / "bin" / "python")
TEST_DB = "/tmp/icu-test.db"

dotenv.load_dotenv(REPO_ROOT / ".env")
HOST = os.getenv("BROKER_HOST", "localhost")
PORT = int(os.getenv("BROKER_PORT", "1883"))
API_PORT = int(os.getenv("API_PORT", "5050"))
API = f"http://localhost:{API_PORT}"
LOGGER = (os.getenv("LOGGER_USER", "logger"), os.getenv("LOGGER_PASS", ""))
DASHBOARD = (os.getenv("DASHBOARD_USER", "dashboard"), os.getenv("DASHBOARD_PASS", ""))

results: list[tuple[str, str, str]] = []


def record(test_id: str, ok: bool, detail: str) -> None:
    status = "PASS" if ok else "FAIL"
    results.append((test_id, status, detail))
    print(f"[{status}] {test_id}: {detail}", flush=True)


def cid(name: str) -> str:
    return f"test-{name}-{secrets.token_hex(4)}"


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def get(path: str):
    with urllib.request.urlopen(API + path, timeout=3) as resp:
        return json.loads(resp.read())


def wait_until(fn, timeout: float, interval: float = 0.25):
    """Call fn until it returns a truthy value or timeout; returns the last value."""
    deadline = time.time() + timeout
    value = None
    while time.time() < deadline:
        try:
            value = fn()
            if value:
                return value
        except Exception:
            value = None
        time.sleep(interval)
    return value


def mqtt_client(name: str, creds: tuple[str, str]) -> mqtt.Client:
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid(name), clean_session=True)
    c.username_pw_set(*creds)
    c.connect(HOST, PORT, keepalive=10)
    c.loop_start()
    return c


def publish_once(creds, topic, payload, qos=1, retain=False) -> None:
    c = mqtt_client("pub", creds)
    c.publish(topic, payload=payload, qos=qos, retain=retain).wait_for_publish(timeout=3)
    c.loop_stop()
    c.disconnect()


def clear_retained() -> None:
    c = mqtt_client("cleaner", LOGGER)
    for node in ("bed1", "bed2"):
        for suffix in ("status/urgent", "status/critical", "online"):
            c.publish(f"icu/{node}/{suffix}", payload=b"", qos=1, retain=True).wait_for_publish(timeout=3)
    c.loop_stop()
    c.disconnect()


def remove_test_db() -> None:
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(TEST_DB + suffix)
        except FileNotFoundError:
            pass


def start_server(log_file) -> subprocess.Popen:
    env = dict(os.environ, DB_PATH=TEST_DB)
    return subprocess.Popen(
        [VENV_PY, "-u", "-m", "server.app"], cwd=REPO_ROOT, env=env,
        stdout=log_file, stderr=subprocess.STDOUT,
    )


def stop(proc: subprocess.Popen | None) -> None:
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def health_connected():
    h = get("/api/health")
    return h if h.get("ok") and h.get("mqtt_connected") else None


def bed1_alerts():
    return get("/api/alerts?node=bed1")["alerts"]


def main() -> int:
    if not port_open(PORT):
        print(f"Broker is not running on port {PORT}. Start it with ./broker/start.sh", file=sys.stderr)
        return 2
    if port_open(API_PORT):
        print(f"Port {API_PORT} is already in use (is the server already running?). Stop it first.", file=sys.stderr)
        return 2

    server = node = None
    log_path = Path("/tmp/icu-test-server.log")
    log_file = open(log_path, "w")
    try:
        remove_test_db()
        clear_retained()

        # S1
        server = start_server(log_file)
        h = wait_until(health_connected, timeout=10)
        record("S1", bool(h), "health ok and mqtt_connected" if h else f"health not connected within 10 s (see {log_path})")

        # S2
        node = subprocess.Popen(
            [VENV_PY, "-u", "sim/fake_node.py", "--node", "bed1"], cwd=REPO_ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True,
        )
        time.sleep(4)
        node.stdin.write("2\n"); node.stdin.flush()
        time.sleep(4)
        node.stdin.write("3\n"); node.stdin.flush()
        alerts = wait_until(lambda: (a := bed1_alerts()) and {x["level"] for x in a} == {"urgent", "critical"} and a, timeout=8)
        levels = sorted(x["level"] for x in alerts or [])
        record("S2", levels == ["critical", "urgent"], f"bed1 alerts: {levels}")

        # S3
        stop(server)
        server = start_server(log_file)
        wait_until(health_connected, timeout=10)
        time.sleep(2)  # let retained alerts be re-delivered
        after = bed1_alerts()
        same = sorted((a["id"], a["level"], a["received_at"]) for a in after) == \
            sorted((a["id"], a["level"], a["received_at"]) for a in alerts or [])
        record("S3", len(after) == 2 and same, f"{len(after)} alerts after restart, unchanged={same}")

        # S4
        def bed1_node():
            nodes = {n["node"]: n for n in get("/api/nodes")["nodes"]}
            n = nodes.get("bed1")
            return n if n and n["online"] is True and n["heartbeat_age_s"] is not None and n["heartbeat_age_s"] < 15 else None
        n = wait_until(bed1_node, timeout=12)
        record("S4", bool(n), f"bed1 online, heartbeat_age_s={n['heartbeat_age_s']}" if n else "bed1 not online with fresh heartbeat")

        # S5
        critical = next((a for a in after if a["level"] == "critical"), {})
        ack = {
            "node": "bed1", "level": "critical", "alert_ts": critical.get("alert_ts"),
            "ack_ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "by": "dashboard",
        }
        publish_once(DASHBOARD, "icu/bed1/ack", json.dumps(ack), qos=1, retain=False)
        acked = wait_until(
            lambda: (a := bed1_alerts()) and all(x["ack_ts"] and x["response_s"] is not None and x["response_s"] >= 0 for x in a) and a,
            timeout=3,
        )
        record("S5", bool(acked), f"response_s={[x['response_s'] for x in acked]}" if acked else "alerts not acknowledged within 3 s")

        # S6
        received = []
        sub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid("s6"), clean_session=True)
        sub.username_pw_set(*LOGGER)
        sub.on_message = lambda c, u, m: received.append((m.topic, m.payload, m.retain))
        sub.on_connect = lambda c, u, f, rc, p: c.subscribe("icu/bed1/status/#", qos=1)
        sub.connect(HOST, PORT, keepalive=10)
        sub.loop_start()
        time.sleep(2)
        sub.loop_stop(); sub.disconnect()
        retained_alerts = [t for t, p, r in received if r and p and t.endswith(("/urgent", "/critical"))]
        record("S6", not retained_alerts, "no retained alert" if not retained_alerts else f"retained: {retained_alerts}")

        # S7
        s = get("/api/stats")
        acked_total = s["by_level"]["urgent"]["acknowledged"] + s["by_level"]["critical"]["acknowledged"]
        means = [s["by_level"][lv]["mean_response_s"] for lv in ("urgent", "critical")]
        ok = s["total_alerts"] == 2 and acked_total == 2 and s["open_alerts"] == 0 and all(m is not None for m in means)
        record("S7", ok, f"total={s['total_alerts']} acknowledged={acked_total} open={s['open_alerts']} means={means}")

        # S8
        node.stdin.write("k\n"); node.stdin.flush()

        def offline_seen():
            nodes = {n["node"]: n for n in get("/api/nodes")["nodes"]}
            events = get("/api/events")["events"]
            return nodes.get("bed1", {}).get("online") is False and any(
                e["node"] == "bed1" and e["state"] == "offline" for e in events)
        ok = bool(wait_until(offline_seen, timeout=10))
        record("S8", ok, "bed1 offline with offline event" if ok else "bed1 not offline within 10 s")
    except Exception as e:
        record("ERROR", False, f"{type(e).__name__}: {e}")
    finally:
        if node and node.poll() is None:
            node.kill()
        stop(server)
        log_file.close()
        try:
            clear_retained()
        except Exception as e:
            print(f"[CLEANUP WARNING] {e}", file=sys.stderr)
        remove_test_db()

    print()
    for test_id, status, detail in results:
        print(f"{test_id:<6} {status:<5} {detail}")
    failed = [r for r in results if r[1] != "PASS"]
    print("\nALL SERVER TESTS PASSED." if not failed else f"\n{len(failed)} TEST(S) FAILED.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
