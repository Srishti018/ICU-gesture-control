#!/usr/bin/env python3
"""End-to-end contract check of the node against a real broker (C1-C10, Role A plan §10.10).

Usage: .venv/bin/python node/tests/verify_node_contract.py [--fusion rule|model]
Subscriber login: CHECK_USER / CHECK_PASS environment variables, else LOGGER_USER / LOGGER_PASS from .env.
Nothing else may run as bed1 while this runs (same client ID).
"""

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time

from dotenv import dotenv_values
import paho.mqtt.client as mqtt

REPO_ROOT = Path(__file__).resolve().parents[2]
VENV_PY = str(REPO_ROOT / ".venv" / "bin" / "python")
NODE = "bed1"
TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

env = dotenv_values(REPO_ROOT / ".env")
HOST = env.get("BROKER_HOST") or "localhost"
PORT = int(env.get("BROKER_PORT") or 1883)
CHECK_USER = os.environ.get("CHECK_USER") or env.get("LOGGER_USER") or "logger"
CHECK_PASS = os.environ.get("CHECK_PASS") or env.get("LOGGER_PASS") or ""

results = []


def record(cid, ok, detail):
    results.append((cid, "PASS" if ok else "FAIL", detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {cid}: {detail}", flush=True)


def client(name):
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"test-{name}-{secrets.token_hex(4)}",
                    clean_session=True)
    c.username_pw_set(CHECK_USER, CHECK_PASS)
    return c


class Recorder:
    def __init__(self):
        self.msgs = []
        self.lock = threading.Lock()
        self.c = client("node-contract")
        self.c.on_message = self._on
        ready = threading.Event()
        self.c.on_connect = lambda c, u, f, rc, p: (c.subscribe(f"icu/{NODE}/#", qos=1), ready.set())
        self.c.connect(HOST, PORT, keepalive=10)
        self.c.loop_start()
        if not ready.wait(5):
            raise SystemExit(f"cannot connect to the broker at {HOST}:{PORT} as {CHECK_USER}")
        time.sleep(0.5)

    def _on(self, c, u, m):
        with self.lock:
            self.msgs.append({"topic": m.topic, "payload": m.payload.decode(errors="replace"), "qos": m.qos,
                              "retain": bool(m.retain), "t": time.time()})

    def get(self, suffix=None, since=0.0, pred=None):
        with self.lock:
            out = [m for m in self.msgs if m["t"] >= since]
        if suffix:
            out = [m for m in out if m["topic"] == f"icu/{NODE}/{suffix}"]
        return [m for m in out if pred(m)] if pred else out

    def wait(self, suffix, timeout, since=0.0, pred=None):
        end = time.time() + timeout
        while time.time() < end:
            found = self.get(suffix, since, pred)
            if found:
                return found[0]
            time.sleep(0.05)
        return None

    def stop(self):
        self.c.loop_stop()
        self.c.disconnect()


def retained(suffix, timeout=2.0):
    """What a NEW subscriber receives on icu/bed1/<suffix> (None if nothing retained)."""
    got = []
    c = client("retained")
    c.on_message = lambda cl, u, m: got.append((m.payload.decode(errors="replace"), bool(m.retain)))
    c.on_connect = lambda cl, u, f, rc, p: cl.subscribe(f"icu/{NODE}/{suffix}", qos=1)
    c.connect(HOST, PORT, keepalive=10)
    c.loop_start()
    end = time.time() + timeout
    while time.time() < end and not got:
        time.sleep(0.05)
    c.loop_stop()
    c.disconnect()
    return got[0] if got else None


def clear_retained():
    c = client("cleaner")
    c.connect(HOST, PORT, keepalive=10)
    c.loop_start()
    for suffix in ("status/urgent", "status/critical", "online"):
        c.publish(f"icu/{NODE}/{suffix}", b"", qos=1, retain=True).wait_for_publish(timeout=3)
    c.loop_stop()
    c.disconnect()


def status_ok(payload: str) -> str | None:
    try:
        d = json.loads(payload)
    except json.JSONDecodeError:
        return "not JSON"
    if list(d) != ["node", "ts", "level", "p", "features", "hr", "bio_source"]:
        return f"keys {list(d)}"
    f, p = d["features"], d["p"]
    checks = [d["node"] == NODE, bool(TS.match(d["ts"])), d["level"] in ("routine", "urgent", "critical"),
              list(p) == ["routine", "urgent", "critical"], list(f) == ["gesture_conf", "tremor", "hr_delta", "spo2"],
              isinstance(f["gesture_conf"], float), isinstance(f["tremor"], float), type(f["hr_delta"]) is int,
              type(f["spo2"]) is int, type(d["hr"]) is int, d["bio_source"] in ("live", "replay")]
    return None if all(checks) else f"bad field types/values: {d}"


def start_node(fusion, log_dir):
    cmd = [VENV_PY, "-u", "-m", "node.main", "--node", NODE, "--vision", "synthetic", "--bio", "replay:rest",
           "--fusion", fusion, "--no-oled", "--no-buzzer", "--log-dir", log_dir]
    return subprocess.Popen(cmd, cwd=REPO_ROOT, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, text=True)


def send(proc, key):
    proc.stdin.write(key + "\n")
    proc.stdin.flush()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fusion", choices=["rule", "model"], default="rule")
    args = ap.parse_args()

    if retained("online") == ("online", True):
        print("Something is already online as bed1 (Pi node, fake node or another test). Stop it first.",
              file=sys.stderr)
        return 2
    clear_retained()
    rec = Recorder()
    log_dir = tempfile.mkdtemp(prefix="icu-contract-")
    proc = None
    try:
        t0 = time.time()
        proc = start_node(args.fusion, log_dir)
        # C1
        m = rec.wait("online", 10, t0, lambda m: m["payload"] == "online")
        r = retained("online")
        record("C1", bool(m) and r == ("online", True), "online published and retained" if m and r == ("online", True)
               else f"online={bool(m)}, retained={r}")
        # C2
        t = time.time()
        time.sleep(10)
        routine = rec.get("status/routine", t)
        bad = [e for e in (status_ok(x["payload"]) for x in routine) if e]
        ok = len(routine) in (3, 4) and all(x["qos"] == 0 and not x["retain"] for x in routine) and not bad
        record("C2", ok, f"{len(routine)} routine msgs in 10 s, QoS 0, not retained" + (f"; {bad[0]}" if bad else ""))
        # C3
        hb = rec.wait("heartbeat", 12, t0)
        hbd = json.loads(hb["payload"]) if hb else {}
        record("C3", bool(hb) and set(hbd) == {"node", "ts", "uptime_s"} and isinstance(hbd.get("uptime_s"), int),
               f"heartbeat {hbd}" if hb else "no heartbeat within 12 s")
        # C4
        t = time.time()
        send(proc, "g")
        first = rec.wait("status/urgent", 6, t)
        time.sleep(7)
        urgent = rec.get("status/urgent", t)
        r = retained("status/urgent")
        ok = bool(first) and len(urgent) == 1 and first["qos"] == 1 and r is not None and r[1]
        record("C4", ok, f"{len(urgent)} urgent alert(s), QoS {first['qos'] if first else '-'}, retained={bool(r and r[1])}")
        # C5
        t = time.time()
        send(proc, "x")
        crit = rec.wait("status/critical", 9, t)
        time.sleep(4)
        crits = rec.get("status/critical", t)
        delta = json.loads(crit["payload"])["features"]["hr_delta"] if crit else None
        record("C5", bool(crit) and len(crits) == 1 and delta is not None and delta >= 15 and crit["qos"] == 1,
               f"{len(crits)} critical alert(s), hr_delta={delta}")
        # C6
        r = retained("status/critical")
        record("C6", r is not None and r[1] and json.loads(r[0])["level"] == "critical",
               "new subscriber gets the critical alert with retain=True" if r else "no retained critical alert")
        # C7
        send(proc, "g")
        time.sleep(4)
        send(proc, "r")
        time.sleep(3.5)
        t = time.time()
        send(proc, "g")
        send(proc, "x")
        again = rec.wait("status/critical", 10, t)
        record("C7", bool(again), "new critical alert after falling and rising again" if again
               else "no new critical alert after the second rise")
        # C8
        sums = [sum(json.loads(x["payload"])["p"].values()) for x in rec.get("status/routine", t0)]
        record("C8", bool(sums) and all(abs(s - 1.0) <= 0.01 for s in sums),
               f"{len(sums)} status messages, p sums {min(sums):.2f}..{max(sums):.2f}" if sums else "no status")
        # C9
        t = time.time()
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=5)
        off = rec.wait("online", 10, t, lambda m: m["payload"] == "offline")
        record("C9", bool(off), f"offline (Last Will) after {off['t'] - t:.1f} s" if off else "no offline within 10 s")
        # C10
        t = time.time()
        proc = start_node(args.fusion, log_dir)
        on = rec.wait("online", 10, t, lambda m: m["payload"] == "online")
        time.sleep(1)
        t = time.time()
        send(proc, "q")
        off = rec.wait("online", 8, t, lambda m: m["payload"] == "offline")
        try:
            code = proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            code = None
        record("C10", bool(on) and bool(off) and code == 0, f"online={bool(on)}, offline on q={bool(off)}, exit={code}")
    except Exception as e:
        record("ERROR", False, f"{type(e).__name__}: {e}")
    finally:
        if proc and proc.poll() is None:
            proc.kill()
            proc.wait()
        rec.stop()
        clear_retained()

    print()
    for cid, status, detail in results:
        print(f"{cid:<6} {status:<5} {detail}")
    failed = [r for r in results if r[1] != "PASS"]
    print("\nALL CONTRACT CHECKS PASSED." if not failed else f"\n{len(failed)} CHECK(S) FAILED.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
