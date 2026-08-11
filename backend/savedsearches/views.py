from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import mixins, permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from .models import SavedSearch
from .serializers import SavedSearchSerializer
from .services import find_new_matches


@extend_schema_view(
    list=extend_schema(
        tags=["Saved Searches"],
        summary="List saved searches",
        description="The authenticated user's saved searches, newest first.",
    ),
    create=extend_schema(
        tags=["Saved Searches"],
        summary="Save the current search",
        description=(
            "Persist a search so new matching listings alert the user. "
            "`filters` mirrors the Rooms list params (q, area, room_type, "
            "gender_preference, price_min, price_max, verified)."
        ),
    ),
    destroy=extend_schema(tags=["Saved Searches"], summary="Delete a saved search"),
)
class SavedSearchViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """CRUD for the authenticated user's saved searches + manual check."""

    serializer_class = SavedSearchSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SavedSearch.objects.none()
        return SavedSearch.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @extend_schema(
        tags=["Saved Searches"],
        summary="Check a saved search now",
        description=(
            "Run the saved search immediately and report how many new "
            "matching rooms exist since the last check (without notifying). "
            "Also refreshes last_checked_at."
        ),
        responses=inline_serializer(
            "SavedSearchCheckResponse",
            fields={"new_matches": serializers.IntegerField()},
        ),
    )
    @action(detail=True, methods=["post"])
    def check(self, request: Request, pk=None) -> Response:
        """Run this saved search and report new matches since last check."""
        from django.utils import timezone

        saved_search = self.get_object()
        matches = find_new_matches(saved_search)
        saved_search.last_checked_at = timezone.now()
        saved_search.save(update_fields=["last_checked_at"])
        return Response({"new_matches": len(matches)})
