#!/usr/bin/env python3
"""
sim/fake_node.py - Simulated ICU Bed Node for ICU Fusion.

Pretends to be a Raspberry Pi bed node publishing vitals, alerts, and heartbeats
over MQTT according to docs/contracts.md.
"""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import random
import signal
import sys
import threading
import time

from dotenv import load_dotenv
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion


LEVEL_RANK = {
    "routine": 0,
    "urgent": 1,
    "critical": 2,
}


class NodeState:
    """Thread-safe state container for the simulated node."""

    def __init__(self, initial_level: str = "routine", initial_source: str = "live"):
        self._lock = threading.Lock()
        self._level = initial_level
        self._bio_source = initial_source
        self._running = True

    def get_state(self) -> tuple[str, str]:
        with self._lock:
            return self._level, self._bio_source

    def set_level(self, level: str) -> None:
        with self._lock:
            self._level = level

    def toggle_bio_source(self) -> str:
        with self._lock:
            self._bio_source = "replay" if self._bio_source == "live" else "live"
            return self._bio_source

    def stop(self) -> None:
        with self._lock:
            self._running = False

    def is_running(self) -> bool:
        with self._lock:
            return self._running


def generate_probabilities(level: str) -> dict[str, float]:
    """Generate probability distributions with the highest probability on the active level."""
    if level == "routine":
        p_routine = round(random.uniform(0.85, 0.95), 2)
        p_urgent = round(random.uniform(0.02, max(0.02, 1.0 - p_routine - 0.01)), 2)
        p_critical = round(max(0.0, 1.0 - p_routine - p_urgent), 2)
        return {"routine": p_routine, "urgent": p_urgent, "critical": p_critical}
    elif level == "urgent":
        p_urgent = round(random.uniform(0.80, 0.92), 2)
        p_routine = round(random.uniform(0.02, max(0.02, 1.0 - p_urgent - 0.01)), 2)
        p_critical = round(max(0.0, 1.0 - p_urgent - p_routine), 2)
        return {"routine": p_routine, "urgent": p_urgent, "critical": p_critical}
    else:  # critical
        p_critical = round(random.uniform(0.80, 0.92), 2)
        p_urgent = round(random.uniform(0.02, max(0.02, 1.0 - p_critical - 0.01)), 2)
        p_routine = round(max(0.0, 1.0 - p_critical - p_urgent), 2)
        return {"routine": p_routine, "urgent": p_urgent, "critical": p_critical}


def generate_features_and_hr(level: str) -> tuple[dict, int]:
    """Generate realistic vitals and feature values based on the status level."""
    spo2 = random.randint(96, 99)
    if level == "routine":
        gesture_conf = round(random.uniform(0.0, 0.20), 2)
        hr_delta = random.randint(-3, 5)
        tremor = round(random.uniform(0.001, 0.005), 3)
    elif level == "urgent":
        gesture_conf = round(random.uniform(0.80, 0.95), 2)
        hr_delta = random.randint(-3, 5)
        tremor = round(random.uniform(0.008, 0.020), 3)
    else:  # critical
        gesture_conf = round(random.uniform(0.80, 0.95), 2)
        hr_delta = random.randint(18, 30)
        tremor = round(random.uniform(0.010, 0.030), 3)

    hr = 75 + hr_delta
    features = {
        "gesture_conf": gesture_conf,
        "tremor": tremor,
        "hr_delta": hr_delta,
        "spo2": spo2,
    }
    return features, hr


def input_listener(state: NodeState) -> None:
    """Read user commands from stdin and adjust node state."""
    while state.is_running():
        try:
            line = sys.stdin.readline()
            if not line:
                # EOF reached (e.g., stdin not interactive)
                time.sleep(0.5)
                continue
            cmd = line.strip().lower()
            if not cmd:
                continue

            if cmd == "1":
                state.set_level("routine")
                print(">> [CONTROL] Status level set to: routine")
            elif cmd == "2":
                state.set_level("urgent")
                print(">> [CONTROL] Status level set to: urgent")
            elif cmd == "3":
                state.set_level("critical")
                print(">> [CONTROL] Status level set to: critical")
            elif cmd == "r":
                new_src = state.toggle_bio_source()
                print(f">> [CONTROL] bio_source toggled to: {new_src}")
            elif cmd == "q":
                print(">> [CONTROL] Clean quit requested.")
                state.stop()
                break
            elif cmd == "k":
                print(">> [CONTROL] Hard kill requested via os._exit(1). Last Will should fire.")
                os._exit(1)
            else:
                print(f">> [CONTROL] Unknown command: {cmd!r} (Use: 1=routine, 2=urgent, 3=critical, r=toggle source, q=quit, k=hard kill)")
        except Exception:
            break


