from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.admin_api import cms_views, views

cms_router = DefaultRouter()
cms_router.register("features", cms_views.ProjectFeatureViewSet, basename="admin-feature")
cms_router.register("team", cms_views.TeamMemberViewSet, basename="admin-team-member")
cms_router.register("releases", cms_views.AppReleaseViewSet, basename="admin-release")
cms_router.register("plans", cms_views.PricingPlanViewSet, basename="admin-plan")

urlpatterns = [
    path("cms/", include(cms_router.urls)),
    path("me/", views.me, name="admin-me"),
    path("overview/", views.overview, name="admin-overview"),
    path("users/", views.users_list, name="admin-users"),
    path("users/<int:user_id>/", views.user_detail, name="admin-user-detail"),
    path("users/<int:user_id>/adjust-coin/", views.adjust_coin, name="admin-adjust-coin"),
    path("transactions/", views.transactions_list, name="admin-transactions"),
    path("reviews/", views.reviews_list, name="admin-reviews"),
    path("reviews/<int:review_id>/reply/", views.reply_review, name="admin-reply-review"),
    path("scans/", views.scans_list, name="admin-scans"),
    path("scans/<int:scan_id>/", views.scan_detail, name="admin-scan-detail"),
    path("orders/", views.orders_list, name="admin-orders"),
    path("dashboard/", views.dashboard, name="admin-dashboard"),
    path("audit-log/", views.audit_log, name="admin-audit-log"),
    path("announcements/active/", views.active_announcements, name="admin-active-announcements"),
    path("announcements/", views.announcements_admin, name="admin-announcements"),
    path("announcements/<int:pk>/", views.announcement_detail, name="admin-announcement-detail"),
]
