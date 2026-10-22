import { ChevronDown, History } from "lucide-react";
import { useMemo, useState } from "react";
import { bedName, formatNumber, formatSeconds, formatWhen } from "../lib/format.js";
import { levelMeta } from "../lib/levels.js";

export default function HistorySection({ alerts, available, now }) {
  const [open, setOpen] = useState(true);
  const [bed, setBed] = useState("all");
  const [level, setLevel] = useState("all");
  const [state, setState] = useState("all");

  const beds = useMemo(
    () => [...new Set((alerts ?? []).map((a) => a.node))].sort((a, b) => a.localeCompare(b, undefined, { numeric: true })),
    [alerts],
  );
  const rows = (alerts ?? []).filter(
    (a) =>
      (bed === "all" || a.node === bed) &&
      (level === "all" || a.level === level) &&
      (state === "all" || (state === "open" ? a.ack_ts === null : a.ack_ts !== null)),
  );

  return (
    <section className="history" aria-labelledby="history-title">
      <button type="button" className="history-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <History size={18} aria-hidden="true" />
        <h2 id="history-title">Alert history</h2>
        {available && alerts && <span className="history-count num">{alerts.length} stored</span>}
        <ChevronDown className={`chev ${open ? "chev-open" : ""}`} size={18} aria-hidden="true" />
      </button>

      {open &&
        (!available ? (
          <p className="panel-empty" data-testid="history-unavailable">
            History unavailable — the server isn't reachable. Live tiles keep working.
          </p>
        ) : (
          <>
            <div className="filters">
              <label>
                Bed
                <select value={bed} onChange={(e) => setBed(e.target.value)} data-testid="filter-bed">
                  <option value="all">All beds</option>
                  {beds.map((b) => (
                    <option key={b} value={b}>
                      {bedName(b)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Level
                <select value={level} onChange={(e) => setLevel(e.target.value)} data-testid="filter-level">
                  <option value="all">All levels</option>
                  <option value="critical">Critical</option>
                  <option value="urgent">Urgent</option>
                </select>
              </label>
              <label>
                Status
                <select value={state} onChange={(e) => setState(e.target.value)} data-testid="filter-state">
                  <option value="all">All</option>
                  <option value="open">Open</option>
                  <option value="acked">Acknowledged</option>
                </select>
              </label>
            </div>
            {rows.length === 0 ? (
              <p className="panel-empty">{alerts?.length ? "No alerts match these filters." : "No alerts recorded yet."}</p>
            ) : (
              <div className="table-wrap">
                <table className="history-table" data-testid="history-table">
                  <thead>
                    <tr>
                      <th scope="col">Raised</th>
                      <th scope="col">Bed</th>
                      <th scope="col">Level</th>
                      <th scope="col">HR</th>
                      <th scope="col">SpO₂</th>
                      <th scope="col">Gesture</th>
                      <th scope="col">Biosignals</th>
                      <th scope="col">Acknowledged</th>
                      <th scope="col">Response</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((a) => {
                      const { label, Icon } = levelMeta(a.level);
                      return (
                        <tr key={a.id} data-testid="history-row">
                          <td className="num">{formatWhen(a.received_at, now)}</td>
                          <td>{bedName(a.node)}</td>
                          <td className={`lvl lvl-${a.level}`}>
                            <Icon size={14} aria-hidden="true" /> {label}
                          </td>
                          <td className="num">{formatNumber(a.hr)}</td>
                          <td className="num">{typeof a.spo2 === "number" ? `${a.spo2}%` : "—"}</td>
                          <td className="num">{typeof a.gesture_conf === "number" ? `${Math.round(a.gesture_conf * 100)}%` : "—"}</td>
                          <td>{a.bio_source === "replay" ? "Replay" : a.bio_source === "live" ? "Live" : "—"}</td>
                          <td className="num">{a.ack_ts === null ? <span className="open-tag">Open</span> : formatWhen(a.ack_received_at, now)}</td>
                          <td className="num" data-testid="history-response">
                            {formatSeconds(a.response_s)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        ))}
    </section>
  );
}
