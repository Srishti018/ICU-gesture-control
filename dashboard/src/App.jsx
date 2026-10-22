import { useCallback, useEffect, useMemo, useReducer } from "react";
import AlertBanner from "./components/AlertBanner.jsx";
import AlertLog from "./components/AlertLog.jsx";
import NodeGrid from "./components/NodeGrid.jsx";
import StatsStrip from "./components/StatsStrip.jsx";
import TopBar from "./components/TopBar.jsx";
import { useMqtt } from "./hooks/useMqtt.js";
import { useNow } from "./hooks/useNow.js";
import { usePolling } from "./hooks/usePolling.js";
import { fetchAlerts, fetchHealth, fetchStats } from "./lib/api.js";
import { initialState, nodesReducer } from "./state/nodesReducer.js";

// Give the server a moment to store an alert/ack before we re-fetch history.
const HISTORY_REFRESH_DELAY_MS = 600;

export default function App() {
  const [state, dispatch] = useReducer(nodesReducer, initialState);
  const { status: brokerStatus, publishAck } = useMqtt(dispatch);
  const now = useNow();

  const health = usePolling(fetchHealth, 5000);
  const alerts = usePolling(fetchAlerts, 10000);
  const stats = usePolling(fetchStats, 10000);
  const historyOk = Boolean(health.data?.ok) && !health.error;

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

  // The banner shows only while its alert is still active.
  const event = state.lastAlertEvent;
  const bannerEvent = event && state.nodes[event.node]?.alerts[event.level] ? event : null;
  const dismissBanner = useCallback(() => dispatch({ type: "DISMISS_BANNER" }), []);

  const historyAvailable = historyOk && !alerts.error;

  return (
    <div className="app">
      <TopBar brokerStatus={brokerStatus} historyOk={historyOk} now={now} />
      <AlertBanner event={bannerEvent} onDismiss={dismissBanner} />
      <main>
        {historyOk && !stats.error && <StatsStrip stats={stats.data} />}
        <NodeGrid nodes={state.nodes} now={now} lastAlertEvent={state.lastAlertEvent} onAck={publishAck} />
        <AlertLog alerts={alerts.data} available={historyAvailable} />
      </main>
    </div>
  );
}
