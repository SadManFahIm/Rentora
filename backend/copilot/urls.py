from django.urls import path

from .views import CopilotChatView, CopilotListingFactsView

urlpatterns = [
    path("chat/", CopilotChatView.as_view(), name="copilot-chat"),
    path("listing/<int:pk>/", CopilotListingFactsView.as_view(), name="copilot-listing-facts"),
]
