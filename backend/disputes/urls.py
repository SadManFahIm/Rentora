from django.urls import path

from .views import (
    DisputeAdminActionView,
    DisputeAdminListView,
    DisputeDetailView,
    DisputeEvidenceView,
    DisputeListCreateView,
)

urlpatterns = [
    path("", DisputeListCreateView.as_view(), name="dispute-list-create"),
    path("admin/", DisputeAdminListView.as_view(), name="dispute-admin-list"),
    path("admin/<int:pk>/action/", DisputeAdminActionView.as_view(), name="dispute-admin-action"),
    path("<int:pk>/", DisputeDetailView.as_view(), name="dispute-detail"),
    path("<int:pk>/evidence/", DisputeEvidenceView.as_view(), name="dispute-evidence"),
]
