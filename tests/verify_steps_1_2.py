#!/usr/bin/env python3
"""
tests/verify_steps_1_2.py - Automated verification for Steps 1 (Broker) and 2 (Fake Node).

Tests MQTT broker authentication, access control, retained messages, WebSocket listener,
and all simulated bed node behaviors per docs/contracts.md.
"""

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
from typing import Callable, List, Optional, Tuple

import dotenv
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion


REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PY = str(REPO_ROOT / ".venv" / "bin" / "python")

STATUS_KEYS = {"node", "ts", "level", "p", "features", "hr", "bio_source"}
FEATURE_KEYS = {"gesture_conf", "tremor", "hr_delta", "spo2"}
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
# level: (gesture_conf, tremor, hr_delta) ranges from the plan, section 7.1
VALUE_RANGES = {
    "routine": ((0.00, 0.20), (0.002, 0.008), (-3, 5)),
    "urgent": ((0.80, 0.95), (0.004, 0.012), (-3, 5)),
    "critical": ((0.80, 0.95), (0.008, 0.020), (18, 30)),
}


def cid(name: str) -> str:
    """Unique test client ID: test-<name>-<8 hex>."""
    return f"test-{name}-{secrets.token_hex(4)}"


def is_3dp_float(x) -> bool:
    return isinstance(x, float) and round(x, 3) == x


def status_errors(data: dict, node: str, level: str) -> List[str]:
    """Check a status payload against Appendix A and the plan's value ranges."""
    errors = []
    if set(data.keys()) != STATUS_KEYS:
        errors.append(f"top-level keys {sorted(data.keys())} != {sorted(STATUS_KEYS)}")
        return errors
    if data["node"] != node:
        errors.append(f"node {data['node']!r} != {node!r}")
    if not isinstance(data["ts"], str) or not TS_RE.match(data["ts"]):
        errors.append(f"ts {data['ts']!r} not YYYY-MM-DDTHH:MM:SS")
    if data["level"] != level:
        errors.append(f"level {data['level']!r} != {level!r}")
    if data["bio_source"] not in ("live", "replay"):
        errors.append(f"bio_source {data['bio_source']!r} invalid")

    p = data["p"]
    if not isinstance(p, dict) or set(p.keys()) != {"routine", "urgent", "critical"}:
        errors.append(f"p invalid: {p}")
    else:
        if not all(isinstance(v, (int, float)) and round(v, 2) == v for v in p.values()):
            errors.append(f"p values not rounded to 2 decimals: {p}")
        if abs(sum(p.values()) - 1.0) > 0.01:
            errors.append(f"p sums to {sum(p.values())}, expected 1.00")
        if max(p, key=p.get) != level:
            errors.append(f"p highest is not on {level}: {p}")

    feat = data["features"]
    if not isinstance(feat, dict) or set(feat.keys()) != FEATURE_KEYS:
        errors.append(f"features invalid: {feat}")
        return errors
    (g_lo, g_hi), (t_lo, t_hi), (d_lo, d_hi) = VALUE_RANGES[level]
    g, t, d, s = feat["gesture_conf"], feat["tremor"], feat["hr_delta"], feat["spo2"]
    if not (isinstance(g, (int, float)) and g_lo <= g <= g_hi and round(g, 3) == g):
        errors.append(f"gesture_conf {g} not in {g_lo}..{g_hi} (3 dp)")
    if not (is_3dp_float(t) and t_lo <= t <= t_hi):
        errors.append(f"tremor {t} not in {t_lo}..{t_hi} (3 dp)")
    if not (type(d) is int and d_lo <= d <= d_hi):
        errors.append(f"hr_delta {d!r} not int in {d_lo}..{d_hi}")
    if not (type(s) is int and 96 <= s <= 99):
        errors.append(f"spo2 {s!r} not int in 96..99")
    if not (type(data["hr"]) is int and data["hr"] == 75 + d):
        errors.append(f"hr {data['hr']!r} != 75 + hr_delta")
    return errors


@dataclass
class RecordedMessage:
    topic: str
    payload: bytes
    payload_str: str
    qos: int
    retain: bool
    arrival_time: float


