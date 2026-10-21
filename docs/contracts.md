# ICU Fusion — MQTT contract v1 (21 Oct 2026)

## Broker
- Mosquitto 2.x on the laptop. Anonymous access disabled.
- Port 1883: MQTT (Pi nodes, fake node, Flask logger).
- Port 9001: MQTT over WebSockets (browser dashboard).
- Users: bed1, bed2 (nodes), logger (Flask), dashboard (browser).
- Node ids: bed1, bed2. Timestamps: ISO 8601 local time, e.g. 2026-10-25T10:02:11.

## Topics
| Topic | Publisher | QoS | Retain | When |
| icu/{node}/status/routine  | node      | 0 | no  | every 3 s window |
| icu/{node}/status/urgent   | node      | 1 | yes | when level rises to urgent |
| icu/{node}/status/critical | node      | 1 | yes | when level rises to critical |
| icu/{node}/heartbeat       | node      | 0 | no  | every 10 s |
| icu/{node}/online          | node/LWT  | 1 | yes | "online" on connect; broker sends "offline" via LWT |
| icu/{node}/ack             | dashboard | 1 | no  | nurse presses Acknowledge |

## Payloads (JSON)
Status (same shape on routine, urgent, critical):
{"node":"bed1","ts":"2026-10-25T10:02:11","level":"critical",
 "p":{"routine":0.04,"urgent":0.11,"critical":0.85},
 "features":{"gesture_conf":0.91,"tremor":0.010,"hr_delta":24,"spo2":98},
 "hr":99,"bio_source":"replay"}

Heartbeat: {"node":"bed1","ts":"...","uptime_s":312}

Online: plain text "online" or "offline" (not JSON).

Ack: {"node":"bed1","level":"critical","alert_ts":"...","ack_ts":"...","by":"dashboard"}

## Rules
1. Nodes connect with keepalive 5 s and a Last Will: topic icu/{node}/online, payload "offline", QoS 1, retain.
2. On connect, a node publishes "online" (QoS 1, retain) to icu/{node}/online.
3. Urgent/critical are published only when the level rises compared with the previous window. Staying critical does not republish.
4. Routine messages carry the live vitals; the dashboard uses them for the live view.
5. An alert stays until acknowledged. On ack, the logger stores it and publishes an EMPTY retained message to icu/{node}/status/urgent and /critical to clear them.
6. Every subscriber ignores empty payloads (they are clears, not data).
7. bio_source is "live" or "replay"; the dashboard shows a REPLAY badge when it is "replay".