import { describe, expect, it } from "vitest";
import {
  ackUnconfirmed,
  activeAlert,
  displayLevel,
  heartbeatStale,
  initialState,
  nodesReducer,
} from "./nodesReducer.js";

const status = (level, extra = {}) =>
  JSON.stringify({
    node: "bed1",
    ts: "2026-10-25T10:02:11",
    level,
    p: { routine: 0.04, urgent: 0.11, critical: 0.85 },
    features: { gesture_conf: 0.91, tremor: 0.01, hr_delta: 24, spo2: 98 },
    hr: 99,
    bio_source: "live",
    ...extra,
  });

const msg = (topic, payload, retain = false, at = 1000) => ({ type: "MESSAGE", topic, payload, retain, at });

const run = (...actions) => actions.reduce(nodesReducer, initialState);

describe("nodesReducer MESSAGE", () => {
  it("routine sets status and creates the node", () => {
    const s = run(msg("icu/bed1/status/routine", status("routine"), false, 500));
    const n = s.nodes.bed1;
    expect(n.status.level).toBe("routine");
    expect(n.statusAt).toBe(500);
    expect(n.firstSeenAt).toBe(500);
    expect(n.alerts).toEqual({ urgent: null, critical: null });
  });

  it("retained critical sets the alert without lastAlertEvent", () => {
    const s = run(msg("icu/bed1/status/critical", status("critical"), true));
    expect(s.nodes.bed1.alerts.critical.level).toBe("critical");
    expect(s.lastAlertEvent).toBeNull();
  });

  it("non-retained critical sets lastAlertEvent", () => {
    const s = run(msg("icu/bed1/status/critical", status("critical"), false, 1234));
    expect(s.lastAlertEvent).toEqual({ node: "bed1", level: "critical", at: 1234 });
  });

  it("empty payload clears that alert only", () => {
    const s = run(
      msg("icu/bed1/status/urgent", status("urgent")),
      msg("icu/bed1/status/critical", status("critical")),
      msg("icu/bed1/status/critical", "", true),
    );
    expect(s.nodes.bed1.alerts.critical).toBeNull();
    expect(s.nodes.bed1.alerts.urgent.level).toBe("urgent");
  });

  it("clearing both alerts resets ackPendingSince", () => {
    let s = run(
      msg("icu/bed1/status/urgent", status("urgent")),
      msg("icu/bed1/status/critical", status("critical")),
      { type: "ACK_SENT", node: "bed1", at: 2000 },
    );
    expect(s.nodes.bed1.ackPendingSince).toBe(2000);
    s = nodesReducer(s, msg("icu/bed1/status/urgent", "", true));
    expect(s.nodes.bed1.ackPendingSince).toBe(2000);
    s = nodesReducer(s, msg("icu/bed1/status/critical", "", true));
    expect(s.nodes.bed1.ackPendingSince).toBeNull();
  });

  it("invalid JSON leaves state unchanged", () => {
    const s0 = run(msg("icu/bed1/status/routine", status("routine")));
    expect(nodesReducer(s0, msg("icu/bed1/status/routine", "{bad"))).toBe(s0);
    expect(nodesReducer(s0, msg("icu/bed1/status/critical", "{bad"))).toBe(s0);
    expect(nodesReducer(initialState, msg("icu/bed2/status/routine", "nope"))).toBe(initialState);
  });

  it("empty payloads and acks never create a node", () => {
    expect(nodesReducer(initialState, msg("icu/bed2/status/critical", "", true))).toBe(initialState);
    expect(nodesReducer(initialState, msg("icu/bed2/online", "", true))).toBe(initialState);
    expect(nodesReducer(initialState, msg("icu/bed2/ack", '{"node":"bed2"}'))).toBe(initialState);
  });

  it("heartbeat and online update liveness", () => {
    const s = run(
      msg("icu/bed1/online", "online", true, 100),
      msg("icu/bed1/heartbeat", '{"node":"bed1","ts":"x","uptime_s":1}', false, 200),
    );
    expect(s.nodes.bed1.online).toBe(true);
    expect(s.nodes.bed1.lastHeartbeatAt).toBe(200);
    expect(nodesReducer(s, msg("icu/bed1/online", "offline", true)).nodes.bed1.online).toBe(false);
  });

  it("DISMISS_BANNER clears lastAlertEvent", () => {
    const s = run(msg("icu/bed1/status/urgent", status("urgent")), { type: "DISMISS_BANNER" });
    expect(s.lastAlertEvent).toBeNull();
  });
});

describe("selectors", () => {
  const base = () => run(msg("icu/bed1/online", "online", true, 0)).nodes.bed1;

  it("activeAlert prefers critical and displayLevel follows it", () => {
    const s = run(
      msg("icu/bed1/status/routine", status("routine")),
      msg("icu/bed1/status/urgent", status("urgent")),
    );
    expect(displayLevel(s.nodes.bed1)).toBe("urgent");
    const s2 = nodesReducer(s, msg("icu/bed1/status/critical", status("critical")));
    expect(activeAlert(s2.nodes.bed1).level).toBe("critical");
    expect(displayLevel(s2.nodes.bed1)).toBe("critical");
  });

  it("displayLevel falls back to status, then routine", () => {
    expect(displayLevel(base())).toBe("routine");
    const s = run(msg("icu/bed1/status/routine", status("urgent")));
    expect(displayLevel(s.nodes.bed1)).toBe("urgent");
  });

  it("heartbeatStale boundary at 25 s, only when online", () => {
    const n = { ...base(), lastHeartbeatAt: 1000 };
    expect(heartbeatStale(n, 26000)).toBe(false);
    expect(heartbeatStale(n, 26001)).toBe(true);
    expect(heartbeatStale({ ...n, online: false }, 99999)).toBe(false);
    expect(heartbeatStale({ ...n, online: null }, 99999)).toBe(false);
    const noHb = { ...base(), firstSeenAt: 0, lastHeartbeatAt: null };
    expect(heartbeatStale(noHb, 25000)).toBe(false);
    expect(heartbeatStale(noHb, 25001)).toBe(true);
  });

  it("ackUnconfirmed boundary at 5 s, only with an active alert", () => {
    const s = run(
      msg("icu/bed1/status/critical", status("critical")),
      { type: "ACK_SENT", node: "bed1", at: 10000 },
    );
    const n = s.nodes.bed1;
    expect(ackUnconfirmed(n, 15000)).toBe(false);
    expect(ackUnconfirmed(n, 15001)).toBe(true);
    expect(ackUnconfirmed({ ...n, alerts: { urgent: null, critical: null } }, 99999)).toBe(false);
    expect(ackUnconfirmed({ ...n, ackPendingSince: null }, 99999)).toBe(false);
  });
});