class MessageRecorder:
    """Subscribes to icu/# and records all received MQTT messages."""

    def __init__(self, host: str, port: int, user: str, password: str, client_id: str = "recorder"):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.client_id = cid(client_id)
        self.messages: List[RecordedMessage] = []
        self._lock = threading.Lock()
        self.client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=self.client_id)
        if self.user:
            self.client.username_pw_set(self.user, self.password)
        self.client.on_message = self._on_message
        self.connected_event = threading.Event()
        self.client.on_connect = self._on_connect

    def _on_connect(self, c, userdata, flags, rc, props):
        if rc == 0:
            self.connected_event.set()

    def _on_message(self, c, userdata, msg):
        try:
            payload_str = msg.payload.decode("utf-8")
        except Exception:
            payload_str = str(msg.payload)
        rec = RecordedMessage(
            topic=msg.topic,
            payload=msg.payload,
            payload_str=payload_str,
            qos=msg.qos,
            retain=msg.retain,
            arrival_time=time.time(),
        )
        with self._lock:
            self.messages.append(rec)

    def start(self):
        self.client.connect(self.host, self.port, keepalive=10)
        self.client.subscribe("icu/#", qos=1)
        self.client.loop_start()
        if not self.connected_event.wait(timeout=5.0):
            raise RuntimeError(f"Recorder failed to connect to {self.host}:{self.port}")

    def stop(self):
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass

    def clear(self):
        with self._lock:
            self.messages.clear()

    def get_messages(
        self,
        topic_filter: Optional[str] = None,
        since: Optional[float] = None,
        predicate: Optional[Callable[[RecordedMessage], bool]] = None,
    ) -> List[RecordedMessage]:
        with self._lock:
            res = list(self.messages)
        if since is not None:
            res = [m for m in res if m.arrival_time >= since]
        if topic_filter is not None:
            res = [m for m in res if m.topic == topic_filter]
        if predicate is not None:
            res = [m for m in res if predicate(m)]
        return res

    def wait_for(
        self,
        predicate: Callable[[RecordedMessage], bool],
        timeout: float = 5.0,
        since: Optional[float] = None,
        poll_interval: float = 0.05,
    ) -> Optional[RecordedMessage]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            matches = self.get_messages(since=since, predicate=predicate)
            if matches:
                return matches[0]
            time.sleep(poll_interval)
        return None


def cleanup_retained_topics(host: str, port: int, user: str, password: str):
    """Clear all test and node retained messages by publishing empty retained payloads."""
    topics = [
        "icu/bed1/online",
        "icu/bed1/status/routine",
        "icu/bed1/status/urgent",
        "icu/bed1/status/critical",
        "icu/bed1/heartbeat",
        "icu/bed2/online",
        "icu/bed2/status/routine",
        "icu/bed2/status/urgent",
        "icu/bed2/status/critical",
        "icu/bed2/heartbeat",
        "icu/test/b1",
        "icu/test/b4",
        "icu/test/ws",
        "icu/test/ws_test",
        "icu/test/retained",
        "icu/test/retain_flag",
    ]
    try:
        cleaner = mqtt.Client(
            CallbackAPIVersion.VERSION2,
            client_id=cid("cleaner"),
        )
        if user:
            cleaner.username_pw_set(user, password)
        cleaner.connect(host, port, keepalive=5)
        cleaner.loop_start()
        for t in topics:
            cleaner.publish(t, payload=b"", qos=1, retain=True)
        time.sleep(0.5)
        cleaner.loop_stop()
        cleaner.disconnect()
    except Exception as e:
        print(f"[CLEANUP WARNING] {e}", file=sys.stderr)


# ==============================================================================
# Step 1: Broker Tests (B1 - B5)
# ==============================================================================

def test_b1(host: str, port: int, logger_user: str, logger_pass: str, bed1_user: str, bed1_pass: str) -> Tuple[str, str]:
    """B1: logger can subscribe and bed1 can publish on port 1883 (message received)."""
    sub_received = []
    sub_event = threading.Event()

    def on_sub_connect(c, u, f, rc, p):
        if rc == 0:
            c.subscribe("icu/test/b1", qos=1)

    def on_sub_msg(c, u, msg):
        sub_received.append(msg.payload.decode("utf-8"))
        sub_event.set()

    sub_client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=cid("b1_sub"))
    sub_client.username_pw_set(logger_user, logger_pass)
    sub_client.on_connect = on_sub_connect
    sub_client.on_message = on_sub_msg

    pub_client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=cid("b1_pub"))
    pub_client.username_pw_set(bed1_user, bed1_pass)

    try:
        sub_client.connect(host, port, keepalive=5)
        sub_client.loop_start()
        time.sleep(0.3)

        pub_client.connect(host, port, keepalive=5)
        pub_client.loop_start()
        pub_client.publish("icu/test/b1", payload="b1_payload_ok", qos=1)

        if sub_event.wait(timeout=5.0):
            if "b1_payload_ok" in sub_received:
                return "PASS", "logger subscribed and bed1 published successfully"
            return "FAIL", f"Unexpected payload received: {sub_received}"
        return "FAIL", "Message not received within 5s"
    finally:
        sub_client.loop_stop()
        sub_client.disconnect()
        pub_client.loop_stop()
        pub_client.disconnect()


def test_b2(host: str, port: int) -> Tuple[str, str]:
    """B2: Anonymous connection is refused."""
    event = threading.Event()
    refused = False
    refusal_reason = ""

    def on_connect(c, u, f, rc, p):
        nonlocal refused, refusal_reason
        if rc != 0:
            refused = True
            refusal_reason = f"Refused with return code: {rc}"
        event.set()

    anon_client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=cid("b2_anon"))
    anon_client.on_connect = on_connect

    try:
        anon_client.connect(host, port, keepalive=5)
        anon_client.loop_start()
        event.wait(timeout=3.0)
    except Exception as e:
        refused = True
        refusal_reason = f"Connection exception: {e}"
    finally:
        anon_client.loop_stop()
        try:
            anon_client.disconnect()
        except Exception:
            pass

    if refused:
        return "PASS", refusal_reason or "Anonymous connection was refused"
    return "FAIL", "Anonymous connection was unexpectedly accepted"


