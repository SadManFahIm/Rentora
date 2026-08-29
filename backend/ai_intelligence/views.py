"""AI Intelligence Layer — Phase 18.1 + 18.2 + 18.3 + 18.4 API views.

All views require admin authentication (IsAdminUser).
"""

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    AIAlert,
    AIAlertRule,
    AIExecutionLog,
    AIFeatureRegistry,
    AIPrompt,
    AIPromptVersion,
    EvaluationCase,
    EvaluationDataset,
    EvaluationMetric,
    EvaluationRun,
    EvaluationThreshold,
    ProviderHealth,
)
from .serializers import (
    AIAlertRuleSerializer,
    AIAlertSerializer,
    AIExecutionLogSerializer,
    AIFeatureRegistrySerializer,
    AIPromptCreateSerializer,
    AIPromptDetailSerializer,
    AIPromptListSerializer,
    AIPromptVersionCreateSerializer,
    AIPromptVersionSerializer,
    AlertLifecycleActionSerializer,
    EvaluationCaseResultSerializer,
    EvaluationCaseSerializer,
    EvaluationDatasetCreateSerializer,
    EvaluationDatasetDetailSerializer,
    EvaluationDatasetListSerializer,
    EvaluationMetricSerializer,
    EvaluationRunCreateSerializer,
    EvaluationRunDetailSerializer,
    EvaluationRunListSerializer,
    EvaluationThresholdSerializer,
    ModelComparisonSerializer,
    PromptComparisonSerializer,
    ProviderHealthSerializer,
    ProviderStatsSerializer,
    RegressionCheckSerializer,
    RunComparisonSerializer,
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


# ---------------------------------------------------------------------------
# Phase 18.3 — Evaluation Framework Views
# ---------------------------------------------------------------------------


class _AdminPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or getattr(request.user, "role", "") == "admin")
        )


class EvaluationMetricListView(generics.ListCreateAPIView):
    """List all evaluation metrics or create a new one."""

    permission_classes = [_AdminPermission]
    queryset = EvaluationMetric.objects.all()
    serializer_class = EvaluationMetricSerializer


class EvaluationDatasetListView(generics.ListCreateAPIView):
    """List all evaluation datasets or create a new one."""

    permission_classes = [_AdminPermission]

    def get_queryset(self):
        return EvaluationDataset.objects.select_related("feature").all()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return EvaluationDatasetCreateSerializer
        return EvaluationDatasetListSerializer

    def create(self, request, *args, **kwargs):
        ser = EvaluationDatasetCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        from .services import create_dataset

        try:
            dataset = create_dataset(
                dataset_key=ser.validated_data["dataset_key"],
                name=ser.validated_data["name"],
                feature_id=ser.validated_data.get("feature_id"),
                description=ser.validated_data.get("description", ""),
                dataset_type=ser.validated_data.get("dataset_type", "synthetic"),
                created_by=request.user,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            EvaluationDatasetListSerializer(dataset).data,
            status=status.HTTP_201_CREATED,
        )


class EvaluationDatasetDetailView(generics.RetrieveAPIView):
    """Get evaluation dataset detail with cases."""

    permission_classes = [_AdminPermission]
    queryset = EvaluationDataset.objects.select_related("feature")
    serializer_class = EvaluationDatasetDetailSerializer
    lookup_field = "pk"


class EvaluationCaseListView(generics.ListAPIView):
    """List evaluation cases for a dataset."""

    permission_classes = [_AdminPermission]
    serializer_class = EvaluationCaseSerializer

    def get_queryset(self):
        dataset_id = self.kwargs.get("dataset_id")
        return EvaluationCase.objects.filter(dataset_id=dataset_id)


class EvaluationThresholdListView(generics.ListCreateAPIView):
    """List or create evaluation thresholds."""

    permission_classes = [_AdminPermission]
    serializer_class = EvaluationThresholdSerializer

    def get_queryset(self):
        feature_id = self.request.query_params.get("feature_id")
        qs = EvaluationThreshold.objects.select_related("feature", "metric").all()
        if feature_id:
            qs = qs.filter(feature__feature_id=feature_id)
        return qs

    def create(self, request, *args, **kwargs):
        from .services import set_threshold

        feature_id = request.data.get("feature_id")
        metric_key = request.data.get("metric_key")
        threshold_min = request.data.get("threshold_min")
        threshold_max = request.data.get("threshold_max")
        try:
            threshold = set_threshold(
                feature_id=feature_id,
                metric_key=metric_key,
                threshold_min=threshold_min,
                threshold_max=threshold_max,
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            EvaluationThresholdSerializer(threshold).data,
            status=status.HTTP_201_CREATED,
        )


