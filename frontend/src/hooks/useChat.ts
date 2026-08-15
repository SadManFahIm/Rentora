import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { chatService } from "../services/chatService";
import type {
  BlockedUser,
  ChatMessage,
  ChatRoom,
  Report,
  ReportAdminAction,
  ReportCategory,
} from "../types";

// ============================================================
// CHAT QUERY/MUTATION HOOKS
// ============================================================

export const chatKeys = {
  all: ["chat"] as const,
  rooms: () => [...chatKeys.all, "rooms"] as const,
  messages: (roomId: number, search: string) =>
    [...chatKeys.all, "messages", roomId, search] as const,
  blocked: () => [...chatKeys.all, "blocked"] as const,
  reports: (status: string) => [...chatKeys.all, "reports", status] as const,
};

/** The current user's chat rooms. Polled lightly so unread counts / online
 * dots in the sidebar stay reasonably fresh without a dedicated presence
 * channel for the list view. */
export function useChatRooms() {
  return useQuery<ChatRoom[]>({
    queryKey: chatKeys.rooms(),
    queryFn: () => chatService.getRooms(),
    staleTime: 10_000,
    refetchInterval: 15_000,
  });
}

/** Message history for a room (initial page load; the WebSocket in
 * ChatWindow.tsx handles real-time updates from here on). */
export function useChatMessages(roomId: number | null, search = "") {
  return useQuery<ChatMessage[]>({
    queryKey: chatKeys.messages(roomId ?? -1, search),
    queryFn: () => chatService.getMessages(roomId as number, search || undefined),
    enabled: roomId != null,
  });
}

/** Get-or-create a direct chat with a user (optionally about a room listing). */
export function useStartDirectChat() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, listingId }: { userId: number; listingId?: number }) =>
      chatService.startDirectChat(userId, listingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chatKeys.rooms() });
    },
  });
}

export function useUploadChatFile() {
  return useMutation({
    mutationFn: (file: File) => chatService.uploadFile(file),
  });
}

// ---- Report / block (Phase 12.4) ----

/** The caller's list of blocked users (used by ChatWindow to lock a
 * conversation and offer an Unblock action). */
export function useBlockedUsers() {
  return useQuery<BlockedUser[]>({
    queryKey: chatKeys.blocked(),
    queryFn: () => chatService.getBlockedUsers(),
    staleTime: 30_000,
  });
}

export function useBlockUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: number) => chatService.blockUser(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chatKeys.blocked() });
    },
  });
}

export function useUnblockUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: number) => chatService.unblockUser(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chatKeys.blocked() });
    },
  });
}

export function useReportUser() {
  return useMutation({
    mutationFn: (payload: {
      targetUserId: number;
      category: ReportCategory;
      description?: string;
      messageId?: number | null;
    }) => chatService.reportUser(payload),
  });
}

/** Admin moderation queue for user/message reports. `status` may be "all" to
 * see every report regardless of state (defaults to open/unresolved). */
export function useAdminReports(status = "open") {
  return useQuery<Report[]>({
    queryKey: chatKeys.reports(status),
    queryFn: () => chatService.getReports(status),
  });
}

export function useActOnReport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      reportId,
      action,
      note,
    }: {
      reportId: number;
      action: ReportAdminAction;
      note?: string;
    }) => chatService.actOnReport(reportId, action, note),
    onSuccess: () => {
      // Refresh both the open queue and the full list after a decision.
      queryClient.invalidateQueries({ queryKey: chatKeys.all });
    },
  });
}
