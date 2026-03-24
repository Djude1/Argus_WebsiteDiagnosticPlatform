"""
主要 URL 路由設定
"""
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

# ── 後台 Admin API ────────────────────────────────────────────────
from accounts.admin_views import AdminUserListView, AdminUserDetailView
from products.admin_views import (
    AdminProductListView, AdminProductDetailView,
    AdminProductFileUploadView,
    AdminFeatureListView, AdminFeatureDetailView,
    AdminSpecListView, AdminSpecDetailView,
)
from orders.admin_views import AdminOrderListView, AdminOrderDetailView
from team.admin_views import AdminTeamListView, AdminTeamDetailView
from content.admin_views import (
    AdminContentSectionView,
    AdminDownloadFeatureListView, AdminDownloadFeatureDetailView,
    AdminDownloadStepListView, AdminDownloadStepDetailView,
    AdminImpactFeedbackView,
    AdminAnnouncementListView, AdminAnnouncementDetailView,
)
from analytics.admin_views import AdminTrafficView, AdminActivityLogView

admin_api = [
    # 帳號管理
    path('accounts/',        AdminUserListView.as_view(),   name='admin-user-list'),
    path('accounts/<int:pk>/', AdminUserDetailView.as_view(), name='admin-user-detail'),
    # 商品管理
    path('products/',        AdminProductListView.as_view(),   name='admin-product-list'),
    path('products/<int:pk>/', AdminProductDetailView.as_view(), name='admin-product-detail'),
    path('products/<int:pk>/upload/', AdminProductFileUploadView.as_view(), name='admin-product-upload'),
    path('products/<int:product_id>/features/', AdminFeatureListView.as_view(),  name='admin-feature-list'),
    path('features/<int:pk>/',                  AdminFeatureDetailView.as_view(), name='admin-feature-detail'),
    path('products/<int:product_id>/specs/',    AdminSpecListView.as_view(),      name='admin-spec-list'),
    path('specs/<int:pk>/',                     AdminSpecDetailView.as_view(),    name='admin-spec-detail'),
    # 訂單管理
    path('orders/',        AdminOrderListView.as_view(),   name='admin-order-list'),
    path('orders/<int:pk>/', AdminOrderDetailView.as_view(), name='admin-order-detail'),
    # 成員管理
    path('team/',        AdminTeamListView.as_view(),   name='admin-team-list'),
    path('team/<int:pk>/', AdminTeamDetailView.as_view(), name='admin-team-detail'),
    # 頁面內容管理
    path('content/<str:section>/', AdminContentSectionView.as_view(),          name='admin-content-section'),
    path('content-features/',      AdminDownloadFeatureListView.as_view(),      name='admin-dl-feature-list'),
    path('content-features/<int:pk>/', AdminDownloadFeatureDetailView.as_view(), name='admin-dl-feature-detail'),
    path('content-steps/',         AdminDownloadStepListView.as_view(),         name='admin-dl-step-list'),
    path('content-steps/<int:pk>/', AdminDownloadStepDetailView.as_view(),      name='admin-dl-step-detail'),
    # 分析儀表板
    path('analytics/traffic/',  AdminTrafficView.as_view(),      name='admin-traffic'),
    path('analytics/logs/',     AdminActivityLogView.as_view(),  name='admin-activity-logs'),
    # 撞擊回饋記錄
    path('impact-feedback/',    AdminImpactFeedbackView.as_view(), name='admin-impact-feedback'),
    # APP 公告管理
    path('announcements/',          AdminAnnouncementListView.as_view(),   name='admin-announcement-list'),
    path('announcements/<int:pk>/', AdminAnnouncementDetailView.as_view(), name='admin-announcement-detail'),
]

urlpatterns = [
    # JWT 認證
    path('api/token/',         TokenObtainPairView.as_view(),  name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(),     name='token_refresh'),

    # 公開 API
    path('api/accounts/', include('accounts.urls')),
    path('api/products/', include('products.urls')),
    path('api/orders/',   include('orders.urls')),
    path('api/team/',     include('team.urls')),
    path('api/content/',  include('content.urls')),

    # 後台管理 API（需登入）
    path('api/admin/', include(admin_api)),
    # 公開流量追蹤
    path('api/analytics/', include('analytics.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