class EvaluationRunListView(generics.ListCreateAPIView):
    """List evaluation runs or create a new one."""

    permission_classes = [_AdminPermission]

    def get_queryset(self):
        qs = EvaluationRun.objects.select_related("feature", "dataset").all()
        feature_id = self.request.query_params.get("feature_id")
        if feature_id:
            qs = qs.filter(feature__feature_id=feature_id)
        run_status = self.request.query_params.get("status")
        if run_status:
            qs = qs.filter(status=run_status)
        return qs

    def get_serializer_class(self):
        if self.request.method == "POST":
            return EvaluationRunCreateSerializer
        return EvaluationRunListSerializer

    def create(self, request, *args, **kwargs):
        ser = EvaluationRunCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        from .services import create_evaluation_run

        try:
            run = create_evaluation_run(
                feature_id=ser.validated_data.get("feature_id"),
                dataset_key=ser.validated_data.get("dataset_key"),
                dataset_version=ser.validated_data.get("dataset_version"),
                prompt_key=ser.validated_data.get("prompt_key"),
                prompt_version=ser.validated_data.get("prompt_version"),
                model_name=ser.validated_data.get("model_name", ""),
                provider=ser.validated_data.get("provider", ""),
                baseline_run_id=ser.validated_data.get("baseline_run_id"),
                experiment_key=ser.validated_data.get("experiment_key", ""),
                variant_key=ser.validated_data.get("variant_key", ""),
                max_cases=ser.validated_data.get("max_cases", 1000),
                timeout_seconds=ser.validated_data.get("timeout_seconds", 3600),
                created_by=request.user,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            EvaluationRunListSerializer(run).data,
            status=status.HTTP_201_CREATED,
        )


class EvaluationRunDetailView(generics.RetrieveAPIView):
    """Get evaluation run detail with case results."""

    permission_classes = [_AdminPermission]

    def get_queryset(self):
        return EvaluationRun.objects.select_related("feature", "dataset").prefetch_related(
            "case_results"
        )

    serializer_class = EvaluationRunDetailSerializer


class EvaluationRunExecuteView(APIView):
    """Execute an evaluation run (synchronous for small, async for large)."""

    permission_classes = [_AdminPermission]

    def post(self, request, run_id: int):
        from .services import execute_evaluation_run

        result = execute_evaluation_run(run_id)
        if result.get("status") == "error":
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)


class EvaluationRunCancelView(APIView):
    """Cancel a pending or running evaluation."""

    permission_classes = [_AdminPermission]

    def post(self, request, run_id: int):
        from .services import cancel_evaluation_run

        cancelled = cancel_evaluation_run(run_id)
        if not cancelled:
            return Response(
                {"error": "Run not found or cannot be cancelled"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"status": "cancelled"}, status=status.HTTP_200_OK)


class EvaluationCaseResultListView(generics.ListAPIView):
    """List case results for an evaluation run."""

    permission_classes = [_AdminPermission]
    serializer_class = EvaluationCaseResultSerializer

    def get_queryset(self):
        from .models import EvaluationCaseResult

        run_id = self.kwargs.get("run_id")
        qs = EvaluationCaseResult.objects.filter(run_id=run_id)
        passed = self.request.query_params.get("passed")
        if passed is not None:
            qs = qs.filter(passed=passed.lower() in ("true", "1"))
        return qs


