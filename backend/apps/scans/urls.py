from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.scans.views import (
    FindingViewSet,
    PageViewSet,
    ScanJobViewSet,
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

urlpatterns = router.urls + [
    path("dashboard/", dashboard_summary, name="dashboard-summary"),
    path("history/", origin_history, name="origin-history"),
    path("audit/", audit_log, name="audit-log"),
    path("findings-by-category/", findings_by_category, name="findings-by-category"),
    path("estimate/", estimate_scan, name="estimate-scan"),
]

