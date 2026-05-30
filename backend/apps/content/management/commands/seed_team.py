from django.core.management.base import BaseCommand

from apps.content.models import TeamMember

TEAM_DATA = [
    {
        "sort_order": 0,
        "name": "組長A",
        "role": "全端整合 / 專題組長",
        "avatar_emoji": "👑",
        "bio": "負責整體專案規劃與系統整合，協調前後端架構設計。",
        "skills": ["Django", "React", "Docker", "系統架構"],
        "skill_levels": [
            {"name": "Django", "level": 90},
            {"name": "React", "level": 85},
            {"name": "Docker", "level": 80},
            {"name": "系統整合", "level": 92},
        ],
        "contributions": [
            {"title": "專案規劃與架構設計", "desc": "訂定系統架構、技術選型、分工規劃"},
            {"title": "後端 API 整合", "desc": "Django REST Framework API 設計與整合"},
            {"title": "部署與維運", "desc": "Docker Compose 多服務部署流程"},
        ],
        "email": "",
        "github_url": "",
    },
    {
        "sort_order": 1,
        "name": "B同學",
        "role": "前端工程師",
        "avatar_emoji": "🎨",
        "bio": "負責前端 React 介面開發與視覺設計，打造直覺的使用者體驗。",
        "skills": ["React", "CSS", "Figma", "PWA"],
        "skill_levels": [
            {"name": "React", "level": 88},
            {"name": "CSS/Tailwind", "level": 85},
            {"name": "UI 設計", "level": 80},
            {"name": "PWA", "level": 75},
        ],
        "contributions": [
            {"title": "React UI 元件開發", "desc": "App.jsx 所有頁面元件設計與實作"},
            {"title": "視覺設計", "desc": "色彩系統、排版、互動動畫"},
            {"title": "PWA 離線支援", "desc": "Service Worker、manifest 設定"},
        ],
        "email": "",
        "github_url": "",
    },
    {
        "sort_order": 2,
        "name": "C同學",
        "role": "後端 / 資料庫工程師",
        "avatar_emoji": "🗄️",
        "bio": "負責後端 API 開發、資料庫設計與 Celery 非同步任務管理。",
        "skills": ["Django", "PostgreSQL", "Celery", "Redis"],
        "skill_levels": [
            {"name": "Django", "level": 88},
            {"name": "PostgreSQL", "level": 85},
            {"name": "Celery", "level": 82},
            {"name": "Redis", "level": 78},
        ],
        "contributions": [
            {"title": "資料庫設計與 Migration", "desc": "設計 ScanJob、Billing 等核心 Model"},
            {"title": "Celery 非同步掃描任務", "desc": "掃描工作佇列與進度追蹤"},
            {"title": "點數計費系統", "desc": "CoinWallet 冪等交易設計"},
        ],
        "email": "",
        "github_url": "",
    },
    {
        "sort_order": 3,
        "name": "D同學",
        "role": "網頁架設 / 資料處理",
        "avatar_emoji": "🕷️",
        "bio": "負責伺服器部署、Playwright 爬蟲開發與掃描資料分析處理。",
        "skills": ["Playwright", "Nginx", "Python", "資料分析"],
        "skill_levels": [
            {"name": "Playwright 爬蟲", "level": 90},
            {"name": "Nginx 部署", "level": 82},
            {"name": "Python 資料處理", "level": 85},
            {"name": "安全掃描分析", "level": 80},
        ],
        "contributions": [
            {"title": "Playwright BFS 爬蟲", "desc": "多深度網站爬取、截圖與頁面分析"},
            {"title": "四維掃描器", "desc": "SEO/AEO/GEO/Security 掃描邏輯"},
            {"title": "伺服器架設與 Nginx", "desc": "Docker 部署、反向代理、SSL 設定"},
        ],
        "email": "",
        "github_url": "",
    },
]


class Command(BaseCommand):
    help = "Seed 四位組員資料（idempotent）"

    def handle(self, *args, **options):
        for data in TEAM_DATA:
            member, created = TeamMember.objects.update_or_create(
                name=data["name"],
                defaults={k: v for k, v in data.items() if k != "name"},
            )
            action = "建立" if created else "更新"
            self.stdout.write(f"  {action}：{member.name} ({member.role})")
        self.stdout.write(self.style.SUCCESS("[OK] 組員資料 seed 完成"))
