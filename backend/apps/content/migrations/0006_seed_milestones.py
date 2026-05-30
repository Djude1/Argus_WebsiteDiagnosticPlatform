"""seed 5 個專案里程碑（給 /project 頁 timeline 顯示）。"""

from datetime import date

from django.db import migrations


MILESTONES = [
    {
        "title": "MVP 完成",
        "date": date(2026, 5, 20),
        "description": "後端 Django + DRF + Celery、前端 React + Vite + Zustand、Playwright 爬蟲、四維 scanner、Word 報告全部就位",
        "icon": "🎯",
        "sort_order": 1,
    },
    {
        "title": "Hermes-Agent 上線",
        "date": date(2026, 5, 24),
        "description": "整合 MiniMax / GLM / Gemini 三 provider chain，OpenAI tool-calling 格式 8 個 tools、observe-think-act 主迴圈與 token 安全閘",
        "icon": "🤖",
        "sort_order": 2,
    },
    {
        "title": "商業化模組",
        "date": date(2026, 5, 26),
        "description": "Coin 點數錢包、4 個購點方案、3 步驟結帳 wizard、平台評論系統、React /admin 後台、AI 用量 dashboard",
        "icon": "💎",
        "sort_order": 3,
    },
    {
        "title": "PWA 與公開頁",
        "date": date(2026, 5, 26),
        "description": "manifest + service worker 真實 PWA 可安裝，4 個公開行銷頁（/project /team /purchase /download）+ CMS 管理",
        "icon": "📱",
        "sort_order": 4,
    },
    {
        "title": "電子發票 + 載具",
        "date": date(2026, 5, 27),
        "description": "結帳支援雲端發票、手機條碼、自然人憑證；reviews 大改為 Trustpilot 風（點讚 / 精選 / lightbox / admin 真名）",
        "icon": "✨",
        "sort_order": 5,
    },
]


def seed(apps, schema_editor):
    Milestone = apps.get_model("content", "ProjectMilestone")
    for spec in MILESTONES:
        Milestone.objects.get_or_create(title=spec["title"], defaults=spec)


class Migration(migrations.Migration):
    dependencies = [("content", "0005_projectmilestone")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
