import { activeAlert, displayLevel } from "../state/nodesReducer.js";

const RANK = { critical: 0, urgent: 1, offline: 2, routine: 3 };

/** Sort key: an active alert's level, else offline, else the latest status level. */
export function severityOf(node) {
  const alert = activeAlert(node);
  if (alert) return alert.level;
  if (node.online === false) return "offline";
  const level = displayLevel(node);
  return level in RANK ? level : "routine";
}

const byId = (a, b) => a.id.localeCompare(b.id, undefined, { numeric: true });

/** critical -> urgent -> offline -> routine, then by bed id (bed2 before bed10). */
export function sortBySeverity(nodes) {
  return [...nodes].sort((a, b) => RANK[severityOf(a)] - RANK[severityOf(b)] || byId(a, b));
}

/** Highest-severity alert first, then the oldest alert first. */
export function sortAlerts(rows) {
  return [...rows].sort(
    (a, b) => RANK[a.alert.level] - RANK[b.alert.level] || a.since - b.since || byId(a.node, b.node),
  );
}
