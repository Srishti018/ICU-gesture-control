import { bedName, formatDuration } from "../lib/format.js";
import { levelMeta } from "../lib/levels.js";
import AckControl from "./AckControl.jsx";

export default function AlertStrip({ rows, now, onAck }) {
  if (rows.length === 0) return null;
  return (
    <section className="alert-strip" aria-label="Active alerts" data-testid="alert-strip">
      {rows.map(({ node, alert, since }) => {
        const { word, Icon } = levelMeta(alert.level);
        return (
          <div key={node.id} className={`alert-row sev-${alert.level}`} data-testid={`alert-row-${node.id}`}>
            <Icon className="alert-row-icon" size={22} aria-hidden="true" />
            <span className="alert-row-bed">{bedName(node.id)}</span>
            <span className="alert-row-level">{word}</span>
            <span className="alert-row-age">
              for <span className="num">{formatDuration((now - since) / 1000)}</span>
            </span>
            <AckControl node={node} alert={alert} now={now} onAck={onAck} compact />
          </div>
        );
      })}
    </section>
  );
}
