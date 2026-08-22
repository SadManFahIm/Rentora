from django.urls import path

from .views import PlanListView, SubscriptionActionView, SubscriptionMeView

urlpatterns = [
    path("plans/", PlanListView.as_view(), name="subscription-plans"),
    path("subscription/me/", SubscriptionMeView.as_view(), name="subscription-me"),
    path(
        "subscription/<int:pk>/cancel/",
        SubscriptionActionView.as_view(),
        name="subscription-cancel",
    ),
    path(
        "subscription/<int:pk>/renew/",
        SubscriptionActionView.as_view(),
        name="subscription-renew",
    ),
]
