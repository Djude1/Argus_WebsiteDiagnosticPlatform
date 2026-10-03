"""首頁功能卡「Word 報告匯出」改為 PDF（2026-10-03 報告改為只提供 PDF）。

只更新仍是種子原文的資料列；管理員在後台改過的內容不動。
"""

from django.db import migrations

OLD_TITLE = "Word 報告匯出"
OLD_DESCRIPTION = "python-docx 自動生成完整報告：封面、摘要、各頁 Findings、附錄；給管理層直接交付。"
NEW_TITLE = "PDF 報告匯出"
NEW_DESCRIPTION = "自動生成完整 PDF 報告：封面、摘要、各頁 Findings、附錄與防偽編號；給管理層直接交付。"


def forwards(apps, schema_editor):
    ProjectFeature = apps.get_model("content", "ProjectFeature")
    ProjectFeature.objects.filter(title=OLD_TITLE, description=OLD_DESCRIPTION).update(
        title=NEW_TITLE, description=NEW_DESCRIPTION
    )


def backwards(apps, schema_editor):
    ProjectFeature = apps.get_model("content", "ProjectFeature")
    ProjectFeature.objects.filter(title=NEW_TITLE, description=NEW_DESCRIPTION).update(
        title=OLD_TITLE, description=OLD_DESCRIPTION
    )


class Migration(migrations.Migration):
    dependencies = [("content", "0014_partner_inquiry_spam_status")]

    operations = [migrations.RunPython(forwards, backwards)]
