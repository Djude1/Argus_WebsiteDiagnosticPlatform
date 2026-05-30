"""預設內容 seed：6 features、4 team members、1 PWA release。

reverse 時不刪除（避免 admin 編輯過的內容被回滾移除）。
"""

from django.db import migrations
from django.utils import timezone


FEATURES = [
    {
        "icon": "🕷️",
        "title": "全站爬蟲",
        "description": "Playwright headless Chromium 自動 BFS 同網域、深度 3 層、最多 50 頁，含 robots.txt 遵守與 RPS 限制。",
        "sort_order": 1,
    },
    {
        "icon": "🔍",
        "title": "四維靜態掃描",
        "description": "SEO / AEO / GEO / 被動資安四個維度，每頁產出 Finding 含證據、座標、修補建議與 AI handoff prompt。",
        "sort_order": 2,
    },
    {
        "icon": "🤖",
        "title": "Hermes Agent",
        "description": "MiniMax / GLM / Gemini provider chain，OpenAI tool calling 格式，自動執行擬真使用者操作回報 UX 問題。",
        "sort_order": 3,
    },
    {
        "icon": "🎯",
        "title": "互動式報告",
        "description": "中央長截圖 + Canvas 高光框 + 紅框雙向跳轉 + Top Actions 按鈕化，找問題、看修補一目了然。",
        "sort_order": 4,
    },
    {
        "icon": "📄",
        "title": "Word 報告匯出",
        "description": "python-docx 自動生成完整報告：封面、摘要、各頁 Findings、附錄；給管理層直接交付。",
        "sort_order": 5,
    },
    {
        "icon": "🛡️",
        "title": "授權式掃描",
        "description": "送出前強制勾選授權書、記錄 IP / 時間 / UA；明顯第三方網域要求二次確認；主動測試需額外授權。",
        "sort_order": 6,
    },
]

TEAM = [
    {
        "name": "後端工程師",
        "role": "Backend Lead",
        "avatar_emoji": "🧑‍💻",
        "bio": "負責 Django REST 架構、Celery 任務佇列、Playwright 爬蟲核心與 LLM Agent 整合。",
        "skills": ["Django 5", "DRF", "Celery", "Playwright", "PostgreSQL"],
        "sort_order": 1,
    },
    {
        "name": "前端工程師",
        "role": "Frontend Lead",
        "avatar_emoji": "🎨",
        "bio": "React 18 + Vite SPA、Canvas 互動報告、Zustand 狀態、整套淺色 / 深色主題 CSS。",
        "skills": ["React 18", "Tailwind", "Zustand", "SVG", "PWA"],
        "sort_order": 2,
    },
    {
        "name": "AI / Agent",
        "role": "AI Engineer",
        "avatar_emoji": "🧠",
        "bio": "Hermes Agent 行為架構、OpenAI tool calling schema、provider fallback 與 token 安全閘設計。",
        "skills": ["LLM", "Tool Calling", "MiniMax", "GLM", "Prompt"],
        "sort_order": 3,
    },
    {
        "name": "DevOps / QA",
        "role": "DevOps & QA",
        "avatar_emoji": "🛠️",
        "bio": "Docker Compose 部署、nginx 反向代理、187+ 自動化測試覆蓋、ruff 程式碼品質。",
        "skills": ["Docker", "nginx", "pytest", "ruff", "CI"],
        "sort_order": 4,
    },
]

RELEASE = {
    "version": "1.0.0",
    "platform": "pwa",
    "release_notes": (
        "首次 PWA 釋出：可在 Chrome / Edge / Safari 「加到主畫面」"
        "後離線使用，含登入、掃描列表、互動報告與購點功能。"
    ),
    "download_url": "",  # 站內安裝
    "icon_url": "",
    "is_active": True,
    "is_latest": True,
}


def seed(apps, schema_editor):
    Feature = apps.get_model("content", "ProjectFeature")
    Member = apps.get_model("content", "TeamMember")
    Release = apps.get_model("content", "AppRelease")
    for spec in FEATURES:
        Feature.objects.get_or_create(title=spec["title"], defaults=spec)
    for spec in TEAM:
        Member.objects.get_or_create(name=spec["name"], defaults=spec)
    if not Release.objects.exists():
        Release.objects.create(released_at=timezone.now(), **RELEASE)


class Migration(migrations.Migration):
    dependencies = [("content", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