def main():
    repo_root = Path(__file__).resolve().parent.parent
    env_file = repo_root / ".env"
    load_dotenv(dotenv_path=env_file)

    parser = argparse.ArgumentParser(description="Simulated ICU Bed Node (ICU Fusion)")
    parser.add_argument("--node", default="bed1", help="Node ID (default: bed1)")
    parser.add_argument("--user", default=None, help="MQTT username (overrides .env)")
    parser.add_argument("--password", default=None, help="MQTT password (overrides .env)")
    parser.add_argument("--host", default=None, help="Broker host (overrides .env)")
    parser.add_argument("--port", type=int, default=None, help="Broker port (overrides .env)")
    args = parser.parse_args()

    node_id = args.node

    # Determine broker host and port
    broker_host = args.host or os.getenv("BROKER_HOST", "localhost")
    broker_port = args.port or int(os.getenv("BROKER_PORT", "1883"))

    # Determine username
    if args.user is not None:
        username = args.user
    else:
        if node_id == "bed1" and os.getenv("NODE_USER"):
            username = os.getenv("NODE_USER")
        else:
            username = node_id

    # Determine password
    if args.password is not None:
        password = args.password
    else:
        if node_id == "bed1":
            password = os.getenv("BED1_PASS") or os.getenv("NODE_PASS", "")
        elif node_id == "bed2":
            password = os.getenv("BED2_PASS") or os.getenv("NODE_PASS", "")
        else:
            password = os.getenv("NODE_PASS", "")

    state = NodeState(initial_level="routine", initial_source="live")

    # Signal handlers for clean shutdown
    def sig_handler(sig, frame):
        print("\n>> Received signal, initiating clean shutdown...")
        state.stop()

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    client_id = f"sim_{node_id}_{os.getpid()}_{int(time.time())}"
    client = mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id=client_id,
    )

    if username:
        client.username_pw_set(username=username, password=password)

    # Rule 1: Connect with keepalive 5s and Last Will: topic icu/{node}/online, payload "offline", QoS 1, retain
    client.will_set(
        topic=f"icu/{node_id}/online",
        payload="offline",
        qos=1,
        retain=True,
    )

    # Rule 2: On connect, publish "online" (QoS 1, retain) to icu/{node}/online
    def on_connect(c, userdata, flags, reason_code, properties):
        if reason_code == 0:
            print(f"Connected to broker at {broker_host}:{broker_port} as user '{username}' (client_id={client_id})")
            c.publish(f"icu/{node_id}/online", payload="online", qos=1, retain=True)
            print(f"[PUB] icu/{node_id}/online (retained, QoS 1) -> online")
        else:
            print(f"Failed to connect to broker: {reason_code}")

    client.on_connect = on_connect

    print(f"Connecting fake node '{node_id}' (client_id={client_id}) to {broker_host}:{broker_port}...")
    try:
        client.connect(broker_host, broker_port, keepalive=5)
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    client.loop_start()

    # Start interactive input thread
    input_t = threading.Thread(target=input_listener, args=(state,), daemon=True)
    input_t.start()

    print(f"Fake node running for '{node_id}'.")
    print("Controls: [1] routine  [2] urgent  [3] critical  [r] toggle bio_source  [q] quit  [k] hard kill")

    start_time = time.time()
    last_status_time = 0.0
    last_heartbeat_time = 0.0
    status_interval = 3.0
    heartbeat_interval = 10.0

    previous_level = "routine"

    try:
        while state.is_running():
            now = time.time()

            # Status message every 3 s
            if now - last_status_time >= status_interval:
                current_level, bio_source = state.get_state()
                ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                features, hr = generate_features_and_hr(current_level)
                p = generate_probabilities(current_level)

                status_payload = {
                    "node": node_id,
                    "ts": ts,
                    "level": current_level,
                    "p": p,
                    "features": features,
                    "hr": hr,
                    "bio_source": bio_source,
                }
                status_json = json.dumps(status_payload)

                # Rule 4: Routine message every 3 s window (QoS 0, no retain)
                client.publish(f"icu/{node_id}/status/routine", payload=status_json, qos=0, retain=False)
                print(f"[PUB] icu/{node_id}/status/routine -> level={current_level} hr={hr} spo2={features['spo2']} gesture_conf={features['gesture_conf']:.2f}")

                # Rule 3: Urgent/critical published only when level rises compared with previous window (QoS 1, retain)
                curr_rank = LEVEL_RANK[current_level]
                prev_rank = LEVEL_RANK[previous_level]

                if curr_rank > prev_rank:
                    alert_topic = f"icu/{node_id}/status/{current_level}"
                    client.publish(alert_topic, payload=status_json, qos=1, retain=True)
                    print(f"[PUB] {alert_topic} (retained, QoS 1) -> level={current_level} hr={hr} spo2={features['spo2']} gesture_conf={features['gesture_conf']:.2f}")

                previous_level = current_level
                last_status_time = now

            # Heartbeat message every 10 s (QoS 0, no retain)
            if now - last_heartbeat_time >= heartbeat_interval:
                uptime_s = int(now - start_time)
                ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                hb_payload = {
                    "node": node_id,
                    "ts": ts,
                    "uptime_s": uptime_s,
                }
                client.publish(f"icu/{node_id}/heartbeat", payload=json.dumps(hb_payload), qos=0, retain=False)
                print(f"[PUB] icu/{node_id}/heartbeat -> uptime_s={uptime_s}")
                last_heartbeat_time = now

            time.sleep(0.1)

    finally:
        # Clean shutdown (command 'q' or SIGINT/SIGTERM)
        print("Cleaning up: publishing 'offline' and disconnecting...")
        try:
            pub_info = client.publish(f"icu/{node_id}/online", payload="offline", qos=1, retain=True)
            print(f"[PUB] icu/{node_id}/online (retained, QoS 1) -> offline")
            pub_info.wait_for_publish(timeout=2.0)
        except Exception as e:
            print(f"Error publishing offline status: {e}")

        try:
            client.disconnect()
            client.loop_stop()
        except Exception:
            pass

    print("Fake node stopped.")


if __name__ == "__main__":
    main()

