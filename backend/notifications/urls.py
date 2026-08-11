from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import NotificationViewSet, PushSubscriptionView

router = DefaultRouter()
router.register("", NotificationViewSet, basename="notification")

urlpatterns = [
    path("push/subscribe/", PushSubscriptionView.as_view(), name="push-subscribe"),
    *router.urls,
]
