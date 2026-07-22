import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { bookingService } from "../services/bookingService";
import type { Booking, CreateBookingPayload } from "../types";

// ============================================================
// BOOKING QUERY / MUTATION HOOKS
// ============================================================

export const bookingKeys = {
  all: ["bookings"] as const,
  mine: () => [...bookingKeys.all, "mine"] as const,
};

/** Current user's bookings. */
export function useBookings() {
  return useQuery<Booking[]>({
    queryKey: bookingKeys.mine(),
    queryFn: async () => (await bookingService.getMyBookings()).data,
  });
}

/** Create a booking and refresh the bookings list on success. */
export function useCreateBooking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: CreateBookingPayload) =>
      (await bookingService.createBooking(payload)).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bookingKeys.mine() });
    },
  });
}
