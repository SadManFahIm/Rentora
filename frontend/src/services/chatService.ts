import { api } from "./api";
import {
  mapChatMessage,
  mapChatRoom,
  type ApiChatMessage,
  type ApiChatRoom,
  type Paginated,
} from "./mappers";
import type { ChatMessage, ChatMessageType, ChatRoom } from "../types";

// ============================================================
// CHAT SERVICE — real /chat/ endpoints (REST fallback; the
// WebSocket connection in ChatWindow.tsx is the real-time path).
// ============================================================

export interface UploadedChatFile {
  fileUrl: string;
  messageType: ChatMessageType;
}

export const chatService = {
  /** GET /chat/rooms/ — chat rooms the current user belongs to. */
  async getRooms(): Promise<ChatRoom[]> {
    const { data } = await api.get<Paginated<ApiChatRoom>>("/chat/rooms/");
    return data.results.map(mapChatRoom);
  },

  /** POST /chat/rooms/ — get-or-create a direct chat with `userId`,
   * optionally tied to a room listing. */
  async startDirectChat(userId: number, listingId?: number): Promise<ChatRoom> {
    const { data } = await api.post<ApiChatRoom>("/chat/rooms/", {
      user_id: userId,
      ...(listingId != null ? { listing_id: listingId } : {}),
    });
    return mapChatRoom(data);
  },

  /** GET /chat/rooms/:id/messages/ — paginated, newest-first from the API;
   * returned here in chronological (oldest-first) order for direct rendering. */
  async getMessages(roomId: number, search?: string): Promise<ChatMessage[]> {
    const { data } = await api.get<Paginated<ApiChatMessage>>(
      `/chat/rooms/${roomId}/messages/`,
      { params: search ? { search } : undefined }
    );
    return data.results.map(mapChatMessage).reverse();
  },

  /** POST /chat/rooms/:id/messages/ — REST fallback for sending a message
   * (the live UI sends over the WebSocket instead; this exists for
   * non-realtime callers / as a resilience fallback). */
  async sendMessage(
    roomId: number,
    payload: { content: string; message_type?: ChatMessageType; file_url?: string }
  ): Promise<ChatMessage> {
    const { data } = await api.post<ApiChatMessage>(
      `/chat/rooms/${roomId}/messages/`,
      payload
    );
    return mapChatMessage(data);
  },

  /** POST /chat/upload/ — multipart upload, returns the stored file's URL
   * and inferred message type ("image" or "file"). */
  async uploadFile(file: File): Promise<UploadedChatFile> {
    const form = new FormData();
    form.append("file", file);
    const { data } = await api.post<{ file_url: string; message_type: string }>(
      "/chat/upload/",
      form,
      { headers: { "Content-Type": "multipart/form-data" } }
    );
    return { fileUrl: data.file_url, messageType: data.message_type as ChatMessageType };
  },

  /** GET /chat/online-status/ — split `userIds` into online/offline. */
  async getOnlineStatus(
    userIds: number[]
  ): Promise<{ online: number[]; offline: number[] }> {
    const { data } = await api.get<{ online: number[]; offline: number[] }>(
      "/chat/online-status/",
      { params: { user_ids: userIds.join(",") } }
    );
    return data;
  },
};

export default chatService;