def test_b3(host: str, port: int, bed1_user: str) -> Tuple[str, str]:
    """B3: Wrong password is refused."""
    event = threading.Event()
    refused = False
    refusal_reason = ""

    def on_connect(c, u, f, rc, p):
        nonlocal refused, refusal_reason
        if rc != 0:
            refused = True
            refusal_reason = f"Refused with return code: {rc}"
        event.set()

    wrong_client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=cid("b3_wrong"))
    wrong_client.username_pw_set(bed1_user, "definitely_wrong_password_xyz")
    wrong_client.on_connect = on_connect

    try:
        wrong_client.connect(host, port, keepalive=5)
        wrong_client.loop_start()
        event.wait(timeout=3.0)
    except Exception as e:
        refused = True
        refusal_reason = f"Connection exception: {e}"
    finally:
        wrong_client.loop_stop()
        try:
            wrong_client.disconnect()
        except Exception:
            pass

    if refused:
        return "PASS", refusal_reason or "Wrong password refused"
    return "FAIL", "Connection with wrong password was unexpectedly accepted"


def test_b4(host: str, port: int, bed1_user: str, bed1_pass: str, logger_user: str, logger_pass: str) -> Tuple[str, str]:
    """B4: Retained message: publish with retain, then a NEW client subscribing receives it with retain=True;
       then clear it with an empty retained message and confirm a new subscriber gets nothing."""
    topic = "icu/test/b4_retained"
    token = "kept_token_b4"

    # 1. Publish retained message as bed1
    pub = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=cid("b4_pub"))
    pub.username_pw_set(bed1_user, bed1_pass)
    pub.connect(host, port, keepalive=5)
    pub.loop_start()
    pub.publish(topic, payload=token, qos=1, retain=True)
    time.sleep(0.5)
    pub.loop_stop()
    pub.disconnect()

    # 2. Connect NEW client subscribing to the topic
    rec_event = threading.Event()
    received_msgs = []

    def on_msg1(c, u, msg):
        received_msgs.append((msg.payload.decode("utf-8"), msg.retain))
        rec_event.set()

    new_sub = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=cid("b4_newsub"))
    new_sub.username_pw_set(logger_user, logger_pass)
    new_sub.on_message = on_msg1
    new_sub.connect(host, port, keepalive=5)
    new_sub.subscribe(topic, qos=1)
    new_sub.loop_start()

    if not rec_event.wait(timeout=4.0):
        new_sub.loop_stop()
        new_sub.disconnect()
        return "FAIL", "New subscriber did not receive the retained message"

    payload_rcvd, retain_flag = received_msgs[0]
    new_sub.loop_stop()
    new_sub.disconnect()

    if payload_rcvd != token:
        return "FAIL", f"Expected payload '{token}', got '{payload_rcvd}'"
    if not retain_flag:
        return "FAIL", f"Expected retain=True on new subscriber delivery, got {retain_flag}"

    # 3. Clear with empty retained message
    clear_pub = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=cid("b4_clear"))
    clear_pub.username_pw_set(bed1_user, bed1_pass)
    clear_pub.connect(host, port, keepalive=5)
    clear_pub.loop_start()
    clear_pub.publish(topic, payload=b"", qos=1, retain=True)
    time.sleep(0.5)
    clear_pub.loop_stop()
    clear_pub.disconnect()

    # 4. Connect ANOTHER new client and verify nothing arrives
    cleared_event = threading.Event()
    cleared_msgs = []

    def on_msg2(c, u, msg):
        cleared_msgs.append(msg.payload)
        cleared_event.set()

    sub2 = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=cid("b4_sub2"))
    sub2.username_pw_set(logger_user, logger_pass)
    sub2.on_message = on_msg2
    sub2.connect(host, port, keepalive=5)
    sub2.subscribe(topic, qos=1)
    sub2.loop_start()

    arrived = cleared_event.wait(timeout=2.0)
    sub2.loop_stop()
    sub2.disconnect()

    if arrived and len(cleared_msgs) > 0 and len(cleared_msgs[0]) > 0:
        return "FAIL", f"Expected no retained message after clear, but received: {cleared_msgs}"

    return "PASS", "Retained message verified and cleared successfully"


