function averageResponse(byLevel) {
  let total = 0;
  let count = 0;
  for (const level of Object.values(byLevel)) {
    if (level.mean_response_s !== null) {
      total += level.mean_response_s * level.acknowledged;
      count += level.acknowledged;
    }
  }
  return count ? (total / count).toFixed(1) : "—";
}

function Stat({ label, value, cls = "" }) {
  return (
    <div className={`stat ${cls}`}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

export default function StatsStrip({ stats }) {
  if (!stats) return null;
  const { urgent, critical } = stats.by_level;
  return (
    <section className="stats">
      <Stat label="Urgent alerts" value={urgent.count} cls="level-urgent" />
      <Stat label="Critical alerts" value={critical.count} cls="level-critical" />
      <Stat label="Acknowledged" value={urgent.acknowledged + critical.acknowledged} />
      <Stat label="Avg response (s)" value={averageResponse(stats.by_level)} />
      <Stat label="Offline events" value={stats.offline_events} />
    </section>
  );
}
