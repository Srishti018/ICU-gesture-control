"""MQTT logger: subscribes to every icu/ topic and stores what it receives.

Handlers take (node, payload_bytes, retain) and only touch db.py, so they can be
unit tested without a broker. The ack handler also takes a publish function.
"""

import json
import logging

import paho.mqtt.client as mqtt

from server import config, db
from server.timeutil import now_local_iso

log = logging.getLogger("mqtt")

SUBSCRIPTIONS = [
    "icu/+/status/routine",
    "icu/+/status/urgent",
    "icu/+/status/critical",
    "icu/+/heartbeat",
    "icu/+/online",
    "icu/+/ack",
]
ALERT_LEVELS = ("urgent", "critical")


def parse_topic(topic: str) -> tuple[str, str] | None:
    """'icu/bed1/status/critical' -> ('bed1', 'status/critical'); None if not ours."""
    parts = topic.split("/")
    if len(parts) < 3 or parts[0] != "icu" or not parts[1]:
        return None
    return parts[1], "/".join(parts[2:])


def _load_json(node: str, kind: str, payload: bytes) -> dict | None:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        log.warning("invalid JSON on icu/%s/%s, ignored", node, kind)
        return None
    if not isinstance(data, dict):
        log.warning("non-object JSON on icu/%s/%s, ignored", node, kind)
        return None
    if "node" in data and data["node"] != node:
        log.warning("payload node %r differs from topic node %r; using topic", data["node"], node)
        data["node"] = node
    return data


# --- handlers ---------------------------------------------------------------

def handle_routine(node: str, payload: bytes, retain: bool) -> None:
    data = _load_json(node, "status/routine", payload)
    if data is None:
        return
    db.upsert_status(node, json.dumps(data), now_local_iso())


def handle_alert(node: str, level: str, payload: bytes, retain: bool) -> None:
    data = _load_json(node, f"status/{level}", payload)
    if data is None:
        return
    alert_ts = data.get("ts") or now_local_iso()
    if db.insert_alert(node, level, alert_ts, now_local_iso(), json.dumps(data)):
        log.info("ALERT %s %s", node, level)


def handle_heartbeat(node: str, payload: bytes, retain: bool) -> None:
    db.upsert_heartbeat(node, now_local_iso())


def handle_online(node: str, payload: bytes, retain: bool) -> None:
    text = payload.decode("utf-8", errors="replace").strip()
    if text not in ("online", "offline"):
        log.warning("unexpected payload on icu/%s/online: %r, ignored", node, text[:40])
        return
    if db.set_online(node, text == "online", now_local_iso()):
        log.info("NODE %s %s", node, text)


def handle_ack(node: str, payload: bytes, retain: bool, publish) -> None:
    data = _load_json(node, "ack", payload)
    if data is None:
        return
    ack_received_at = now_local_iso()
    count = db.ack_open_alerts(node, data.get("ack_ts") or ack_received_at, ack_received_at)
    for level in ALERT_LEVELS:
        publish(f"icu/{node}/status/{level}", b"", qos=1, retain=True)
    if count:
        log.info("ACK %s: %d alert(s) acknowledged", node, count)
    else:
        log.warning("ACK %s: no open alerts (retained alerts cleared anyway)", node)


def dispatch(topic: str, payload: bytes, retain: bool, publish) -> None:
    """Route one message to its handler. Never raises."""
    parsed = parse_topic(topic)
    if parsed is None:
        return
    node, kind = parsed
    if not payload:
        log.debug("empty payload on %s ignored", topic)
        return
    try:
        if kind == "status/routine":
            handle_routine(node, payload, retain)
        elif kind in ("status/urgent", "status/critical"):
            handle_alert(node, kind.split("/")[1], payload, retain)
        elif kind == "heartbeat":
            handle_heartbeat(node, payload, retain)
        elif kind == "online":
            handle_online(node, payload, retain)
        elif kind == "ack":
            handle_ack(node, payload, retain, publish)
    except Exception:
        log.exception("handler failed for %s", topic)


# --- client -----------------------------------------------------------------

class MqttWorker:
    def __init__(self):
        self.connected = False
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="logger-server",
            clean_session=True,
        )
        self.client.username_pw_set(config.LOGGER_USER, config.LOGGER_PASS)
        self.client.reconnect_delay_set(min_delay=1, max_delay=10)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def start(self) -> None:
        log.info("connecting to broker %s:%d as %s", config.BROKER_HOST, config.BROKER_PORT, config.LOGGER_USER)
        self.client.connect_async(config.BROKER_HOST, config.BROKER_PORT, keepalive=30)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.disconnect()
        self.client.loop_stop()

    def publish(self, topic: str, payload: bytes, qos: int, retain: bool) -> None:
        self.client.publish(topic, payload=payload, qos=qos, retain=retain)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            log.error("broker refused connection: %s", reason_code)
            return
        self.connected = True
        client.subscribe([(topic, 1) for topic in SUBSCRIPTIONS])
        log.info("connected to broker; subscribed to %d topics", len(SUBSCRIPTIONS))

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected = False
        log.warning("disconnected from broker (%s); will retry", reason_code)

    def _on_message(self, client, userdata, msg):
        dispatch(msg.topic, msg.payload, msg.retain, self.publish)
