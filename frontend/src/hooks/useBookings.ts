import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { bookingService } from "../services/bookingService";
import { getApiErrorMessage } from "../services/errors";
import type { Booking, BookingStatus, CreateBookingPayload } from "../types";

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
    queryFn: () => bookingService.getMyBookings(),
  });
}

/** Create a booking and refresh the bookings list on success. */
export function useCreateBooking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateBookingPayload) =>
      bookingService.createBooking(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bookingKeys.mine() });
      toast.success("Booking request sent!");
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not create booking."));
    },
  });
}

/** Approve / reject / cancel a booking. */
export function useUpdateBookingStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ bookingId, status }: { bookingId: number; status: BookingStatus }) =>
      bookingService.updateBookingStatus(bookingId, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bookingKeys.mine() });
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not update booking."));
    },
  });
}
