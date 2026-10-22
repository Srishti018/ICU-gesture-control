import { HeartPulse, Moon, Repeat, Sun, Volume2, VolumeX } from "lucide-react";

const BROKER = {
  connected: { tone: "ok", text: "Live" },
  connecting: { tone: "warn", text: "Connecting…" },
  reconnecting: { tone: "bad", text: "Reconnecting…" },
  offline: { tone: "bad", text: "Disconnected" },
};

function StatusItem({ label, tone, text, testId }) {
  return (
    <span className={`status-item tone-${tone}`} data-testid={testId}>
      <span className="status-dot" aria-hidden="true" />
      <span className="status-label">{label}</span>
      <span className="status-text">{text}</span>
    </span>
  );
}

const pad = (n) => String(n).padStart(2, "0");

export default function TopBar({ brokerStatus, serverOk, replayActive, now, theme, onToggleTheme, sound, onToggleSound, onShowAbout }) {
  const broker = BROKER[brokerStatus] ?? BROKER.offline;
  const d = new Date(now);
  return (
    <header className="topbar">
      <div className="brand">
        <HeartPulse className="brand-icon" size={24} aria-hidden="true" />
        <div>
          <div className="brand-name">ICU Fusion</div>
          <div className="brand-ward">ICU · Demo ward</div>
        </div>
      </div>

      <div className="topbar-status">
        <StatusItem label="Broker" tone={broker.tone} text={broker.text} testId="broker-status" />
        <StatusItem
          label="Server"
          tone={serverOk ? "ok" : "bad"}
          text={serverOk ? "OK" : "Unreachable"}
          testId="server-status"
        />
        {replayActive && (
          <button type="button" className="replay-chip" data-testid="replay-chip" onClick={onShowAbout}>
            <Repeat size={14} aria-hidden="true" />
            Biosignals replayed
          </button>
        )}
      </div>

      <div className="topbar-tools">
        <time className="clock" dateTime={d.toISOString()} aria-label="Current time">
          {pad(d.getHours())}:{pad(d.getMinutes())}:{pad(d.getSeconds())}
        </time>
        <button
          type="button"
          className="icon-btn"
          data-testid="sound-toggle"
          aria-pressed={sound}
          aria-label="Alert sound"
          onClick={onToggleSound}
          title={sound ? "Alert sound on" : "Alert sound off"}
        >
          {sound ? <Volume2 size={18} aria-hidden="true" /> : <VolumeX size={18} aria-hidden="true" />}
          <span>{sound ? "Sound on" : "Enable sound"}</span>
        </button>
        <button
          type="button"
          className="icon-btn"
          data-testid="theme-toggle"
          onClick={onToggleTheme}
          aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          title={theme === "dark" ? "Light theme (projector)" : "Dark theme"}
        >
          {theme === "dark" ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
          <span>{theme === "dark" ? "Light" : "Dark"}</span>
        </button>
      </div>
    </header>
  );
}
