import { useCallback, useEffect, useRef, useState } from "react";
import mqtt from "mqtt";
import { config } from "../config.js";
import { nowLocalIso } from "../lib/time.js";
import { ackTopic } from "../lib/topics.js";

const randomHex8 = () =>
  Array.from(crypto.getRandomValues(new Uint8Array(4)), (b) => b.toString(16).padStart(2, "0")).join("");

/** Live MQTT connection. Dispatches every message as a MESSAGE action. */
export function useMqtt(dispatch) {
  const [status, setStatus] = useState("connecting");
  const clientRef = useRef(null);

  useEffect(() => {
    const client = mqtt.connect(`ws://${config.brokerHost}:${config.brokerWsPort}`, {
      username: config.username,
      password: config.password,
      clientId: "dashboard-" + randomHex8(),
      clean: true,
      reconnectPeriod: 2000,
      connectTimeout: 5000,
    });
    clientRef.current = client;

    client.on("connect", () => {
      setStatus("connected");
      client.subscribe("icu/+/#", { qos: 1 });
    });
    client.on("reconnect", () => setStatus("reconnecting"));
    client.on("close", () => setStatus("offline"));
    client.on("offline", () => setStatus("offline"));
    client.on("error", (err) => console.warn("MQTT error:", err.message));
    client.on("message", (topic, buf, packet) => {
      dispatch({ type: "MESSAGE", topic, payload: buf.toString(), retain: packet.retain, at: Date.now() });
    });

    // StrictMode runs effects twice in development; end the first client fully.
    return () => {
      client.end(true);
      clientRef.current = null;
    };
  }, [dispatch]);

  const publishAck = useCallback(
    (node, alert) => {
      const client = clientRef.current;
      if (!client) return;
      const payload = {
        node,
        level: alert.level,
        alert_ts: alert.ts,
        ack_ts: nowLocalIso(),
        by: "dashboard",
      };
      client.publish(ackTopic(node), JSON.stringify(payload), { qos: 1, retain: false });
      dispatch({ type: "ACK_SENT", node, at: Date.now() });
    },
    [dispatch],
  );

  return { status, publishAck };
}
