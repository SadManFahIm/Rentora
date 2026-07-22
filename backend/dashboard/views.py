from __future__ import annotations

from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from bookings.models import Booking, Review
from rooms.models import Room
from users.models import User

# Profile fields that each contribute an equal share to profile completion.
_PROFILE_FIELDS = ("avatar", "phone", "bio", "date_of_birth")


class DashboardStatsView(APIView):
    """Aggregate activity stats for the authenticated user's dashboard.

    ``GET /api/v1/dashboard/stats/``

    Always returns a common block (tenant-relevant counts + profile
    completion). For landlords it additionally returns a ``landlord`` block
    covering their listings, received bookings, average rating and revenue.

    All counts/sums are computed with ORM aggregates (a handful of queries
    total, independent of how much data the user has) — no per-row lookups.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = request.user

        data = {
            **self._common_stats(user),
            "profile_completion": self._profile_completion(user),
        }

        if user.role == User.Role.LANDLORD:
            data["landlord"] = self._landlord_stats(user)

        return Response(data)

    @staticmethod
    def _common_stats(user: User) -> dict:
        """Counts relevant to every user, as the tenant/reviewer/recipient.

        The two booking counts are collapsed into a single aggregate query
        using conditional ``Count`` filters.
        """
        booking_counts = Booking.objects.filter(tenant=user).aggregate(
            active=Count("id", filter=Q(status=Booking.Status.APPROVED)),
            pending=Count("id", filter=Q(status=Booking.Status.PENDING)),
        )

        return {
            "saved_rooms_count": user.wishlist_items.count(),
            "active_bookings": booking_counts["active"],
            "pending_bookings": booking_counts["pending"],
            "total_reviews_given": Review.objects.filter(user=user).count(),
            "unread_notifications": user.notifications.filter(is_read=False).count(),
        }

    @staticmethod
    def _profile_completion(user: User) -> int:
        """Percentage of key profile fields filled in (25% per field)."""
        share = 100 // len(_PROFILE_FIELDS)
        filled = 0
        for field in _PROFILE_FIELDS:
            value = getattr(user, field)
            # Treat empty strings / blank ImageFields / None all as "missing".
            if value:
                filled += 1
        return filled * share

    @staticmethod
    def _landlord_stats(user: User) -> dict:
        """Listing/booking/revenue stats for a landlord's owned rooms."""
        room_agg = Room.objects.filter(owner=user).aggregate(
            total_listings=Count("id"),
            avg_rating=Avg("rating"),
        )

        booking_agg = Booking.objects.filter(room__owner=user).aggregate(
            total_bookings_received=Count("id"),
            total_revenue=Sum(
                "monthly_rent",
                filter=Q(status=Booking.Status.APPROVED),
            ),
        )

        avg_rating = room_agg["avg_rating"] or Decimal("0")
        total_revenue = booking_agg["total_revenue"] or Decimal("0")

        return {
            "total_listings": room_agg["total_listings"],
            "total_bookings_received": booking_agg["total_bookings_received"],
            "avg_rating": round(float(avg_rating), 2),
            "total_revenue": float(total_revenue),
        }
