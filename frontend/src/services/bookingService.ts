import type { ApiResponse } from "./api";
// import { api } from "./api"; // ← enable in Phase 3 for real HTTP calls
import { mockRooms } from "../data/mockData";
import type { Booking, BookingStatus, CreateBookingPayload } from "../types";

// ============================================================
// BOOKING SERVICE
// Mock implementation backed by mockData.
// ============================================================

const delay = (ms = 250) => new Promise((r) => setTimeout(r, ms));

const wrap = <T>(data: T, meta?: Record<string, unknown>): ApiResponse<T> => ({
  data,
  meta,
});

// In-memory booking list seeded from mock rooms.
let mockBookings: Booking[] = [
  { ...mockRooms[0], status: "approved", date: "Feb 22, 2025" },
  { ...mockRooms[2], status: "pending", date: "Feb 25, 2025" },
];

export const bookingService = {
  async getMyBookings(): Promise<ApiResponse<Booking[]>> {
    await delay();
    return wrap(mockBookings, { total: mockBookings.length });
    // Phase 3: return (await api.get<ApiResponse<Booking[]>>("/bookings/me")).data;
  },

  async createBooking(
    payload: CreateBookingPayload
  ): Promise<ApiResponse<Booking>> {
    await delay();
    const room = mockRooms.find((r) => r.id === payload.roomId);
    if (!room) {
      throw new Error(`Room ${payload.roomId} not found`);
    }
    const booking: Booking = { ...room, status: "pending", date: payload.date };
    mockBookings = [booking, ...mockBookings];
    return wrap(booking);
    // Phase 3: return (await api.post<ApiResponse<Booking>>("/bookings", payload)).data;
  },

  async updateBookingStatus(
    roomId: number,
    status: BookingStatus
  ): Promise<ApiResponse<Booking>> {
    await delay();
    const booking = mockBookings.find((b) => b.id === roomId);
    if (!booking) {
      throw new Error(`Booking for room ${roomId} not found`);
    }
    booking.status = status;
    return wrap(booking);
    // Phase 3: return (await api.patch<ApiResponse<Booking>>(`/bookings/${roomId}`, { status })).data;
  },
};

export default bookingService;
