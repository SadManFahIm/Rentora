from django.urls import path

from .views import FeatureFlagDetailView, FeatureFlagListView

urlpatterns = [
    path("", FeatureFlagListView.as_view(), name="feature-flag-list"),
    path("<str:key>/", FeatureFlagDetailView.as_view(), name="feature-flag-detail"),
]
