from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path, re_path
from django.views.generic import TemplateView
from django.views.static import serve

FRONTEND_DIST = settings.BASE_DIR.parent / "frontend" / "dist"


def robots_txt(request):
    lines = [
        "User-agent: *",
        "Disallow: /admin/",
        "Disallow: /django-admin/",
        "",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


urlpatterns = [
    path("robots.txt", robots_txt),
    # Django Admin 搬到 /django-admin/，把 /admin/* 讓給 React 後台
    path("django-admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/billing/", include("apps.billing.urls")),
    path("api/reviews/", include("apps.reviews.urls")),
    path("api/admin/", include("apps.admin_api.urls")),
    path("api/content/", include("apps.content.urls")),
    path("api/insights/", include("apps.insights.urls")),
    path("api/", include("apps.scans.urls")),
    # 由 Django 直接服務 Vite build 出的靜態 assets，讓 runserver 模式不必另開 npm dev
    re_path(
        r"^assets/(?P<path>.*)$",
        serve,
        {"document_root": FRONTEND_DIST / "assets"},
    ),
    # PWA 必要檔案（從 frontend/dist 根目錄 serve）
    re_path(
        r"^(?P<path>manifest\.webmanifest|service-worker\.js|pwa-icon\.svg)$",
        serve,
        {"document_root": FRONTEND_DIST},
    ),
    # SPA fallback：其他路徑（含 /admin/*）都回傳 index.html，由 React Router 處理
    # （Docker 模式由 nginx 處理 SPA fallback，此路由在容器內為惰性 fallback）
    re_path(
        r"^(?!django-admin/|api/|static/|media/).*$",
        TemplateView.as_view(template_name="index.html"),
    ),
]
