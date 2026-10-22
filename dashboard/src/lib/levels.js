import { AlertOctagon, AlertTriangle, CheckCircle2, WifiOff } from "lucide-react";

/** Word + icon for every severity, so colour is never the only signal. */
export const LEVEL_META = {
  routine: { label: "Routine", word: "ROUTINE", Icon: CheckCircle2 },
  urgent: { label: "Urgent", word: "URGENT", Icon: AlertTriangle },
  critical: { label: "Critical", word: "CRITICAL", Icon: AlertOctagon },
  offline: { label: "Offline", word: "OFFLINE", Icon: WifiOff },
};

export const levelMeta = (level) => LEVEL_META[level] ?? LEVEL_META.routine;
