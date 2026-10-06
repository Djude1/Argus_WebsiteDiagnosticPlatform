from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.rebuild.views import SiteRebuildViewSet, shared_rebuild, shared_rebuild_html

router = DefaultRouter()
router.register("rebuilds", SiteRebuildViewSet, basename="rebuild")

urlpatterns = [
    path("share/rebuilds/<str:token>/", shared_rebuild, name="shared-rebuild"),
    path("share/rebuilds/<str:token>/html/", shared_rebuild_html, name="shared-rebuild-html"),
    *router.urls,
]
