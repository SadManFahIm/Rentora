import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  BadgeCheck,
  Ban,
  Check,
  CheckCheck,
  Flag,
  Loader2,
  MoreVertical,
  Paperclip,
  Pencil,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  UserCheck,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { useApp } from "../../context/AppContext";
import {
  useBlockedUsers,
  useBlockUser,
  useChatMessages,
  useChatRooms,
  useDeleteMessage,
  useEditMessage,
  useReportUser,
  useUnblockUser,
  useUploadChatFile,
} from "../../hooks/useChat";
import { useWebSocket } from "../../hooks/useWebSocket";
import { track } from "../../services/analytics";
import { mapChatMessage, type ApiChatMessage } from "../../services/mappers";
import type { ChatMessage, ChatRoom, ChatSafetyInfo, ChatUser, ReportCategory } from "../../types";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Input } from "../ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { cn } from "../../lib/utils";

// ============================================================
// Wire shapes pushed by chat/consumers.py (see backend/chat/consumers.py).
// ============================================================
type ChatWsEvent =
  | { type: "chat_message"; message: ApiChatMessage }
  | { type: "chat_message_updated"; message: ApiChatMessage }
  | { type: "chat_message_deleted"; message: ApiChatMessage }
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
      {participant.tenantVerified && (participant.completedBookings ?? 0) > 0 && (
        <span
          title="Approved bookings this tenant has completed on Rentora."
          className="rounded-full bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400"
        >
          ✓ {(participant.completedBookings ?? 0).toLocaleString()} completed booking
          {(participant.completedBookings ?? 0) > 1 ? "s" : ""}
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

/** Report categories offered to a chat user (mirrors the backend choices). */
const REPORT_CATEGORIES: { value: ReportCategory; label: string; hint: string }[] = [
  { value: "scam", label: "Scam", hint: "Suspicious behaviour or a fraudulent offer" },
  { value: "harassment", label: "Harassment", hint: "Abusive or threatening messages" },
  {
    value: "fake_listing",
    label: "Fake listing",
    hint: "The listing may not exist or is misleading",
  },
  {
    value: "payment_fraud",
    label: "Payment fraud",
    hint: "Suspicious payment requests or links",
  },
  {
    value: "impersonation",
    label: "Impersonation",
    hint: "Pretending to be someone else",
  },
  { value: "spam", label: "Spam", hint: "Unsolicited or repetitive messages" },
  { value: "other", label: "Other", hint: "Something else" },
];

/** Report a user (optionally anchored to one of their messages) — Phase 12.4.
 * Reports land in the admin moderation queue; the reporter is notified of the
 * outcome. The category picker + description give admins the context they need
 * without exposing private message history. */
function ReportUserDialog({
  open,
  onOpenChange,
  userId,
  userName,
  messageId,
  messagePreview,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  userId?: number;
  userName: string;
  messageId?: number;
  messagePreview?: string;
}) {
  const report = useReportUser();
  const [category, setCategory] = useState<ReportCategory | "">("");
  const [description, setDescription] = useState("");

  // Reset the form each time the dialog opens (it may target a new message).
  useEffect(() => {
    if (open) {
      setCategory("");
      setDescription("");
    }
  }, [open]);

  const submit = async () => {
    if (!category || userId == null) return;
    try {
      await report.mutateAsync({
        targetUserId: userId,
        category,
        description: description.trim() || undefined,
        messageId,
      });
      toast.success("Thanks — our moderation team will review this report.");
      onOpenChange(false);
    } catch {
      toast.error("Could not submit the report. Please try again.");
    }
  };

  const preview =
    messagePreview && messagePreview.length > 120
      ? `${messagePreview.slice(0, 120)}…`
      : messagePreview;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Flag className="size-4 text-red-500" /> Report {userName}
          </DialogTitle>
          <DialogDescription>
            {messageId != null
              ? "This report is anchored to one of their messages. Our moderation team will review it and you'll be notified of the outcome."
              : "Tell us what happened — our moderation team will review it and you'll be notified of the outcome."}
          </DialogDescription>
        </DialogHeader>

        {preview && (
          <p className="rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-600 dark:bg-gray-800/60 dark:text-gray-400">
            “{preview}”
          </p>
        )}

        <div className="flex flex-col gap-3">
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-400">
              Reason
            </label>
            <Select value={category} onValueChange={(v) => setCategory(v as ReportCategory)}>
              <SelectTrigger className="h-10">
                <SelectValue placeholder="Select a reason…" />
              </SelectTrigger>
              <SelectContent>
                {REPORT_CATEGORIES.map((c) => (
                  <SelectItem key={c.value} value={c.value}>
                    {c.label} — {c.hint}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-400">
              Details (optional)
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={2000}
              rows={3}
              placeholder="Add anything that helps our team understand…"
              className="w-full resize-none rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-sm text-foreground placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-orange-500/40 dark:border-gray-700"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={report.isPending}>
            Cancel
          </Button>
          <Button
            className="bg-red-600 text-white hover:bg-red-700"
            onClick={submit}
            disabled={report.isPending || !category}
          >
            {report.isPending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Flag className="size-4" />
            )}
            Submit report
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
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
  // Message search (Tier-1 quick win): filters the loaded history via the
  // backend's `?search=` — deleted messages are excluded server-side.
  const [search, setSearch] = useState("");
  // Message editing (Tier-1 quick win): which message is being edited in
  // place, and the in-progress text.
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<ChatMessage | null>(null);
  // Report / block (Phase 12.4): the header menu, who we're reporting (with
  // an optional message anchor), and whether the confirm-block sheet is open.
  const [menuOpen, setMenuOpen] = useState(false);
  const [reportTarget, setReportTarget] = useState<{
    userId: number;
    userName: string;
    messageId?: number;
    messagePreview?: string;
  } | null>(null);
  const [confirmBlockOpen, setConfirmBlockOpen] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const typingClearTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const myTypingStopTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const roomsQuery = useChatRooms();
  const messagesQuery = useChatMessages(selectedRoomId, search);
  const uploadFile = useUploadChatFile();
  const editMutation = useEditMessage();
  const deleteMutation = useDeleteMessage();
  const blockedQuery = useBlockedUsers();
  const blockMutation = useBlockUser();
  const unblockMutation = useUnblockUser();

  const rooms = roomsQuery.data ?? [];
  const selectedRoom: ChatRoom | null = rooms.find((r) => r.id === selectedRoomId) ?? null;

  // Phase 12.4: a conversation is closed (both directions, enforced server-
  // side too) if either side blocked the other. We know our own blocks here;
  // the other side's block surfaces as a send refusal from the API/WS.
  const otherParticipant = selectedRoom?.otherParticipant ?? null;
  const isOtherBlocked =
    otherParticipant != null && (blockedQuery.data ?? []).some((b) => b.id === otherParticipant.id);

  // A room opened via a deep link (?room=5, e.g. from "Message Owner" on a
  // listing) should take effect even before the rooms list has loaded.
  useEffect(() => {
    if (roomParam && Number(roomParam) !== selectedRoomId) {
      setSelectedRoomId(Number(roomParam));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomParam]);

  // Funnel event (Tier 5): opening a conversation is the third conversion
  // step. Fire once per room (when the selected room actually changes).
  useEffect(() => {
    if (selectedRoomId != null) {
      track("chat_started", { room_id: selectedRoomId });
    }
  }, [selectedRoomId]);

  // Reset to the REST-fetched history whenever the room changes / reloads.
  useEffect(() => {
    setMessages(messagesQuery.data ?? []);
  }, [messagesQuery.data]);

  useEffect(() => {
    setTypingUserName(null);
    setSafetyNotice(null);
    setEditingId(null);
    setSearch("");
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
    } else if (lastMessage.type === "chat_message_updated") {
      // The sender edited a message — replace it in place (also covers our
      // own edits, which come back over the same socket).
      const updated = mapChatMessage(lastMessage.message);
      setMessages((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
      if (editingId === updated.id) setEditingId(null);
    } else if (lastMessage.type === "chat_message_deleted") {
      // Soft-delete — update the message to its deleted state in place so the
      // thread keeps its shape.
      const deleted = mapChatMessage(lastMessage.message);
      setMessages((prev) => prev.map((m) => (m.id === deleted.id ? deleted : m)));
      if (editingId === deleted.id) setEditingId(null);
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
  }, [lastMessage, editingId]);

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

  // ---- Message edit / delete (Tier-1 quick win) ----

  const startEdit = (message: ChatMessage) => {
    setEditingId(message.id);
    setEditDraft(message.content);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditDraft("");
  };

  const saveEdit = async (message: ChatMessage) => {
    const content = editDraft.trim();
    if (!content || content === message.content || !selectedRoomId) {
      cancelEdit();
      return;
    }
    try {
      const updated = await editMutation.mutateAsync({
        roomId: selectedRoomId,
        messageId: message.id,
        content,
      });
      setMessages((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
      setEditingId(null);
      setEditDraft("");
      toast.success("Message updated.");
    } catch {
      toast.error("Could not edit the message. Please try again.");
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget || !selectedRoomId) return;
    try {
      await deleteMutation.mutateAsync({
        roomId: selectedRoomId,
        messageId: deleteTarget.id,
      });
      // The REST delete returns 204; build the deleted state locally (the
      // WebSocket also delivers it to other participants).
      setMessages((prev) =>
        prev.map((m) =>
          m.id === deleteTarget.id
            ? {
                ...m,
                content: "[Message deleted]",
                isDeleted: true,
                editedAt: new Date().toISOString(),
              }
            : m
        )
      );
      setDeleteTarget(null);
      toast.success("Message deleted.");
    } catch {
      toast.error("Could not delete the message. Please try again.");
    }
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

  const handleBlock = async () => {
    if (!otherParticipant) return;
    try {
      await blockMutation.mutateAsync(otherParticipant.id);
      toast.success(
        `${displayName(otherParticipant)} is now blocked — you won't receive their messages.`
      );
      setConfirmBlockOpen(false);
      setMenuOpen(false);
    } catch {
      toast.error("Could not block this user right now.");
    }
  };

  const handleUnblock = async () => {
    if (!otherParticipant) return;
    try {
      await unblockMutation.mutateAsync(otherParticipant.id);
      toast.success(`You unblocked ${displayName(otherParticipant)}.`);
      setMenuOpen(false);
    } catch {
      toast.error("Could not unblock this user right now.");
    }
  };

  const openReportUser = () => {
    if (!otherParticipant) return;
    setMenuOpen(false);
    setReportTarget({
      userId: otherParticipant.id,
      userName: displayName(otherParticipant),
    });
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

              {/* Message search (Tier-1 quick win) */}
              <div className="relative hidden sm:block">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-gray-400" />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search…"
                  aria-label="Search messages"
                  className="h-8 w-32 rounded-lg pl-8 text-xs transition-all focus:w-44 focus:ring-2 focus:ring-orange-500/40"
                />
                {search && (
                  <button
                    type="button"
                    onClick={() => setSearch("")}
                    aria-label="Clear message search"
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-foreground"
                  >
                    <X className="size-3" />
                  </button>
                )}
              </div>

              {/* Report / block menu (Phase 12.4) */}
              <div className="relative">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-9 shrink-0 rounded-xl text-gray-500 hover:text-foreground dark:text-gray-400"
                  aria-label="Conversation options"
                  aria-expanded={menuOpen}
                  onClick={() => setMenuOpen((v) => !v)}
                >
                  <MoreVertical className="size-4" />
                </Button>
                {menuOpen && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                    <div className="absolute right-0 z-20 mt-1 w-52 overflow-hidden rounded-xl border border-gray-200 bg-card shadow-lg dark:border-gray-800">
                      <button
                        type="button"
                        onClick={openReportUser}
                        className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-sm text-foreground transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/60"
                      >
                        <Flag className="size-4 text-red-500" /> Report user
                      </button>
                      {isOtherBlocked ? (
                        <button
                          type="button"
                          onClick={handleUnblock}
                          className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-sm text-foreground transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/60"
                        >
                          <UserCheck className="size-4 text-emerald-500" /> Unblock user
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => {
                            setMenuOpen(false);
                            setConfirmBlockOpen(true);
                          }}
                          className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-sm text-red-600 transition-colors hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40"
                        >
                          <Ban className="size-4" /> Block user
                        </button>
                      )}
                    </div>
                  </>
                )}
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
              ) : messages.length === 0 && search ? (
                <div className="text-sm text-gray-600 dark:text-gray-400">
                  No messages match “{search}”.
                </div>
              ) : (
                messages.map((m) => {
                  const mine = m.sender.id === user?.id;
                  const blocked = m.safety?.blocked === true;
                  const deleted = m.isDeleted === true;
                  const editing = editingId === m.id;
                  return (
                    <div key={m.id} className={cn("group max-w-[70%]", mine && "self-end")}>
                      {editing ? (
                        <div className="rounded-2xl rounded-bl-sm border border-orange-300 bg-card p-2 dark:border-orange-500/40">
                          <textarea
                            value={editDraft}
                            onChange={(e) => setEditDraft(e.target.value)}
                            rows={2}
                            autoFocus
                            aria-label="Edit message"
                            className="w-full resize-none rounded-lg bg-transparent px-1 text-sm text-foreground focus:outline-none"
                          />
                          <div className="mt-1 flex justify-end gap-1.5">
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              className="h-7 px-2 text-xs"
                              onClick={cancelEdit}
                              disabled={editMutation.isPending}
                            >
                              Cancel
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              className="h-7 gap-1 bg-orange-600 px-2 text-xs text-white hover:bg-orange-700"
                              onClick={() => saveEdit(m)}
                              disabled={editMutation.isPending || !editDraft.trim()}
                            >
                              {editMutation.isPending ? (
                                <Loader2 className="size-3 animate-spin" />
                              ) : (
                                <Check className="size-3" />
                              )}
                              Save
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <div
                          className={cn(
                            "rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-sm leading-relaxed",
                            deleted && !blocked
                              ? "border border-gray-200 bg-gray-50 italic text-gray-400 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-500"
                              : blocked
                                ? "flex items-center gap-1.5 border border-red-200 bg-red-50 text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400"
                                : mine
                                  ? "rounded-bl-2xl rounded-br-sm bg-orange-600 text-white"
                                  : "bg-gray-100 text-foreground dark:bg-gray-800"
                          )}
                        >
                          {m.messageType === "image" && m.fileUrl && !deleted ? (
                            <a href={m.fileUrl} target="_blank" rel="noreferrer">
                              <img
                                src={m.fileUrl}
                                alt={m.content}
                                className="max-w-60 rounded-lg"
                              />
                            </a>
                          ) : m.messageType === "file" && m.fileUrl && !deleted ? (
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
                      )}
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
                        {m.editedAt && !deleted && <span className="italic">(edited)</span>}
                        {mine && !deleted ? (
                          <>
                            <MessageStatusIcon status={m.status} />
                            {/* Edit / delete (Tier-1 quick win) — own text
                                messages only, on hover. */}
                            {m.messageType === "text" && !blocked && (
                              <span className="flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                                <button
                                  type="button"
                                  onClick={() => startEdit(m)}
                                  aria-label="Edit message"
                                  title="Edit message"
                                  className="rounded p-0.5 text-gray-400 hover:bg-gray-100 hover:text-foreground dark:hover:bg-gray-800"
                                >
                                  <Pencil className="size-3" />
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setDeleteTarget(m)}
                                  aria-label="Delete message"
                                  title="Delete message"
                                  className="rounded p-0.5 text-gray-400 hover:bg-gray-100 hover:text-red-500 dark:hover:bg-gray-800 dark:hover:text-red-400"
                                >
                                  <Trash2 className="size-3" />
                                </button>
                              </span>
                            )}
                          </>
                        ) : (
                          // Report this specific message (e.g. a suspicious
                          // payment request) — Phase 12.4. Appears on hover.
                          <button
                            type="button"
                            onClick={() =>
                              setReportTarget({
                                userId: m.sender.id,
                                userName: displayName(m.sender),
                                messageId: m.id,
                                messagePreview: m.content,
                              })
                            }
                            aria-label="Report this message"
                            title="Report this message"
                            className="rounded p-0.5 text-gray-400 opacity-0 transition-opacity hover:bg-gray-100 hover:text-red-500 group-hover:opacity-100 dark:hover:bg-gray-800 dark:hover:text-red-400"
                          >
                            <Flag className="size-3" />
                          </button>
                        )}
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

            {isOtherBlocked ? (
              <div className="flex items-center justify-between gap-3 border-t border-gray-200 px-5 py-4 dark:border-gray-800">
                <p className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                  <Ban className="size-4 shrink-0 text-red-500" />
                  You blocked {displayName(otherParticipant)} — this conversation is closed.
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleUnblock}
                  disabled={unblockMutation.isPending}
                  className="shrink-0"
                >
                  {unblockMutation.isPending ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <UserCheck className="size-3.5" />
                  )}
                  Unblock
                </Button>
              </div>
            ) : (
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
            )}
          </>
        )}
      </div>

      {/* Confirm-block dialog (Phase 12.4) */}
      <Dialog open={confirmBlockOpen} onOpenChange={setConfirmBlockOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Ban className="size-4 text-red-500" /> Block {displayName(otherParticipant)}?
            </DialogTitle>
            <DialogDescription>
              They won't be able to message you, and this conversation will be closed for both
              sides. You can unblock them any time from this chat.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmBlockOpen(false)}
              disabled={blockMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              className="bg-red-600 text-white hover:bg-red-700"
              onClick={handleBlock}
              disabled={blockMutation.isPending}
            >
              {blockMutation.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Ban className="size-4" />
              )}
              Block user
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Report user / message dialog (Phase 12.4) */}
      <ReportUserDialog
        open={reportTarget != null}
        onOpenChange={(open) => {
          if (!open) setReportTarget(null);
        }}
        userId={reportTarget?.userId}
        userName={reportTarget?.userName ?? ""}
        messageId={reportTarget?.messageId}
        messagePreview={reportTarget?.messagePreview}
      />

      {/* Delete-message confirm (Tier-1 quick win) */}
      <Dialog open={deleteTarget != null} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Trash2 className="size-4 text-red-500" /> Delete this message?
            </DialogTitle>
            <DialogDescription>
              This removes the message for both of you. It can't be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteTarget(null)}
              disabled={deleteMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              className="bg-red-600 text-white hover:bg-red-700"
              onClick={confirmDelete}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Trash2 className="size-4" />
              )}
              Delete message
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
