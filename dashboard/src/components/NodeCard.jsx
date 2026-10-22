import { secondsSince } from "../lib/time.js";
import { activeAlert, ackUnconfirmed, displayLevel, heartbeatStale } from "../state/nodesReducer.js";
import ProbabilityBars from "./ProbabilityBars.jsx";

const PULSE_MS = 10000;

const fmt = (v, digits = 0) => (typeof v === "number" ? v.toFixed(digits) : "—");
const signed = (v) => (typeof v === "number" ? (v > 0 ? `+${v}` : `${v}`) : "—");

export default function NodeCard({ node, now, lastAlertEvent, onAck }) {
  const alert = activeAlert(node);
  const level = displayLevel(node);
  const shown = node.status ?? alert;
  const features = shown?.features ?? {};
  const offline = node.online === false;
  const replay = node.status?.bio_source === "replay" || alert?.bio_source === "replay";
  const pulsing =
    alert && lastAlertEvent?.node === node.id && lastAlertEvent.level === alert.level && now - lastAlertEvent.at < PULSE_MS;
  const unconfirmed = ackUnconfirmed(node, now);
  const ackDisabled = node.ackPendingSince !== null && !unconfirmed;

  const classes = ["card"];
  if (alert) classes.push(`alert-border-${alert.level}`);
  if (pulsing) classes.push("pulse");
  if (offline) classes.push("offline");

  return (
    <article className={classes.join(" ")} data-testid={`card-${node.id}`}>
      <header className="card-head">
        <h2>{node.id}</h2>
        <span className={`dot ${offline ? "dot-off" : node.online ? "dot-on" : "dot-unknown"}`} />
        <span className="online-text">{offline ? "OFFLINE" : node.online ? "Online" : "Unknown"}</span>
        <span className="hb">
          {node.lastHeartbeatAt ? `heartbeat ${secondsSince(node.lastHeartbeatAt, now)}s ago` : "no heartbeat yet"}
        </span>
      </header>

      <div className="card-body">
        <div className={`level-label level-${level}`}>{offline ? "OFFLINE" : level.toUpperCase()}</div>
        {replay && <div className="replay-badge">BIOSIGNAL: REPLAY</div>}

        <div className="vitals">
          <div><span className="v">{fmt(shown?.hr)}</span><span className="u">HR bpm</span></div>
          <div><span className="v">{fmt(features.spo2)}</span><span className="u">SpO₂ %</span></div>
          <div><span className="v">{signed(features.hr_delta)}</span><span className="u">ΔHR bpm</span></div>
        </div>

        <div className="features">
          <span>Gesture {typeof features.gesture_conf === "number" ? `${Math.round(features.gesture_conf * 100)}%` : "—"}</span>
          <span>Tremor {fmt(features.tremor, 3)}</span>
        </div>

        <ProbabilityBars p={shown?.p} />

        {heartbeatStale(node, now) && <div className="warning">No heartbeat for 25 s</div>}
      </div>

      {alert && (
        <div className="card-actions">
          <button className={`ack-btn level-bg-${alert.level}`} disabled={ackDisabled} onClick={() => onAck(node.id, alert)}>
            {ackDisabled ? "Acknowledging…" : unconfirmed ? "Retry Acknowledge" : "Acknowledge"}
          </button>
          {unconfirmed && <div className="warning">Not confirmed — is the server running?</div>}
        </div>
      )}
    </article>
  );
}
