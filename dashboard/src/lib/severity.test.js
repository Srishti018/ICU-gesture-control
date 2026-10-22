import { describe, expect, it } from "vitest";
import { initialState, nodesReducer } from "../state/nodesReducer.js";
import { looksLikeRule } from "./modelOutput.js";
import { severityOf, sortAlerts, sortBySeverity } from "./severity.js";

const msg = (topic, payload, retain = false) => ({ type: "MESSAGE", topic, payload, retain, at: 1000 });
const status = (node, level) =>
  JSON.stringify({ node, ts: "2026-10-25T10:02:11", level, p: { routine: 0.1, urgent: 0.1, critical: 0.8 }, hr: 80 });

function build(...messages) {
  return Object.values(messages.reduce(nodesReducer, initialState).nodes);
}

describe("severity sort", () => {
  it("orders critical, urgent, offline, routine, then by bed number", () => {
    const nodes = build(
      msg("icu/bed10/status/routine", status("bed10", "routine")),
      msg("icu/bed2/status/routine", status("bed2", "routine")),
      msg("icu/bed3/online", "offline", true),
      msg("icu/bed4/status/urgent", status("bed4", "urgent")),
      msg("icu/bed5/status/critical", status("bed5", "critical")),
      msg("icu/bed1/status/routine", status("bed1", "routine")),
    );
    expect(sortBySeverity(nodes).map((n) => n.id)).toEqual(["bed5", "bed4", "bed3", "bed1", "bed2", "bed10"]);
  });

  it("an offline bed with an active alert still sorts by its alert", () => {
    const [n] = build(msg("icu/bed1/status/critical", status("bed1", "critical")), msg("icu/bed1/online", "offline"));
    expect(severityOf(n)).toBe("critical");
  });

  it("a bed still critical after acknowledgement sorts as critical", () => {
    const [n] = build(msg("icu/bed1/status/routine", status("bed1", "critical")));
    expect(severityOf(n)).toBe("critical");
  });

  it("sortAlerts puts critical first, then the oldest", () => {
    const rows = [
      { node: { id: "bed1" }, alert: { level: "urgent" }, since: 1 },
      { node: { id: "bed2" }, alert: { level: "critical" }, since: 9 },
      { node: { id: "bed3" }, alert: { level: "critical" }, since: 5 },
    ];
    expect(sortAlerts(rows).map((r) => r.node.id)).toEqual(["bed3", "bed2", "bed1"]);
  });
});

describe("rule fallback detection", () => {
  it("matches the rule's 0.90/0.05/0.05 and one-hot outputs", () => {
    expect(looksLikeRule({ routine: 0.05, urgent: 0.05, critical: 0.9 })).toBe(true);
    expect(looksLikeRule({ routine: 1, urgent: 0, critical: 0 })).toBe(true);
  });
  it("does not match model-like outputs or bad input", () => {
    expect(looksLikeRule({ routine: 0.04, urgent: 0.11, critical: 0.85 })).toBe(false);
    expect(looksLikeRule({ routine: 0.9, urgent: 0.1 })).toBe(false);
    expect(looksLikeRule(null)).toBe(false);
  });
});
