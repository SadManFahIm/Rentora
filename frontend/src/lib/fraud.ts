import type { FraudSeverity } from "../types";

/**
 * Badge text for a flagged listing — the exact string the RoomModal badge
 * renders. Extracted from the component so the risk label is a single,
 * testable source of truth. Low-severity flags show the bare badge
 * (informational); clean listings render nothing (the component gates the
 * badge on ``flagged`` anyway, this just makes the contract explicit).
 */
export function fraudBadgeLabel(severity: FraudSeverity): string {
  if (severity === "high") return "Under review (high risk)";
  if (severity === "medium") return "Under review (medium risk)";
  if (severity === "low") return "Under review";
  return "";
}
