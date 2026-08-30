"""Rentora AI Rental Agent — API routes (Phase 19.2).

Mounted at ``api/v1/rental/``:
* ``POST /chat/``              — start a conversation / send a turn
* ``GET  /conversations/``     — the user's own conversations
* ``GET  /conversations/<pk>/``— enriched detail (cards, proposals, chips)
* ``GET  /runs/<run_key>/``    — one run's status
* ``POST /proposals/<key>/approve/`` — tenant self-consent (bookmark)
* ``POST /proposals/<key>/reject/``  — tenant decline (bookmark)
"""

from django.urls import path

from . import views

app_name = "rental_agent"

urlpatterns = [
    path("chat/", views.RentalChatView.as_view(), name="chat"),
    path("conversations/", views.ConversationListView.as_view(), name="conversations"),
    path(
        "conversations/<int:pk>/",
        views.ConversationDetailView.as_view(),
        name="conversation-detail",
    ),
    path("runs/<uuid:run_key>/", views.RunStatusView.as_view(), name="run-status"),
    path(
        "proposals/<uuid:proposal_key>/approve/",
        views.ProposalConsentView.as_view(),
        name="proposal-approve",
    ),
    path(
        "proposals/<uuid:proposal_key>/reject/",
        views.ProposalRejectView.as_view(),
        name="proposal-reject",
    ),
]
