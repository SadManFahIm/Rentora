"""Agent SDK — Phase 19.0 URL configuration."""

from django.urls import path

from . import views

app_name = "agents"

urlpatterns = [
    # Public catalog (audience-aware)
    path("", views.AgentCatalogView.as_view(), name="catalog"),
    path("agents/<str:key>/", views.AgentCatalogDetailView.as_view(), name="catalog-detail"),
    # Admin — registry
    path("admin/registry/", views.AgentRegistryListView.as_view(), name="registry-list"),
    path(
        "admin/registry/<str:key>/",
        views.AgentRegistryDetailView.as_view(),
        name="registry-detail",
    ),
    path(
        "admin/registry/<str:key>/activate/",
        views.AgentActivateView.as_view(),
        name="registry-activate",
    ),
    path(
        "admin/registry/<str:key>/deactivate/",
        views.AgentDeactivateView.as_view(),
        name="registry-deactivate",
    ),
    # Conversations + runs (own)
    path("conversations/", views.ConversationListCreateView.as_view(), name="conversation-list"),
    path(
        "conversations/<int:pk>/",
        views.ConversationDetailView.as_view(),
        name="conversation-detail",
    ),
    path(
        "conversations/<int:pk>/messages/",
        views.ConversationMessagesView.as_view(),
        name="conversation-messages",
    ),
    path(
        "conversations/<int:pk>/runs/",
        views.ConversationRunsView.as_view(),
        name="conversation-runs",
    ),
    # Admin — runs / tool calls / proposals
    path("admin/runs/", views.AgentRunListView.as_view(), name="run-list"),
    path("admin/runs/<uuid:run_key>/", views.AgentRunDetailView.as_view(), name="run-detail"),
    path(
        "admin/runs/<uuid:run_key>/evaluate/",
        views.AgentRunEvaluateView.as_view(),
        name="run-evaluate",
    ),
    path(
        "admin/tool-calls/",
        views.AgentToolCallListView.as_view(),
        name="tool-call-list",
    ),
    path("admin/proposals/", views.ProposalListView.as_view(), name="proposal-list"),
    path(
        "admin/proposals/<uuid:proposal_key>/",
        views.ProposalDetailView.as_view(),
        name="proposal-detail",
    ),
    path(
        "admin/proposals/<uuid:proposal_key>/approve/",
        views.ProposalApproveView.as_view(),
        name="proposal-approve",
    ),
    path(
        "admin/proposals/<uuid:proposal_key>/reject/",
        views.ProposalRejectView.as_view(),
        name="proposal-reject",
    ),
    path(
        "admin/proposals/<uuid:proposal_key>/apply/",
        views.ProposalApplyView.as_view(),
        name="proposal-apply",
    ),
]