class RunComparisonView(APIView):
    """Compare two evaluation runs."""

    permission_classes = [_AdminPermission]

    def post(self, request):
        ser = RunComparisonSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        from .services import compare_runs

        result = compare_runs(
            ser.validated_data["run_a_id"],
            ser.validated_data["run_b_id"],
        )
        if "error" in result:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class ModelComparisonView(APIView):
    """Compare two models on the same feature and dataset."""

    permission_classes = [_AdminPermission]

    def post(self, request):
        ser = ModelComparisonSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        from .services import compare_models

        result = compare_models(
            ser.validated_data["feature_id"],
            ser.validated_data["model_a"],
            ser.validated_data["model_b"],
            ser.validated_data["dataset_key"],
        )
        if "error" in result:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class PromptComparisonView(APIView):
    """Compare two prompt versions on the same dataset."""

    permission_classes = [_AdminPermission]

    def post(self, request):
        ser = PromptComparisonSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        from .services import compare_prompts

        result = compare_prompts(
            ser.validated_data["prompt_key"],
            ser.validated_data["version_a"],
            ser.validated_data["version_b"],
            ser.validated_data["dataset_key"],
        )
        if "error" in result:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class RegressionCheckView(APIView):
    """Check a run for quality regressions."""

    permission_classes = [_AdminPermission]

    def post(self, request):
        ser = RegressionCheckSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        from .services import check_regression

        result = check_regression(ser.validated_data["run_id"])
        if "error" in result:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class BaselineListView(APIView):
    """List latest baselines for a feature."""

    permission_classes = [_AdminPermission]

    def get(self, request):
        feature_id = request.query_params.get("feature_id")
        if not feature_id:
            return Response(
                {"error": "feature_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from .services import get_latest_baselines

        runs = get_latest_baselines(feature_id)
        return Response(EvaluationRunListSerializer(runs, many=True).data)


# ---------------------------------------------------------------------------
# Phase 18.4 — AI Intelligence Dashboard
# ---------------------------------------------------------------------------


class _DashboardBase(APIView):
    """Shared guards/helpers for dashboard endpoints (admin-only)."""

    permission_classes = [_AdminPermission]

    def _days(self, request, default: int = 30) -> int:
        try:
            return min(max(int(request.query_params.get("days", default)), 1), 365)
        except (ValueError, TypeError):
            return default


class AIDashboardSummaryView(_DashboardBase):
    """Overview KPIs for the AI Intelligence Dashboard."""

    def get(self, request):
        from .dashboard import get_ai_summary

        data = get_ai_summary(
            days=self._days(request, 30),
            feature_id=request.query_params.get("feature_id") or None,
            provider=request.query_params.get("provider") or None,
            model=request.query_params.get("model") or None,
        )
        return Response(data)


class AIFeatureHealthListView(_DashboardBase):
    """Health summary for every registered AI feature."""

    def get(self, request):
        from .dashboard import get_feature_health_list

        return Response(get_feature_health_list(days=self._days(request, 30)))


class AIFeatureHealthDetailView(_DashboardBase):
    """Drill-down for a single AI feature."""

    def get(self, request, feature_id: str):
        from .dashboard import get_feature_health_detail

        return Response(get_feature_health_detail(feature_id, days=self._days(request, 30)))


class AIModelHealthView(_DashboardBase):
    """Model health view: telemetry + evaluation per (provider, model)."""

    def get(self, request):
        from .dashboard import get_model_health

        return Response(get_model_health(days=self._days(request, 30)))


class AIModelCompareView(_DashboardBase):
    """Compare two model versions on their latest completed evaluations."""

    def get(self, request):
        from .dashboard import compare_model_versions

        provider = request.query_params.get("provider")
        model = request.query_params.get("model")
        version_a = request.query_params.get("version_a")
        version_b = request.query_params.get("version_b")
        if not (provider and model and version_a and version_b):
            return Response(
                {"error": "provider, model, version_a and version_b query params are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            compare_model_versions(
                provider=provider,
                model=model,
                version_a=version_a,
                version_b=version_b,
                days=self._days(request, 90),
            )
        )


class AIProviderHealthView(_DashboardBase):
    """Provider-level operational health from telemetry + health windows."""

    def get(self, request):
        from .dashboard import get_provider_health

        return Response(get_provider_health(days=self._days(request, 30)))


class AICostDashboardView(_DashboardBase):
    """AI cost intelligence (ESTIMATED USD, never claimed as billing)."""

    def get(self, request):
        from .dashboard import get_cost_dashboard

        return Response(get_cost_dashboard(days=self._days(request, 30)))


class AIPerformanceDashboardView(_DashboardBase):
    """Latency dashboard: overall, per feature/model/provider, daily trend."""

    def get(self, request):
        from .dashboard import get_performance_dashboard

        return Response(get_performance_dashboard(days=self._days(request, 30)))


class AIErrorDashboardView(_DashboardBase):
    """Error/reliability dashboard."""

    def get(self, request):
        from .dashboard import get_error_dashboard

        return Response(
            get_error_dashboard(
                days=self._days(request, 30),
                feature_id=request.query_params.get("feature_id") or None,
            )
        )


class AIQualityDashboardView(_DashboardBase):
    """Latest evaluation/quality per feature."""

    def get(self, request):
        from .dashboard import get_quality_dashboard

        return Response(
            get_quality_dashboard(
                feature_id=request.query_params.get("feature_id") or None,
                days=self._days(request, 180),
            )
        )


class AIDriftStatusView(_DashboardBase):
    """Latest model drift status (derived from Phase 17 metrics)."""

    def get(self, request):
        from .dashboard import get_drift_status

        return Response(get_drift_status(model_name=request.query_params.get("model_name") or None))


class AIPromptHealthView(_DashboardBase):
    """Prompt health: active/previous version, feature, model, latest eval."""

    def get(self, request):
        from .dashboard import get_prompt_health

        return Response(get_prompt_health(days=self._days(request, 90)))


# ---------------------------------------------------------------------------
# Phase 18.4 — AI Alerts
# ---------------------------------------------------------------------------


class AIAlertRuleListCreateView(generics.ListCreateAPIView):
    """List alert rules or create a new one (admin only)."""

    permission_classes = [_AdminPermission]
    queryset = AIAlertRule.objects.select_related("feature").all()
    serializer_class = AIAlertRuleSerializer

    def get_queryset(self):
        qs = AIAlertRule.objects.select_related("feature").all()
        alert_type = self.request.query_params.get("alert_type")
        metric = self.request.query_params.get("metric")
        enabled = self.request.query_params.get("enabled")
        if alert_type:
            qs = qs.filter(alert_type=alert_type)
        if metric:
            qs = qs.filter(metric=metric)
        if enabled is not None:
            qs = qs.filter(is_enabled=enabled.lower() in ("true", "1"))
        return qs

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        rule = ser.save(created_by=request.user)
        from audit.services import log_action

        log_action(
            actor=request.user,
            action="ai_intelligence.alert_rule_created",
            target=rule,
            request=request,
            detail={
                "rule_key": rule.rule_key,
                "metric": rule.metric,
                "threshold": rule.threshold_value,
                "severity": rule.severity,
            },
        )
        return Response(AIAlertRuleSerializer(rule).data, status=status.HTTP_201_CREATED)


class AIAlertRuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get / update / delete a single alert rule (admin only)."""

    permission_classes = [_AdminPermission]
    queryset = AIAlertRule.objects.all()
    serializer_class = AIAlertRuleSerializer

    def perform_update(self, serializer):
        from audit.services import log_action

        rule = serializer.save()
        log_action(
            actor=self.request.user,
            action="ai_intelligence.alert_rule_updated",
            target=rule,
            request=self.request,
            detail={
                "rule_key": rule.rule_key,
                "metric": rule.metric,
                "threshold": rule.threshold_value,
                "is_enabled": rule.is_enabled,
            },
        )

    def perform_destroy(self, instance):
        from audit.services import log_action

        log_action(
            actor=self.request.user,
            action="ai_intelligence.alert_rule_deleted",
            target=instance,
            request=self.request,
            detail={"rule_key": instance.rule_key},
        )
        instance.delete()


class AIAlertListView(generics.ListAPIView):
    """List AI alerts with filters + pagination (admin only)."""

    permission_classes = [_AdminPermission]
    serializer_class = AIAlertSerializer

    def get_queryset(self):
        qs = AIAlert.objects.select_related("rule", "feature", "acknowledged_by").all()
        severity = self.request.query_params.get("severity")
        alert_status = self.request.query_params.get("status")
        alert_type = self.request.query_params.get("alert_type")
        feature_id = self.request.query_params.get("feature_id")
        if severity:
            qs = qs.filter(severity=severity)
        if alert_status:
            qs = qs.filter(status=alert_status)
        if alert_type:
            qs = qs.filter(alert_type=alert_type)
        if feature_id:
            qs = qs.filter(feature__feature_id=feature_id)
        return qs


class AIAlertDetailView(generics.RetrieveAPIView):
    """Get a single AI alert (admin only)."""

    permission_classes = [_AdminPermission]
    queryset = AIAlert.objects.select_related("rule", "feature").all()
    serializer_class = AIAlertSerializer


class AIAlertAcknowledgeView(APIView):
    """Acknowledge an alert (admin only, audited)."""

    permission_classes = [_AdminPermission]

    def post(self, request, pk: int):
        from .alerts import acknowledge_alert

        ser = AlertLifecycleActionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            alert = acknowledge_alert(
                pk, request.user, note=ser.validated_data["note"], request=request
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        if not alert:
            return Response({"error": "Alert not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(AIAlertSerializer(alert).data)


class AIAlertResolveView(APIView):
    """Resolve an alert (admin only, audited)."""

    permission_classes = [_AdminPermission]

    def post(self, request, pk: int):
        from .alerts import resolve_alert

        ser = AlertLifecycleActionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            alert = resolve_alert(
                pk, request.user, note=ser.validated_data["note"], request=request
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        if not alert:
            return Response({"error": "Alert not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(AIAlertSerializer(alert).data)


class AIAlertSuppressView(APIView):
    """Suppress an alert (admin only, audited)."""

    permission_classes = [_AdminPermission]

    def post(self, request, pk: int):
        from .alerts import suppress_alert

        ser = AlertLifecycleActionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            alert = suppress_alert(
                pk, request.user, note=ser.validated_data["note"], request=request
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        if not alert:
            return Response({"error": "Alert not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(AIAlertSerializer(alert).data)


class AIAlertEvaluateView(APIView):
    """Manually evaluate all enabled alert rules (admin only, audited)."""

    permission_classes = [_AdminPermission]

    def post(self, request):
        from .alerts import evaluate_all_rules

        result = evaluate_all_rules(actor=request.user, request=request)
        return Response(result)
