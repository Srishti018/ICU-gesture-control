import { describe, expect, it } from "vitest";
import {
  HR_HISTORY_MS,
  MAX_EVENTS,
  ackResponse,
  ackUnconfirmed,
  activeAlert,
  alertSince,
  appendHr,
  displayLevel,
  heartbeatStale,
  initialState,
  isPulsing,
  nodesReducer,
  pushEvent,
  ruleFallback,
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

describe("HR history buffer", () => {
  it("keeps only the last 2 minutes of samples", () => {
    let h = [];
    for (let t = 0; t <= 180_000; t += 3000) h = appendHr(h, t, 70 + (t % 7));
    expect(h[0].at).toBe(60_000);
    expect(h.at(-1).at).toBe(180_000);
    expect(h.every((s) => s.at >= 180_000 - HR_HISTORY_MS)).toBe(true);
  });

  it("ignores missing or non-numeric HR", () => {
    const h = [{ at: 0, hr: 70 }];
    expect(appendHr(h, 3000, null)).toBe(h);
    expect(appendHr(h, 3000, "80")).toBe(h);
    expect(appendHr(h, 3000, NaN)).toBe(h);
  });

  it("routine messages feed the buffer", () => {
    const s = run(
      msg("icu/bed1/status/routine", status("routine", { hr: 80 }), false, 1000),
      msg("icu/bed1/status/routine", status("routine", { hr: 82 }), false, 4000),
    );
    expect(s.nodes.bed1.hrHistory).toEqual([{ at: 1000, hr: 80 }, { at: 4000, hr: 82 }]);
  });
});

describe("activity feed", () => {
  it("records live alerts, acknowledgements, offline and online, newest first", () => {
    const s = run(
      msg("icu/bed1/online", "online", true, 0),
      msg("icu/bed1/status/critical", status("critical"), false, 1000),
      msg("icu/bed1/status/urgent", "", false, 2000),
      msg("icu/bed1/status/critical", "", false, 2001),
      msg("icu/bed1/online", "offline", false, 3000),
      msg("icu/bed1/online", "online", false, 4000),
    );
    expect(s.events.map((e) => e.kind)).toEqual(["online", "offline", "ack", "alert"]);
    const ack = s.events[2];
    expect(ack).toMatchObject({ node: "bed1", level: "critical", alertTs: "2026-10-25T10:02:11", at: 2001 });
    expect(s.nodes.bed1.lastAck).toEqual({ level: "critical", alertTs: "2026-10-25T10:02:11", at: 2001 });
  });

  it("acknowledging urgent + critical logs one event for the highest level", () => {
    const s = run(
      msg("icu/bed1/status/urgent", status("urgent")),
      msg("icu/bed1/status/critical", status("critical")),
      msg("icu/bed1/status/urgent", ""),
      msg("icu/bed1/status/critical", ""),
    );
    expect(s.events.filter((e) => e.kind === "ack")).toHaveLength(1);
    expect(s.nodes.bed1.lastAck.level).toBe("critical");
  });

  it("retained messages on page load are not news", () => {
    const s = run(msg("icu/bed1/online", "offline", true), msg("icu/bed1/status/urgent", status("urgent"), true));
    expect(s.events).toEqual([]);
  });

  it("caps the list at 50 events with unique ids", () => {
    let s = initialState;
    for (let i = 0; i < 60; i++) s = pushEvent(s, { kind: "online", node: "bed1", at: i });
    expect(s.events).toHaveLength(MAX_EVENTS);
    expect(s.events[0].at).toBe(59);
    expect(new Set(s.events.map((e) => e.id)).size).toBe(MAX_EVENTS);
  });

  it("TICK logs heartbeat lost once, and a heartbeat brings it back", () => {
    let s = run(msg("icu/bed1/online", "online", true, 0), msg("icu/bed1/heartbeat", "{}", false, 1000));
    s = nodesReducer(s, { type: "TICK", now: 20_000 });
    expect(s.events).toEqual([]);
    s = nodesReducer(s, { type: "TICK", now: 26_001 });
    s = nodesReducer(s, { type: "TICK", now: 27_001 });
    expect(s.events.map((e) => e.kind)).toEqual(["heartbeat-lost"]);
    s = nodesReducer(s, msg("icu/bed1/heartbeat", "{}", false, 28_000));
    expect(s.events.map((e) => e.kind)).toEqual(["heartbeat-back", "heartbeat-lost"]);
    expect(s.nodes.bed1.heartbeatLost).toBe(false);
  });
});

describe("alert timing and response", () => {
  it("alertSince uses the alert's own timestamp, never in the future", () => {
    const s = run(msg("icu/bed1/status/critical", status("critical"), false, 5000));
    const ts = new Date(2026, 9, 25, 10, 2, 11).getTime();
    expect(alertSince(s.nodes.bed1, ts + 42_000)).toBe(ts);
    expect(alertSince(s.nodes.bed1, ts - 1000)).toBe(ts - 1000);
    const bad = run(msg("icu/bed1/status/critical", status("critical", { ts: "?" }), false, 5000));
    expect(alertSince(bad.nodes.bed1, 9000)).toBe(5000);
  });

  it("pulses for the first 10 s of a live alert only", () => {
    const live = run(msg("icu/bed1/status/critical", status("critical"), false, 1000)).nodes.bed1;
    expect(isPulsing(live, 10_999)).toBe(true);
    expect(isPulsing(live, 11_000)).toBe(false);
    const retained = run(msg("icu/bed1/status/critical", status("critical"), true, 1000)).nodes.bed1;
    expect(isPulsing(retained, 1001)).toBe(false);
  });

  it("ackResponse finds the server's response time for the acknowledged alert", () => {
    const s = run(msg("icu/bed1/status/critical", status("critical")), msg("icu/bed1/status/critical", ""));
    const n = s.nodes.bed1;
    expect(ackResponse(n, null)).toBeNull();
    expect(ackResponse(n, [{ node: "bed1", alert_ts: "2026-10-25T10:02:11", response_s: null }])).toBeNull();
    expect(ackResponse(n, [{ node: "bed1", alert_ts: "2026-10-25T10:02:11", response_s: 8.2 }])).toBe(8.2);
    expect(ackResponse(n, [{ node: "bed2", alert_ts: "2026-10-25T10:02:11", response_s: 8.2 }])).toBeNull();
  });

  it("rule fallback needs two rule-shaped outputs in a row", () => {
    const rule = { p: { routine: 0.05, urgent: 0.9, critical: 0.05 } };
    let s = run(msg("icu/bed1/status/routine", status("urgent", rule)));
    expect(ruleFallback(s.nodes.bed1)).toBe(false);
    s = nodesReducer(s, msg("icu/bed1/status/routine", status("urgent", rule)));
    expect(ruleFallback(s.nodes.bed1)).toBe(true);
    s = nodesReducer(s, msg("icu/bed1/status/routine", status("urgent")));
    expect(ruleFallback(s.nodes.bed1)).toBe(false);
  });
});
