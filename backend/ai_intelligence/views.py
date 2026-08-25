"""AI Intelligence Layer — Phase 18.1 + 18.2 API views.

All views require admin authentication (IsAdminUser).
"""

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AIExecutionLog, AIFeatureRegistry, AIPrompt, AIPromptVersion, ProviderHealth
from .serializers import (
    AIExecutionLogSerializer,
    AIFeatureRegistrySerializer,
    AIPromptCreateSerializer,
    AIPromptDetailSerializer,
    AIPromptListSerializer,
    AIPromptVersionCreateSerializer,
    AIPromptVersionSerializer,
    ProviderHealthSerializer,
    ProviderStatsSerializer,
)
from .services import (
    activate_prompt_version,
    create_prompt,
    create_prompt_version,
    deactivate_prompt_version,
    get_provider_stats,
    rollback_prompt,
    update_provider_health,
)

# ---------------------------------------------------------------------------
# Feature Registry
# ---------------------------------------------------------------------------


class AIFeatureRegistryListView(generics.ListAPIView):
    """List all registered AI features."""

    permission_classes = [permissions.IsAdminUser]
    serializer_class = AIFeatureRegistrySerializer
    queryset = AIFeatureRegistry.objects.all()


class AIFeatureRegistryDetailView(generics.RetrieveAPIView):
    """Retrieve a single AI feature by feature_id."""

    permission_classes = [permissions.IsAdminUser]
    serializer_class = AIFeatureRegistrySerializer
    queryset = AIFeatureRegistry.objects.all()
    lookup_field = "feature_id"


class AIFeatureRegistryUpdateView(generics.UpdateAPIView):
    """Update an AI feature's configuration."""

    permission_classes = [permissions.IsAdminUser]
    serializer_class = AIFeatureRegistrySerializer
    queryset = AIFeatureRegistry.objects.all()
    lookup_field = "feature_id"


# ---------------------------------------------------------------------------
# Prompt Registry
# ---------------------------------------------------------------------------


