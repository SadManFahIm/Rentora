from django.urls import path

from .views import (
    AddonOrderActionView,
    AddonOrderListView,
    AddonServiceDetailView,
    AddonServiceListView,
    MarketplaceRecommendView,
    ProviderMeView,
    ProviderRegistrationView,
)

urlpatterns = [
    path(
        "providers/register/",
        ProviderRegistrationView.as_view(),
        name="marketplace-provider-register",
    ),
    path("providers/me/", ProviderMeView.as_view(), name="marketplace-provider-me"),
    path("services/", AddonServiceListView.as_view(), name="marketplace-services"),
    path("services/<int:pk>/", AddonServiceDetailView.as_view(), name="marketplace-service-detail"),
    path("orders/", AddonOrderListView.as_view(), name="marketplace-orders"),
    path(
        "orders/<int:pk>/action/", AddonOrderActionView.as_view(), name="marketplace-order-action"
    ),
    path("recommend/", MarketplaceRecommendView.as_view(), name="marketplace-recommend"),
]
