import { useEffect, useRef, useState } from "react";
import { Bot, Check, HandCoins, Loader2, Send, ShieldCheck, X } from "lucide-react";
import useNegotiationAgent from "../../hooks/useNegotiationAgent";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import type { NegotiationOffer, NegotiationPayload } from "../../services/negotiationAgentService";
import type { RentalAgentProposal } from "../../services/rentalAgentService";

const EXAMPLES: string[] = [
  "Can I ask for a lower rent on this room?",
  "Draft an offer of ৳9,000 for me",
  "What is a fair counter to their latest offer?",
];

const PROPOSAL_STATUS_LABEL: Record<string, string> = {
  pending: "Awaiting your approval",
  approved: "Approved — preparing to apply",
  applied: "Applied by the agent",
  rejected: "Rejected",
  expired: "Expired",
  failed: "Apply failed",
};

const NEGOTIATION_STATUS_STYLE: Record<string, string> = {
  initiated: "bg-sky-500/10 text-sky-700 dark:text-sky-400",
  active: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  offer_pending: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  counter_offer_pending: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  accepted: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  rejected: "bg-rose-500/10 text-rose-700 dark:text-rose-400",
  expired: "bg-gray-500/10 text-gray-500",
  cancelled: "bg-gray-500/10 text-gray-500",
  closed: "bg-sky-500/10 text-sky-700 dark:text-sky-400",
};

const OFFER_STATUS_LABEL: Record<string, string> = {
  draft: "Draft",
  sent: "Sent",
  accepted: "Accepted",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
  expired: "Expired",
};

/**
 * Phase 19.4 AI Negotiation Agent panel.
 *
 * A participant-facing agent that prepares offers/counters, sets your price
 * boundaries and (with your explicit consent, one proposal at a time) sends
 * offers, accepts a counterpart offer or closes the negotiation. Nothing is
 * ever final without approving a consent card in the chat, and the agent never
 * books or charges — closing hands off to the existing booking flow.
 */
