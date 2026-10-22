import NodeCard from "./NodeCard.jsx";

export default function NodeGrid({ nodes, now, lastAlertEvent, onAck }) {
  const list = Object.values(nodes).sort((a, b) => a.id.localeCompare(b.id));
  if (list.length === 0) return <div className="empty">Waiting for nodes…</div>;
  return (
    <section className="grid">
      {list.map((n) => (
        <NodeCard key={n.id} node={n} now={now} lastAlertEvent={lastAlertEvent} onAck={onAck} />
      ))}
    </section>
  );
}
