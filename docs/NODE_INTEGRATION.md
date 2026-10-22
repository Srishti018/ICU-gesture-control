# Node integration guide (for Role A — Raspberry Pi `bed1`)

This is everything the Pi needs to talk to the laptop's broker. The full contract is in [contracts.md](contracts.md); it is fixed, so please follow it exactly.

## Broker connection

| Setting | Value |
| --- | --- |
| Host | the laptop's IP on the phone hotspot (Role C tells you on the day; `start_all.sh` prints it) |
| Port | `1883` (plain MQTT) |
| Username | `bed1` |
| Password | from the team (it is not written in any file in this repo) |
| Client ID | `node-bed1` (must be unique — don't run the fake node as `bed1` at the same time) |
| Keepalive | 5 s |
| Clean session | true |

Keep the password out of your code: read it from an environment variable or a git-ignored file.

## What the Pi must do

1. **Connect with keepalive 5 s and a Last Will**: topic `icu/bed1/online`, payload `offline`, QoS 1, retain true. Set the Will *before* connecting.
2. **On every successful connect**, publish `online` (plain text, not JSON) to `icu/bed1/online`, QoS 1, retain true.
3. **Every 3 s window**, publish the status payload to `icu/bed1/status/routine`, QoS 0, retain false — whatever the level is. This carries the live vitals the dashboard shows.
4. **Only when the level rises** compared with the previous window (routine → urgent, routine → critical, urgent → critical), *also* publish the same payload to `icu/bed1/status/urgent` or `icu/bed1/status/critical`, QoS 1, retain true. Staying critical does not republish. Treat the first window's previous level as routine.
5. **Every 10 s**, publish a heartbeat to `icu/bed1/heartbeat`, QoS 0, retain false: `{"node": "bed1", "ts": "2026-10-25T10:02:11", "uptime_s": 312}`.
6. **`bio_source`** is `"live"` for real sensor data and `"replay"` for recorded data. On demo day the biosignals are replayed, so send `"replay"`; the dashboard shows a REPLAY badge.

The Pi does **not** handle acknowledgements. The laptop clears retained alerts after a nurse acknowledges.

Status payload (same shape on routine, urgent and critical):

```json
{"node": "bed1", "ts": "2026-10-25T10:02:11", "level": "critical",
 "p": {"routine": 0.04, "urgent": 0.11, "critical": 0.85},
 "features": {"gesture_conf": 0.91, "tremor": 0.010, "hr_delta": 24, "spo2": 98},
 "hr": 99, "bio_source": "replay"}
```

- `ts`: local time, `YYYY-MM-DDTHH:MM:SS`, no timezone.
- `p`: the model's three class probabilities, summing to 1.
- `hr`, `hr_delta`, `spo2`: integers. `gesture_conf`, `tremor`: floats.

## Minimal Python example (paho-mqtt 2.x)

`pip install "paho-mqtt>=2.0"`. Replace `classify_window()` with your camera + model code.

```python
import json
import os
import threading
import time
from datetime import datetime

import paho.mqtt.client as mqtt

BROKER = os.environ.get("BROKER_HOST", "192.168.0.100")  # laptop IP on the hotspot
NODE = "bed1"
PASSWORD = os.environ["NODE_PASS"]                       # never hard-code it
RANK = {"routine": 0, "urgent": 1, "critical": 2}


def now():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"node-{NODE}", clean_session=True)
client.username_pw_set(NODE, PASSWORD)
client.will_set(f"icu/{NODE}/online", "offline", qos=1, retain=True)   # rule 1: Will before connect


def on_connect(c, userdata, flags, reason_code, properties):
    if not reason_code.is_failure:
        c.publish(f"icu/{NODE}/online", "online", qos=1, retain=True)  # rule 2


client.on_connect = on_connect
client.connect(BROKER, 1883, keepalive=5)
client.loop_start()   # network thread: keeps the 5 s keepalive going and reconnects

start = time.monotonic()


def heartbeat_loop():
    while True:
        hb = {"node": NODE, "ts": now(), "uptime_s": int(time.monotonic() - start)}
        client.publish(f"icu/{NODE}/heartbeat", json.dumps(hb), qos=0, retain=False)
        time.sleep(10)


threading.Thread(target=heartbeat_loop, daemon=True).start()


def classify_window():
    """Replace with your model. Returns (level, p, features, hr)."""
    return ("routine",
            {"routine": 0.85, "urgent": 0.10, "critical": 0.05},
            {"gesture_conf": 0.05, "tremor": 0.004, "hr_delta": 1, "spo2": 98},
            76)


prev_level = "routine"
while True:
    level, p, features, hr = classify_window()
    payload = json.dumps({"node": NODE, "ts": now(), "level": level, "p": p,
                          "features": features, "hr": hr, "bio_source": "replay"})
    client.publish(f"icu/{NODE}/status/routine", payload, qos=0, retain=False)      # every window
    if RANK[level] > RANK[prev_level]:                                              # rule 3: only on rise
        client.publish(f"icu/{NODE}/status/{level}", payload, qos=1, retain=True)
    prev_level = level
    time.sleep(3)
```

## Test the connection from the Pi first

Before running project code, check the Pi can reach the broker:

```bash
sudo apt install mosquitto-clients
mosquitto_pub -h <laptop IP> -p 1883 -u bed1 -P '<bed1 password>' -t icu/bed1/heartbeat -m test
```

No output means it worked. "Connection refused" means the wrong IP, the broker isn't running, or the laptop firewall is blocking port 1883. "Not authorized" means the wrong password.

## How you know it works

- A **bed1** card appears on the dashboard (http://&lt;laptop IP&gt;:5173), shows "Online", and its heartbeat age stays under 10 s.
- The vitals update every 3 s. A rise to urgent/critical shows the coloured card, a banner, and an Acknowledge button.
- Unplugging the Pi or killing your program turns the card grey ("OFFLINE") within about 10 s. That is the Last Will working.
- Role C can confirm the same behaviour with the checks in `tests/verify_steps_1_2.py` (N1–N12), which test the fake node against the same rules.
