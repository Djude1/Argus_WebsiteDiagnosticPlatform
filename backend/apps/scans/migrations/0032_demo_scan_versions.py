"""既有示範專案的三次掃描補上同一組評分版本（2026-10-09）。

示範資料匯出時沒有版本欄位，建立出來的掃描版本是空字串，總覽與掃描紀錄一律顯示
「評分規則已更新，無法直接比較」。只動示範專案、且版本仍為空的掃描；值固定寫在這裡，
之後版本常數變動不影響這個 migration。
"""

from django.db import migrations

SCORING_VERSION = "2"
RULESET_VERSION = "2026.10.09"


def fill_demo_versions(apps, schema_editor):
    ScanJob = apps.get_model("scans", "ScanJob")
    ScanJob.objects.filter(project__is_demo=True, scoring_version="").update(
        scoring_version=SCORING_VERSION, ruleset_version=RULESET_VERSION
    )


class Migration(migrations.Migration):

    dependencies = [
        ("scans", "0031_scanjob_fingerprint"),
    ]

    operations = [
        migrations.RunPython(fill_demo_versions, migrations.RunPython.noop),
    ]
