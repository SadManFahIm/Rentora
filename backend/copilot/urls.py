from django.urls import path

from .views import (
    AgreementCheckerView,
    CopilotChatView,
    CopilotListingFactsView,
    CopilotShareSummaryView,
    LandlordCopilotView,
    NegotiationAssistantView,
    RentalAdvisorView,
    SupportCopilotView,
)

urlpatterns = [
    path("chat/", CopilotChatView.as_view(), name="copilot-chat"),
    path("support/", SupportCopilotView.as_view(), name="copilot-support"),
    path(
        "listing/<int:pk>/",
        CopilotListingFactsView.as_view(),
        name="copilot-listing-facts",
    ),
    path(
        "share-summary/<int:pk>/",
        CopilotShareSummaryView.as_view(),
        name="copilot-share-summary",
    ),
    path("advisor/", RentalAdvisorView.as_view(), name="copilot-advisor"),
    path("negotiate/", NegotiationAssistantView.as_view(), name="copilot-negotiate"),
    path(
        "agreement-check/",
        AgreementCheckerView.as_view(),
        name="copilot-agreement-check",
    ),
    path("landlord/", LandlordCopilotView.as_view(), name="copilot-landlord"),
]
