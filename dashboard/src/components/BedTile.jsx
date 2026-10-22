import { Clock, Cpu, Repeat, WifiOff } from "lucide-react";
import { bedName, formatAgo, formatDuration, formatNumber, formatSeconds, formatSigned, formatSpan, formatWhen } from "../lib/format.js";
import { levelMeta } from "../lib/levels.js";
import { severityOf } from "../lib/severity.js";
import {
  ackResponse,
  activeAlert,
  alertSince,
  heartbeatStale,
  isPulsing,
  ruleFallback,
} from "../state/nodesReducer.js";
import AckControl from "./AckControl.jsx";
import GestureMeter from "./GestureMeter.jsx";
import ModelBar from "./ModelBar.jsx";
import Sparkline from "./Sparkline.jsx";

// How long "Acknowledged · response 8.2 s" stays on the tile after the alert clears.
const ACK_NOTE_MS = 60_000;

function connection(node, now) {
  if (node.online === false) return { cls: "conn-off", word: "Offline" };
  if (heartbeatStale(node, now)) return { cls: "conn-warn", word: "No heartbeat" };
  if (node.online === true) return { cls: "conn-on", word: "Online" };
  return { cls: "conn-unknown", word: "Connecting" };
}

export default function BedTile({ node, now, alerts, paused, onAck }) {
  const alert = activeAlert(node);
  const severity = severityOf(node);
  const offline = node.online === false;
  const shown = node.status ?? alert;
  const f = shown?.features ?? {};
  const name = bedName(node.id);
  const conn = connection(node, now);
  const { word, Icon } = levelMeta(severity);
  const since = alertSince(node, now);
  const replay = shown?.bio_source === "replay";
  const showAck = !alert && node.lastAck && now - node.lastAck.at < ACK_NOTE_MS;
  const response = showAck ? ackResponse(node, alerts) : null;
  const updatedAt = node.statusAt ?? node.lastHeartbeatAt;
  const updatedAge = updatedAt ? (now - updatedAt) / 1000 : null;

  const classes = ["tile", `sev-${severity}`];
  if (alert) classes.push("has-alert");
  if (alert && isPulsing(node, now)) classes.push("pulse");
  if (offline) classes.push("is-offline");

  const accessibleName = [
    name,
    severity === "offline" ? "offline" : `${severity}${alert ? " alert" : ""}`,
    typeof shown?.hr === "number" ? `heart rate ${shown.hr}` : null,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <article className={classes.join(" ")} aria-label={accessibleName} data-testid={`bed-tile-${node.id}`}>
      <header className="tile-head">
        <h2 className="tile-name">{name}</h2>
        <span className={`conn ${conn.cls}`} data-testid="connection-state">
          <span className="conn-dot" aria-hidden="true" />
          {conn.word}
        </span>
        <span className={`tile-updated ${paused || (updatedAge ?? 0) > 10 ? "is-stale" : ""}`}>
          {updatedAge === null ? "no data yet" : `updated ${formatAgo(updatedAge)}`}
          {paused && updatedAge !== null ? " · paused" : ""}
        </span>
      </header>

      <div className="sev-block">
        <Icon className="sev-icon" size={30} aria-hidden="true" />
        <span className="sev-word" data-testid="tile-level">
          {word}
        </span>
        <span className="sev-detail" data-testid="tile-alert-age">
          {alert ? (
            <>
              <Clock size={16} aria-hidden="true" />
              {levelMeta(alert.level).label} for <span className="num">{formatDuration((now - since) / 1000)}</span>
            </>
          ) : showAck ? (
            <span className="ack-done" data-testid="ack-done">
              Acknowledged · response{" "}
              <span className="num">{response === null ? "…" : formatSeconds(response)}</span>
            </span>
          ) : offline ? null : (
            "No active alert"
          )}
        </span>
      </div>

      {offline && (
        <div className="tile-notice notice-off" data-testid="offline-notice">
          <WifiOff size={16} aria-hidden="true" />
          {node.offlineAt ? `No signal since ${formatWhen(node.offlineAt, now)}` : "No signal"} · device disconnected
        </div>
      )}
      {!offline && heartbeatStale(node, now) && (
        <div className="tile-notice notice-warn">
          No heartbeat for {formatSpan((now - (node.lastHeartbeatAt ?? node.firstSeenAt)) / 1000)} — check the device
        </div>
      )}

      {!shown ? (
        <div className="tile-skeleton" aria-label="Waiting for the first reading">
          <div className="skel skel-lg" />
          <div className="skel" />
          <div className="skel" />
          <span className="skel-text">Waiting for the first reading…</span>
        </div>
      ) : (
        <div className="tile-body">
          <div className="vitals">
            <div className="vital vital-hr">
              <span className="label">Heart rate</span>
              <span className="vital-value num">
                {formatNumber(shown.hr)}
                <span className="unit">bpm</span>
              </span>
              <Sparkline samples={node.hrHistory} now={now} />
            </div>
            <div className="vital">
              <span className="label">SpO₂</span>
              <span className="vital-value vital-sm num">
                {formatNumber(f.spo2)}
                <span className="unit">%</span>
              </span>
            </div>
            <div className="vital">
              <span className="label" title="Heart rate change from the patient's resting baseline">
                ΔHR<span className="label-long"> vs baseline</span>
              </span>
              <span className="vital-value vital-sm num">
                {formatSigned(f.hr_delta)}
                <span className="unit">bpm</span>
              </span>
            </div>
          </div>

          <div className="signals">
            <GestureMeter value={f.gesture_conf} />
            <div className="tremor">
              <span className="label">Tremor</span>
              <span className="num">{formatNumber(f.tremor, 3)}</span>
            </div>
          </div>

          <ModelBar p={shown.p} />

          {(replay || ruleFallback(node)) && (
            <div className="badges">
              {replay && (
                <span className="badge" data-testid="replay-badge">
                  <Repeat size={14} aria-hidden="true" />
                  Biosignals: replay
                </span>
              )}
              {ruleFallback(node) && (
                <span className="badge" data-testid="rule-badge">
                  <Cpu size={14} aria-hidden="true" />
                  Rule fallback
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {alert && <AckControl node={node} alert={alert} now={now} onAck={onAck} />}
    </article>
  );
}
