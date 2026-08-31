"""Listing Autopilot URL routing (Phase 19.3) — mounted at ``api/v1/autopilot/``."""

from django.urls import path

from .views import (
    AutopilotAnalysesView,
    AutopilotOverviewView,
    AutopilotProposalsView,
    ProposalApproveView,
    ProposalBulkApproveView,
    ProposalRejectView,
)

urlpatterns = [
    path("overview/", AutopilotOverviewView.as_view(), name="autopilot-overview"),
    path("proposals/", AutopilotProposalsView.as_view(), name="autopilot-proposals"),
    path("analyses/", AutopilotAnalysesView.as_view(), name="autopilot-analyses"),
    path(
        "proposals/bulk-approve/", ProposalBulkApproveView.as_view(), name="autopilot-bulk-approve"
    ),
    path(
        "proposals/<uuid:proposal_key>/approve/",
        ProposalApproveView.as_view(),
        name="autopilot-proposal-approve",
    ),
    path(
        "proposals/<uuid:proposal_key>/reject/",
        ProposalRejectView.as_view(),
        name="autopilot-proposal-reject",
    ),
]
