"""Logs a `view` UserActivity whenever an authenticated user retrieves a
single room's detail (GET /api/v1/rooms/<id>/).

A page view isn't a model-lifecycle event, so this can't be a signal the way
the wishlist/booking activity is — a lightweight middleware that inspects the
resolved view name after the response is generated is the simplest way to
observe it without touching RoomViewSet itself.
"""

from __future__ import annotations

import datetime

from django.utils import timezone

from .models import UserActivity

# Skip logging a duplicate `view` row if the same user viewed the same room
# within this window — a page refresh shouldn't inflate a room's weight in
# the user's preference vector the way a genuinely repeat, spaced-out visit
# should.
VIEW_DEDUPE_WINDOW = datetime.timedelta(minutes=5)


class RoomViewActivityMiddleware:
    """Logs a `view` activity for authenticated GETs to the room detail endpoint."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        self._maybe_log_view(request, response)
        return response

    def _maybe_log_view(self, request, response) -> None:
        if request.method != "GET" or response.status_code != 200:
            return

        match = getattr(request, "resolver_match", None)
        if match is None or match.view_name != "room-detail":
            return

        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return

        room_id = match.kwargs.get("pk")
        if not room_id:
            return

        recent_cutoff = timezone.now() - VIEW_DEDUPE_WINDOW
        already_logged_recently = UserActivity.objects.filter(
            user=user,
            room_id=room_id,
            activity_type=UserActivity.ActivityType.VIEW,
            created_at__gte=recent_cutoff,
        ).exists()
        if already_logged_recently:
            return

        UserActivity.objects.create(
            user=user,
            room_id=room_id,
            activity_type=UserActivity.ActivityType.VIEW,
            weight=UserActivity.DEFAULT_WEIGHTS[UserActivity.ActivityType.VIEW],
        )
