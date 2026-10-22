export default function AlertBanner({ event, onDismiss }) {
  if (!event) return null;
  return (
    <div className={`banner level-bg-${event.level}`} role="alert">
      <span>
        {event.level.toUpperCase()} — {event.node}
      </span>
      <button className="banner-close" onClick={onDismiss} aria-label="Dismiss">
        ×
      </button>
    </div>
  );
}
