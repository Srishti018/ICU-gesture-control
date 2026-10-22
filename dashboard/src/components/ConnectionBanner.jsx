import { WifiOff } from "lucide-react";

export default function ConnectionBanner({ brokerStatus }) {
  if (brokerStatus !== "reconnecting" && brokerStatus !== "offline") return null;
  return (
    <div className="conn-banner" role="status" data-testid="connection-banner">
      <WifiOff size={18} aria-hidden="true" />
      <strong>Live data paused — reconnecting…</strong>
      <span>Values on the tiles are the last ones received.</span>
    </div>
  );
}
