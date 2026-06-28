"""以系統手冊（第115401組）的真實組員，取代先前的佔位團隊資料。

先前的種子有兩套互不一致的佔位資料：
- migration 0002 / 0004：name 是職稱（後端工程師 / 前端工程師 / AI / Agent / DevOps / QA）
- seed_team 指令：name 是「組長A / B同學 / C同學 / D同學」

本 migration 清除這兩套佔位成員，改以手冊「表 4-2-2 工作內容與貢獻度表」
與「表 4-2-1 分工表」的真實 4 位組員建立，並以 student_id 為冪等鍵。
reverse 時不刪除（避免回滾誤刪 staff 後台已編輯的真實資料）。
"""

from django.db import migrations

# 兩套已知佔位成員的 name（清除用）
PLACEHOLDER_NAMES = [
    "後端工程師", "前端工程師", "AI / Agent", "DevOps / QA",  # 0002 / 0004
    "組長A", "B同學", "C同學", "D同學",  # seed_team（舊版）
]

# 真實組員：bio 取自手冊表 4-2-2；contributions 取自表 4-2-1 的 ● 主責項目
REAL_TEAM = [
    {
        "student_id": "11246034",
        "name": "侯雨利",
        "role": "組長｜系統架構與後端整合",
        "avatar_emoji": "👑",
        "bio": "負責整體系統架構規劃與技術選型、後端 API 整合（Django + DRF）、"
               "Docker Compose 部署與維運，並統籌前後端協調與系統手冊撰寫。",
        "skills": ["Django", "DRF", "Docker Compose", "系統架構", "Google OAuth"],
        "skill_levels": [
            {"name": "系統架構規劃", "level": 92},
            {"name": "Django / DRF", "level": 88},
            {"name": "Docker 部署維運", "level": 85},
            {"name": "專案統籌", "level": 90},
        ],
        "contributions": [
            {"title": "系統架構設計", "desc": "前後端分離分層架構與技術選型"},
            {"title": "後端 API 與登入整合", "desc": "Google OAuth / JWT 認證、評論與 CMS API"},
            {"title": "Docker 部署與維運", "desc": "Compose 多服務容器化 + cloudflared 對外通道"},
            {"title": "報告產出與文件統籌", "desc": "Word 弱點報告、系統手冊統整與格式校對"},
        ],
        "email": "11246034@ntub.edu.tw",
        "github_url": "",
        "sort_order": 0,
        "is_active": True,
    },
    {
        "student_id": "11246001",
        "name": "羅建凱",
        "role": "組員｜前端開發與 UI/UX",
        "avatar_emoji": "🎨",
        "bio": "負責 React 18 前端 SPA 開發（掃描提交、結果展示、後台管理）、"
               "ReactFlow 網站拓樸圖，以及全站 UI/UX 視覺設計與互動效果。",
        "skills": ["React 18", "Vite", "Tailwind CSS", "ReactFlow", "UI/UX"],
        "skill_levels": [
            {"name": "React 18 SPA", "level": 90},
            {"name": "UI/UX 設計", "level": 88},
            {"name": "Tailwind CSS", "level": 85},
            {"name": "ReactFlow 視覺化", "level": 78},
        ],
        "contributions": [
            {"title": "React SPA 全頁開發", "desc": "掃描提交、儀表板、歷史、結果詳情與後台"},
            {"title": "ReactFlow 網站拓樸圖", "desc": "視覺化 BFS 爬取的頁面節點結構"},
            {"title": "全站 UI/UX 與互動", "desc": "配色、版面、動效與結帳 3 步驟精靈"},
            {"title": "API 規格與行銷頁", "desc": "RESTful 介面規格、產品介紹與團隊介紹頁"},
        ],
        "email": "11246001@ntub.edu.tw",
        "github_url": "",
        "sort_order": 1,
        "is_active": True,
    },
    {
        "student_id": "11246038",
        "name": "李仕傑",
        "role": "組員｜資料庫與計費後端",
        "avatar_emoji": "🗄️",
        "bio": "負責 PostgreSQL 資料庫設計與 Migration、Celery 非同步掃描任務、"
               "點數計費系統（BillingService 冪等交易）與後端 API 開發。",
        "skills": ["PostgreSQL", "Celery", "Redis", "BillingService", "REST API"],
        "skill_levels": [
            {"name": "PostgreSQL 設計", "level": 88},
            {"name": "計費冪等交易", "level": 86},
            {"name": "Celery 非同步", "level": 84},
            {"name": "REST API", "level": 82},
        ],
        "contributions": [
            {"title": "資料庫設計與 ER 模型", "desc": "PostgreSQL schema、Migration 與實體關聯"},
            {"title": "點數計費系統", "desc": "CoinWallet 冪等交易、預扣／結算／退款機制"},
            {"title": "Celery 非同步任務", "desc": "掃描工作佇列與進度追蹤"},
            {"title": "資料 API", "desc": "Findings／Dashboard 與掃描歷史／稽核 API"},
        ],
        "email": "11246038@ntub.edu.tw",
        "github_url": "",
        "sort_order": 2,
        "is_active": True,
    },
    {
        "student_id": "11246041",
        "name": "曾子睿",
        "role": "組員｜爬蟲與四維掃描引擎",
        "avatar_emoji": "🕷️",
        "bio": "負責 Playwright BFS 爬蟲引擎、四維掃描引擎（SEO／AEO／GEO／Security）"
               "開發，以及 Nginx 反向代理與伺服器部署設定。",
        "skills": ["Playwright", "四維掃描", "Nginx", "Python", "資安掃描"],
        "skill_levels": [
            {"name": "Playwright 爬蟲", "level": 90},
            {"name": "四維掃描引擎", "level": 88},
            {"name": "被動資安分析", "level": 82},
            {"name": "Nginx 部署", "level": 80},
        ],
        "contributions": [
            {"title": "Playwright BFS 爬蟲", "desc": "同網域、深度爬取、截圖與頁面證據保存"},
            {"title": "四維掃描引擎", "desc": "SEO／AEO／GEO／Security 規則與 Finding 產出"},
            {"title": "四維加權評分與取消", "desc": "0–100 綜合評分與合作式掃描取消機制"},
            {"title": "合規與主動探測", "desc": "robots／same-origin、katana 整合、主動探測模組"},
        ],
        "email": "11246041@ntub.edu.tw",
        "github_url": "",
        "sort_order": 3,
        "is_active": True,
    },
]


def seed(apps, schema_editor):
    Member = apps.get_model("content", "TeamMember")
    # 清除兩套佔位成員
    Member.objects.filter(name__in=PLACEHOLDER_NAMES).delete()
    # 以 student_id 為冪等鍵建立 / 更新真實組員
    for data in REAL_TEAM:
        Member.objects.update_or_create(
            student_id=data["student_id"],
            defaults={k: v for k, v in data.items() if k != "student_id"},
        )


class Migration(migrations.Migration):
    dependencies = [("content", "0008_teammember_student_id")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