def test_b5(host: str, ws_port: int, mqtt_port: int, dash_user: str, dash_pass: str, logger_user: str, logger_pass: str) -> Tuple[str, str]:
    """B5: WebSocket listener: connect with transport='websockets' to localhost:9001 as dashboard user,
       subscribe to icu/#, and receive a test message published on 1883."""
    topic = "icu/test/b5_ws"
    payload = "ws_test_token"
    ws_event = threading.Event()
    received_msgs = []

    def on_ws_connect(c, u, f, rc, p):
        if rc == 0:
            c.subscribe("icu/#", qos=1)

    def on_ws_msg(c, u, msg):
        if msg.topic == topic:
            received_msgs.append(msg.payload.decode("utf-8"))
            ws_event.set()

    ws_client = mqtt.Client(
        CallbackAPIVersion.VERSION2,
        client_id=cid("b5_ws"),
        transport="websockets",
    )
    ws_client.username_pw_set(dash_user, dash_pass)
    ws_client.on_connect = on_ws_connect
    ws_client.on_message = on_ws_msg

    try:
        ws_client.connect(host, ws_port, keepalive=5)
        ws_client.loop_start()
        time.sleep(0.5)

        # Publish via standard MQTT on port 1883
        pub = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=cid("b5_pub"))
        pub.username_pw_set(logger_user, logger_pass)
        pub.connect(host, mqtt_port, keepalive=5)
        pub.loop_start()
        pub.publish(topic, payload=payload, qos=1)
        time.sleep(0.3)
        pub.loop_stop()
        pub.disconnect()

        if ws_event.wait(timeout=5.0):
            if payload in received_msgs:
                return "PASS", "WebSocket client received message published via 1883"
            return "FAIL", f"Unexpected payload: {received_msgs}"
        return "FAIL", "WebSocket client did not receive message within 5s"
    finally:
        ws_client.loop_stop()
        try:
            ws_client.disconnect()
        except Exception:
            pass


# ==============================================================================
# Step 2: Fake Node Tests (N1 - N12)
# ==============================================================================

