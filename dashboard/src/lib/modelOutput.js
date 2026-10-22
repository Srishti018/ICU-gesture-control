import { LEVELS } from "./topics.js";

// The node's rule fallback publishes 0.90 on the chosen level and 0.05 on the
// other two (node/fusion_adapter.py). A one-hot vector counts too.
const RULE_PATTERNS = [
  [0.9, 0.05, 0.05],
  [1, 0, 0],
];

/** True when p looks like the fixed rule rather than a trained model. */
export function looksLikeRule(p) {
  if (!p || typeof p !== "object") return false;
  const values = LEVELS.map((l) => p[l]);
  if (!values.every((v) => typeof v === "number")) return false;
  values.sort((a, b) => b - a);
  return RULE_PATTERNS.some((pattern) => pattern.every((v, i) => Math.abs(values[i] - v) < 1e-6));
}
