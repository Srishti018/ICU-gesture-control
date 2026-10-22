import { LEVELS } from "../lib/topics.js";
import { levelMeta } from "../lib/levels.js";

/** One stacked bar of p(routine/urgent/critical); the winning class is labelled in text. */
export default function ModelBar({ p }) {
  if (!p) return null;
  const pct = Object.fromEntries(LEVELS.map((l) => [l, Math.round((p[l] ?? 0) * 100)]));
  const winner = LEVELS.reduce((a, b) => ((p[b] ?? 0) > (p[a] ?? 0) ? b : a));
  const summary = LEVELS.map((l) => `${levelMeta(l).label} ${pct[l]}%`).join(", ");
  return (
    <div className="model">
      <div className="meter-head">
        <span className="label">Model output</span>
        <span className="model-winner">
          {levelMeta(winner).label} <span className="num">{pct[winner]}%</span>
        </span>
      </div>
      <div className="model-bar" role="img" aria-label={`Model probabilities: ${summary}`}>
        {LEVELS.map((l) =>
          pct[l] > 0 ? (
            <div key={l} className={`model-seg seg-${l}`} style={{ flexGrow: pct[l] }} title={`${levelMeta(l).label} ${pct[l]}%`} />
          ) : null,
        )}
      </div>
      <div className="model-legend" aria-hidden="true">
        {LEVELS.map((l) => (
          <span key={l} className={l === winner ? "is-winner" : ""}>
            <i className={`swatch seg-${l}`} />
            {levelMeta(l).label} <span className="num">{pct[l]}%</span>
          </span>
        ))}
      </div>
    </div>
  );
}
