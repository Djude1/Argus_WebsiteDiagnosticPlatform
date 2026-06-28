"""以系統手冊（表 4-1-1 專案甘特圖 / 4-1 專案時程）的真實開發歷程，
取代先前擠在 2026/05 的 5 個里程碑。

手冊時程：114/12（2025/12）起始 → 115/06（2026/06）初評，共 7 個月。
依甘特圖各階段歸納為 7 個里程碑，跨越真實月份。
reverse 時不刪除（避免回滾誤刪 staff 後台已編輯的內容）。
"""

from datetime import date

from django.db import migrations

# 先前 0006 seed 的舊里程碑（清除用）
OLD_TITLES = [
    "MVP 完成", "Hermes-Agent 上線", "商業化模組",
    "PWA 與公開頁", "電子發票 + 載具",
]

# 依手冊表 4-1-1 甘特圖階段歸納的真實開發歷程
MILESTONES = [
    {
        "title": "主題構思與需求分析",
        "date": date(2025, 12, 5),
        "description": "確立 Argus 四維健檢主題，蒐集資料與競品分析（AHHA / GeoWeb），定義使用者需求與功能範圍。",
        "icon": "📌",
        "sort_order": 1,
    },
    {
        "title": "系統架構與 UI/UX 設計",
        "date": date(2026, 1, 10),
        "description": "前後端分離架構設計、資料庫 Schema 設計，完成 UI/UX 原型與 Logo 設計。",
        "icon": "🎨",
        "sort_order": 2,
    },
    {
        "title": "資料庫與後端 API 建置",
        "date": date(2026, 2, 15),
        "description": "建置 PostgreSQL 資料庫，開發 Django REST Framework API 並整合 Django 框架。",
        "icon": "🗄️",
        "sort_order": 3,
    },
    {
        "title": "爬蟲與四維掃描引擎",
        "date": date(2026, 3, 15),
        "description": "Playwright BFS 爬蟲引擎，與 SEO／AEO／GEO／資安四維掃描引擎開發。",
        "icon": "🕷️",
        "sort_order": 4,
    },
    {
        "title": "前端 SPA 與互動報告",
        "date": date(2026, 4, 15),
        "description": "React 前端 SPA 開發、建議互動介面與 Word 報告匯出。",
        "icon": "🖥️",
        "sort_order": 5,
    },
    {
        "title": "商業化、後台、PWA 與部署",
        "date": date(2026, 5, 20),
        "description": "點數計費與商業化、管理後台與 PWA、Docker 容器化部署、Hermes-Agent（Phase 2）與網站拓樸圖。",
        "icon": "💎",
        "sort_order": 6,
    },
    {
        "title": "系統整合測試與初評",
        "date": date(2026, 6, 2),
        "description": "系統整合測試、文件撰寫與簡報製作，完成系統手冊並進行初評排練。",
        "icon": "🚀",
        "sort_order": 7,
    },
]


def seed(apps, schema_editor):
    Milestone = apps.get_model("content", "ProjectMilestone")
    # 清除舊的 5 個里程碑
    Milestone.objects.filter(title__in=OLD_TITLES).delete()
    # 以 title 為冪等鍵建立 / 更新真實開發歷程
    for spec in MILESTONES:
        Milestone.objects.update_or_create(
            title=spec["title"],
            defaults={k: v for k, v in spec.items() if k != "title"},
        )


class Migration(migrations.Migration):
    dependencies = [("content", "0009_seed_real_team")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
