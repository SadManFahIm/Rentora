from django.urls import path

from .views import (
    DriftMetricListView,
    ModelVersionListView,
    RetrainRequestListView,
    RunDriftCheckView,
)

urlpatterns = [
    path("models/", ModelVersionListView.as_view(), name="ml-models-list"),
    path("drift/", DriftMetricListView.as_view(), name="ml-drift-list"),
    path("retrain/", RetrainRequestListView.as_view(), name="ml-retrain-list"),
    path("drift/check/", RunDriftCheckView.as_view(), name="ml-drift-check"),
]
