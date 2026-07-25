import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { chatService } from "../services/chatService";
import type { ChatMessage, ChatRoom } from "../types";

// ============================================================
// CHAT QUERY/MUTATION HOOKS
// ============================================================

export const chatKeys = {
  all: ["chat"] as const,
  rooms: () => [...chatKeys.all, "rooms"] as const,
  messages: (roomId: number, search: string) =>
    [...chatKeys.all, "messages", roomId, search] as const,
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
