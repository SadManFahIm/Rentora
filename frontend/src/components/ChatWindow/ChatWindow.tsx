import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  BadgeCheck,
  Check,
  CheckCheck,
  Paperclip,
  Send,
  ShieldAlert,
  ShieldCheck,
  X,
} from "lucide-react";
import { useApp } from "../../context/AppContext";
import { useChatMessages, useChatRooms, useUploadChatFile } from "../../hooks/useChat";
import { useWebSocket } from "../../hooks/useWebSocket";
import { mapChatMessage, type ApiChatMessage } from "../../services/mappers";
import type { ChatMessage, ChatRoom, ChatSafetyInfo, ChatUser } from "../../types";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { cn } from "../../lib/utils";

// ============================================================
// Wire shapes pushed by chat/consumers.py (see backend/chat/consumers.py).
// ============================================================
type ChatWsEvent =
  | { type: "chat_message"; message: ApiChatMessage }
  | { type: "typing_indicator"; user_id: number; user_name: string; is_typing: boolean }
  | { type: "read_receipt"; user_id: number; last_read_at: string }
  | { type: "error"; detail: string };

// How long we keep showing "typing…" after the last typing:true event if no
// explicit typing:false ever arrives (mirrors the client-side auto-clear the
// backend's Day 2 spec calls for).
const TYPING_CLEAR_DELAY_MS = 5000;
// How long of silence before we tell the room we've stopped typing.
const TYPING_STOP_DELAY_MS = 3000;

function displayName(u: ChatUser | null | undefined): string {
  if (!u) return "Unknown";
  const full = [u.firstName, u.lastName].filter(Boolean).join(" ").trim();
  return full || u.username;
}