export default function NegotiationPanel({
  roomId,
  className,
}: {
  roomId?: number;
  className?: string;
}) {
  const {
    messages,
    proposals,
    suggestions,
    sending,
    acting,
    error,
    featureEnabled,
    agentName,
    agentDescription,
    lastAction,
    negotiations,
    activeKey,
    negotiation,
    negotiationLoading,
    send,
    reply,
    approve,
    reject,
    reset,
    select,
    withdrawOffer,
    rejectOffer,
    rejectWhole,
    cancelWhole,
  } = useNegotiationAgent(roomId);

  const [input, setInput] = useState("");
  const [showTimeline, setShowTimeline] = useState(false);
  const [justApproved, setJustApproved] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo?.({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, sending, lastAction]);

  const submit = (text: string) => {
    if (!text.trim() || sending || acting) return;
    setInput("");
    setJustApproved(false);
    void send(text);
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

  const canSend = featureEnabled && !sending && !acting;
  const busy = sending || acting;
  const showRail = roomId == null;
  const roomWithNegotiation = negotiation != null;

  return (
    <div className={cn("flex h-full min-h-0 flex-col", className)}>
      <div className="flex items-center justify-between border-b border-gray-100 px-4 py-2 dark:border-gray-800">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 text-sm font-bold text-foreground">
            <HandCoins className="size-4 text-orange-500" />
            {agentName}
          </div>
          <div className="text-[10px] text-gray-500 dark:text-gray-400">{agentDescription}</div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {featureEnabled ? (
            <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">
              live · consent-gated
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
          The negotiation agent isn&apos;t enabled yet — what you see could be cached. Try again
          once the feature flag <code>ai.negotiation_agent</code> is turned on.
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        {showRail && (
          <nav
            aria-label="Your negotiations"
            className="w-52 shrink-0 overflow-y-auto border-r border-gray-100 px-2 py-2 dark:border-gray-800"
          >
            <div className="mb-1 px-2 text-[10px] font-bold uppercase tracking-wide text-gray-400">
              Negotiations
            </div>
            {negotiations.length === 0 && (
              <p className="px-2 text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
                Nothing yet — send a message from a room&apos;s chat to start a negotiation.
              </p>
            )}
            <div className="space-y-1">
              {negotiations.map((row) => (
                <button
                  key={row.key}
                  type="button"
                  onClick={() => void select(row.key)}
                  className={cn(
                    "w-full rounded-xl border px-2.5 py-2 text-left transition",
                    activeKey === row.key
                      ? "border-orange-200 bg-orange-50 dark:border-orange-800 dark:bg-orange-950/30"
                      : "border-gray-100 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/60"
                  )}
                >
                  <div className="truncate text-[11px] font-bold text-foreground">
                    {row.room_title}
                  </div>
                  <div className="mt-0.5 flex items-center gap-1.5 text-[10px] text-gray-500 dark:text-gray-400">
                    <span className="truncate">{row.peer_name || "—"}</span>
                    <span
                      className={cn(
                        "ml-auto shrink-0 rounded-full px-1.5 py-0.5 font-semibold",
                        NEGOTIATION_STATUS_STYLE[row.status] ?? "bg-gray-100 text-gray-500"
                      )}
                    >
                      {row.status.replace("_", " ")}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </nav>
        )}

        <div className="flex min-h-0 flex-1 flex-col">
          {negotiationLoading ? (
            <div className="flex items-center justify-center gap-2 py-10 text-xs text-gray-500">
              <Loader2 className="size-3.5 animate-spin" /> Loading negotiation…
            </div>
          ) : (
            <>
              {roomWithNegotiation && (
                <NegotiationSummary
                  negotiation={negotiation}
                  busy={busy}
                  showTimeline={showTimeline}
                  onToggleTimeline={() => setShowTimeline((v) => !v)}
                  onWithdraw={withdrawOffer}
                  onRejectOffer={rejectOffer}
                  onRejectWhole={rejectWhole}
                  onCancelWhole={cancelWhole}
                  onAskAccept={(offer) =>
                    send(`Please accept the offer of ৳${offer.amount.toLocaleString()}`)
                  }
                />
              )}

              {/* Messages */}
              <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
                {messages.length === 0 && (
                  <div className="rounded-2xl bg-gray-50 p-4 text-sm leading-relaxed text-gray-600 dark:bg-gray-800/60 dark:text-gray-400">
                    {roomWithNegotiation || roomId != null
                      ? "Hi! I'm the Rentora AI Negotiation Agent. I can draft offers and counter-offers, set your price boundaries and walk the conversation to a consent card. Nothing is sent or final until you approve a proposal in this chat — and I never book or charge. Try something like:"
                      : "Hi! I'm the Rentora AI Negotiation Agent. Ask me to draft an offer, counter a landlord's price or set your boundaries — every action lands on an approval card you control. Try something like:"}
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
                    className={cn(
                      "flex flex-col gap-1.5",
                      m.role === "user" ? "items-end" : "items-start"
                    )}
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
                  </div>
                ))}

                {/* Consent: offers / boundaries / sends / accept / finalize */}
                {proposals.length > 0 && (
                  <div className="rounded-2xl border border-amber-200 bg-amber-50/60 p-3 dark:border-amber-900 dark:bg-amber-950/30">
                    <div className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-amber-700 dark:text-amber-400">
                      <ShieldCheck className="size-3.5" />
                      {proposals.length} step{proposals.length > 1 ? "s" : ""} await your approval
                    </div>
                    <div className="space-y-2">
                      {proposals.map((p) => (
                        <ProposalRow key={p.key} p={p} onApprove={onApprove} onReject={onReject} />
                      ))}
                    </div>
                    {justApproved && (
                      <p className="mt-2 text-[10px] leading-relaxed text-gray-500 dark:text-gray-400">
                        Approved! The agent applies it as the manual next step. Track everything in
                        the offers and timeline above.
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
              {suggestions.length > 0 && !busy && (
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
                  placeholder="Negotiate in Bangla or English…"
                  className="h-10 text-sm"
                  aria-label="Message the negotiation agent"
                />
                <Button
                  type="submit"
                  size="icon"
                  className="h-10 w-10 shrink-0 rounded-xl bg-orange-600 text-white hover:bg-orange-700"
                  disabled={!canSend || !input.trim()}
                  aria-label="Send"
                >
                  {sending ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Send className="size-4" />
                  )}
                </Button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function NegotiationSummary({
  negotiation,
  busy,
  showTimeline,
  onToggleTimeline,
  onWithdraw,
  onRejectOffer,
  onRejectWhole,
  onCancelWhole,
  onAskAccept,
}: {
  negotiation: NegotiationPayload;
  busy: boolean;
  showTimeline: boolean;
  onToggleTimeline: () => void;
  onWithdraw: (offerKey: string) => void;
  onRejectOffer: (offerKey: string) => void;
  onRejectWhole: () => void;
  onCancelWhole: () => void;
  onAskAccept: (offer: NegotiationOffer) => void;
}) {
  const room = negotiation.room;
  const price =
    room.price_text || (room.price_bdt != null ? `৳${room.price_bdt.toLocaleString()}` : "—");
  const accepted =
    negotiation.offers.find((o) => o.status === "accepted") ??
    (negotiation.status === "accepted" ? negotiation.offers[0] : null);
  const constraints = negotiation.my_constraints;

  return (
    <div className="border-b border-gray-100 px-4 py-3 dark:border-gray-800">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide",
                NEGOTIATION_STATUS_STYLE[negotiation.status] ?? "bg-gray-100 text-gray-500"
              )}
            >
              {negotiation.status_label}
            </span>
            <span className="truncate text-sm font-bold text-foreground">{room.title}</span>
          </div>
          <div className="mt-0.5 text-[11px] text-gray-500 dark:text-gray-400">
            Listed {price} · you are the <b className="text-foreground">{negotiation.my_role}</b> ·
            counterparty: <b className="text-foreground">{negotiation.peer_name || "—"}</b>
            {negotiation.expires_at && (
              <>
                {" · expires "}
                {new Date(negotiation.expires_at).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                })}
              </>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {negotiation.can_reject && (
            <Button
              size="sm"
              variant="outline"
              className="h-7 px-2 text-[10px] text-rose-600 dark:text-rose-400"
              onClick={onRejectWhole}
              disabled={busy}
            >
              <X className="size-3" />
              Reject negotiation
            </Button>
          )}
          {negotiation.can_cancel && (
            <Button
              size="sm"
              variant="outline"
              className="h-7 px-2 text-[10px]"
              onClick={onCancelWhole}
              disabled={busy}
            >
              Cancel
            </Button>
          )}
          {accepted && (
            <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 dark:text-emerald-400">
              ✓ Agreed: ৳{accepted.amount.toLocaleString()}/mo
            </span>
          )}
        </div>
      </div>

      {constraints && (constraints.min_amount != null || constraints.max_amount != null) && (
        <div className="mt-2 text-[11px] text-gray-600 dark:text-gray-400">
          My price range:{" "}
          <b>
            ৳{constraints.min_amount?.toLocaleString() ?? "—"}–৳
            {constraints.max_amount?.toLocaleString() ?? "—"}
          </b>
          <span className="ml-1 text-gray-400">
            · counterpart{" "}
            {negotiation.peer_constraints_set ? "has set theirs" : "hasn't set theirs"}
          </span>
        </div>
      )}

      {negotiation.offers.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {negotiation.offers.map((offer) => (
            <span
              key={offer.key}
              className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-white py-0.5 pl-2 pr-1 text-[10px] font-medium text-gray-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300"
              title={offer.message}
            >
              <span className="text-gray-400">
                {offer.sender_role === "tenant" ? "You" : offer.sender_name}
              </span>
              <span className="font-bold text-foreground">
                {offer.kind === "counter" ? "counter " : ""}৳{offer.amount.toLocaleString()}
              </span>
              <span
                className={cn(
                  "rounded-full px-1.5 py-px",
                  offer.status === "sent"
                    ? "bg-amber-500/10 text-amber-700 dark:text-amber-400"
                    : offer.status === "accepted"
                      ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                      : offer.status === "rejected"
                        ? "bg-rose-500/10 text-rose-700 dark:text-rose-400"
                        : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400"
                )}
              >
                {OFFER_STATUS_LABEL[offer.status] ?? offer.status}
              </span>
              {offer.can_withdraw && (
                <button
                  type="button"
                  onClick={() => onWithdraw(offer.key)}
                  disabled={busy}
                  className="rounded-full px-1 text-gray-400 transition hover:text-rose-600"
                  aria-label="Withdraw this offer"
                >
                  <X className="size-3" />
                </button>
              )}
              {offer.can_reject && (
                <button
                  type="button"
                  onClick={() => onRejectOffer(offer.key)}
                  disabled={busy}
                  className="rounded-full px-1 text-gray-400 transition hover:text-rose-600"
                  aria-label="Reject this offer"
                >
                  <X className="size-3" />
                </button>
              )}
              {offer.can_accept && (
                <button
                  type="button"
                  onClick={() => onAskAccept(offer)}
                  disabled={busy}
                  className="rounded-full bg-emerald-600 px-1.5 py-px font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-50"
                  aria-label="Ask the agent to accept this offer"
                >
                  <Check className="size-3" />
                </button>
              )}
            </span>
          ))}
        </div>
      )}

      {negotiation.timeline.length > 0 && (
        <button
          type="button"
          onClick={onToggleTimeline}
          className="mt-2 text-[10px] font-semibold text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
        >
          {showTimeline ? "Hide" : "Show"} activity timeline ({negotiation.timeline.length})
        </button>
      )}
      {showTimeline && (
        <ol className="mt-2 space-y-1 border-l border-gray-200 pl-3 dark:border-gray-700">
          {negotiation.timeline.map((event, index) => (
            <li
              key={`${event.event}-${event.created_at}-${index}`}
              className="text-[10px] text-gray-500"
            >
              <span className="font-semibold text-foreground">
                {event.event.replace(/_/g, " ")}
              </span>
              {" · "}
              {event.actor_name || "system"}
              {event.detail?.amount != null && (
                <> − ৳{Number(event.detail.amount).toLocaleString()}</>
              )}
              {event.created_at && new Date(event.created_at).toLocaleString("en-US", {})}
            </li>
          ))}
        </ol>
      )}
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
  const toolLabel = p.tool.replace(/^negotiation\./, "").replace(/_/g, " ");
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-2.5 dark:border-gray-700 dark:bg-gray-900">
      <div className="mb-1 flex items-center gap-2">
        <Bot className="size-3.5 shrink-0 text-gray-400" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[11px] font-bold text-foreground">{toolLabel}</div>
        </div>
      </div>
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
