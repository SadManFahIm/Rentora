import { useState } from "react";
import { ScrollText } from "lucide-react";
import { useAuditTrail } from "../../hooks/useAudit";
import { cn } from "../../lib/utils";

const PREFIXES = [
  { value: "", label: "All" },
  { value: "kyc", label: "KYC" },
  { value: "report", label: "Reports" },
  { value: "moderation", label: "Moderation" },
  { value: "dispute", label: "Disputes" },
  { value: "fraud", label: "Fraud" },
] as const;

/** Append-only audit trail — every sensitive admin action with its actor,
 * target and detail. Read-only; entries are never edited or deleted. */
export function AuditTrailTab() {
  const [prefix, setPrefix] = useState("");
  const { data: entries = [], isLoading } = useAuditTrail(prefix || undefined);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <ScrollText className="size-5 text-orange-600" />
        <div>
          <h2 className="font-display text-lg font-bold text-foreground">Audit Trail</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Append-only record of admin actions — KYC, reports, moderation, disputes, fraud.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {PREFIXES.map((p) => (
          <button
            key={p.value}
            type="button"
            onClick={() => setPrefix(p.value)}
            className={cn(
              "rounded-full px-3 py-1 text-xs font-semibold transition-colors",
              prefix === p.value
                ? "bg-orange-600 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
            )}
          >
            {p.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="py-15 text-center text-gray-600 dark:text-gray-400">Loading…</div>
      ) : entries.length === 0 ? (
        <div className="flex flex-col items-center rounded-2xl border border-dashed border-gray-300 px-5 py-15 text-center text-gray-600 dark:border-gray-700 dark:text-gray-400">
          <ScrollText className="mb-4 size-12" />
          <h3 className="mb-2 font-display text-lg font-bold text-foreground">No entries</h3>
          <p>Nothing matches this filter yet.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {entries.map((e) => (
            <div
              key={e.id}
              className="flex flex-col gap-1 rounded-xl border border-gray-200 bg-card p-3 dark:border-gray-800 sm:flex-row sm:items-center"
            >
              <span className="inline-flex w-fit shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-xs font-semibold text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                {e.action}
              </span>
              <span className="text-sm text-gray-600 dark:text-gray-400">
                {e.actorUsername || "system"}
                {e.targetType && (
                  <>
                    {" "}
                    · {e.targetType} #{e.targetId}
                  </>
                )}
              </span>
              <span className="ml-auto shrink-0 text-xs text-gray-500 dark:text-gray-500">
                {new Date(e.createdAt).toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
