from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    KycDocumentFileView,
    KycDocumentListCreateView,
    KycPendingApplicationsView,
    KycReviewView,
    UserViewSet,
)

router = DefaultRouter()
router.register("", UserViewSet, basename="user")

urlpatterns = [
    # Literal KYC paths come *before* the router's generic <pk> route so
    # "kyc/documents/" can't be captured as a user pk.
    path("kyc/documents/", KycDocumentListCreateView.as_view(), name="kyc-documents"),
    path(
        "kyc/documents/<int:document_id>/file/",
        KycDocumentFileView.as_view(),
        name="kyc-document-file",
    ),
    path("kyc/pending/", KycPendingApplicationsView.as_view(), name="kyc-pending"),
    path("kyc/<int:user_id>/review/", KycReviewView.as_view(), name="kyc-review"),
    *router.urls,
]
