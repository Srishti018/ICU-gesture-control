import { bedName, formatSeconds, formatWhen } from "../lib/format.js";
import { levelMeta } from "../lib/levels.js";

const MAX_BARS = 20;
const W = 320;
const H = 140;
const M = { top: 12, right: 8, bottom: 20, left: 32 };

function niceMax(v) {
  for (const step of [5, 10, 15, 20, 30, 60, 120, 300, 600]) if (v <= step) return step;
  return Math.ceil(v / 600) * 600;
}

/** Response time of each acknowledged alert, oldest to newest. Custom SVG, no chart library. */
export default function ResponseChart({ alerts }) {
  const rows = (alerts ?? [])
    .filter((a) => typeof a.response_s === "number")
    .slice(0, MAX_BARS)
    .reverse();
  if (rows.length === 0) return <p className="panel-empty">Response times appear here once an alert is acknowledged.</p>;

  const max = niceMax(Math.max(...rows.map((r) => r.response_s)));
  const innerW = W - M.left - M.right;
  const innerH = H - M.top - M.bottom;
  const slot = innerW / MAX_BARS;
  const barW = Math.max(4, slot - 2); // 2px gap between bars
  const y = (v) => M.top + innerH - (v / max) * innerH;

  return (
    <figure className="chart">
      <figcaption className="label">Response time per acknowledged alert (last {MAX_BARS})</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Response times of the last ${rows.length} acknowledged alerts, up to ${max} seconds`}>
        {[0, max / 2, max].map((v) => (
          <g key={v}>
            <line x1={M.left} x2={W - M.right} y1={y(v)} y2={y(v)} className={v === 0 ? "axis" : "grid"} />
            <text x={M.left - 6} y={y(v) + 4} textAnchor="end" className="tick">
              {v} s
            </text>
          </g>
        ))}
        {rows.map((r, i) => {
          const x = M.left + (MAX_BARS - rows.length + i) * slot + 1;
          const h = Math.max(2, y(0) - y(r.response_s));
          const tip = `${bedName(r.node)} · ${levelMeta(r.level).label} · ${formatSeconds(r.response_s)} · ${formatWhen(r.received_at)}`;
          return (
            <g key={r.id} className="bar-hit" tabIndex={0} aria-label={tip}>
              <title>{tip}</title>
              <rect x={x - 1} y={M.top} width={slot} height={innerH} className="hit" />
              <path
                className={`bar seg-${r.level}`}
                d={`M${x},${y(0)} v${-(h - 3)} q0,-3 3,-3 h${barW - 6} q3,0 3,3 v${h - 3} z`}
              />
            </g>
          );
        })}
        <text x={M.left} y={H - 4} className="tick">
          oldest
        </text>
        <text x={W - M.right} y={H - 4} textAnchor="end" className="tick">
          newest
        </text>
      </svg>
      <div className="model-legend">
        {["urgent", "critical"].map((l) => {
          const { label, Icon } = levelMeta(l);
          return (
            <span key={l}>
              <i className={`swatch seg-${l}`} />
              <Icon size={12} aria-hidden="true" />
              {label}
            </span>
          );
        })}
      </div>
    </figure>
  );
}
