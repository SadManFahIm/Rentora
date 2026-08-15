from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    KycAuditTrailView,
    KycDocumentFileView,
    KycDocumentListCreateView,
    KycPendingApplicationsView,
    KycReviewView,
    KycSlaStatsView,
    ReferralInfoView,
    TenantKycFileView,
    TenantKycPendingApplicationsView,
    TenantKycReviewView,
    TenantKycView,
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
    path("kyc/audit/", KycAuditTrailView.as_view(), name="kyc-audit"),
    path("kyc/sla/", KycSlaStatsView.as_view(), name="kyc-sla"),
    path("kyc/<int:user_id>/review/", KycReviewView.as_view(), name="kyc-review"),
    # Tenant KYC (Phase 12 — two-sided trust): the tenant's own status/upload,
    # the auth-gated document endpoint, and the admin review queue.
    path("tenant-kyc/", TenantKycView.as_view(), name="tenant-kyc"),
    path(
        "tenant-kyc/<int:user_id>/file/",
        TenantKycFileView.as_view(),
        name="tenant-kyc-file",
    ),
    path(
        "tenant-kyc/pending/",
        TenantKycPendingApplicationsView.as_view(),
        name="tenant-kyc-pending",
    ),
    path(
        "tenant-kyc/<int:user_id>/review/",
        TenantKycReviewView.as_view(),
        name="tenant-kyc-review",
    ),
    path("referral/", ReferralInfoView.as_view(), name="referral-info"),
    *router.urls,
]
