import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Bot, Loader2, MessageSquare, Send, Sparkles, Volume2, VolumeX, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useCopilot } from "../../hooks/useCopilot";
import { useSpeechOutput } from "../../hooks/useSpeechOutput";
import roomService from "../../services/roomService";
import { useCopilotStore } from "../../stores/copilotStore";
import AiToolsPanel from "../AiToolsPanel/AiToolsPanel";
import { cn } from "../../lib/utils";
import type { Room } from "../../types";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import RoomModal from "../RoomModal/RoomModal";

/**
 * Rentora Copilot — floating conversational room discovery.
 *
 * Opens a chat panel (mobile responsive, bottom-right). Every listing shown
 * comes straight from the backend's search engine; "View" opens the full
 * RoomModal for that listing, and the suggestion chips are quick replies
 * the backend generated from the current intent.
 */
export default function CopilotWidget() {
  const { messages, isSending, isOpen, setIsOpen, send, reset, listingMode, openWithListing } =
    useCopilot();
  const listingContext = useCopilotStore((s) => s.listingContext);
  const aiToolRequest = useCopilotStore((s) => s.aiToolRequest);
  const consumeAiTool = useCopilotStore((s) => s.consumeAiTool);
  const [input, setInput] = useState("");
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);
  const [loadingRoom, setLoadingRoom] = useState<number | null>(null);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [initialTool, setInitialTool] = useState<string | undefined>(undefined);
  const scrollRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { t } = useTranslation();
  // Phase 15 — B3 Copilot voice: reads the last assistant reply aloud in the
  // UI language. Browser TTS only — nothing is recorded or uploaded.
  const {
    supported: ttsSupported,
    status: ttsStatus,
    speak,
    stop,
  } = useSpeechOutput(t("copilot.ttsLang"));
  const [speakingId, setSpeakingId] = useState<string | null>(null);

  // Auto-scroll to the newest message.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, isSending]);

  // Stop any in-flight speech when the widget closes or the tools panel opens.
  useEffect(() => {
    if (!isOpen || toolsOpen) {
      stop();
      setSpeakingId(null);
    }
  }, [isOpen, toolsOpen, stop]);

  // Tier 3 listing mode: when a page asks the Copilot to talk about a
  // listing, open the widget and seed the grounded listing conversation.
  useEffect(() => {
    if (listingContext) {
      openWithListing(listingContext);
    }
  }, [listingContext, openWithListing]);

  // Tier 4 one-shot AI-tool request: open the widget directly on the tools
  // panel with the requested tab (e.g. RoomModal's "Draft negotiation").
  useEffect(() => {
    if (aiToolRequest) {
      setInitialTool(aiToolRequest);
      setIsOpen(true);
      setToolsOpen(true);
      reset();
      consumeAiTool();
    }
  }, [aiToolRequest, setIsOpen, reset, consumeAiTool]);

  const submit = (text: string) => {
    if (!text.trim() || isSending) return;
    setInput("");
    void send(text);
  };

  const openRoom = async (id: number) => {
    setLoadingRoom(id);
    try {
      const room = await roomService.getRoomById(id);
      setSelectedRoom(room);
    } catch {
      navigate(`/rooms?q=${encodeURIComponent(String(id))}`);
    } finally {
      setLoadingRoom(null);
    }
  };

  // Phase 15 — B3: toggle reading a Copilot reply aloud (browser TTS).
  const speakMessage = (id: string, text: string) => {
    if (speakingId === id) {
      stop();
      setSpeakingId(null);
      return;
    }
    if (!ttsSupported) return;
    setSpeakingId(id);
    speak(text);
  };

  // Clear the highlight once speech finishes (the hook returns to "idle").
  useEffect(() => {
    if (ttsStatus === "idle" && speakingId !== null) setSpeakingId(null);
  }, [ttsStatus, speakingId]);

  return (
    <>
      {/* Floating trigger button */}
      <button
        type="button"
        aria-label={isOpen ? t("copilot.close") : t("copilot.open")}
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full shadow-lg transition-all",
          isOpen
            ? "bg-gray-800 text-white hover:bg-gray-700 dark:bg-gray-700 dark:hover:bg-gray-600"
            : "bg-gradient-to-br from-orange-500 to-amber-500 text-white hover:scale-105"
        )}
      >
        {isOpen ? <X className="size-6" /> : <Bot className="size-7" />}
      </button>

      {isOpen && (
        <div className="fixed bottom-24 right-6 z-50 flex h-[min(560px,calc(100dvh-7rem))] w-[min(380px,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-gray-700 dark:bg-gray-900">
          {/* Header */}
          <div className="flex items-center gap-2.5 border-b border-gray-100 bg-gradient-to-r from-orange-500/10 to-amber-500/10 px-4 py-3 dark:border-gray-800">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-orange-500 to-amber-500 text-white">
              <Sparkles className="size-4" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="font-display text-sm font-bold text-foreground">
                {t("copilot.title")}
              </div>
              <div className="text-[11px] text-gray-600 dark:text-gray-400">
                {listingMode ? t("copilot.listingMode") : t("copilot.subtitle")}
              </div>
            </div>
            {messages.length > 0 && (
              <button
                type="button"
                onClick={reset}
                className="rounded-lg px-2 py-1 text-[11px] font-semibold text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800"
              >
                New chat
              </button>
            )}
          </div>

          {/* Tier-4 AI tools toggle */}
          <div className="flex items-center gap-1 border-b border-gray-100 px-3 py-1.5 dark:border-gray-800">
            <button
              type="button"
              onClick={() => {
                setToolsOpen((v) => !v);
                if (!toolsOpen) reset();
              }}
              className={cn(
                "inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-semibold transition",
                toolsOpen
                  ? "bg-orange-500/10 text-orange-600 dark:text-orange-400"
                  : "text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
              )}
            >
              <Sparkles className="size-3" />
              AI Tools
            </button>
            <span className="text-[10px] text-gray-400">
              advisor · agreement · negotiation · support
            </span>
          </div>

          {toolsOpen ? (
            <div className="min-h-0 flex-1">
              <AiToolsPanel
                key={initialTool ?? "tools"}
                listingId={listingMode ? listingContext?.id : undefined}
                listingPrice={listingContext?.price}
                initialTool={
                  (initialTool as "advisor" | "agreement" | "negotiate" | "support") ?? "advisor"
                }
              />
            </div>
          ) : (
            /* Messages */
            <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
              {messages.length === 0 && (
                <div className="rounded-2xl bg-gray-50 p-4 text-sm leading-relaxed text-gray-600 dark:bg-gray-800/60 dark:text-gray-400">
                  Hi! 👋 Try something like:
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {[
                      "Uttara-তে ১০ হাজারের মধ্যে room",
                      "furnished studio in Dhanmondi",
                      "AC single room, Mirpur",
                    ].map((example) => (
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
                    {m.text}
                  </div>

                  {/* Phase 15 — B3: read the reply aloud (browser TTS). */}
                  {m.role === "assistant" && (
                    <button
                      type="button"
                      onClick={() => speakMessage(m.id, m.text)}
                      disabled={!ttsSupported}
                      aria-label={
                        speakingId === m.id ? t("copilot.stopSpeaking") : t("copilot.speak")
                      }
                      title={speakingId === m.id ? t("copilot.stopSpeaking") : t("copilot.speak")}
                      className="flex items-center gap-1 rounded-full border border-gray-200 bg-white px-2 py-0.5 text-[10px] font-semibold text-gray-500 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400 dark:hover:bg-gray-800"
                    >
                      {speakingId === m.id ? (
                        <VolumeX className="size-3" />
                      ) : (
                        <Volume2 className="size-3" />
                      )}
                      {speakingId === m.id ? t("copilot.stopSpeaking") : t("copilot.speak")}
                    </button>
                  )}

                  {/* Intent chips ("what AI understood") */}
                  {m.role === "assistant" && m.intent && m.intent.hints.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {m.intent.hints.map((hint) => (
                        <span
                          key={hint}
                          className="rounded-full border border-orange-200 bg-orange-50 px-2 py-0.5 text-[10px] font-semibold text-orange-600 dark:border-orange-800/60 dark:bg-orange-950/30 dark:text-orange-400"
                        >
                          {hint}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Retrieved listing cards */}
                  {m.role === "assistant" && m.listings && m.listings.length > 0 && (
                    <div className="flex w-full max-w-[85%] flex-col gap-2">
                      {m.listings.map((l) => (
                        <div
                          key={l.id}
                          className="flex items-center gap-2.5 rounded-xl border border-gray-200 bg-white p-2.5 dark:border-gray-700 dark:bg-gray-900"
                        >
                          {l.image ? (
                            <img
                              src={l.image}
                              alt={l.title}
                              className="h-12 w-16 shrink-0 rounded-lg object-cover"
                            />
                          ) : (
                            <div className="flex h-12 w-16 shrink-0 items-center justify-center rounded-lg bg-gray-100 text-gray-400 dark:bg-gray-800">
                              <MessageSquare className="size-4" />
                            </div>
                          )}
                          <div className="min-w-0 flex-1">
                            <div className="truncate text-xs font-bold text-foreground">
                              {l.title}
                            </div>
                            <div className="text-[11px] text-gray-600 dark:text-gray-400">
                              {l.area} · ৳{l.price.toLocaleString()}/mo
                              {l.verified && (
                                <span className="ml-1 text-emerald-600 dark:text-emerald-400">
                                  ✓ verified
                                </span>
                              )}
                            </div>
                          </div>
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 px-2 text-[11px]"
                            onClick={() => void openRoom(l.id)}
                            disabled={loadingRoom === l.id}
                          >
                            {loadingRoom === l.id ? (
                              <Loader2 className="size-3 animate-spin" />
                            ) : (
                              "View"
                            )}
                          </Button>
                        </div>
                      ))}
                      <Button
                        size="sm"
                        className="h-8 text-xs"
                        onClick={() =>
                          navigate(
                            m.intent?.areas?.length || m.intent?.budget_max
                              ? `/rooms?q=${encodeURIComponent(m.intent?.hints?.join(" "))}&smart=1`
                              : "/rooms"
                          )
                        }
                      >
                        View all {m.intent?.hints ? "on Rooms page" : "rooms"} →
                      </Button>
                    </div>
                  )}

                  {/* Quick-reply suggestions */}
                  {m.role === "assistant" && m.suggestions && m.suggestions.length > 0 && (
                    <div className="flex max-w-[85%] flex-wrap gap-1">
                      {m.suggestions.map((s) => (
                        <button
                          key={s}
                          type="button"
                          onClick={() => submit(s)}
                          className="rounded-full border border-gray-200 bg-white px-2.5 py-1 text-[11px] font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}

              {isSending && (
                <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                  <Loader2 className="size-3.5 animate-spin" /> Searching listings…
                </div>
              )}
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
              placeholder={t("copilot.placeholder")}
              className="h-10 text-sm"
              aria-label={t("copilot.title")}
            />
            <Button
              type="submit"
              size="icon"
              className="h-10 w-10 shrink-0 rounded-xl bg-orange-600 text-white hover:bg-orange-700"
              disabled={isSending || !input.trim()}
              aria-label="Send"
            >
              <Send className="size-4" />
            </Button>
          </form>
        </div>
      )}

      {selectedRoom && <RoomModal room={selectedRoom} onClose={() => setSelectedRoom(null)} />}
    </>
  );
}
