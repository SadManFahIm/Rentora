import { useEffect, useRef, useState } from "react";
import { Bot, Check, Loader2, Send, ShieldCheck, X } from "lucide-react";
import useRentalAgent from "../../hooks/useRentalAgent";
import type { Room } from "../../types";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import RoomModal from "../RoomModal/RoomModal";
import type { RentalAgentCard, RentalAgentProposal } from "../../services/rentalAgentService";

const EXAMPLES: string[] = [
  "Uttara-তে ১০ হাজারের মধ্যে room",
  "furnished studio in Dhanmondi",
  "AC single room, Mirpur",
];

const PROPOSAL_STATUS_LABEL: Record<string, string> = {
  pending: "Awaiting your approval",
  approved: "Approved — preparing to apply",
  applied: "Applied by the agent",
  rejected: "Rejected",
  expired: "Expired",
  failed: "Apply failed",
};

/**
 * Phase 19.2 AI Rental Agent chat panel.
 *
 * A grounded, tenant-facing agent: search, room details, commute estimates,
 * price comparisons and bookmark requests — every room card is backend Ground
 * Truth (never invented). Bookmarking is a manual consent step: "approve" here
 * is the honest UI for self-granting via token holding (between the two
 * asynchronous apply stages), mirrored by the Alternative service channel.
 */