def run_all_tests() -> int:
    env_file = REPO_ROOT / ".env"
    dotenv.load_dotenv(dotenv_path=env_file)

    broker_host = os.getenv("BROKER_HOST", "localhost")
    broker_port = int(os.getenv("BROKER_PORT", "1883"))
    broker_ws_port = int(os.getenv("BROKER_WS_PORT", "9001"))

    logger_user = os.getenv("LOGGER_USER", "logger")
    logger_pass = os.getenv("LOGGER_PASS", "")

    bed1_user = os.getenv("NODE_USER", "bed1")
    bed1_pass = os.getenv("BED1_PASS") or os.getenv("NODE_PASS", "")

    bed2_user = "bed2"
    bed2_pass = os.getenv("BED2_PASS") or os.getenv("NODE_PASS", "")

    dash_user = os.getenv("DASHBOARD_USER", "dashboard")
    dash_pass = os.getenv("DASHBOARD_PASS", "")

    print("================================================================================")
    print("           ICU Fusion — Automated Verification (Steps 1 & 2)                    ")
    print("================================================================================")
    print(f"Target Broker: {broker_host}:{broker_port} (MQTT), {broker_host}:{broker_ws_port} (WS)")
    print()

    results: List[Tuple[str, str, str, str]] = []

    # Clean up any lingering retained messages before beginning
    cleanup_retained_topics(broker_host, broker_port, logger_user, logger_pass)

    # --------------------------------------------------------------------------
    # Step 1: Broker Tests
    # --------------------------------------------------------------------------
    print("--- Running Broker Tests (Step 1) ---")

    # B1
    status, reason = test_b1(broker_host, broker_port, logger_user, logger_pass, bed1_user, bed1_pass)
    results.append(("B1", "logger subscribe & bed1 publish (1883)", status, reason))
    print(f"[{status}] B1: {reason}")

    # B2
    status, reason = test_b2(broker_host, broker_port)
    results.append(("B2", "Anonymous connection refused", status, reason))
    print(f"[{status}] B2: {reason}")

    # B3
    status, reason = test_b3(broker_host, broker_port, bed1_user)
    results.append(("B3", "Wrong password refused", status, reason))
    print(f"[{status}] B3: {reason}")

    # B4
    status, reason = test_b4(broker_host, broker_port, bed1_user, bed1_pass, logger_user, logger_pass)
    results.append(("B4", "Retained message delivery & clear", status, reason))
    print(f"[{status}] B4: {reason}")

    # B5
    status, reason = test_b5(broker_host, broker_ws_port, broker_port, dash_user, dash_pass, logger_user, logger_pass)
    results.append(("B5", "WebSocket listener on port 9001", status, reason))
    print(f"[{status}] B5: {reason}")

    # --------------------------------------------------------------------------
    # Step 2: Fake Node Tests (N1 - N12)
    # --------------------------------------------------------------------------
    print("\n--- Running Fake Node Tests (Step 2) ---")

    recorder = MessageRecorder(broker_host, broker_port, logger_user, logger_pass)
    recorder.start()

    proc: Optional[subprocess.Popen] = None
    proc2: Optional[subprocess.Popen] = None

    try:
        cleanup_retained_topics(broker_host, broker_port, logger_user, logger_pass)
        recorder.clear()

        # Launch fake node bed1
        fake_node_script = str(REPO_ROOT / "sim" / "fake_node.py")
        cmd = [VENV_PY, "-u", fake_node_script, "--node", "bed1"]
        proc_start_time = time.time()
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        # N1: On start, icu/bed1/online receives "online", retained
        online_msg = recorder.wait_for(
            lambda m: m.topic == "icu/bed1/online" and m.payload_str == "online",
            timeout=5.0,
        )
        if online_msg:
            # Verify retained on broker via a separate new subscriber
            check_sub = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=cid("n1_check"))
            check_sub.username_pw_set(logger_user, logger_pass)
            check_event = threading.Event()
            check_retain = False

            def on_n1_msg(c, u, msg):
                nonlocal check_retain
                if msg.topic == "icu/bed1/online" and msg.payload.decode("utf-8") == "online":
                    check_retain = msg.retain
                    check_event.set()

            check_sub.on_message = on_n1_msg
            check_sub.connect(broker_host, broker_port, keepalive=5)
            check_sub.subscribe("icu/bed1/online", qos=1)
            check_sub.loop_start()
            check_event.wait(timeout=3.0)
            check_sub.loop_stop()
            check_sub.disconnect()

            if check_retain:
                results.append(("N1", "icu/bed1/online receives 'online' retained on start", "PASS", "Received 'online' with retain=True on broker"))
                print("[PASS] N1: icu/bed1/online receives 'online' retained on start")
            else:
                results.append(("N1", "icu/bed1/online receives 'online' retained on start", "FAIL", "Message received but retain flag was not True on broker"))
                print("[FAIL] N1: Message received but retain flag was not True on broker")
        else:
            results.append(("N1", "icu/bed1/online receives 'online' retained on start", "FAIL", "Timed out waiting for 'online' on icu/bed1/online"))
            print("[FAIL] N1: Timed out waiting for 'online' on icu/bed1/online")

        # N2: Routine status: over 10 s, 3 or 4 messages on icu/bed1/status/routine, QoS 0, not retained
        t_window_start = time.time()
        time.sleep(10.0)
        t_window_end = time.time()

        routine_msgs = recorder.get_messages(
            topic_filter="icu/bed1/status/routine",
            since=t_window_start,
        )
        count_routine = len(routine_msgs)
        if count_routine in (3, 4):
            qos_retain_ok = all(m.qos == 0 and not m.retain for m in routine_msgs)
            if qos_retain_ok:
                results.append(("N2", "Routine status over 10 s (3-4 msgs, QoS 0, not retained)", "PASS", f"Received {count_routine} messages, all QoS 0, retain=False"))
                print(f"[PASS] N2: Routine status over 10 s ({count_routine} messages, QoS 0, retain=False)")
            else:
                results.append(("N2", "Routine status over 10 s (3-4 msgs, QoS 0, not retained)", "FAIL", "Some routine messages had QoS!=0 or retain!=False"))
                print("[FAIL] N2: Some routine messages had QoS!=0 or retain!=False")
        else:
            results.append(("N2", "Routine status over 10 s (3-4 msgs, QoS 0, not retained)", "FAIL", f"Expected 3 or 4 messages over 10s, got {count_routine}"))
            print(f"[FAIL] N2: Expected 3 or 4 messages over 10s, got {count_routine}")

        # N3: Payload shape matches contract exactly
        if routine_msgs:
            sample = routine_msgs[-1]
            try:
                errors = []
                for m in routine_msgs:
                    errors += status_errors(json.loads(m.payload_str), "bed1", "routine")
                if routine_msgs and json.loads(sample.payload_str)["bio_source"] != "live":
                    errors.append("bio_source should start as 'live'")

                if not errors:
                    results.append(("N3", "Payload shape matches contract", "PASS", "All contract fields, types, and values validated"))
                    print("[PASS] N3: Payload shape matches contract exactly")
                else:
                    results.append(("N3", "Payload shape matches contract", "FAIL", "; ".join(errors)))
                    print(f"[FAIL] N3: Payload errors: {'; '.join(errors)}")
            except Exception as e:
                results.append(("N3", "Payload shape matches contract", "FAIL", f"JSON parsing error: {e}"))
                print(f"[FAIL] N3: JSON parsing error: {e}")
        else:
            results.append(("N3", "Payload shape matches contract", "FAIL", "No routine status message available to validate"))
            print("[FAIL] N3: No routine status message available to validate")

        # N4: Heartbeat on icu/bed1/heartbeat within 12 s, with node, ts and uptime_s
        hb_msg = recorder.wait_for(
            lambda m: m.topic == "icu/bed1/heartbeat",
            timeout=12.0,
            since=proc_start_time,
        )
        if hb_msg:
            try:
                hb_data = json.loads(hb_msg.payload_str)
                if (
                    hb_data.get("node") == "bed1"
                    and re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$", hb_data.get("ts", ""))
                    and isinstance(hb_data.get("uptime_s"), int)
                    and hb_data.get("uptime_s") >= 0
                ):
                    results.append(("N4", "Heartbeat on icu/bed1/heartbeat within 12 s", "PASS", f"Heartbeat received: uptime_s={hb_data['uptime_s']}"))
                    print(f"[PASS] N4: Heartbeat received: uptime_s={hb_data['uptime_s']}")
                else:
                    results.append(("N4", "Heartbeat on icu/bed1/heartbeat within 12 s", "FAIL", f"Invalid heartbeat payload: {hb_data}"))
                    print(f"[FAIL] N4: Invalid heartbeat payload: {hb_data}")
            except Exception as e:
                results.append(("N4", "Heartbeat on icu/bed1/heartbeat within 12 s", "FAIL", f"JSON error: {e}"))
                print(f"[FAIL] N4: JSON error: {e}")
        else:
            results.append(("N4", "Heartbeat on icu/bed1/heartbeat within 12 s", "FAIL", "Timed out waiting for heartbeat"))
            print("[FAIL] N4: Timed out waiting for heartbeat")

        # N5: Send '2': exactly ONE message on icu/bed1/status/urgent, QoS 1, gesture_conf in 0.8-0.95, hr_delta in -3..5. Wait 7 s: no second urgent message.
        t_send_2 = time.time()
        assert proc.stdin is not None
        proc.stdin.write("2\n")
        proc.stdin.flush()

        urgent_msg = recorder.wait_for(
            lambda m: m.topic == "icu/bed1/status/urgent",
            timeout=5.0,
            since=t_send_2,
        )

        if urgent_msg:
            time.sleep(7.0)
            urgent_all = recorder.get_messages(
                topic_filter="icu/bed1/status/urgent",
                since=t_send_2,
            )
            count_urgent = len(urgent_all)
            try:
                errors = status_errors(json.loads(urgent_msg.payload_str), "bed1", "urgent")
                if count_urgent != 1:
                    errors.append(f"Expected exactly 1 urgent message, received {count_urgent}")
                if urgent_msg.qos != 1:
                    errors.append(f"QoS is {urgent_msg.qos}, expected 1")

                if not errors:
                    results.append(("N5", "Send '2': 1 urgent msg (QoS 1, features valid, no repeats)", "PASS", "Received 1 urgent message, QoS 1, features valid, no repeats over 7s"))
                    print("[PASS] N5: Exactly 1 urgent message (QoS 1, valid features, no repeat in 7s)")
                else:
                    results.append(("N5", "Send '2': 1 urgent msg (QoS 1, features valid, no repeats)", "FAIL", "; ".join(errors)))
                    print(f"[FAIL] N5: {'; '.join(errors)}")
            except Exception as e:
                results.append(("N5", "Send '2': 1 urgent msg (QoS 1, features valid, no repeats)", "FAIL", f"JSON parsing error: {e}"))
                print(f"[FAIL] N5: JSON parsing error: {e}")
        else:
            results.append(("N5", "Send '2': 1 urgent msg (QoS 1, features valid, no repeats)", "FAIL", "No message received on icu/bed1/status/urgent"))
            print("[FAIL] N5: No message received on icu/bed1/status/urgent")

        # N6: Send '3': exactly ONE message on icu/bed1/status/critical, QoS 1, hr_delta in 18-30. Wait 7 s: no repeat.
        t_send_3 = time.time()
        proc.stdin.write("3\n")
        proc.stdin.flush()

        critical_msg = recorder.wait_for(
            lambda m: m.topic == "icu/bed1/status/critical",
            timeout=5.0,
            since=t_send_3,
        )

        if critical_msg:
            time.sleep(7.0)
            critical_all = recorder.get_messages(
                topic_filter="icu/bed1/status/critical",
                since=t_send_3,
            )
            count_critical = len(critical_all)
            try:
                errors = status_errors(json.loads(critical_msg.payload_str), "bed1", "critical")
                if count_critical != 1:
                    errors.append(f"Expected exactly 1 critical message, received {count_critical}")
                if critical_msg.qos != 1:
                    errors.append(f"QoS is {critical_msg.qos}, expected 1")

                if not errors:
                    results.append(("N6", "Send '3': 1 critical msg (QoS 1, hr_delta 18-30, no repeat)", "PASS", "Received 1 critical message, QoS 1, hr_delta 18..30, no repeats over 7s"))
                    print("[PASS] N6: Exactly 1 critical message (QoS 1, hr_delta in 18-30, no repeat in 7s)")
                else:
                    results.append(("N6", "Send '3': 1 critical msg (QoS 1, hr_delta 18-30, no repeat)", "FAIL", "; ".join(errors)))
                    print(f"[FAIL] N6: {'; '.join(errors)}")
            except Exception as e:
                results.append(("N6", "Send '3': 1 critical msg (QoS 1, hr_delta 18-30, no repeat)", "FAIL", f"JSON parsing error: {e}"))
                print(f"[FAIL] N6: JSON parsing error: {e}")
        else:
            results.append(("N6", "Send '3': 1 critical msg (QoS 1, hr_delta 18-30, no repeat)", "FAIL", "No message received on icu/bed1/status/critical"))
            print("[FAIL] N6: No message received on icu/bed1/status/critical")

        # N7: A NEW subscriber now receives the critical message with retain=True
        n7_client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=cid("n7_sub"))
        n7_client.username_pw_set(logger_user, logger_pass)
        n7_event = threading.Event()
        n7_retained = False
        n7_payload = ""

        def on_n7_msg(c, u, msg):
            nonlocal n7_retained, n7_payload
            if msg.topic == "icu/bed1/status/critical":
                n7_retained = msg.retain
                n7_payload = msg.payload.decode("utf-8")
                n7_event.set()

        n7_client.on_message = on_n7_msg
        n7_client.connect(broker_host, broker_port, keepalive=5)
        n7_client.subscribe("icu/bed1/status/critical", qos=1)
        n7_client.loop_start()

        if n7_event.wait(timeout=4.0):
            n7_client.loop_stop()
            n7_client.disconnect()
            if n7_retained:
                results.append(("N7", "NEW subscriber receives critical message with retain=True", "PASS", "Retained critical message received by new subscriber"))
                print("[PASS] N7: NEW subscriber receives critical message with retain=True")
            else:
                results.append(("N7", "NEW subscriber receives critical message with retain=True", "FAIL", "Message received but retain flag was False"))
                print("[FAIL] N7: Message received but retain flag was False")
        else:
            n7_client.loop_stop()
            n7_client.disconnect()
            results.append(("N7", "NEW subscriber receives critical message with retain=True", "FAIL", "No message arrived for new subscriber"))
            print("[FAIL] N7: No message arrived for new subscriber")

        # N8: Send '1', wait 4 s, send '3': a new critical message is published (it was a rise again)
        proc.stdin.write("1\n")
        proc.stdin.flush()
        time.sleep(4.0)

        t_rise = time.time()
        proc.stdin.write("3\n")
        proc.stdin.flush()

        rise_critical = recorder.wait_for(
            lambda m: m.topic == "icu/bed1/status/critical",
            timeout=5.0,
            since=t_rise,
        )
        if rise_critical and rise_critical.qos == 1:
            results.append(("N8", "Send '1', wait 4s, send '3': new critical message published", "PASS", "New critical message published upon re-escalation"))
            print("[PASS] N8: Re-escalation to critical triggers new alert publish")
        else:
            results.append(("N8", "Send '1', wait 4s, send '3': new critical message published", "FAIL", "No new critical message published upon level rise"))
            print("[FAIL] N8: No new critical message published upon level rise")

        # N9: Send 'r': next routine message has bio_source 'replay'
        t_r = time.time()
        proc.stdin.write("r\n")
        proc.stdin.flush()

        replay_routine = recorder.wait_for(
            lambda m: m.topic == "icu/bed1/status/routine",
            timeout=5.0,
            since=t_r,
        )
        if replay_routine:
            try:
                rep_data = json.loads(replay_routine.payload_str)
                if rep_data.get("bio_source") == "replay":
                    results.append(("N9", "Send 'r': next routine message has bio_source 'replay'", "PASS", "bio_source successfully toggled to 'replay'"))
                    print("[PASS] N9: bio_source is 'replay' after toggling")
                else:
                    results.append(("N9", "Send 'r': next routine message has bio_source 'replay'", "FAIL", f"bio_source is '{rep_data.get('bio_source')}'"))
                    print(f"[FAIL] N9: bio_source is '{rep_data.get('bio_source')}'")
            except Exception as e:
                results.append(("N9", "Send 'r': next routine message has bio_source 'replay'", "FAIL", f"JSON parsing error: {e}"))
                print(f"[FAIL] N9: JSON parsing error: {e}")
        else:
            results.append(("N9", "Send 'r': next routine message has bio_source 'replay'", "FAIL", "Timed out waiting for routine message"))
            print("[FAIL] N9: Timed out waiting for routine message")

        # N10: Send 'k' (hard kill): icu/bed1/online becomes 'offline' within 10 s (Last Will)
        t_k = time.time()
        proc.stdin.write("k\n")
        proc.stdin.flush()

        offline_lwt = recorder.wait_for(
            lambda m: m.topic == "icu/bed1/online" and m.payload_str == "offline",
            timeout=10.0,
            since=t_k,
        )
        try:
            proc.wait(timeout=3.0)
        except Exception:
            pass

        if offline_lwt:
            results.append(("N10", "Send 'k' (hard kill): icu/bed1/online becomes 'offline' (LWT)", "PASS", "Last Will message 'offline' received within 10s"))
            print("[PASS] N10: Last Will message 'offline' received upon hard kill")
        else:
            results.append(("N10", "Send 'k' (hard kill): icu/bed1/online becomes 'offline' (LWT)", "FAIL", "Timed out waiting for LWT 'offline' on icu/bed1/online"))
            print("[FAIL] N10: Timed out waiting for LWT 'offline' on icu/bed1/online")

        # N11: Restart as bed1, send 'q': icu/bed1/online becomes 'offline' (clean quit)
        cmd_restart = [VENV_PY, "-u", fake_node_script, "--node", "bed1"]
        t_restart = time.time()
        proc = subprocess.Popen(
            cmd_restart,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        online_n11 = recorder.wait_for(
            lambda m: m.topic == "icu/bed1/online" and m.payload_str == "online",
            timeout=5.0,
            since=t_restart,
        )
        if not online_n11:
            results.append(("N11", "Restart as bed1, send 'q': clean quit publishes 'offline'", "FAIL", "Did not receive 'online' upon restart"))
            print("[FAIL] N11: Did not receive 'online' upon restart")
        else:
            t_q = time.time()
            proc.stdin.write("q\n")
            proc.stdin.flush()

            offline_n11 = recorder.wait_for(
                lambda m: m.topic == "icu/bed1/online" and m.payload_str == "offline",
                timeout=5.0,
                since=t_q,
            )
            exit_code = proc.wait(timeout=5.0)

            if offline_n11 and exit_code == 0:
                results.append(("N11", "Restart as bed1, send 'q': clean quit publishes 'offline'", "PASS", "Clean quit published 'offline' and process exited 0"))
                print("[PASS] N11: Clean quit published 'offline' and exited 0")
            else:
                results.append(("N11", "Restart as bed1, send 'q': clean quit publishes 'offline'", "FAIL", f"offline_received={bool(offline_n11)}, exit_code={exit_code}"))
                print(f"[FAIL] N11: offline_received={bool(offline_n11)}, exit_code={exit_code}")

        # N12: Run bed1 and bed2 at the same time for 10 s: both publish routine messages,
        # and neither disconnects the other (check that each client ID is unique)
        cleanup_retained_topics(broker_host, broker_port, logger_user, logger_pass)
        cmd_bed1 = [VENV_PY, "-u", fake_node_script, "--node", "bed1"]
        cmd_bed2 = [VENV_PY, "-u", fake_node_script, "--node", "bed2"]

        t_simultaneous = time.time()
        proc = subprocess.Popen(
            cmd_bed1,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        proc2 = subprocess.Popen(
            cmd_bed2,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        time.sleep(10.0)

        p1_alive = proc.poll() is None
        p2_alive = proc2.poll() is None

        bed1_routine = recorder.get_messages(
            topic_filter="icu/bed1/status/routine",
            since=t_simultaneous,
        )
        bed2_routine = recorder.get_messages(
            topic_filter="icu/bed2/status/routine",
            since=t_simultaneous,
        )

        # Neither node may have gone offline during the 10 s window
        early_offline = recorder.get_messages(
            since=t_simultaneous,
            predicate=lambda m: m.topic in ("icu/bed1/online", "icu/bed2/online") and m.payload_str == "offline",
        )
        t_quit = time.time()

        # Clean quit both, then read their output to look for disconnect lines
        outputs = []
        for p in (proc, proc2):
            try:
                out, _ = p.communicate("q\n", timeout=5.0)
                outputs.append(out or "")
            except Exception:
                outputs.append("")
        saw_disconnect = any("disconnected" in out for out in outputs)
        early_offline = [m for m in early_offline if m.arrival_time < t_quit]

        if saw_disconnect or early_offline:
            results.append(("N12", "Simultaneous bed1 and bed2 run without disconnecting (unique client IDs)", "FAIL", f"disconnect_in_output={saw_disconnect}, offline_during_window={len(early_offline)}"))
            print(f"[FAIL] N12: disconnect_in_output={saw_disconnect}, offline_during_window={len(early_offline)}")
        elif p1_alive and p2_alive and len(bed1_routine) >= 3 and len(bed2_routine) >= 3:
            results.append(("N12", "Simultaneous bed1 and bed2 run without disconnecting (unique client IDs)", "PASS", f"Both alive for 10s: bed1={len(bed1_routine)} msgs, bed2={len(bed2_routine)} msgs"))
            print(f"[PASS] N12: Both bed1 and bed2 published routine messages simultaneously (bed1={len(bed1_routine)}, bed2={len(bed2_routine)})")
        else:
            results.append(("N12", "Simultaneous bed1 and bed2 run without disconnecting (unique client IDs)", "FAIL", f"p1_alive={p1_alive}, p2_alive={p2_alive}, bed1_msgs={len(bed1_routine)}, bed2_msgs={len(bed2_routine)}"))
            print(f"[FAIL] N12: p1_alive={p1_alive}, p2_alive={p2_alive}, bed1_msgs={len(bed1_routine)}, bed2_msgs={len(bed2_routine)}")

    finally:
        # Stop any remaining processes
        for p in (proc, proc2):
            if p and p.poll() is None:
                try:
                    p.kill()
                except Exception:
                    pass

        # Cleanup retained messages on broker
        cleanup_retained_topics(broker_host, broker_port, logger_user, logger_pass)
        recorder.stop()

    # --------------------------------------------------------------------------
    # Final Report
    # --------------------------------------------------------------------------
    print("\n" + "=" * 90)
    print(f"{'ID':<6} | {'Test Description':<48} | {'Status':<6} | {'Reason / Details'}")
    print("-" * 90)
    all_passed = True
    for test_id, desc, status, reason in results:
        if status != "PASS":
            all_passed = False
        print(f"{test_id:<6} | {desc:<48} | {status:<6} | {reason}")
    print("=" * 90)

    if all_passed:
        print("\nALL TESTS PASSED SUCCESSFULLY.")
        return 0
    else:
        print("\nSOME TESTS FAILED. PLEASE SEE DETAILS ABOVE.")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())

