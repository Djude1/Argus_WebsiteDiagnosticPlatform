from rest_framework.routers import DefaultRouter

from apps.rebuild.views import SiteRebuildViewSet

router = DefaultRouter()
router.register("rebuilds", SiteRebuildViewSet, basename="rebuild")

urlpatterns = router.urls
