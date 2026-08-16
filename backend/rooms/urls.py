from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import CommuteEtaView, RoomViewSet

router = DefaultRouter()
router.register("", RoomViewSet, basename="room")

# The static route must precede router.urls: DefaultRouter's detail pattern
# `^(?P<pk>[^/.]+)/$` would otherwise swallow "eta" as a room pk.
urlpatterns = [
    path("eta/", CommuteEtaView.as_view(), name="commute-eta"),
    *router.urls,
]
