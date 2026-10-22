import { formatClock } from "../lib/time.js";

const BROKER_PILL = {
  connected: { cls: "ok", text: "Broker: Connected" },
  connecting: { cls: "warn", text: "Broker: Connecting…" },
  reconnecting: { cls: "warn", text: "Broker: Reconnecting" },
  offline: { cls: "bad", text: "Broker: Offline" },
};

export default function TopBar({ brokerStatus, historyOk, now }) {
  const broker = BROKER_PILL[brokerStatus] ?? BROKER_PILL.offline;
  return (
    <header className="topbar">
      <h1>ICU Gesture + Biosignal Fusion — Nurse Station</h1>
      <div className="topbar-right">
        <span className={`pill ${broker.cls}`} data-testid="broker-pill">{broker.text}</span>
        <span className={`pill ${historyOk ? "ok" : "muted"}`}>
          {historyOk ? "History: OK" : "History unavailable"}
        </span>
        <span className="clock">{formatClock(now)}</span>
      </div>
    </header>
  );
}
