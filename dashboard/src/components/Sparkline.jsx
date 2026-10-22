import { HR_HISTORY_MS } from "../state/nodesReducer.js";

const W = 160;
const H = 40;
const PAD = 4;
const MIN_SPAN = 20; // bpm: keeps a steady HR from looking like a wild swing
const MIN_WINDOW_MS = 30_000; // until 2 min of history exists, stretch what there is (at least 30 s)

/** HR over the last 2 minutes. Custom SVG; x is time, y auto-scales with a 20 bpm floor. */
export default function Sparkline({ samples, now }) {
  const points = samples.filter((s) => s.at >= now - HR_HISTORY_MS);
  if (points.length < 2) {
    return <div className="sparkline sparkline-empty">Trend after a few readings</div>;
  }
  const hrs = points.map((s) => s.hr);
  let lo = Math.min(...hrs);
  let hi = Math.max(...hrs);
  if (hi - lo < MIN_SPAN) {
    const mid = (hi + lo) / 2;
    lo = mid - MIN_SPAN / 2;
    hi = mid + MIN_SPAN / 2;
  }
  const start = Math.max(now - HR_HISTORY_MS, Math.min(points[0].at, now - MIN_WINDOW_MS));
  const x = (at) => PAD + ((at - start) / (now - start)) * (W - 2 * PAD);
  const y = (hr) => H - PAD - ((hr - lo) / (hi - lo)) * (H - 2 * PAD);
  const d = points.map((s, i) => `${i ? "L" : "M"}${x(s.at).toFixed(1)},${y(s.hr).toFixed(1)}`).join(" ");
  const last = points[points.length - 1];
  const label = `Heart rate, last 2 minutes: ${Math.min(...hrs)} to ${Math.max(...hrs)} bpm, now ${last.hr}`;
  return (
    <svg className="sparkline" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={label}>
      <title>{label}</title>
      <path d={d} className="spark-line" vectorEffect="non-scaling-stroke" />
      <circle cx={x(last.at)} cy={y(last.hr)} r="3" className="spark-dot" />
    </svg>
  );
}
