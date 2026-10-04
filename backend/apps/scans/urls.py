from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.scans.seo_views import gsc_callback
from apps.scans.views import (
    FindingViewSet,
    PageViewSet,
    ScanJobViewSet,
    SiteProjectViewSet,
    VerifiedDomainViewSet,
    audit_log,
    dashboard_summary,
    estimate_scan,
    findings_by_category,
    origin_history,
)

router = DefaultRouter()
router.register("scans", ScanJobViewSet, basename="scan")
router.register("pages", PageViewSet, basename="page")
router.register("findings", FindingViewSet, basename="finding")
router.register("domains", VerifiedDomainViewSet, basename="verified-domain")
router.register("projects", SiteProjectViewSet, basename="site-project")

urlpatterns = router.urls + [
    path("dashboard/", dashboard_summary, name="dashboard-summary"),
    path("history/", origin_history, name="origin-history"),
    path("audit/", audit_log, name="audit-log"),
    path("findings-by-category/", findings_by_category, name="findings-by-category"),
    path("estimate/", estimate_scan, name="estimate-scan"),
    path("gsc/callback/", gsc_callback, name="gsc-callback"),
]

