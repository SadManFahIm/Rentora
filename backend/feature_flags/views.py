"""Feature-flag admin API (staff only).

    GET  /api/v1/flags/            list flags (+ whether each is on for you)
    PATCH /api/v1/flags/{key}/     update a flag (rollout, status, targeting)

Flag checks in the rest of the app use the cache-backed ``models.is_enabled``;
these endpoints are the operational control plane (and a test seam).
"""

from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import FeatureFlag, invalidate_cache, is_enabled


class FeatureFlagSerializer(serializers.ModelSerializer):
    enabled_for_me = serializers.SerializerMethodField()

    class Meta:
        model = FeatureFlag
        fields = [
            "key",
            "label",
            "description",
            "owner",
            "status",
            "rollout_percentage",
            "environments",
            "roles",
            "user_ids",
            "created_at",
            "updated_at",
            "cleanup_plan",
            "enabled_for_me",
        ]
        read_only_fields = ["key", "created_at", "updated_at", "enabled_for_me"]

    def get_enabled_for_me(self, obj) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        return is_enabled(obj.key, user=user, request=request)


class FeatureFlagListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        flags = FeatureFlag.objects.all()
        serializer = FeatureFlagSerializer(flags, many=True, context={"request": request})
        return Response(serializer.data)


class FeatureFlagDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, key: str):
        flag = FeatureFlag.objects.filter(key=key).first()
        if flag is None:
            return Response({"detail": "Flag not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = FeatureFlagSerializer(
            flag, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        invalidate_cache(flag.key)
        return Response(serializer.data)
