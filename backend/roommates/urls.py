from django.urls import path

from .views import (
    RoommateMatchesView,
    RoommateProfileView,
    RoommateRequestActionView,
    RoommateRequestListCreateView,
)

urlpatterns = [
    path("profile/", RoommateProfileView.as_view(), name="roommate-profile"),
    path("matches/", RoommateMatchesView.as_view(), name="roommate-matches"),
    path("requests/", RoommateRequestListCreateView.as_view(), name="roommate-requests"),
    path(
        "requests/<int:request_id>/action/",
        RoommateRequestActionView.as_view(),
        name="roommate-request-action",
    ),
]
