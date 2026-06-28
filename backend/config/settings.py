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

# conn_max_age=0：每個請求結束即關閉 DB 連線。
# 原因：web 用多執行緒 runserver，搭配 conn_max_age>0 的持久連線 +
# 前端高頻輪詢，會讓連線只進不出，撐滿 Postgres max_connections（100）後
# 整個 API 回 500「too many clients already」。設 0 讓連線數被「同時處理中的
# 請求數」上限住，不再累積。改用 gunicorn 綁定 worker 數後可再評估調回 >0。
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=0,
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

# Phase 3 Kali 主動驗證工具（docker exec 呼叫 kali container 的 sqlmap/metasploit）
# 預設關閉；即使開啟，仍需 scan_mode=active 且 active_testing_authorized=True 才會執行（三重鎖）
ARGUS_KALI_ENABLED = env_bool("ARGUS_KALI_ENABLED", default=False)
ARGUS_KALI_CONTAINER = os.getenv("ARGUS_KALI_CONTAINER", "argus-kali-1")
ARGUS_KALI_TIMEOUT = int(os.getenv("ARGUS_KALI_TIMEOUT", "120"))  # 單一工具 subprocess 超時（秒）

# Google OAuth Client ID（從 Google Cloud Console > Credentials 取得）
# 一般使用者透過 Google 帳號登入時用於驗證 ID Token；空字串代表未啟用
GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")

# 點數制度（取代舊的 UserScanQuota 月次數配額）
# - 每月自動發放給所有使用者的贈點
# - 每爬一個頁面的單價（建立掃描時以 max_pages × 此值預扣，完成後依實際頁數退差）
ARGUS_MONTHLY_BONUS_COINS = int(os.getenv("ARGUS_MONTHLY_BONUS_COINS", "200"))
ARGUS_COIN_PER_PAGE = int(os.getenv("ARGUS_COIN_PER_PAGE", "10"))

# Email 寄送（購買收據、未來通知）
# dev 預設用 filebased backend（信件存到 dev_emails/，每封一檔，可直接打開看內容；
# 避開 Windows console cp950 編碼炸 emoji 的問題）。
# production 設 DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
# 並提供 EMAIL_HOST_USER / EMAIL_HOST_PASSWORD（Gmail 用 App Password，不是登入密碼）
EMAIL_BACKEND = os.getenv(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.filebased.EmailBackend",
)
EMAIL_FILE_PATH = os.getenv(
    "EMAIL_FILE_PATH",
    str(PROJECT_ROOT / "backend" / "dev_emails"),
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Argus 系統 <no-reply@argus.local>")

# Django Admin 已完全移除（不再提供 `/django-admin/` 後門）；唯一後台為 React `/admin/*`
# （admin_api 提供 CRUD endpoint）。`django.contrib.admin` 仍留在 INSTALLED_APPS：
# 提供 LogEntry 等基礎設施並避免動到既有 migration，但已無對外 URL、無法存取。
# 舊 jazzmin 設定常數已於 W4 移除（套件已 uv remove）
