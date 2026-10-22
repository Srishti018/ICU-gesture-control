import { formatClock } from "../lib/time.js";

export default function AlertLog({ alerts, available }) {
  return (
    <section className="log">
      <h2>Alert log</h2>
      {!available ? (
        <div className="empty">History unavailable</div>
      ) : !alerts || alerts.length === 0 ? (
        <div className="empty">No alerts yet</div>
      ) : (
        <div className="table-wrap">
          <table data-testid="alert-log">
            <thead>
              <tr>
                <th>Time</th>
                <th>Bed</th>
                <th>Level</th>
                <th>HR</th>
                <th>Gesture %</th>
                <th>Source</th>
                <th>Acknowledged</th>
                <th>Response (s)</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.id}>
                  <td>{formatClock(a.received_at)}</td>
                  <td>{a.node}</td>
                  <td><span className={`chip level-bg-${a.level}`}>{a.level}</span></td>
                  <td>{a.hr ?? "—"}</td>
                  <td>{typeof a.gesture_conf === "number" ? Math.round(a.gesture_conf * 100) : "—"}</td>
                  <td className={a.bio_source === "replay" ? "replay-text" : ""}>{a.bio_source ?? "—"}</td>
                  <td>{formatClock(a.ack_received_at)}</td>
                  <td className="response">{typeof a.response_s === "number" ? a.response_s.toFixed(1) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
