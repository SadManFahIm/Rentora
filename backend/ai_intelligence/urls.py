"""AI Intelligence Layer — Phase 18.1 + 18.2 + 18.3 URL configuration."""

from django.urls import path

from . import views

app_name = "ai_intelligence"

urlpatterns = [
    # Feature registry
    path(
        "features/",
        views.AIFeatureRegistryListView.as_view(),
        name="feature-list",
    ),
    path(
        "features/<str:feature_id>/",
        views.AIFeatureRegistryDetailView.as_view(),
        name="feature-detail",
    ),
    path(
        "features/<str:feature_id>/update/",
        views.AIFeatureRegistryUpdateView.as_view(),
        name="feature-update",
    ),
    # Prompt registry
    path(
        "prompts/",
        views.AIPromptListView.as_view(),
        name="prompt-list",
    ),
    path(
        "prompts/<str:prompt_key>/",
        views.AIPromptDetailView.as_view(),
        name="prompt-detail",
    ),
    path(
        "prompts/<str:prompt_key>/versions/",
        views.AIPromptVersionListView.as_view(),
        name="prompt-version-list",
    ),
    path(
        "prompts/<str:prompt_key>/versions/<int:version>/",
        views.AIPromptVersionDetailView.as_view(),
        name="prompt-version-detail",
    ),
    path(
        "prompts/<str:prompt_key>/versions/<int:version>/activate/",
        views.AIPromptActivateView.as_view(),
        name="prompt-version-activate",
    ),
    path(
        "prompts/<str:prompt_key>/deactivate/",
        views.AIPromptDeactivateView.as_view(),
        name="prompt-version-deactivate",
    ),
    path(
        "prompts/<str:prompt_key>/rollback/",
        views.AIPromptRollbackView.as_view(),
        name="prompt-rollback",
    ),
    path(
        "prompts/<str:prompt_key>/compare/",
        views.AIPromptCompareView.as_view(),
        name="prompt-compare",
    ),
    # Execution logs
    path(
        "logs/",
        views.AIExecutionLogListView.as_view(),
        name="log-list",
    ),
    path(
        "logs/<uuid:execution_id>/",
        views.AIExecutionLogDetailView.as_view(),
        name="log-detail",
    ),
    # Provider health
    path(
        "health/",
        views.ProviderHealthListView.as_view(),
        name="health-list",
    ),
    path(
        "health/stats/",
        views.ProviderStatsView.as_view(),
        name="health-stats",
    ),
    path(
        "health/update/",
        views.UpdateProviderHealthView.as_view(),
        name="health-update",
    ),
    # Phase 18.3 — Evaluation Framework
    # Metrics
    path(
        "eval/metrics/",
        views.EvaluationMetricListView.as_view(),
        name="eval-metric-list",
    ),
    # Datasets
    path(
        "eval/datasets/",
        views.EvaluationDatasetListView.as_view(),
        name="eval-dataset-list",
    ),
    path(
        "eval/datasets/<int:pk>/",
        views.EvaluationDatasetDetailView.as_view(),
        name="eval-dataset-detail",
    ),
    path(
        "eval/datasets/<int:dataset_id>/cases/",
        views.EvaluationCaseListView.as_view(),
        name="eval-case-list",
    ),
    # Thresholds
    path(
        "eval/thresholds/",
        views.EvaluationThresholdListView.as_view(),
        name="eval-threshold-list",
    ),
    # Evaluation runs
    path(
        "eval/runs/",
        views.EvaluationRunListView.as_view(),
        name="eval-run-list",
    ),
    path(
        "eval/runs/<int:pk>/",
        views.EvaluationRunDetailView.as_view(),
        name="eval-run-detail",
    ),
    path(
        "eval/runs/<int:run_id>/execute/",
        views.EvaluationRunExecuteView.as_view(),
        name="eval-run-execute",
    ),
    path(
        "eval/runs/<int:run_id>/cancel/",
        views.EvaluationRunCancelView.as_view(),
        name="eval-run-cancel",
    ),
    path(
        "eval/runs/<int:run_id>/results/",
        views.EvaluationCaseResultListView.as_view(),
        name="eval-case-result-list",
    ),
    # Comparisons
    path(
        "eval/compare/runs/",
        views.RunComparisonView.as_view(),
        name="eval-compare-runs",
    ),
    path(
        "eval/compare/models/",
        views.ModelComparisonView.as_view(),
        name="eval-compare-models",
    ),
    path(
        "eval/compare/prompts/",
        views.PromptComparisonView.as_view(),
        name="eval-compare-prompts",
    ),
    # Regression + baselines
    path(
        "eval/regression/check/",
        views.RegressionCheckView.as_view(),
        name="eval-regression-check",
    ),
    path(
        "eval/baselines/",
        views.BaselineListView.as_view(),
        name="eval-baseline-list",
    ),
]
