"""AI Intelligence Layer — Phase 18.1 URL configuration."""

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
]
