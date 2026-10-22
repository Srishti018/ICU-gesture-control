import { AlertOctagon, AlertTriangle, CheckCircle2, HeartPulse, Wifi, WifiOff } from "lucide-react";
import { bedName, formatSeconds, formatWhen } from "../lib/format.js";
import { levelMeta } from "../lib/levels.js";

function describe(e, alerts) {
  const bed = bedName(e.node);
  switch (e.kind) {
    case "alert":
      return { Icon: e.level === "critical" ? AlertOctagon : AlertTriangle, tone: e.level, text: `${bed} · ${levelMeta(e.level).label} alert raised` };
    case "ack": {
      const row = alerts?.find((a) => a.node === e.node && a.alert_ts === e.alertTs && typeof a.response_s === "number");
      const response = row ? ` · response ${formatSeconds(row.response_s)}` : "";
      return { Icon: CheckCircle2, tone: "ok", text: `${bed} · ${levelMeta(e.level).label} alert acknowledged${response}` };
    }
    case "online":
      return { Icon: Wifi, tone: "ok", text: `${bed} · came online` };
    case "offline":
      return { Icon: WifiOff, tone: "offline", text: `${bed} · went offline` };
    case "heartbeat-lost":
      return { Icon: HeartPulse, tone: "warn", text: `${bed} · heartbeat lost` };
    case "heartbeat-back":
      return { Icon: HeartPulse, tone: "ok", text: `${bed} · heartbeat back` };
    default:
      return { Icon: CheckCircle2, tone: "ok", text: bed };
  }
}

export default function ActivityFeed({ events, alerts, now }) {
  if (events.length === 0) {
    return <p className="panel-empty">No events yet. Alerts, acknowledgements and devices going online or offline appear here.</p>;
  }
  return (
    <ol className="feed" data-testid="activity-feed">
      {events.map((e) => {
        const { Icon, tone, text } = describe(e, alerts);
        return (
          <li key={e.id} className={`feed-item tone-${tone}`}>
            <Icon className="feed-icon" size={16} aria-hidden="true" />
            <span className="feed-text">{text}</span>
            <time className="feed-time num">{formatWhen(e.at, now)}</time>
          </li>
        );
      })}
    </ol>
  );
}
