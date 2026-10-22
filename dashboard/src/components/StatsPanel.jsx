import { formatSeconds } from "../lib/format.js";
import { levelMeta } from "../lib/levels.js";
import ResponseChart from "./ResponseChart.jsx";

export default function StatsPanel({ stats, alerts, available }) {
  if (!available || !stats) {
    return (
      <p className="panel-empty" data-testid="stats-unavailable">
        Statistics unavailable — the server isn't reachable. Live tiles keep working.
      </p>
    );
  }
  const levels = ["critical", "urgent"];
  const totalAck = levels.reduce((n, l) => n + stats.by_level[l].acknowledged, 0);
  return (
    <div className="stats" data-testid="stats-panel">
      <div className="stat-tiles">
        <div className="stat">
          <span className="stat-value num">{stats.total_alerts}</span>
          <span className="label">Alerts</span>
        </div>
        <div className="stat">
          <span className="stat-value num">{totalAck}</span>
          <span className="label">Acknowledged</span>
        </div>
        <div className="stat">
          <span className="stat-value num">{stats.open_alerts}</span>
          <span className="label">Open</span>
        </div>
        <div className="stat">
          <span className="stat-value num">{stats.offline_events}</span>
          <span className="label">Offline events</span>
        </div>
      </div>

      <table className="stat-table">
        <caption className="label">Response time by level</caption>
        <thead>
          <tr>
            <th scope="col">Level</th>
            <th scope="col">Alerts</th>
            <th scope="col">Acked</th>
            <th scope="col">Mean</th>
            <th scope="col">Max</th>
          </tr>
        </thead>
        <tbody>
          {levels.map((l) => {
            const s = stats.by_level[l];
            const { label, Icon } = levelMeta(l);
            return (
              <tr key={l}>
                <th scope="row" className={`lvl lvl-${l}`}>
                  <Icon size={14} aria-hidden="true" /> {label}
                </th>
                <td className="num">{s.count}</td>
                <td className="num">{s.acknowledged}</td>
                <td className="num">{formatSeconds(s.mean_response_s)}</td>
                <td className="num">{formatSeconds(s.max_response_s)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <ResponseChart alerts={alerts} />
    </div>
  );
}
