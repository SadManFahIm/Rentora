import { describe, expect, it } from "vitest";
import {
  mapRoom,
  mapBooking,
  mapNotification,
  mapChatUser,
  mapChatMessage,
  mapChatRoom,
  mapUser,
  relativeTime,
  type ApiBooking,
} from "./mappers";

// ---- fixtures (DRF wire shapes) ----

const apiRoom = (overrides: Record<string, unknown> = {}) => ({
  id: 7,
  title: "Sunlit Studio, Dhanmondi",
  description: "Modern studio",
  room_type: "studio",
  price: "12000.00",
  area: "Dhanmondi",
  lat: "23.7461",
  lng: "90.3742",
  amenities: ["WiFi", "AC"],
  gender_preference: "any",
  size_sqft: 450,
  is_available: true,
  tier: "premium",
  tier_expires_at: "2026-09-01T00:00:00Z",
  is_featured: true,
  rating: "4.8",
  total_reviews: 24,
  verified: true,
  owner: {
    id: 3,
    username: "rahim.hossain",
    first_name: "Rahim",
    last_name: "Hossain",
    avatar: null,
    phone: "01700000000",
    nid_verified: true,
  },
  images: [],
  created_at: "2025-01-01T00:00:00Z",
  ...overrides,
});

describe("mapRoom", () => {
  it("maps every field from the DRF shape", () => {
    const room = mapRoom(apiRoom());
    expect(room).toMatchObject({
      id: 7,
      name: "Sunlit Studio, Dhanmondi",
      type: "Studio",
      price: 12000,
      area: "Dhanmondi",
      rating: 4.8,
      reviews: 24,
      amenities: ["WiFi", "AC"],
      gender: "Any",
      available: true,
      tier: "premium",
      tierExpiresAt: "2026-09-01T00:00:00Z",
      featured: true,
      description: "Modern studio",
      size: 450,
      owner: "Rahim Hossain",
      ownerId: 3,
      verified: true,
    });
  });

  it("falls back to a seeded placeholder image when no images exist", () => {
    const room = mapRoom(apiRoom({ images: [] }));
    expect(room.img).toContain("picsum.photos/seed/rentora-room-7");
  });

  it("picks the primary image when present", () => {
    const room = mapRoom(
      apiRoom({
        images: [
          { id: 1, image: "https://img.example/second.jpg", is_primary: false, created_at: "t" },
          { id: 2, image: "https://img.example/primary.jpg", is_primary: true, created_at: "t" },
        ],
      })
    );
    expect(room.img).toBe("https://img.example/primary.jpg");
  });

  it("falls back to the first image when none is primary", () => {
    const room = mapRoom(
      apiRoom({
        images: [
          { id: 1, image: "https://img.example/first.jpg", is_primary: false, created_at: "t" },
        ],
      })
    );
    expect(room.img).toBe("https://img.example/first.jpg");
  });

  it("uses the username when the owner has no name parts", () => {
    const room = mapRoom(apiRoom({ owner: { ...apiRoom().owner, first_name: "", last_name: "" } }));
    expect(room.owner).toBe("rahim.hossain");
    expect(room.ownerAvatar).toBe("RA"); // initials from the fallback username
  });

  it("handles a missing owner", () => {
    const room = mapRoom(apiRoom({ owner: null }));
    expect(room.owner).toBe("Owner");
    expect(room.ownerId).toBeNull();
  });

  it("defaults missing numbers and optional fields safely", () => {
    const room = mapRoom(
      apiRoom({ lat: undefined, lng: undefined, rating: "0", amenities: undefined })
    );
    expect(room.lat).toBe(0);
    expect(room.lng).toBe(0);
    expect(room.amenities).toEqual([]);
  });
});

describe("mapBooking", () => {
  it("merges room fields with booking data", () => {
    const api = {
      id: 11,
      room: apiRoom({ id: 7 }),
      status: "approved",
      check_in: "2025-02-01T00:00:00Z",
      check_out: null,
      monthly_rent: "12000.00",
      agreement_signed: true,
      notes: "",
      security_deposit_amount: "6000.00",
      security_deposit_paid: true,
      security_deposit_refunded: false,
      created_at: "2025-01-15T00:00:00Z",
    };
    const b = mapBooking(api as ApiBooking);
    expect(b).toMatchObject({
      bookingId: 11,
      status: "approved",
      monthlyRent: 12000,
      securityDepositAmount: 6000,
      securityDepositPaid: true,
      securityDepositRefunded: false,
    });
    expect(b.name).toBe("Sunlit Studio, Dhanmondi");
  });
});

