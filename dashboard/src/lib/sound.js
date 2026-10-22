// Short alert tones via Web Audio. Browsers only allow audio after a user
// gesture, so the AudioContext is created when the nurse enables sound.
// Every pattern plays once; nothing loops.

const PATTERNS = {
  // [frequency Hz, start s, duration s]
  urgent: [[880, 0, 0.18], [880, 0.28, 0.18]],
  critical: [
    [1046, 0, 0.14], [1318, 0.18, 0.14], [1046, 0.36, 0.14],
    [1046, 0.75, 0.14], [1318, 0.93, 0.14], [1046, 1.11, 0.14],
  ],
};

let ctx = null;

/** Call from a click handler. Returns false when Web Audio isn't available. */
export function unlockSound() {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return false;
    ctx = ctx ?? new AudioCtx();
    if (ctx.state === "suspended") ctx.resume();
    return true;
  } catch {
    return false;
  }
}

export function playAlertTone(level) {
  const pattern = PATTERNS[level];
  if (!ctx || !pattern) return;
  const t0 = ctx.currentTime + 0.02;
  for (const [freq, start, dur] of pattern) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    // Short attack/release so the tone doesn't click.
    gain.gain.setValueAtTime(0, t0 + start);
    gain.gain.linearRampToValueAtTime(0.25, t0 + start + 0.02);
    gain.gain.setValueAtTime(0.25, t0 + start + dur - 0.03);
    gain.gain.linearRampToValueAtTime(0, t0 + start + dur);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t0 + start);
    osc.stop(t0 + start + dur + 0.01);
  }
}
