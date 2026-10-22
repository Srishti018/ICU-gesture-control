import { Activity, BarChart3, Info } from "lucide-react";
import { useRef } from "react";

const TABS = [
  { id: "activity", label: "Activity", Icon: Activity },
  { id: "stats", label: "Statistics", Icon: BarChart3 },
  { id: "about", label: "Legend / About", Icon: Info },
];

export default function SidePanel({ tab, onTab, children }) {
  const refs = useRef({});
  const onKey = (e) => {
    const i = TABS.findIndex((t) => t.id === tab);
    const delta = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    const next = TABS[(i + delta + TABS.length) % TABS.length].id;
    onTab(next);
    refs.current[next]?.focus();
  };
  return (
    <aside className="side" aria-label="Activity, statistics and legend">
      <div className="tabs" role="tablist" onKeyDown={onKey}>
        {TABS.map(({ id, label, Icon }) => (
          <button
            key={id}
            ref={(el) => (refs.current[id] = el)}
            type="button"
            role="tab"
            id={`tab-${id}`}
            aria-selected={tab === id}
            aria-controls={`tabpanel-${id}`}
            tabIndex={tab === id ? 0 : -1}
            className="tab"
            data-testid={`tab-${id}`}
            onClick={() => onTab(id)}
          >
            <Icon size={16} aria-hidden="true" />
            {label}
          </button>
        ))}
      </div>
      <div className="tabpanel" role="tabpanel" id={`tabpanel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {children}
      </div>
    </aside>
  );
}
