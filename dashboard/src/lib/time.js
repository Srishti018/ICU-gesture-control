const pad = (n) => String(n).padStart(2, "0");

/** Local time as YYYY-MM-DDTHH:MM:SS (the contract's timestamp format). */
export function nowLocalIso(date = new Date()) {
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  );
}

/** Whole seconds from a ms timestamp until now (never negative). */
export function secondsSince(ms, now = Date.now()) {
  return Math.max(0, Math.floor((now - ms) / 1000));
}

/** HH:MM:SS from a Date, ms number, or contract ISO string. "—" when missing. */
export function formatClock(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string") {
    const m = value.match(/T(\d{2}:\d{2}:\d{2})/);
    return m ? m[1] : value;
  }
  const d = value instanceof Date ? value : new Date(value);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
