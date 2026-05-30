"""補 4 個內建成員的 skill_levels 與 contributions（讓 /team 頁顯示完整）。

只動本檔之前已 seed、且 contributions 仍空的成員，避免覆蓋管理員後續編輯。
"""

from django.db import migrations


TEAM_EXTRA = {
    "後端工程師": {
        "skill_levels": [
            {"name": "Django 5", "level": 92},
            {"name": "Celery", "level": 85},
            {"name": "Playwright", "level": 80},
            {"name": "PostgreSQL", "level": 78},
        ],
        "contributions": [
            {"title": "ScanJob 狀態機", "desc": "queued/crawling/scanning/agent/completed 與合作式 cancel"},
            {"title": "Playwright BFS 爬蟲", "desc": "同網域、深度 3、RPS 限制、cache replay"},
            {"title": "四維 scanner", "desc": "SEO/AEO/GEO/被動資安規則 + Finding bounding_box"},
            {"title": "Word 報告匯出", "desc": "封面 / 摘要 / 各頁 findings / 附錄"},
        ],
    },
    "前端工程師": {
        "skill_levels": [
            {"name": "React 18", "level": 90},
            {"name": "Tailwind", "level": 88},
            {"name": "Zustand", "level": 85},
            {"name": "SVG 視覺化", "level": 75},
        ],
        "contributions": [
            {"title": "互動報告 UX", "desc": "截圖紅框雙向跳轉、Top Actions 按鈕化"},
            {"title": "Dashboard SVG 圖", "desc": "純 CSS/SVG 6 種視覺化元件，無 chart 套件"},
            {"title": "結帳 3 步驟 wizard", "desc": "選方案 / 填資料 / 確認，含電子發票載具"},
            {"title": "PWA 整合", "desc": "manifest + service worker + 一鍵安裝"},
        ],
    },
    "AI / Agent": {
        "skill_levels": [
            {"name": "LLM Tool Calling", "level": 88},
            {"name": "Prompt 設計", "level": 90},
            {"name": "MiniMax / GLM / Gemini", "level": 82},
            {"name": "Token 成本控制", "level": 80},
        ],
        "contributions": [
            {"title": "Hermes-Agent 主迴圈", "desc": "observe→think→act，max 20 步 + token 上限"},
            {"title": "Provider chain", "desc": "MiniMax 優先、GLM 第二、Gemini 備援，自動 fallback"},
            {"title": "8 個 Tool schema", "desc": "click / type_text / scroll / report_ux_issue 等"},
            {"title": "落地為 Finding", "desc": "report_ux_issue 轉成 ux category Finding + AI handoff prompt"},
        ],
    },
    "DevOps / QA": {
        "skill_levels": [
            {"name": "Docker Compose", "level": 88},
            {"name": "nginx 反向代理", "level": 80},
            {"name": "pytest / Django test", "level": 90},
            {"name": "ruff lint", "level": 85},
        ],
        "contributions": [
            {"title": "Docker 5 服務", "desc": "web / worker / redis / db / nginx 一鍵部署"},
            {"title": "210+ 自動化測試", "desc": "覆蓋 model / API / 權限 / billing 流程"},
            {"title": "ruff 程式碼品質", "desc": "import 排序 / E501 / 自動修"},
            {"title": "AdminAuditLog 機制", "desc": "敏感操作審計、IsSuperuser 兩級權限"},
        ],
    },
}


def seed(apps, schema_editor):
    Member = apps.get_model("content", "TeamMember")
    for name, data in TEAM_EXTRA.items():
        member = Member.objects.filter(name=name).first()
        if not member:
            continue
        # 只在欄位為空時補；不覆蓋管理員後續編輯
        updated = False
        if not member.skill_levels:
            member.skill_levels = data["skill_levels"]
            updated = True
        if not member.contributions:
            member.contributions = data["contributions"]
            updated = True
        if updated:
            member.save(update_fields=["skill_levels", "contributions", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [("content", "0003_teammember_contributions_teammember_skill_levels")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
