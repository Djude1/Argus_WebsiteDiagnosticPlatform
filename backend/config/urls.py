from django.conf import settings
from django.db import connection
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.urls import include, path, re_path
from django.views.generic import TemplateView
from django.views.static import serve

FRONTEND_DIST = settings.BASE_DIR.parent / "frontend" / "dist"
FRONTEND_PUBLIC = settings.BASE_DIR.parent / "frontend" / "public"


def robots_txt(request):
    lines = [
        "User-agent: *",
        "Disallow: /admin/",
        "",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


def health_live(request):
    return JsonResponse({"status": "ok"})


def health_ready(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)

    return JsonResponse({"status": "ready"})


def serve_review_image(request, path):
    image_path = settings.MEDIA_ROOT / "review_images" / path

    if not image_path.is_file():
        raise Http404("找不到圖片。")

    response = FileResponse(image_path.open("rb"))
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    response["Cache-Control"] = "public, max-age=86400"

    return response


def _serve_immutable(request, path, document_root=None):
    """
    雜湊命名的 build 資產（/assets/*）
    內容變更即檔名變更，可長期快取。
    """
    response = serve(
        request,
        path,
        document_root=document_root,
    )

    response["Cache-Control"] = (
        "public, max-age=31536000, immutable"
    )

    return response


def _serve_no_cache(request, path, document_root=None):
    """
    PWA 控制檔與 icon
    必須每次重新驗證。
    """
    response = serve(
        request,
        path,
        document_root=document_root,
    )

    response["Cache-Control"] = "no-cache"

    return response


urlpatterns = [

    # robots
    path(
        "robots.txt",
        robots_txt,
    ),


    # React favicon 的原始資產受 Git 追蹤，不需先 build frontend。
    path(
        "favicon.svg",
        _serve_no_cache,
        {
            "path": "favicon.svg",
            "document_root": FRONTEND_PUBLIC,
        },
    ),


    # Health check
    path(
        "api/health/live/",
        health_live,
        name="health-live",
    ),

    path(
        "api/health/ready/",
        health_ready,
        name="health-ready",
    ),


    # Review images
    re_path(
        r"^media/review_images/(?P<path>[0-9a-f]{32}\.(?:jpg|png))$",
        serve_review_image,
        name="review-image",
    ),


    # APIs
    path(
        "api/auth/",
        include("apps.accounts.urls"),
    ),

    path(
        "api/billing/",
        include("apps.billing.urls"),
    ),

    path(
        "api/reviews/",
        include("apps.reviews.urls"),
    ),

    path(
        "api/admin/",
        include("apps.admin_api.urls"),
    ),

    path(
        "api/content/",
        include("apps.content.urls"),
    ),

    path(
        "api/insights/",
        include("apps.insights.urls"),
    ),

    path(
        "api/",
        include("apps.scans.urls"),
    ),


    # Vite hashed assets
    re_path(
        r"^assets/(?P<path>.*)$",
        _serve_immutable,
        {
            "document_root": FRONTEND_DIST / "assets",
        },
    ),


    # PWA files
    re_path(
        r"^(?P<path>manifest\.webmanifest|service-worker\.js|pwa-icon\.svg)$",
        _serve_no_cache,
        {
            "document_root": FRONTEND_DIST,
        },
    ),


    # React SPA fallback
    # 不讓 API/static/media/favicon 被 index.html 吃掉
    re_path(
        r"^(?!api/|static/|media/|favicon\.svg).*$",
        TemplateView.as_view(
            template_name="index.html"
        ),
    ),
]
