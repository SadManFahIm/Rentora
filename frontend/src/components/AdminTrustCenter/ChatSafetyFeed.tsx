import { MessageSquareWarning, ShieldCheck } from "lucide-react";
import { useChatSafetyEvents } from "../../hooks/useChat";
import { cn } from "../../lib/utils";

const riskClasses: Record<string, string> = {
  low: "bg-emerald-500/10 text-emerald-500",
  medium: "bg-amber-500/10 text-amber-500",
  high: "bg-red-500/10 text-red-500",
  critical: "bg-red-600/10 text-red-600",
};

const outcomeClasses: Record<string, string> = {
  warned: "bg-amber-500/10 text-amber-500",
  flagged: "bg-red-500/10 text-red-500",
  blocked: "bg-red-600/10 text-red-600",
};

/** Chat Safety feed (Phase 12.3) — the assessments the engine recorded.
 * Metadata only by design: who, which detectors tripped, the risk and what
 * the engine did. Message content is deliberately never exposed here. */
export function ChatSafetyFeed() {
  const { data: events = [], isLoading } = useChatSafetyEvents();

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <MessageSquareWarning className="size-5 text-orange-600" />
        <div>
          <h2 className="font-display text-lg font-bold text-foreground">Chat Safety</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Recent assessments — metadata only, never the conversation text.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="py-15 text-center text-gray-600 dark:text-gray-400">Loading…</div>
      ) : events.length === 0 ? (
        <div className="flex flex-col items-center rounded-2xl border border-dashed border-gray-300 px-5 py-15 text-center text-gray-600 dark:border-gray-700 dark:text-gray-400">
          <ShieldCheck className="mb-4 size-12 text-emerald-500" />
          <h3 className="mb-2 font-display text-lg font-bold text-foreground">
            No safety events yet
          </h3>
          <p>The chat safety engine has nothing to review right now.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-2.5">
          {events.map((e) => (
            <div
              key={e.id}
              className="rounded-2xl border border-gray-200 bg-card p-4 dark:border-gray-800"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={cn(
                    "inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold",
                    riskClasses[e.risk_level]
                  )}
                >
                  {e.risk_level_display} risk
                </span>
                <span
                  className={cn(
                    "inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold",
                    outcomeClasses[e.outcome]
                  )}
                >
                  {e.outcome_display}
                </span>
                <span className="text-sm font-semibold text-foreground">
                  {e.sender_name || e.sender_username}
                </span>
                <span className="ml-auto text-xs text-gray-500 dark:text-gray-500">
                  room #{e.chat_room} · {new Date(e.created_at).toLocaleString()}
                </span>
              </div>
              {e.detectors.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {e.detectors.map((d) => (
                    <span
                      key={d.key}
                      className="inline-flex rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-400"
                    >
                      {d.label}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
