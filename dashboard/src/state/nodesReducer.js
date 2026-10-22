import { parseTopic } from "../lib/topics.js";

export const STALE_HEARTBEAT_MS = 25000;
export const ACK_CONFIRM_MS = 5000;

export const initialState = { nodes: {}, lastAlertEvent: null };

function newNode(id, at) {
  return {
    id,
    online: null,
    lastHeartbeatAt: null,
    firstSeenAt: at,
    status: null,
    statusAt: null,
    alerts: { urgent: null, critical: null },
    ackPendingSince: null,
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

function handleMessage(state, { topic, payload, retain, at }) {
  const t = parseTopic(topic);
  if (!t || t.kind === "ack") return state;

  const existing = state.nodes[t.node];
  // Empty payloads are clears (contract rule 6): they never create a node.
  if (payload === "" && (!existing || t.kind !== "status" || t.level === "routine")) return state;

  let node = existing ?? newNode(t.node, at);
  let lastAlertEvent = state.lastAlertEvent;

  if (t.kind === "status" && t.level === "routine") {
    const data = parseJson(payload);
    if (data === undefined) return state;
    node = { ...node, status: data, statusAt: at };
  } else if (t.kind === "status") {
    let alert = null;
    if (payload !== "") {
      alert = parseJson(payload);
      if (alert === undefined) return state;
      if (!retain) lastAlertEvent = { node: t.node, level: t.level, at };
    }
    const alerts = { ...node.alerts, [t.level]: alert };
    node = { ...node, alerts };
    if (alerts.urgent === null && alerts.critical === null) node.ackPendingSince = null;
  } else if (t.kind === "heartbeat") {
    node = { ...node, lastHeartbeatAt: at };
  } else if (t.kind === "online") {
    node = { ...node, online: payload === "online" };
  }

  return { ...state, nodes: { ...state.nodes, [t.node]: node }, lastAlertEvent };
}

export function nodesReducer(state, action) {
  switch (action.type) {
    case "MESSAGE":
      return handleMessage(state, action);
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
