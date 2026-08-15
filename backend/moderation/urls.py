from django.urls import path

from .views import (
    ModerationOverviewView,
    PhotoModerationDecisionView,
    PhotoModerationListView,
    ReviewModerationDecisionView,
    ReviewModerationListView,
)

urlpatterns = [
    path("overview/", ModerationOverviewView.as_view(), name="moderation-overview"),
    path("reviews/", ReviewModerationListView.as_view(), name="moderation-review-list"),
    path(
        "reviews/<int:pk>/decision/",
        ReviewModerationDecisionView.as_view(),
        name="moderation-review-decision",
    ),
    path("photos/", PhotoModerationListView.as_view(), name="moderation-photo-list"),
    path(
        "photos/<int:pk>/decision/",
        PhotoModerationDecisionView.as_view(),
        name="moderation-photo-decision",
    ),
]
