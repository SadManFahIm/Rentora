import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import { sendCopilotMessage, type CopilotChatMessage } from "../services/copilotService";
import { getApiErrorMessage } from "../services/errors";

let messageSeq = 0;
const nextId = () => `copilot-${Date.now()}-${messageSeq++}`;

/**
 * Stateful Copilot conversation: message list, in-flight flag, and `send`
 * which threads the session id through so follow-ups keep context.
 */
export function useCopilot() {
  const [messages, setMessages] = useState<CopilotChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const sessionRef = useRef<string | null>(null);

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isSending) return;

      setMessages((prev) => [...prev, { id: nextId(), role: "user", text: trimmed }]);
      setIsSending(true);
      try {
        const res = await sendCopilotMessage(trimmed, sessionRef.current);
        sessionRef.current = res.session_id;
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: "assistant",
            text: res.message,
            listings: res.listings,
            suggestions: res.suggestions,
            intent: res.intent,
          },
        ]);
      } catch (error) {
        toast.error(getApiErrorMessage(error, "Copilot is busy — try again."));
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: "assistant",
            text: "Sorry, I couldn't reach the search engine. Please try again in a moment.",
          },
        ]);
      } finally {
        setIsSending(false);
      }
    },
    [isSending]
  );

  const reset = useCallback(() => {
    sessionRef.current = null;
    setMessages([]);
  }, []);

  return { messages, isSending, isOpen, setIsOpen, send, reset };
}