export default function RentalAgentPanel() {
  const {
    messages,
    proposals,
    suggestions,
    sending,
    error,
    featureEnabled,
    agentName,
    agentDescription,
    lastAction,
    send,
    reply,
    approve,
    reject,
    openRoom,
    reset,
  } = useRentalAgent();

  const [input, setInput] = useState("");
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);
  const [loadingRoomId, setLoadingRoomId] = useState<number | null>(null);
  const [justApproved, setJustApproved] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to the newest message.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending, lastAction]);

  const submit = (text: string) => {
    if (!text.trim() || sending) return;
    setInput("");
    setJustApproved(false);
    void send(text);
  };

  const viewRoom = async (id: number) => {
    setLoadingRoomId(id);
    try {
      setSelectedRoom(await openRoom(id));
    } finally {
      setLoadingRoomId(null);
    }
  };

  const onApprove = async (key: string) => {
    try {
      await approve(key);
      setJustApproved(true);
    } catch {
      setJustApproved(false);
    }
  };

  const onReject = async (key: string) => {
    try {
      await reject(key);
      setJustApproved(false);
    } catch {
      setJustApproved(false);
    }
  };

  const canSend = featureEnabled && !sending;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between border-b border-gray-100 px-4 py-2 dark:border-gray-800">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 text-sm font-bold text-foreground">
            <Bot className="size-4 text-orange-500" />
            {agentName}
          </div>
          <div className="text-[10px] text-gray-500 dark:text-gray-400">{agentDescription}</div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {featureEnabled ? (
            <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">
              live · grounded
            </span>
          ) : (
            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold text-amber-600 dark:text-amber-400">
              feature off
            </span>
          )}
          <button
            type="button"
            onClick={() => void reset()}
            className="rounded-lg px-2 py-1 text-[10px] font-semibold text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800"
          >
            New chat
          </button>
        </div>
      </div>

      {!featureEnabled && (
        <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-[11px] leading-relaxed text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
          The rental agent isn&apos;t enabled yet — what you see could be cached. Try again once the
          feature flag <code>ai.rental_agent</code> is turned on.
        </div>
      )}

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {messages.length === 0 && (
          <div className="rounded-2xl bg-gray-50 p-4 text-sm leading-relaxed text-gray-600 dark:bg-gray-800/60 dark:text-gray-400">
            Hi! I&apos;m the Rentora AI Rental Agent. I can search rooms across Dhaka, show area
            rent trends, estimate commutes and even bookmark a room for you — always grounded in
            real listings. Try something like:
            <div className="mt-2 flex flex-wrap gap-1.5">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => submit(example)}
                  className="rounded-full border border-orange-300 bg-orange-50 px-2.5 py-1 text-xs font-medium text-orange-700 hover:bg-orange-100 dark:border-orange-800 dark:bg-orange-950/40 dark:text-orange-300"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => (
          <div
            key={m.id}
            className={cn("flex flex-col gap-1.5", m.role === "user" ? "items-end" : "items-start")}
          >
            <div
              className={cn(
                "max-w-[85%] whitespace-pre-line rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
                m.role === "user"
                  ? "rounded-br-md bg-orange-600 text-white"
                  : "rounded-bl-md bg-gray-100 text-foreground dark:bg-gray-800"
              )}
            >
              {m.content}
            </div>

            {/* Grounded room cards */}
            {m.role === "assistant" && m.cards && m.cards.length > 0 && (
              <div className="flex w-full max-w-[85%] flex-col gap-2">
                {m.cards.map((card) => (
                  <RoomCard
                    key={card.id}
                    card={card}
                    onView={() => void viewRoom(card.id)}
                    viewLoading={loadingRoomId === card.id}
                  />
                ))}
                <Button
                  size="sm"
                  className="h-8 text-xs"
                  onClick={() => window.open("/rooms", "_blank")}
                >
                  View all on Rooms page →
                </Button>
              </div>
            )}
          </div>
        ))}

        {/* Consent: bookmarking is a manual step */}
        {proposals.length > 0 && (
          <div className="rounded-2xl border border-amber-200 bg-amber-50/60 p-3 dark:border-amber-900 dark:bg-amber-950/30">
            <div className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-amber-700 dark:text-amber-400">
              <ShieldCheck className="size-3.5" />
              {proposals.length} bookmark{proposals.length > 1 ? "s" : ""} await approval
            </div>
            <div className="space-y-2">
              {proposals.map((p) => (
                <ProposalRow key={p.key} p={p} onApprove={onApprove} onReject={onReject} />
              ))}
            </div>
            {justApproved && (
              <p className="mt-2 text-[10px] leading-relaxed text-gray-500 dark:text-gray-400">
                Approved! Bookmarking runs as a manual step — applied by the agent via the token
                channel. Check your Wishlist.
              </p>
            )}
          </div>
        )}

        {error && (
          <div className="rounded-2xl bg-rose-50 px-3.5 py-2.5 text-xs leading-relaxed text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
            {error}
          </div>
        )}

        {sending && (
          <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
            <Loader2 className="size-3.5 animate-spin" />
            {lastAction || "Agent is thinking…"}
          </div>
        )}
      </div>

      {/* Suggestion chips */}
      {suggestions.length > 0 && !sending && (
        <div className="flex max-w-full flex-wrap gap-1 border-t border-gray-100 px-4 pb-2 pt-2 dark:border-gray-800">
          {suggestions.map((s) => (
            <button
              key={s.label}
              type="button"
              onClick={() => reply(s.text)}
              className="rounded-full border border-gray-200 bg-white px-2.5 py-1 text-[11px] font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800"
            >
              {s.label}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <form
        className="flex items-center gap-2 border-t border-gray-100 px-3 py-3 dark:border-gray-800"
        onSubmit={(e) => {
          e.preventDefault();
          submit(input);
        }}
      >
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask in Bangla or English…"
          className="h-10 text-sm"
          aria-label="Message the rental agent"
        />
        <Button
          type="submit"
          size="icon"
          className="h-10 w-10 shrink-0 rounded-xl bg-orange-600 text-white hover:bg-orange-700"
          disabled={!canSend || !input.trim()}
          aria-label="Send"
        >
          {sending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
        </Button>
      </form>

      {selectedRoom && <RoomModal room={selectedRoom} onClose={() => setSelectedRoom(null)} />}
    </div>
  );
}

function RoomCard({
  card,
  onView,
  viewLoading,
}: {
  card: RentalAgentCard;
  onView: () => void;
  viewLoading: boolean;
}) {
  const price =
    card.price_text || (card.price_bdt != null ? `৳${card.price_bdt.toLocaleString()}` : "—");
  return (
    <div className="flex items-center gap-2.5 rounded-xl border border-gray-200 bg-white p-2.5 dark:border-gray-700 dark:bg-gray-900">
      {card.image ? (
        <img
          src={card.image}
          alt={card.title}
          className="h-12 w-16 shrink-0 rounded-lg object-cover"
        />
      ) : (
        <div className="flex h-12 w-16 shrink-0 items-center justify-center rounded-lg bg-gray-100 text-gray-400 dark:bg-gray-800">
          <Bot className="size-4" />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs font-bold text-foreground">{card.title}</div>
        <div className="text-[11px] text-gray-600 dark:text-gray-400">
          {card.area_display} · {price}/mo
          {card.featured && <span className="ml-1 text-orange-600">★ featured</span>}
          {card.verified && (
            <span className="ml-1 text-emerald-600 dark:text-emerald-400">✓ verified</span>
          )}
        </div>
        {card.amenities.length > 0 && (
          <div className="mt-0.5 truncate text-[10px] text-gray-400">
            {card.amenities.join(" · ")}
          </div>
        )}
      </div>
      <Button
        size="sm"
        variant="outline"
        className="h-7 shrink-0 px-2 text-[11px]"
        onClick={onView}
        disabled={viewLoading}
      >
        {viewLoading ? <Loader2 className="size-3 animate-spin" /> : "View"}
      </Button>
    </div>
  );
}

function ProposalRow({
  p,
  onApprove,
  onReject,
}: {
  p: RentalAgentProposal;
  onApprove: (key: string) => Promise<void>;
  onReject: (key: string) => Promise<void>;
}) {
  const pending = p.status === "pending";
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-2.5 dark:border-gray-700 dark:bg-gray-900">
      {p.room && (
        <div className="mb-1.5 flex items-center gap-2">
          {p.room.image ? (
            <img
              src={p.room.image}
              alt={p.room.title}
              className="h-10 w-14 shrink-0 rounded-lg object-cover"
            />
          ) : (
            <div className="flex h-10 w-14 shrink-0 items-center justify-center rounded-lg bg-gray-100 text-gray-400 dark:bg-gray-800">
              <Bot className="size-4" />
            </div>
          )}
          <div className="min-w-0 flex-1">
            <div className="truncate text-[11px] font-bold text-foreground">{p.room.title}</div>
            <div className="text-[10px] text-gray-500">
              {p.room.area_display} · {p.room.price_text}
            </div>
          </div>
        </div>
      )}
      {p.summary && (
        <p className="text-[11px] leading-relaxed text-gray-600 dark:text-gray-400">{p.summary}</p>
      )}
      <div className="mt-1.5 flex items-center justify-between gap-2">
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[10px] font-semibold",
            pending
              ? "bg-amber-500/10 text-amber-700 dark:text-amber-400"
              : p.status === "applied"
                ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400"
          )}
        >
          {PROPOSAL_STATUS_LABEL[p.status] ?? p.status}
        </span>
        {pending && (
          <div className="flex shrink-0 gap-1.5">
            <Button
              size="sm"
              variant="outline"
              className="h-6 px-2 text-[10px] text-rose-600 dark:text-rose-400"
              onClick={() => void onReject(p.key)}
            >
              <X className="size-3" />
              Reject
            </Button>
            <Button
              size="sm"
              className="h-6 px-2 text-[10px] bg-emerald-600 hover:bg-emerald-700"
              onClick={() => void onApprove(p.key)}
            >
              <Check className="size-3" />
              Approve
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