class AIPromptListView(generics.ListCreateAPIView):
    """List all prompts or create a new one."""

    permission_classes = [permissions.IsAdminUser]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AIPromptCreateSerializer
        return AIPromptListSerializer

    def get_queryset(self):
        qs = AIPrompt.objects.select_related("feature").prefetch_related("versions").all()

        # Optional filters
        feature = self.request.query_params.get("feature")
        if feature:
            qs = qs.filter(feature_id=feature)

        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)

        prompt_status = self.request.query_params.get("status")
        if prompt_status:
            qs = qs.filter(status=prompt_status)

        return qs

    def create(self, request, *args, **kwargs):
        serializer = AIPromptCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            prompt = create_prompt(
                prompt_key=data["prompt_key"],
                name=data["name"],
                template=data["template"],
                description=data.get("description", ""),
                category=data.get("category", "other"),
                feature_id=data.get("feature"),
                template_type=data.get("template_type", "template"),
                default_model=data.get("default_model", ""),
                input_schema=data.get("input_schema", {}),
                output_schema=data.get("output_schema", {}),
                system_instructions=data.get("system_instructions", ""),
                variables=data.get("variables", {}),
                model_requirement=data.get("model_requirement", ""),
                change_summary=data.get("change_summary", "Initial version"),
                created_by=request.user,
            )
            from audit.services import log_action

            log_action(
                actor=request.user,
                action="ai_intelligence.prompt.created",
                target=prompt,
                request=request,
            )
            return Response(
                AIPromptDetailSerializer(prompt).data,
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class AIPromptDetailView(generics.RetrieveUpdateAPIView):
    """Retrieve or update a prompt's metadata (not template content)."""

    permission_classes = [permissions.IsAdminUser]
    serializer_class = AIPromptDetailSerializer
    queryset = AIPrompt.objects.select_related("feature").prefetch_related("versions").all()
    lookup_field = "prompt_key"

    def update(self, request, *args, **kwargs):
        prompt = self.get_object()
        # Only allow metadata updates, not template
        allowed_fields = {"name", "description", "category", "status", "default_model", "feature"}
        updates = {k: v for k, v in request.data.items() if k in allowed_fields}
        if not updates:
            return Response(
                {"error": "No valid fields to update."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for field, value in updates.items():
            setattr(prompt, field, value)
        prompt.save(update_fields=[*list(updates.keys()), "updated_at"])

        from audit.services import log_action

        log_action(
            actor=request.user,
            action="ai_intelligence.prompt.updated",
            target=prompt,
            request=request,
            detail=updates,
        )
        return Response(AIPromptDetailSerializer(prompt).data)


class AIPromptVersionListView(generics.ListCreateAPIView):
    """List versions for a prompt or create a new version."""

    permission_classes = [permissions.IsAdminUser]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AIPromptVersionCreateSerializer
        return AIPromptVersionSerializer

    def get_queryset(self):
        prompt_key = self.kwargs["prompt_key"]
        return AIPromptVersion.objects.filter(
            prompt__prompt_key=prompt_key,
        ).select_related("prompt", "created_by")

    def create(self, request, *args, **kwargs):
        prompt_key = self.kwargs["prompt_key"]
        serializer = AIPromptVersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            version = create_prompt_version(
                prompt_key=prompt_key,
                template=data["template"],
                system_instructions=data.get("system_instructions", ""),
                variables=data.get("variables", {}),
                model_requirement=data.get("model_requirement", ""),
                change_summary=data.get("change_summary", ""),
                created_by=request.user,
            )
            from audit.services import log_action

            log_action(
                actor=request.user,
                action="ai_intelligence.prompt_version.created",
                target=version,
                request=request,
                detail={"prompt_key": prompt_key, "version": version.version},
            )
            return Response(
                AIPromptVersionSerializer(version).data,
                status=status.HTTP_201_CREATED,
            )
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class AIPromptVersionDetailView(generics.RetrieveAPIView):
    """Retrieve a specific prompt version."""

    permission_classes = [permissions.IsAdminUser]
    serializer_class = AIPromptVersionSerializer
    queryset = AIPromptVersion.objects.select_related("prompt", "created_by").all()

    def get_object(self):
        prompt_key = self.kwargs["prompt_key"]
        version_number = self.kwargs["version"]
        return generics.get_object_or_404(
            AIPromptVersion,
            prompt__prompt_key=prompt_key,
            version=version_number,
        )


class AIPromptActivateView(APIView):
    """Activate a specific prompt version."""

    permission_classes = [permissions.IsAdminUser]

    def post(self, request, prompt_key, version):
        try:
            pv = activate_prompt_version(
                prompt_key,
                version,
                activated_by=request.user,
                request=request,
            )
            return Response(
                AIPromptVersionSerializer(pv).data,
                status=status.HTTP_200_OK,
            )
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND,
            )


class AIPromptDeactivateView(APIView):
    """Deactivate the current active version for a prompt."""

    permission_classes = [permissions.IsAdminUser]

    def post(self, request, prompt_key):
        deactivated = deactivate_prompt_version(
            prompt_key,
            deactivated_by=request.user,
            request=request,
        )
        if deactivated:
            return Response(
                {"message": f"Deactivated active version for {prompt_key}."},
                status=status.HTTP_200_OK,
            )
        return Response(
            {"message": f"No active version found for {prompt_key}."},
            status=status.HTTP_200_OK,
        )


class AIPromptRollbackView(APIView):
    """Rollback a prompt to its previous version."""

    permission_classes = [permissions.IsAdminUser]

    def post(self, request, prompt_key):
        try:
            pv = rollback_prompt(
                prompt_key,
                rolled_back_by=request.user,
                request=request,
            )
            return Response(
                AIPromptVersionSerializer(pv).data,
                status=status.HTTP_200_OK,
            )
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class AIPromptCompareView(APIView):
    """Compare two prompt versions side by side."""

    permission_classes = [permissions.IsAdminUser]

    def get(self, request, prompt_key):
        try:
            v1 = int(request.query_params.get("v1", 0))
            v2 = int(request.query_params.get("v2", 0))
        except (ValueError, TypeError):
            return Response(
                {"error": "v1 and v2 must be integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not v1 or not v2:
            return Response(
                {"error": "Both v1 and v2 query parameters are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ver1 = AIPromptVersion.objects.filter(prompt__prompt_key=prompt_key, version=v1).first()
        ver2 = AIPromptVersion.objects.filter(prompt__prompt_key=prompt_key, version=v2).first()

        if not ver1 or not ver2:
            return Response(
                {"error": "One or both versions not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "prompt_key": prompt_key,
                "v1": AIPromptVersionSerializer(ver1).data,
                "v2": AIPromptVersionSerializer(ver2).data,
            }
        )


# ---------------------------------------------------------------------------
# Execution Logs
# ---------------------------------------------------------------------------


class AIExecutionLogListView(generics.ListAPIView):
    """List AI execution logs with optional filtering."""

    permission_classes = [permissions.IsAdminUser]
    serializer_class = AIExecutionLogSerializer

    def get_queryset(self):
        qs = AIExecutionLog.objects.select_related("user").all()

        # Filter by feature
        feature_key = self.request.query_params.get("feature_key")
        if feature_key:
            qs = qs.filter(feature_key=feature_key)

        # Filter by provider
        provider = self.request.query_params.get("provider")
        if provider:
            qs = qs.filter(provider=provider)

        # Filter by status
        exec_status = self.request.query_params.get("status")
        if exec_status:
            qs = qs.filter(status=exec_status)

        # Filter by user
        user_id = self.request.query_params.get("user_id")
        if user_id:
            qs = qs.filter(user_id=user_id)

        # Filter by prompt
        prompt_key = self.request.query_params.get("prompt_key")
        if prompt_key:
            qs = qs.filter(prompt_key=prompt_key)

        # Filter by execution_id
        execution_id = self.request.query_params.get("execution_id")
        if execution_id:
            qs = qs.filter(execution_id=execution_id)

        # Limit results
        try:
            limit = min(int(self.request.query_params.get("limit", 100)), 500)
        except (ValueError, TypeError):
            limit = 100
        return qs[:limit]


class AIExecutionLogDetailView(generics.RetrieveAPIView):
    """Retrieve a single execution log by execution_id."""

    permission_classes = [permissions.IsAdminUser]
    serializer_class = AIExecutionLogSerializer
    queryset = AIExecutionLog.objects.all()
    lookup_field = "execution_id"


# ---------------------------------------------------------------------------
# Provider Health
# ---------------------------------------------------------------------------


class ProviderHealthListView(generics.ListAPIView):
    """List provider health records with optional filtering."""

    permission_classes = [permissions.IsAdminUser]
    serializer_class = ProviderHealthSerializer

    def get_queryset(self):
        qs = ProviderHealth.objects.all()

        # Filter by provider
        provider = self.request.query_params.get("provider")
        if provider:
            qs = qs.filter(provider=provider)

        # Filter by feature
        feature_key = self.request.query_params.get("feature_key")
        if feature_key:
            qs = qs.filter(feature_key=feature_key)

        # Filter by health status
        is_healthy = self.request.query_params.get("is_healthy")
        if is_healthy is not None:
            qs = qs.filter(is_healthy=is_healthy.lower() == "true")

        return qs


class ProviderStatsView(APIView):
    """Get aggregated provider statistics for a time window."""

    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        feature_key = request.query_params.get("feature_key")
        provider = request.query_params.get("provider")
        try:
            hours = int(request.query_params.get("hours", 24))
        except (ValueError, TypeError):
            hours = 24

        stats = get_provider_stats(
            feature_id=feature_key,
            provider=provider,
            hours=hours,
        )
        serializer = ProviderStatsSerializer(stats)
        return Response(serializer.data)


class UpdateProviderHealthView(APIView):
    """Manually trigger provider health aggregation."""

    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        try:
            hours = int(request.data.get("hours", 1))
        except (ValueError, TypeError):
            hours = 1
        updated = update_provider_health(hours=hours)
        return Response(
            {"updated": updated, "message": f"Updated {updated} provider health records."},
            status=status.HTTP_200_OK,
        )
