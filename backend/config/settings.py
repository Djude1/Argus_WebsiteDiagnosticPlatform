import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")

raw_playwright_browsers_path = os.getenv("PLAYWRIGHT_BROWSERS_PATH", ".ms-playwright")
playwright_browsers_path = Path(raw_playwright_browsers_path)
if not playwright_browsers_path.is_absolute():
    playwright_browsers_path = PROJECT_ROOT / playwright_browsers_path
PLAYWRIGHT_BROWSERS_PATH = str(playwright_browsers_path)
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = PLAYWRIGHT_BROWSERS_PATH


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY must be set in .env")

DEBUG = env_bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "apps.accounts",
    "apps.scans",
    "apps.agent",
    "apps.billing",
    "apps.reviews",
    "apps.admin_api",
    "apps.content",
    "apps.insights",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # 把 Vite build 出的 index.html 視為 Django 可渲染的模板，讓 runserver 一個命令就能服務 SPA
        "DIRS": [PROJECT_ROOT / "frontend" / "dist"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "zh-hant"
TIME_ZONE = "Asia/Taipei"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
)

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_LIFETIME", "60"))
    ),
    "SIGNING_KEY": os.getenv("JWT_SECRET_KEY", SECRET_KEY),
}

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0"))
CELERY_RESULT_BACKEND = os.getenv(
    "CELERY_RESULT_BACKEND",
    os.getenv("REDIS_URL", "redis://localhost:6379/1"),
)
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", default=False)

ARGUS_DEFAULT_MAX_DEPTH = 3
ARGUS_DEFAULT_MAX_PAGES = 50
ARGUS_ACTIVE_MAX_RPS = 2
ARGUS_PASSIVE_MAX_RPS = 5
ARGUS_SCANNER_USER_AGENT = "SiteSense-AI-Scanner/1.0 (authorized-audit)"
ARGUS_AUTO_QUEUE_SCANS = env_bool("ARGUS_AUTO_QUEUE_SCANS", default=not DEBUG)

# Katana 補充型資安爬蟲（Docker 執行，不污染本機環境）
# 前提：本機需有 Docker Desktop 並已 pull 過 projectdiscovery/katana
KATANA_DOCKER_IMAGE = os.getenv("KATANA_DOCKER_IMAGE", "projectdiscovery/katana:latest")
KATANA_TIMEOUT = int(os.getenv("KATANA_TIMEOUT", "90"))  # subprocess 超時（秒）

# Phase 2 Hermes-Agent 上限（避免 token 失控與無限循環）
ARGUS_AGENT_MAX_STEPS = int(os.getenv("ARGUS_AGENT_MAX_STEPS", "20"))
ARGUS_AGENT_MAX_TOKENS = int(os.getenv("ARGUS_AGENT_MAX_TOKENS", "60000"))
ARGUS_AGENT_STEP_TIMEOUT = int(os.getenv("ARGUS_AGENT_STEP_TIMEOUT", "30"))
ARGUS_AGENT_ENABLED = env_bool("ARGUS_AGENT_ENABLED", default=False)

# Google OAuth Client ID（從 Google Cloud Console > Credentials 取得）
# 一般使用者透過 Google 帳號登入時用於驗證 ID Token；空字串代表未啟用
GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")

# 點數制度（取代舊的 UserScanQuota 月次數配額）
# - 每月自動發放給所有使用者的贈點
# - 每爬一個頁面的單價（建立掃描時以 max_pages × 此值預扣，完成後依實際頁數退差）
ARGUS_MONTHLY_BONUS_COINS = int(os.getenv("ARGUS_MONTHLY_BONUS_COINS", "200"))
ARGUS_COIN_PER_PAGE = int(os.getenv("ARGUS_COIN_PER_PAGE", "10"))

# ============================================================
# Django Admin：保留 `/django-admin/` 為 superuser 應急後門（樣式預設、刻意樸素）
# 主要管理介面已搬到 React `/admin/*`（admin_api 提供 CRUD endpoint）
# 以下舊 jazzmin 設定已禁用（套件已 uv remove），保留註解供未來如需 demo Django admin 顏色可參考
# ============================================================
_JAZZMIN_SETTINGS_DEPRECATED = {
    "site_title": "Argus 後台",
    "site_header": "Argus 管理後台",
    "site_brand": "Argus",
    "site_logo": None,
    "site_icon": None,
    "welcome_sign": "歡迎來到 Argus 管理後台",
    "copyright": "Argus AI 網站健檢平台",
    "search_model": [
        "accounts.User",
        "scans.ScanJob",
        "reviews.PlatformReview",
    ],
    "topmenu_links": [
        {"name": "首頁", "url": "admin:index"},
        {"name": "錢包", "url": "admin:billing_coinwallet_changelist"},
        {"name": "交易紀錄", "url": "admin:billing_cointransaction_changelist"},
        {"name": "評論", "url": "admin:reviews_platformreview_changelist"},
        {"name": "掃描", "url": "admin:scans_scanjob_changelist"},
    ],
    "show_sidebar": True,
    "navigation_expanded": True,
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
        "accounts.User": "fas fa-user-shield",
        "billing": "fas fa-coins",
        "billing.CoinWallet": "fas fa-wallet",
        "billing.CoinTransaction": "fas fa-exchange-alt",
        "billing.PricingPlan": "fas fa-tags",
        "billing.PurchaseOrder": "fas fa-receipt",
        "admin_api": "fas fa-shield-alt",
        "admin_api.AdminAuditLog": "fas fa-clipboard-list",
        "content": "fas fa-newspaper",
        "content.ProjectFeature": "fas fa-rocket",
        "content.TeamMember": "fas fa-user-friends",
        "content.AppRelease": "fas fa-mobile-alt",
        "reviews": "fas fa-star-half-alt",
        "reviews.PlatformReview": "fas fa-star",
        "scans": "fas fa-search",
        "scans.ScanJob": "fas fa-spider",
        "scans.Finding": "fas fa-bug",
        "scans.Page": "fas fa-file-alt",
        "scans.AuthorizationConsent": "fas fa-shield-alt",
        "scans.AgentSession": "fas fa-robot",
        "scans.AgentStep": "fas fa-shoe-prints",
    },
    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-circle",
    "related_modal_active": True,
    "changeform_format": "horizontal_tabs",
    "changeform_format_overrides": {
        "accounts.user": "collapsible",
    },
    "show_ui_builder": False,
    "language_chooser": False,
}

_JAZZMIN_UI_TWEAKS_DEPRECATED = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": "navbar-indigo",
    "accent": "accent-info",
    "navbar": "navbar-indigo navbar-dark",
    "no_navbar_border": False,
    "navbar_fixed": True,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": True,
    "sidebar": "sidebar-dark-indigo",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme": "flatly",
    "default_theme_mode": "auto",
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success",
    },
}