function initialsOf(u: ChatUser | null | undefined): string {
  if (!u) return "?";
  const source = displayName(u);
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Small KYC trust badges shown next to a verified participant's name: the
 * landlord badge (KYC-verified owner) and the Phase 12 tenant badge (identity-
 * verified tenant) — each only when the respective verification passed. */
function VerifiedMark({ participant }: { participant?: ChatUser | null }) {
  if (!participant) return null;
  return (
    <>
      {participant.nidVerified && (
        <ShieldCheck
          className="size-3.5 shrink-0 text-emerald-500"
          aria-label="KYC-verified landlord"
        />
      )}
      {participant.tenantVerified && (
        <span title="Identity verified by Rentora.">
          <BadgeCheck
            className="size-3.5 shrink-0 text-emerald-500"
            aria-label="Identity verified tenant"
          />
        </span>
      )}
    </>
  );
}

function Avatar({
  url,
  fallback,
  online,
}: {
  url: string | null | undefined;
  fallback: string;
  online?: boolean | null;
}) {
  return (
    <div className="relative shrink-0">
      {url ? (
        <img src={url} alt="" className="h-9 w-9 rounded-full object-cover" />
      ) : (
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-orange-600 text-xs font-bold text-white">
          {fallback}
        </div>
      )}
      {online === true && (
        <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-card bg-emerald-500" />
      )}
    </div>
  );
}

/** WhatsApp-style receipt: single check = sent, double gray = delivered,
 * double colored = read. Only rendered on the current user's own messages. */
function MessageStatusIcon({ status }: { status: ChatMessage["status"] }) {
  if (status === "read") return <CheckCheck className="size-3.5 text-sky-300" />;
  if (status === "delivered") return <CheckCheck className="size-3.5 text-white/70" />;
  return <Check className="size-3.5 text-white/70" />;
}

export default function ChatWindow() {
  const { user } = useApp();
  const [searchParams, setSearchParams] = useSearchParams();
  const roomParam = searchParams.get("room");

  const [selectedRoomId, setSelectedRoomId] = useState<number | null>(
    roomParam ? Number(roomParam) : null
  );
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [typingUserName, setTypingUserName] = useState<string | null>(null);
  // Chat safety (Phase 12.3): the last warned/flagged assessment to surface
  // as a dismissible caution banner above the conversation.
  const [safetyNotice, setSafetyNotice] = useState<ChatSafetyInfo | null>(null);
  const [input, setInput] = useState("");

  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const typingClearTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const myTypingStopTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const roomsQuery = useChatRooms();
  const messagesQuery = useChatMessages(selectedRoomId);
  const uploadFile = useUploadChatFile();

  const rooms = roomsQuery.data ?? [];
  const selectedRoom: ChatRoom | null = rooms.find((r) => r.id === selectedRoomId) ?? null;

  // A room opened via a deep link (?room=5, e.g. from "Message Owner" on a
  // listing) should take effect even before the rooms list has loaded.
  useEffect(() => {
    if (roomParam && Number(roomParam) !== selectedRoomId) {
      setSelectedRoomId(Number(roomParam));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomParam]);

  // Reset to the REST-fetched history whenever the room changes / reloads.
  useEffect(() => {
    setMessages(messagesQuery.data ?? []);
  }, [messagesQuery.data]);

  useEffect(() => {
    setTypingUserName(null);
    setSafetyNotice(null);
  }, [selectedRoomId]);

  const wsPath = selectedRoomId != null ? `/ws/chat/${selectedRoomId}/` : null;
  const { sendMessage, lastMessage, isConnected } = useWebSocket<ChatWsEvent>(wsPath);

  useEffect(() => {
    if (!lastMessage) return;

    if (lastMessage.type === "chat_message") {
      const incoming = mapChatMessage(lastMessage.message);
      setMessages((prev) => (prev.some((m) => m.id === incoming.id) ? prev : [...prev, incoming]));
      // Chat safety engine (Phase 12.3): warned/flagged messages raise a
      // caution banner; blocked messages render styled in the list itself.
      if (
        incoming.safety &&
        (incoming.safety.outcome === "warned" || incoming.safety.outcome === "flagged")
      ) {
        setSafetyNotice(incoming.safety);
      }
      if (incoming.sender.id !== user?.id) {
        // Someone else's message, and we're actively looking at this room
        // right now — tell the server we've read it immediately.
        setTypingUserName(null);
        sendMessage({ type: "mark_read" });
      }
    } else if (lastMessage.type === "typing_indicator") {
      if (typingClearTimer.current) clearTimeout(typingClearTimer.current);
      if (lastMessage.is_typing) {
        setTypingUserName(lastMessage.user_name);
        typingClearTimer.current = setTimeout(() => setTypingUserName(null), TYPING_CLEAR_DELAY_MS);
      } else {
        setTypingUserName(null);
      }
    } else if (lastMessage.type === "read_receipt") {
      // The other participant just read up to `last_read_at` — reflect that
      // on our own sent messages immediately rather than waiting on a refetch.
      setMessages((prev) =>
        prev.map((m) => (m.sender.id === user?.id ? { ...m, status: "read" } : m))
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastMessage]);

  useEffect(() => {
    // `block: "nearest"` keeps the scroll contained to the messages panel's
    // own scroll container — without it, scrollIntoView() also scrolls every
    // scrollable ancestor (including the page itself) to bring the target
    // into view, which visibly yanks the whole page down on every message.
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, typingUserName]);

  const handleSelectRoom = (room: ChatRoom) => {
    setSelectedRoomId(room.id);
    setSearchParams({ room: String(room.id) });
  };

  const handleInputChange = (value: string) => {
    setInput(value);
    if (!selectedRoomId) return;
    sendMessage({ type: "typing", is_typing: true });
    if (myTypingStopTimer.current) clearTimeout(myTypingStopTimer.current);
    myTypingStopTimer.current = setTimeout(() => {
      sendMessage({ type: "typing", is_typing: false });
    }, TYPING_STOP_DELAY_MS);
  };

  const handleSend = () => {
    const content = input.trim();
    if (!content || !selectedRoomId) return;
    if (myTypingStopTimer.current) clearTimeout(myTypingStopTimer.current);
    sendMessage({ type: "typing", is_typing: false });
    sendMessage({ type: "message", content });
    setInput("");
  };

  const handleFilePicked = async (file: File | undefined) => {
    if (!file || !selectedRoomId) return;
    try {
      const { fileUrl, messageType } = await uploadFile.mutateAsync(file);
      sendMessage({
        type: "message",
        content: file.name,
        message_type: messageType,
        file_url: fileUrl,
      });
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <div className="mx-auto grid max-w-7xl gap-5 px-4 py-12 md:grid-cols-[300px_1fr] md:px-6 md:py-16 lg:px-8">
      {/* Room list */}
      <div className="hidden overflow-hidden rounded-2xl border border-gray-200 bg-card dark:border-gray-800 md:flex md:flex-col">
        <div className="border-b border-gray-200 p-5 dark:border-gray-800">
          <h3 className="font-display text-base font-bold text-foreground">💬 Messages</h3>
        </div>
        <div className="flex-1 overflow-y-auto">
          {roomsQuery.isLoading ? (
            <div className="p-5 text-sm text-gray-600 dark:text-gray-400">
              Loading conversations…
            </div>
          ) : rooms.length === 0 ? (
            <div className="p-5 text-sm text-gray-600 dark:text-gray-400">
              No conversations yet. Open a room listing and tap "Message Owner" to start one.
            </div>
          ) : (
            rooms.map((room) => (
              <button
                key={room.id}
                onClick={() => handleSelectRoom(room)}
                className={cn(
                  "flex w-full items-center gap-3 border-b border-gray-200 px-5 py-3.5 text-left transition-colors last:border-0 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/50",
                  room.id === selectedRoomId && "bg-gray-50 dark:bg-gray-800/50"
                )}
              >
                <Avatar
                  url={room.otherParticipant?.avatar}
                  fallback={initialsOf(room.otherParticipant)}
                  online={room.isOtherUserOnline}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-1">
                      <span className="truncate text-sm font-semibold text-foreground">
                        {displayName(room.otherParticipant)}
                      </span>
                      <VerifiedMark participant={room.otherParticipant} />
                    </div>
                    {room.unreadCount > 0 && (
                      <span className="flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full bg-orange-600 px-1 text-[10px] font-bold text-white">
                        {room.unreadCount}
                      </span>
                    )}
                  </div>
                  <div className="truncate text-xs text-gray-600 dark:text-gray-400">
                    {room.lastMessage?.content ||
                      (room.listingTitle ? `About: ${room.listingTitle}` : "No messages yet")}
                  </div>
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Conversation panel */}
      <div className="flex h-130 flex-col rounded-2xl border border-gray-200 bg-card dark:border-gray-800">
        {!selectedRoom ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center text-gray-600 dark:text-gray-400">
            <p className="font-display text-base font-bold text-foreground">
              Select a conversation
            </p>
            <p className="text-sm">
              Choose a chat on the left, or message a room owner to start one.
            </p>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-3 border-b border-gray-200 px-5 py-4 dark:border-gray-800">
              <Avatar
                url={selectedRoom.otherParticipant?.avatar}
                fallback={initialsOf(selectedRoom.otherParticipant)}
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1">
                  <span className="truncate text-sm font-bold text-foreground">
                    {displayName(selectedRoom.otherParticipant)}
                  </span>
                  <VerifiedMark participant={selectedRoom.otherParticipant} />
                </div>
                <div className="text-xs text-gray-600 dark:text-gray-400">
                  {selectedRoom.isOtherUserOnline ? (
                    <span className="text-emerald-500">● Online</span>
                  ) : (
                    "Offline"
                  )}
                  {!isConnected && " · Reconnecting…"}
                </div>
              </div>
            </div>

            <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-5">
              {safetyNotice && (
                <div className="flex items-start justify-between gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-2.5 text-xs dark:border-amber-500/30 dark:bg-amber-500/10">
                  <p className="flex items-center gap-1.5 text-amber-700 dark:text-amber-400">
                    <ShieldAlert className="size-3.5 shrink-0" />
                    {safetyNotice.warning ?? "Please be cautious with this conversation."}
                  </p>
                  <button
                    type="button"
                    onClick={() => setSafetyNotice(null)}
                    aria-label="Dismiss safety notice"
                    className="shrink-0 text-amber-600/70 hover:text-amber-700 dark:text-amber-400/70"
                  >
                    <X className="size-3.5" />
                  </button>
                </div>
              )}

              {messagesQuery.isLoading ? (
                <div className="text-sm text-gray-600 dark:text-gray-400">Loading messages…</div>
              ) : (
                messages.map((m) => {
                  const mine = m.sender.id === user?.id;
                  const blocked = m.safety?.blocked === true;
                  return (
                    <div key={m.id} className={cn("max-w-[70%]", mine && "self-end")}>
                      <div
                        className={cn(
                          "rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-sm leading-relaxed",
                          blocked
                            ? "flex items-center gap-1.5 border border-red-200 bg-red-50 text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400"
                            : mine
                              ? "rounded-bl-2xl rounded-br-sm bg-orange-600 text-white"
                              : "bg-gray-100 text-foreground dark:bg-gray-800"
                        )}
                      >
                        {m.messageType === "image" && m.fileUrl ? (
                          <a href={m.fileUrl} target="_blank" rel="noreferrer">
                            <img src={m.fileUrl} alt={m.content} className="max-w-60 rounded-lg" />
                          </a>
                        ) : m.messageType === "file" && m.fileUrl ? (
                          <a
                            href={m.fileUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="flex items-center gap-2 underline"
                          >
                            <Paperclip className="size-4 shrink-0" /> {m.content}
                          </a>
                        ) : blocked ? (
                          <span className="flex items-center gap-1.5">
                            <ShieldAlert className="size-4 shrink-0" />
                            {m.content}
                          </span>
                        ) : (
                          m.content
                        )}
                      </div>
                      <div
                        className={cn(
                          "mt-1 flex items-center gap-1 text-xs text-gray-600 dark:text-gray-400",
                          mine ? "justify-end" : "justify-start"
                        )}
                      >
                        {new Date(m.createdAt).toLocaleTimeString([], {
                          hour: "numeric",
                          minute: "2-digit",
                        })}
                        {mine && <MessageStatusIcon status={m.status} />}
                      </div>
                    </div>
                  );
                })
              )}

              {typingUserName && (
                <div className="max-w-[70%]">
                  <div className="flex gap-1 rounded-2xl rounded-bl-sm bg-gray-100 px-4 py-3 dark:bg-gray-800">
                    {[0, 1, 2].map((i) => (
                      <span
                        key={i}
                        className="block h-2 w-2 animate-pulse rounded-full bg-gray-500"
                        style={{ animationDelay: `${i * 0.15}s` }}
                      />
                    ))}
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            <div className="flex gap-2.5 border-t border-gray-200 p-4 dark:border-gray-800">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/gif,image/webp,.pdf,.doc,.docx,.txt,.zip"
                className="hidden"
                onChange={(e) => handleFilePicked(e.target.files?.[0])}
              />
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="shrink-0 rounded-xl"
                title="Attach a file"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploadFile.isPending}
              >
                <Paperclip className={cn("size-4", uploadFile.isPending && "animate-pulse")} />
              </Button>
              <Input
                placeholder="Type a message..."
                value={input}
                onChange={(e) => handleInputChange(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
              />
              <Button
                className="h-11 w-11 shrink-0 rounded-xl bg-orange-600 text-white hover:bg-orange-700"
                size="icon"
                onClick={handleSend}
              >
                <Send className="size-4" />
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
