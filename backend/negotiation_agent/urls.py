"""AI Negotiation Agent — API routes (Phase 19.4).

All paths live under ``/api/v1/negotiation/`` (see config/urls.py).
"""

from django.urls import path

from .views import (
    NegotiationCancelView,
    NegotiationChatView,
    NegotiationConversationDetailView,
    NegotiationConversationListView,
    NegotiationDetailView,
    NegotiationListView,
    NegotiationRejectView,
    NegotiationRunStatusView,
    OfferRejectView,
    ProposalConsentView,
    ProposalRejectView,
)

urlpatterns = [
    path("chat/", NegotiationChatView.as_view(), name="negotiation-chat"),
    path(
        "conversations/",
        NegotiationConversationListView.as_view(),
        name="negotiation-conversations",
    ),
    path(
        "conversations/<int:pk>/",
        NegotiationConversationDetailView.as_view(),
        name="negotiation-conversation-detail",
    ),
    path("runs/<uuid:run_key>/", NegotiationRunStatusView.as_view(), name="negotiation-run-status"),
    path("negotiations/", NegotiationListView.as_view(), name="negotiation-list"),
    path(
        "negotiations/<str:negotiation_key>/",
        NegotiationDetailView.as_view(),
        name="negotiation-detail",
    ),
    path(
        "negotiations/<str:negotiation_key>/reject/",
        NegotiationRejectView.as_view(),
        name="negotiation-reject",
    ),
    path(
        "negotiations/<str:negotiation_key>/cancel/",
        NegotiationCancelView.as_view(),
        name="negotiation-cancel",
    ),
    path(
        "negotiations/<str:negotiation_key>/offers/<str:offer_key>/reject/",
        OfferRejectView.as_view(),
        name="negotiation-offer-reject",
    ),
    path(
        "proposals/<str:proposal_key>/approve/",
        ProposalConsentView.as_view(),
        name="negotiation-proposal-approve",
    ),
    path(
        "proposals/<str:proposal_key>/reject/",
        ProposalRejectView.as_view(),
        name="negotiation-proposal-reject",
    ),
]
