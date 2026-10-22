"""MQTT publisher for the node: Last Will, online, status/alert/heartbeat. Never subscribes."""

import json
import logging
import threading
import time

import paho.mqtt.client as mqtt

from node.payload import heartbeat_payload

log = logging.getLogger("node.mqtt")


def make_client(client_id: str):
    return mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                       client_id=client_id, clean_session=True)


class NodePublisher:
    def __init__(self, settings, client_factory=make_client):
        self.s = settings
        self.node = settings.node_id
        self.connected = False
        self._start = time.monotonic()
        self._stop = threading.Event()
        self._hb_thread = None
        self.client = client_factory(f"node-{self.node}")
        self.client.username_pw_set(settings.node_user, settings.node_pass)
        # Contract rule 1: the Will is set before connecting.
        self.client.will_set(f"icu/{self.node}/online", "offline", qos=1, retain=True)
        self.client.reconnect_delay_set(min_delay=1, max_delay=5)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    # --- connection ----------------------------------------------------------------

    def start(self) -> None:
        self.client.connect_async(self.s.broker_host, self.s.broker_port, keepalive=self.s.keepalive)
        self.client.loop_start()

    def wait_connected(self, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end and not self.connected:
            time.sleep(0.05)
        return self.connected

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if getattr(reason_code, "is_failure", False):
            log.error("MQTT connection refused: %s (check the node user/password in .env)", reason_code)
            return
        self.connected = True
        client.publish(f"icu/{self.node}/online", "online", qos=1, retain=True)
        log.info("MQTT connected to %s:%s as %s", self.s.broker_host, self.s.broker_port, self.s.node_user)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        was = self.connected
        self.connected = False
        if was and not self._stop.is_set():
            log.warning("MQTT disconnected (%s); reconnecting", reason_code)

    # --- publishing ------------------------------------------------------------------

    def _publish(self, topic: str, payload: dict, qos: int, retain: bool):
        try:
            return self.client.publish(topic, json.dumps(payload), qos=qos, retain=retain)
        except Exception as e:  # never crash the window loop on a publish problem
            log.warning("publish to %s failed: %s", topic, e)
            return None

    def publish_status(self, payload: dict):
        return self._publish(f"icu/{self.node}/status/routine", payload, qos=0, retain=False)

    def publish_alert(self, level: str, payload: dict):
        return self._publish(f"icu/{self.node}/status/{level}", payload, qos=1, retain=True)

    def publish_heartbeat(self):
        return self._publish(f"icu/{self.node}/heartbeat",
                             heartbeat_payload(self.node, time.monotonic() - self._start), qos=0, retain=False)

    def start_heartbeat(self) -> None:
        def loop():
            while not self._stop.is_set():
                self.publish_heartbeat()
                self._stop.wait(self.s.heartbeat_s)
        self._hb_thread = threading.Thread(target=loop, name="heartbeat", daemon=True)
        self._hb_thread.start()

    def clean_quit(self) -> None:
        """Publish offline, wait for it, disconnect (contract: clean quit = offline retained)."""
        self._stop.set()
        try:
            info = self.client.publish(f"icu/{self.node}/online", "offline", qos=1, retain=True)
            info.wait_for_publish(timeout=3)
        except Exception as e:
            log.warning("offline message not confirmed: %s", e)
        try:
            self.client.disconnect()
        finally:
            self.client.loop_stop()
