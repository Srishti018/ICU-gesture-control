import { parseLocalIso } from "../lib/format.js";
import { looksLikeRule } from "../lib/modelOutput.js";
import { parseTopic } from "../lib/topics.js";

export const STALE_HEARTBEAT_MS = 25000;
export const ACK_CONFIRM_MS = 5000;
export const HR_HISTORY_MS = 2 * 60 * 1000;
export const MAX_EVENTS = 50;
// Two rule-shaped outputs in a row before the "Rule fallback" badge appears,
// so a model output that happens to be 0.90/0.05/0.05 once doesn't trigger it.
export const RULE_STREAK_MIN = 2;

export const initialState = { nodes: {}, lastAlertEvent: null, events: [], nextEventId: 1 };

function newNode(id, at) {
  return {
    id,
    online: null,
    lastHeartbeatAt: null,
    firstSeenAt: at,
    status: null,
    statusAt: null,
    alerts: { urgent: null, critical: null },
    // When each alert arrived live (null for retained alerts seen on page load).
    alertRaisedAt: { urgent: null, critical: null },
    // The highest alert seen since the node last had none; becomes lastAck when cleared.
    peakAlert: null,
    lastAck: null,
    ackPendingSince: null,
    offlineAt: null,
    heartbeatLost: false,
    hrHistory: [],
    ruleStreak: 0,
  };
}

function parseJson(text) {
  try {
    const value = JSON.parse(text);
    return value && typeof value === "object" ? value : undefined;
  } catch {
    return undefined;
  }
}

/** Append one HR sample and drop samples older than windowMs before it. */
export function appendHr(history, at, hr, windowMs = HR_HISTORY_MS) {
  if (typeof hr !== "number" || !Number.isFinite(hr)) return history;
  const cutoff = at - windowMs;
  return [...history.filter((s) => s.at >= cutoff), { at, hr }];
}

/** Newest-first event list capped at MAX_EVENTS. */
export function pushEvent(state, event) {
  const events = [{ id: state.nextEventId, ...event }, ...state.events].slice(0, MAX_EVENTS);
  return { ...state, events, nextEventId: state.nextEventId + 1 };
}

const higher = (a, b) => (!a ? b : !b ? a : b.level === "critical" ? b : a);

function handleMessage(state, { topic, payload, retain, at }) {
  const t = parseTopic(topic);
  if (!t || t.kind === "ack") return state;

  const existing = state.nodes[t.node];
  // Empty payloads are clears (contract rule 6): they never create a node.
  if (payload === "" && (!existing || t.kind !== "status" || t.level === "routine")) return state;

  let node = existing ?? newNode(t.node, at);
  let lastAlertEvent = state.lastAlertEvent;
  const events = [];

  if (t.kind === "status" && t.level === "routine") {
    const data = parseJson(payload);
    if (data === undefined) return state;
    node = {
      ...node,
      status: data,
      statusAt: at,
      hrHistory: appendHr(node.hrHistory, at, data.hr),
      ruleStreak: looksLikeRule(data.p) ? node.ruleStreak + 1 : 0,
    };
  } else if (t.kind === "status") {
    let alert = null;
    if (payload !== "") {
      alert = parseJson(payload);
      if (alert === undefined) return state;
      if (!retain) {
        lastAlertEvent = { node: t.node, level: t.level, at };
        events.push({ kind: "alert", node: t.node, level: t.level, at });
      }
    }
    const alerts = { ...node.alerts, [t.level]: alert };
    const alertRaisedAt = { ...node.alertRaisedAt, [t.level]: alert && !retain ? at : null };
    node = { ...node, alerts, alertRaisedAt, peakAlert: alert ? higher(node.peakAlert, alert) : node.peakAlert };
    if (alerts.urgent === null && alerts.critical === null) {
      node.ackPendingSince = null;
      if (node.peakAlert) {
        const { level, ts } = node.peakAlert;
        node.lastAck = { level, alertTs: ts, at };
        node.peakAlert = null;
        events.push({ kind: "ack", node: t.node, level, alertTs: ts, at });
      }
    }
  } else if (t.kind === "heartbeat") {
    if (node.heartbeatLost) events.push({ kind: "heartbeat-back", node: t.node, at });
    node = { ...node, lastHeartbeatAt: at, heartbeatLost: false };
  } else if (t.kind === "online") {
    const online = payload === "online";
    // Live changes only: retained flags on page load are state, not news.
    if (!retain && online !== node.online) events.push({ kind: online ? "online" : "offline", node: t.node, at });
    node = {
      ...node,
      online,
      heartbeatLost: false,
      offlineAt: online ? null : retain ? (node.lastHeartbeatAt ?? node.statusAt) : at,
    };
  }

  let next = { ...state, nodes: { ...state.nodes, [t.node]: node }, lastAlertEvent };
  for (const e of events) next = pushEvent(next, e);
  return next;
}

/** Once a second: log "heartbeat lost" the first time a node goes quiet. */
function handleTick(state, now) {
  let next = state;
  for (const node of Object.values(state.nodes)) {
    if (!node.heartbeatLost && heartbeatStale(node, now)) {
      next = { ...next, nodes: { ...next.nodes, [node.id]: { ...node, heartbeatLost: true } } };
      next = pushEvent(next, { kind: "heartbeat-lost", node: node.id, at: now });
    }
  }
  return next;
}

export function nodesReducer(state, action) {
  switch (action.type) {
    case "MESSAGE":
      return handleMessage(state, action);
    case "TICK":
      return handleTick(state, action.now);
    case "ACK_SENT": {
      const node = state.nodes[action.node];
      if (!node) return state;
      return { ...state, nodes: { ...state.nodes, [action.node]: { ...node, ackPendingSince: action.at } } };
    }
    case "DISMISS_BANNER":
      return state.lastAlertEvent === null ? state : { ...state, lastAlertEvent: null };
    default:
      return state;
  }
}

// --- selectors ---------------------------------------------------------------

export const activeAlert = (n) => n.alerts.critical ?? n.alerts.urgent ?? null;

export const displayLevel = (n) => activeAlert(n)?.level ?? n.status?.level ?? "routine";

export const heartbeatStale = (n, now) =>
  n.online === true && now - (n.lastHeartbeatAt ?? n.firstSeenAt) > STALE_HEARTBEAT_MS;

export const ackUnconfirmed = (n, now) =>
  n.ackPendingSince !== null && activeAlert(n) !== null && now - n.ackPendingSince > ACK_CONFIRM_MS;

/** When the active alert started (ms): its own timestamp, else when it arrived. */
export function alertSince(n, now) {
  const alert = activeAlert(n);
  if (!alert) return null;
  const ts = parseLocalIso(alert.ts);
  const fallback = n.alertRaisedAt[alert.level] ?? now;
  return ts === null ? fallback : Math.min(ts, now);
}

/** Pulse a new alert for its first 10 s only (never for retained alerts after a reload). */
export const PULSE_MS = 10000;
export function isPulsing(n, now) {
  const alert = activeAlert(n);
  const raised = alert ? n.alertRaisedAt[alert.level] : null;
  return raised !== null && now - raised < PULSE_MS;
}

export const ruleFallback = (n) => n.ruleStreak >= RULE_STREAK_MIN;

/** Response time from the server's alert log for this node's last acknowledged alert. */
export function ackResponse(n, alerts) {
  if (!n.lastAck || !Array.isArray(alerts)) return null;
  const row = alerts.find(
    (a) => a.node === n.id && a.alert_ts === n.lastAck.alertTs && typeof a.response_s === "number",
  );
  return row ? row.response_s : null;
}
