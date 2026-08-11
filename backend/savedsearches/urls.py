from rest_framework.routers import DefaultRouter

from .views import SavedSearchViewSet

router = DefaultRouter()
router.register("", SavedSearchViewSet, basename="saved-search")

urlpatterns = router.urls
