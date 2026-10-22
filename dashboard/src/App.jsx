import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import AboutPanel from "./components/AboutPanel.jsx";
import ActivityFeed from "./components/ActivityFeed.jsx";
import AlertStrip from "./components/AlertStrip.jsx";
import BedTile from "./components/BedTile.jsx";
import ConnectionBanner from "./components/ConnectionBanner.jsx";
import EmptyState from "./components/EmptyState.jsx";
import HistorySection from "./components/HistorySection.jsx";
import SidePanel from "./components/SidePanel.jsx";
import StatsPanel from "./components/StatsPanel.jsx";
import TopBar from "./components/TopBar.jsx";
import { useMqtt } from "./hooks/useMqtt.js";
import { useNow } from "./hooks/useNow.js";
import { usePolling } from "./hooks/usePolling.js";
import { useTheme } from "./hooks/useTheme.js";
import { fetchAlerts, fetchHealth, fetchStats } from "./lib/api.js";
import { bedName } from "./lib/format.js";
import { levelMeta } from "./lib/levels.js";
import { sortAlerts, sortBySeverity } from "./lib/severity.js";
import { playAlertTone, unlockSound } from "./lib/sound.js";
import { activeAlert, alertSince, initialState, nodesReducer } from "./state/nodesReducer.js";

// Give the server a moment to store an alert/ack before we re-fetch history.
const HISTORY_REFRESH_DELAY_MS = 600;
const HISTORY_LIMIT = 200;

const fetchHistory = () => fetchAlerts(HISTORY_LIMIT);

function announcement(e) {
  if (!e) return "";
  const bed = bedName(e.node);
  if (e.kind === "alert") return `${levelMeta(e.level).label} alert: ${bed}`;
  if (e.kind === "ack") return `${bed} ${e.level} alert acknowledged`;
  if (e.kind === "offline") return `${bed} went offline`;
  return "";
}

export default function App() {
  const [state, dispatch] = useReducer(nodesReducer, initialState);
  const { status: brokerStatus, publishAck } = useMqtt(dispatch);
  const now = useNow();
  const { theme, toggle: toggleTheme } = useTheme();
  const [tab, setTab] = useState("activity");
  const [sound, setSound] = useState(false);

  const health = usePolling(fetchHealth, 5000);
  const alerts = usePolling(fetchHistory, 10000);
  const stats = usePolling(fetchStats, 10000);
  const serverOk = Boolean(health.data?.ok) && !health.error;

  useEffect(() => dispatch({ type: "TICK", now }), [now]);

  // Refresh history immediately when a new alert arrives or any alert clears.
  const alertKey = useMemo(
    () =>
      Object.values(state.nodes)
        .map((n) => `${n.id}:${n.alerts.urgent ? 1 : 0}${n.alerts.critical ? 1 : 0}`)
        .join(","),
    [state.nodes],
  );
  const refreshAlerts = alerts.refresh;
  const refreshStats = stats.refresh;
  useEffect(() => {
    const id = setTimeout(() => {
      refreshAlerts();
      refreshStats();
    }, HISTORY_REFRESH_DELAY_MS);
    return () => clearTimeout(id);
  }, [state.lastAlertEvent, alertKey, refreshAlerts, refreshStats]);

  // One tone per new live alert, only when the nurse has enabled sound.
  const latest = state.events[0];
  const lastToneId = useRef(0);
  useEffect(() => {
    if (!latest || latest.kind !== "alert" || latest.id <= lastToneId.current) return;
    lastToneId.current = latest.id;
    if (sound) playAlertTone(latest.level);
  }, [latest, sound]);

  const toggleSound = useCallback(() => {
    setSound((on) => (on ? false : unlockSound()));
  }, []);

  const nodes = sortBySeverity(Object.values(state.nodes));
  const alertRows = sortAlerts(
    nodes.filter((n) => activeAlert(n)).map((n) => ({ node: n, alert: activeAlert(n), since: alertSince(n, now) })),
  );
  const replayActive = nodes.some((n) => n.online !== false && n.status?.bio_source === "replay");
  const historyAvailable = serverOk && !alerts.error;
  const paused = brokerStatus === "reconnecting" || brokerStatus === "offline";

  return (
    <div className="app">
      <a className="skip-link" href="#beds">
        Skip to beds
      </a>
      <TopBar
        brokerStatus={brokerStatus}
        serverOk={serverOk}
        replayActive={replayActive}
        now={now}
        theme={theme}
        onToggleTheme={toggleTheme}
        sound={sound}
        onToggleSound={toggleSound}
        onShowAbout={() => setTab("about")}
      />
      <ConnectionBanner brokerStatus={brokerStatus} />
      <AlertStrip rows={alertRows} now={now} onAck={publishAck} />

      <div className="sr-only" aria-live="assertive" aria-atomic="true" data-testid="live-region">
        {announcement(latest)}
      </div>

      <div className="layout">
        <main id="beds" className="beds" aria-label="Beds">
          {nodes.length === 0 ? (
            <EmptyState />
          ) : (
            <div className="bed-grid">
              {nodes.map((n) => (
                <BedTile key={n.id} node={n} now={now} alerts={alerts.data} paused={paused} onAck={publishAck} />
              ))}
            </div>
          )}
        </main>

        <SidePanel tab={tab} onTab={setTab}>
          {tab === "activity" && <ActivityFeed events={state.events} alerts={alerts.data} now={now} />}
          {tab === "stats" && <StatsPanel stats={stats.data} alerts={alerts.data} available={serverOk && !stats.error} />}
          {tab === "about" && <AboutPanel />}
        </SidePanel>
      </div>

      <HistorySection alerts={alerts.data} available={historyAvailable} now={now} />
    </div>
  );
}
