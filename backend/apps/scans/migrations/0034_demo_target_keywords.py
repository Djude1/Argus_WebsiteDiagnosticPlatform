"""既有示範專案補上預設目標關鍵字（2026-10-11，SEO 分析「搜尋關鍵字」分頁的示範資料）。

只補 target_keywords 為空的示範專案；使用者自己設定過的不動。反向操作不做事。
"""

from django.db import migrations

DEMO_TARGET_KEYWORDS = ["耶加雪菲", "手沖咖啡", "濾掛咖啡", "冷萃咖啡", "咖啡豆 訂閱"]


def fill_demo_keywords(apps, schema_editor):
    SiteProject = apps.get_model("scans", "SiteProject")
    for project in SiteProject.objects.filter(is_demo=True):
        if not project.target_keywords:
            project.target_keywords = list(DEMO_TARGET_KEYWORDS)
            project.save(update_fields=["target_keywords"])


class Migration(migrations.Migration):
    dependencies = [("scans", "0033_scanjob_ai_insight")]

    operations = [migrations.RunPython(fill_demo_keywords, migrations.RunPython.noop)]
