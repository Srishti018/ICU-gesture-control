import { LEVELS } from "../lib/topics.js";

export default function ProbabilityBars({ p }) {
  if (!p) return null;
  return (
    <div className="probs">
      {LEVELS.map((level) => {
        const pct = Math.round((p[level] ?? 0) * 100);
        return (
          <div className="prob-row" key={level}>
            <span className="prob-label">{level}</span>
            <div className="prob-track">
              <div className={`prob-fill level-bg-${level}`} style={{ width: `${pct}%` }} />
            </div>
            <span className="prob-pct">{pct}%</span>
          </div>
        );
      })}
    </div>
  );
}
