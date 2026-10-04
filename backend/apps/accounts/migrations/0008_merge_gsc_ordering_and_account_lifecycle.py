"""合併登入事件排序與帳號生命週期的獨立 migration。"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_loginevent_stable_ordering"),
        ("accounts", "0007_user_handle_and_deleted_at"),
    ]

    operations = []