describe("mapNotification", () => {
  it("uses message and computes relative time", () => {
    const n = mapNotification({
      id: 1,
      notification_type: "booking",
      notification_type_display: "Booking",
      title: "New booking",
      message: "Rahim booked your room",
      is_read: false,
      action_url: "/bookings/11",
      created_at: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
    });
    expect(n.text).toBe("Rahim booked your room");
    expect(n.read).toBe(false);
    expect(n.time).toBe("5m ago");
  });

  it("falls back to the title when message is empty", () => {
    const n = mapNotification({
      id: 2,
      notification_type: "general",
      notification_type_display: "General",
      title: "Welcome!",
      message: "",
      is_read: true,
      action_url: "",
      created_at: new Date().toISOString(),
    });
    expect(n.text).toBe("Welcome!");
  });
});

describe("relativeTime", () => {
  it("returns empty string for invalid dates", () => {
    expect(relativeTime("not-a-date")).toBe("");
  });
  it("handles just-now, hours, days and older", () => {
    const now = Date.now();
    expect(relativeTime(new Date(now - 1000 * 10).toISOString())).toBe("just now");
    expect(relativeTime(new Date(now - 1000 * 60 * 60 * 3).toISOString())).toBe("3h ago");
    expect(relativeTime(new Date(now - 1000 * 60 * 60 * 24 * 5).toISOString())).toBe("5d ago");
    const old = new Date(now - 1000 * 60 * 60 * 24 * 400).toISOString();
    expect(relativeTime(old)).toMatch(/^\d{1,2}\/\d{1,2}\/\d{4}$/);
  });
});

describe("chat mappers", () => {
  const chatUser = {
    id: 5,
    username: "sabbir.rahman",
    first_name: "Sabbir",
    last_name: "Rahman",
    avatar: null,
  };

  it("mapChatUser", () => {
    expect(mapChatUser(chatUser)).toMatchObject({
      id: 5,
      username: "sabbir.rahman",
      firstName: "Sabbir",
      lastName: "Rahman",
      avatar: null,
    });
  });

  it("mapChatMessage", () => {
    const m = mapChatMessage({
      id: 21,
      chat_room: 3,
      sender: chatUser,
      content: "hi",
      message_type: "text",
      file_url: "",
      is_read: true,
      status: "sent",
      created_at: "2025-01-01T00:00:00Z",
    });
    expect(m).toMatchObject({
      id: 21,
      chatRoomId: 3,
      content: "hi",
      messageType: "text",
      status: "sent",
      createdAt: "2025-01-01T00:00:00Z",
    });
    expect(m.sender.username).toBe("sabbir.rahman");
  });

  it("mapChatRoom with full participants and last message", () => {
    const r = mapChatRoom({
      id: 3,
      room_type: "listing",
      listing: 7,
      listing_title: "Sunlit Studio",
      participants: [chatUser, { ...chatUser, id: 3, username: "rahim.hossain" }],
      other_participant: { ...chatUser, id: 3, username: "rahim.hossain" },
      is_other_user_online: true,
      last_message: {
        id: 21,
        chat_room: 3,
        sender: chatUser,
        content: "hi",
        message_type: "text",
        file_url: "",
        is_read: true,
        status: "sent",
        created_at: "2025-01-01T00:00:00Z",
      },
      unread_count: 2,
      created_at: "2025-01-01T00:00:00Z",
      updated_at: "2025-01-02T00:00:00Z",
    });
    expect(r.listingTitle).toBe("Sunlit Studio");
    expect(r.participants).toHaveLength(2);
    expect(r.otherParticipant?.username).toBe("rahim.hossain");
    expect(r.isOtherUserOnline).toBe(true);
    expect(r.lastMessage?.content).toBe("hi");
    expect(r.unreadCount).toBe(2);
  });

  it("mapChatRoom tolerates missing other_participant and last_message", () => {
    const r = mapChatRoom({
      id: 4,
      room_type: "direct",
      listing: null,
      listing_title: null,
      participants: [],
      other_participant: null,
      is_other_user_online: null,
      last_message: null,
      unread_count: 0,
      created_at: "2025-01-01T00:00:00Z",
      updated_at: "2025-01-01T00:00:00Z",
    });
    expect(r.otherParticipant).toBeNull();
    expect(r.lastMessage).toBeNull();
    expect(r.participants).toEqual([]);
  });
});

describe("mapUser", () => {
  it("prefers pk over id and joins name parts", () => {
    const u = mapUser({
      pk: 9,
      username: "tanvir.islam",
      email: "tanvir.islam@rentora.com",
      first_name: "Tanvir",
      last_name: "Islam",
      phone: "018",
      role: "landlord",
      avatar: null,
      nid_verified: false,
    });
    expect(u).toMatchObject({
      id: 9,
      name: "Tanvir Islam",
      email: "tanvir.islam@rentora.com",
      username: "tanvir.islam",
      role: "landlord",
      phone: "018",
      nidVerified: false,
    });
  });

  it("falls back to id and to username/email for the display name", () => {
    const u = mapUser({
      id: 4,
      username: "nadia.islam",
      email: "nadia@rentora.com",
      first_name: "",
      last_name: "",
    });
    expect(u.id).toBe(4);
    expect(u.name).toBe("nadia.islam");
  });
});
