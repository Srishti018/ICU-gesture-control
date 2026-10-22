#!/usr/bin/env python3
"""
sim/fake_node.py - Simulated ICU bed node for ICU Fusion.

Publishes exactly what the Raspberry Pi publishes (docs/contracts.md):
routine status every 3 s, urgent/critical on level rise, heartbeat every 10 s,
and online/offline with a Last Will. Controlled one line at a time from stdin.
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


REPO_ROOT = Path(__file__).resolve().parent.parent

LEVEL_RANK = {"routine": 0, "urgent": 1, "critical": 2}
LEVELS = list(LEVEL_RANK)

STATUS_INTERVAL_S = 3.0
HEARTBEAT_INTERVAL_S = 10.0
KEEPALIVE_S = 5

# level: (gesture_conf range, tremor range, hr_delta range)
VALUE_RANGES = {
    "routine": ((0.00, 0.20), (0.002, 0.008), (-3, 5)),
    "urgent": ((0.80, 0.95), (0.004, 0.012), (-3, 5)),
    "critical": ((0.80, 0.95), (0.008, 0.020), (18, 30)),
}

HELP = "Commands: 1=routine 2=urgent 3=critical r=toggle bio_source q=quit k=hard kill"


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def log(msg: str) -> None:
    print(f"{datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


def make_probabilities(level: str) -> dict:
    """Current level gets 0.70-0.90; the rest is split randomly. Sums to exactly 1.00."""
    top = round(random.uniform(0.70, 0.90), 2)
    others = [lv for lv in LEVELS if lv != level]
    remainder_cents = 100 - round(top * 100)
    first_cents = random.randint(0, remainder_cents)
    p = {
        level: top,
        others[0]: first_cents / 100,
        others[1]: (remainder_cents - first_cents) / 100,
    }
    return {lv: p[lv] for lv in LEVELS}


def make_status(node: str, level: str, bio_source: str) -> dict:
    (g_lo, g_hi), (t_lo, t_hi), (d_lo, d_hi) = VALUE_RANGES[level]
    hr_delta = random.randint(d_lo, d_hi)
    return {
        "node": node,
        "ts": now_iso(),
        "level": level,
        "p": make_probabilities(level),
        "features": {
            "gesture_conf": round(random.uniform(g_lo, g_hi), 3),
            "tremor": round(random.uniform(t_lo, t_hi), 3),
            "hr_delta": hr_delta,
            "spo2": random.randint(96, 99),
        },
        "hr": 75 + hr_delta,
        "bio_source": bio_source,
    }


class FakeNode:
    def __init__(self, node: str, host: str, port: int, user: str, password: str):
        self.node = node
        self.host = host
        self.port = port
        self._lock = threading.Lock()
        self._level = "routine"
        self._bio_source = "live"
        self._stop = threading.Event()
        self.start_time = time.monotonic()

        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"node-{node}",
            clean_session=True,
        )
        self.client.username_pw_set(user, password)
        self.client.will_set(f"icu/{node}/online", payload="offline", qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    # --- MQTT callbacks -----------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            log(f"connect failed: {reason_code}")
            return
        log(f"connected to {self.host}:{self.port} as node-{self.node}")
        self.publish(f"icu/{self.node}/online", "online", qos=1, retain=True, level="-")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        if not self._stop.is_set():
            log(f"disconnected: {reason_code}")

    # --- publishing ---------------------------------------------------------

    def publish(self, topic: str, payload: str, qos: int, retain: bool, level: str):
        info = self.client.publish(topic, payload=payload, qos=qos, retain=retain)
        log(f"PUB {topic} level={level} qos={qos} retain={retain}")
        return info

    def _timer_loop(self):
        prev_rank = LEVEL_RANK["routine"]
        next_status = time.monotonic()
        next_heartbeat = time.monotonic()
        while not self._stop.is_set():
            now = time.monotonic()
            if now >= next_status:
                with self._lock:
                    level, bio_source = self._level, self._bio_source
                payload = json.dumps(make_status(self.node, level, bio_source))
                self.publish(f"icu/{self.node}/status/routine", payload, qos=0, retain=False, level=level)
                rank = LEVEL_RANK[level]
                if rank > prev_rank:
                    self.publish(f"icu/{self.node}/status/{level}", payload, qos=1, retain=True, level=level)
                prev_rank = rank
                next_status += STATUS_INTERVAL_S
            if now >= next_heartbeat:
                hb = {"node": self.node, "ts": now_iso(), "uptime_s": int(now - self.start_time)}
                self.publish(f"icu/{self.node}/heartbeat", json.dumps(hb), qos=0, retain=False, level="-")
                next_heartbeat += HEARTBEAT_INTERVAL_S
            self._stop.wait(0.05)

    # --- control ------------------------------------------------------------

    def handle_command(self, cmd: str) -> None:
        if cmd in ("1", "2", "3"):
            level = LEVELS[int(cmd) - 1]
            with self._lock:
                self._level = level
            log(f"level -> {level}")
        elif cmd == "r":
            with self._lock:
                self._bio_source = "replay" if self._bio_source == "live" else "live"
                src = self._bio_source
            log(f"bio_source -> {src}")
        elif cmd == "q":
            self.quit()
        elif cmd == "k":
            log("hard kill (no disconnect; broker will send Last Will)")
            os._exit(1)
        else:
            log(HELP)

    def quit(self) -> None:
        log("clean quit")
        self._stop.set()
        info = self.publish(f"icu/{self.node}/online", "offline", qos=1, retain=True, level="-")
        try:
            info.wait_for_publish(timeout=3.0)
        except Exception as e:
            log(f"offline publish not confirmed: {e}")
        self.client.disconnect()
        self.client.loop_stop()
        sys.exit(0)

    def run(self) -> None:
        log(f"connecting node-{self.node} to {self.host}:{self.port}")
        try:
            self.client.connect(self.host, self.port, keepalive=KEEPALIVE_S)
        except OSError as e:
            log(f"cannot reach broker: {e}")
            sys.exit(1)
        self.client.loop_start()
        threading.Thread(target=self._timer_loop, daemon=True).start()
        log(HELP)

        for line in sys.stdin:
            cmd = line.strip().lower()
            if cmd:
                self.handle_command(cmd)
        # EOF on stdin: keep running (e.g. started in the background)
        while True:
            time.sleep(3600)


def main() -> None:
    load_dotenv(REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(description="Simulated ICU bed node")
    parser.add_argument("--node", default="bed1", help="node id (default: bed1)")
    parser.add_argument("--host", default=os.getenv("BROKER_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("BROKER_PORT", "1883")))
    parser.add_argument("--user", default=None, help="MQTT username (default: node id)")
    parser.add_argument("--password", default=None, help="MQTT password (default from .env)")
    args = parser.parse_args()

    user = args.user or args.node
    if args.password is not None:
        password = args.password
    elif args.node == "bed2":
        password = os.getenv("BED2_PASS", "")
    else:
        password = os.getenv("NODE_PASS", "")

    node = FakeNode(args.node, args.host, args.port, user, password)
    signal.signal(signal.SIGTERM, lambda *_: node.quit())
    try:
        node.run()
    except KeyboardInterrupt:
        node.quit()


if __name__ == "__main__":
    main()
