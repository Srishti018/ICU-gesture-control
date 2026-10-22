const THRESHOLD = 0.8;

/** Gesture confidence 0–100 % with the 80 % alert threshold marked. */
export default function GestureMeter({ value }) {
  const known = typeof value === "number";
  const pct = known ? Math.round(Math.min(1, Math.max(0, value)) * 100) : 0;
  const above = known && value >= THRESHOLD;
  return (
    <div className="meter">
      <div className="meter-head">
        <span className="label">Gesture confidence</span>
        <span className="meter-value num">{known ? `${pct}%` : "—"}</span>
      </div>
      <div
        className="meter-track"
        role="meter"
        aria-label="Gesture confidence"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={known ? pct : undefined}
        aria-valuetext={known ? `${pct}%${above ? ", above the 80% threshold" : ""}` : "no reading"}
      >
        <div className={`meter-fill ${above ? "meter-fill-above" : ""}`} style={{ width: `${pct}%` }} />
        <div className="meter-mark" style={{ left: `${THRESHOLD * 100}%` }} aria-hidden="true" />
      </div>
      <div className="meter-scale" aria-hidden="true">
        <span style={{ left: `${THRESHOLD * 100}%` }}>80%</span>
      </div>
    </div>
  );
}
