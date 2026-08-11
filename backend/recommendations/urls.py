from django.urls import path

from .views import RecommendationListView, SimilarRoomsView

urlpatterns = [
    path("", RecommendationListView.as_view(), name="recommendations"),
    path("similar/<int:room_id>/", SimilarRoomsView.as_view(), name="similar-rooms"),
]
