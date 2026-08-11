from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import SharedWishlistView, WishlistShareInfoView, WishlistViewSet

router = DefaultRouter()
router.register("", WishlistViewSet, basename="wishlist")

urlpatterns = [
    path("share-info/", WishlistShareInfoView.as_view(), name="wishlist-share-info"),
    path("share/<uuid:token>/", SharedWishlistView.as_view(), name="wishlist-share"),
    *router.urls,
]
