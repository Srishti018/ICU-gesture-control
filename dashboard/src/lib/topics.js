export const LEVELS = ["routine", "urgent", "critical"];
const SIMPLE_KINDS = ["heartbeat", "online", "ack"];

/**
 * "icu/bed1/status/critical" -> {node: "bed1", kind: "status", level: "critical"}
 * "icu/bed1/heartbeat"       -> {node: "bed1", kind: "heartbeat", level: null}
 * Anything else              -> null
 */
export function parseTopic(topic) {
  const parts = topic.split("/");
  if (parts[0] !== "icu" || !parts[1]) return null;
  const node = parts[1];
  if (parts.length === 4 && parts[2] === "status" && LEVELS.includes(parts[3])) {
    return { node, kind: "status", level: parts[3] };
  }
  if (parts.length === 3 && SIMPLE_KINDS.includes(parts[2])) {
    return { node, kind: parts[2], level: null };
  }
  return null;
}

export const ackTopic = (node) => `icu/${node}/ack`;
