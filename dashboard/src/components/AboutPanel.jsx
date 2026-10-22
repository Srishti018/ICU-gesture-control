import { levelMeta } from "../lib/levels.js";

const LEVELS = [
  ["routine", "No call for help. Vitals are shown live; nothing needs doing."],
  ["urgent", "The patient is holding up an open palm, the help gesture. Go to the bed."],
  ["critical", "The help gesture together with physical distress, such as heart rate 15 bpm or more above the patient's baseline. Go now."],
  ["offline", "The bed device stopped sending. The broker reports it within about 10 s (Last Will)."],
];

export default function AboutPanel() {
  return (
    <div className="about" data-testid="about-panel">
      <h3>What the levels mean</h3>
      <dl className="about-levels">
        {LEVELS.map(([level, text]) => {
          const { word, Icon } = levelMeta(level);
          return (
            <div key={level} className={`about-level lvl-${level}`}>
              <dt>
                <Icon size={16} aria-hidden="true" /> {word}
              </dt>
              <dd>{text}</dd>
            </div>
          );
        })}
      </dl>

      <h3>Where the data comes from</h3>
      <p>
        Biosignals in this demo are <strong>replayed from real recordings</strong> when a tile shows “Biosignals:
        replay”; gesture detection from the camera is <strong>live</strong>.
      </p>

      <h3>The four inputs to the model</h3>
      <ul className="about-inputs">
        <li><strong>Gesture confidence</strong> — how sure the camera is that an open palm is held up (alert threshold 80%).</li>
        <li><strong>Tremor</strong> — how much the fingertips shake relative to the wrist (amplitude).</li>
        <li><strong>ΔHR</strong> — heart rate minus the patient's resting baseline, in bpm.</li>
        <li><strong>SpO₂</strong> — blood oxygen saturation, in %.</li>
      </ul>
      <p>
        The model turns these into probabilities for routine, urgent and critical. “Rule fallback” means the bed is
        using the fixed threshold rule instead of the trained model.
      </p>

      <h3>Acknowledging</h3>
      <p>
        Acknowledge tells the server a nurse has seen the alert. The server records the response time and clears the
        alert on every screen.
      </p>
    </div>
  );
}
