import { api } from "./api";
import { mapBooking, type ApiBooking, type Paginated } from "./mappers";
import type { Booking, BookingStatus, CreateBookingPayload } from "../types";

// ============================================================
// BOOKING SERVICE — real /bookings/ endpoints
// ============================================================

export const bookingService = {
  /** GET /bookings/ — bookings where the user is tenant or room owner. */
  async getMyBookings(): Promise<Booking[]> {
    const { data } = await api.get<Paginated<ApiBooking>>("/bookings/");
    return data.results.map(mapBooking);
  },

  /** POST /bookings/ — request a booking for a room. */
  async createBooking({ roomId, checkIn }: CreateBookingPayload): Promise<Booking> {
    const { data } = await api.post<ApiBooking>("/bookings/", {
      room: roomId,
      check_in: checkIn,
    });
    return mapBooking(data);
  },

  /** PATCH /bookings/:id/ — approve / reject / cancel. */
  async updateBookingStatus(
    bookingId: number,
    status: BookingStatus
  ): Promise<Booking> {
    const { data } = await api.patch<ApiBooking>(`/bookings/${bookingId}/`, {
      status,
    });
    return mapBooking(data);
  },
};

export default bookingService;
