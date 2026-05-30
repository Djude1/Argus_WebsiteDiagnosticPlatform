# -*- coding: utf-8 -*-
from django.db import migrations


LEGAL_TITLE = "重要法律聲明 — 授權掃描義務"

LEGAL_CONTENT = """依台灣《刑法》第 358、359、360 條及相關法規，未經網站擁有者明確書面授權，對他人網站進行自動化掃描、爬取或滲透測試，可能構成非法入侵電腦罪，面臨刑事追訴。

使用 Argus 時，您必須確認：
1. 您是該網站的擁有者，或
2. 您已取得網站擁有者的書面授權。

Argus 對任何未授權掃描行為不承擔法律責任，因違法使用產生的一切後果由使用者自行承擔。"""


def seed_legal_announcement(apps, schema_editor):
    Announcement = apps.get_model("admin_api", "Announcement")
    Announcement.objects.get_or_create(
        title=LEGAL_TITLE,
        defaults={
            "type": "permanent",
            "is_active": True,
            "content": LEGAL_CONTENT,
        },
    )


def remove_legal_announcement(apps, schema_editor):
    Announcement = apps.get_model("admin_api", "Announcement")
    Announcement.objects.filter(title=LEGAL_TITLE, type="permanent").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("admin_api", "0002_add_announcement_model"),
    ]

    operations = [
        migrations.RunPython(seed_legal_announcement, remove_legal_announcement),
    ]
