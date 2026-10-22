const pad = (n) => String(n).padStart(2, "0");

/** "bed1" -> "Bed 1"; any other id is shown as it is. */
export function bedName(id) {
  const m = /^bed(\d+)$/i.exec(id);
  return m ? `Bed ${Number(m[1])}` : id;
}

/** Elapsed seconds as "00:42", "12:05" or "1:02:03". */
export function formatDuration(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${pad(m)}:${pad(sec)}`;
}

/** "32 s", "2 min", "2 h": a length of time, coarser as it gets long. */
export function formatSpan(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  return `${Math.floor(s / 3600)} h`;
}

/** "updated 2 s ago" style age. */
export const formatAgo = (seconds) => `${formatSpan(seconds)} ago`;

/** Contract timestamp "2026-10-25T10:02:11" (local time) -> ms, or null. */
export function parseLocalIso(value) {
  if (typeof value !== "string") return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/.exec(value);
  if (!m) return null;
  const d = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]);
  return Number.isNaN(d.getTime()) ? null : d.getTime();
}

/** History time: "17:23:28" today, "24 Oct 17:23:28" on other days. */
export function formatWhen(value, now = Date.now()) {
  const ms = typeof value === "number" ? value : parseLocalIso(value);
  if (ms === null) return "—";
  const d = new Date(ms);
  const t = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  if (new Date(now).toDateString() === d.toDateString()) return t;
  return `${d.getDate()} ${d.toLocaleString("en-GB", { month: "short" })} ${t}`;
}

/** Response time in seconds as "8.2 s". */
export const formatSeconds = (s) => (typeof s === "number" ? `${s.toFixed(1)} s` : "—");

export const formatSigned = (v) => (typeof v === "number" ? (v > 0 ? `+${v}` : v < 0 ? `−${-v}` : "0") : "—");

export const formatNumber = (v, digits = 0) => (typeof v === "number" ? v.toFixed(digits) : "—");
