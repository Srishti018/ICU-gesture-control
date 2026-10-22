import { bedName } from "../lib/format.js";
import { ackUnconfirmed } from "../state/nodesReducer.js";

/** Acknowledge -> Acknowledging… -> (cleared by the server) or Not confirmed + Retry. */
export default function AckControl({ node, alert, now, onAck, compact = false }) {
  const unconfirmed = ackUnconfirmed(node, now);
  const pending = node.ackPendingSince !== null && !unconfirmed;
  const name = bedName(node.id);
  return (
    <div className={`ack ${compact ? "ack-compact" : ""}`}>
      <button
        type="button"
        className={`ack-btn sev-${alert.level}`}
        data-testid={compact ? `strip-ack-${node.id}` : "ack-button"}
        disabled={pending}
        aria-label={`${pending ? "Acknowledging" : unconfirmed ? "Retry acknowledge" : "Acknowledge"} ${alert.level} alert, ${name}`}
        onClick={() => onAck(node.id, alert)}
      >
        {pending ? "Acknowledging…" : unconfirmed ? "Retry" : "Acknowledge"}
      </button>
      {unconfirmed && (
        <span className="ack-warning" role="status" data-testid={compact ? undefined : "ack-unconfirmed"}>
          Not confirmed — is the server running?
        </span>
      )}
    </div>
  );
}
