import os

from django.contrib.auth.hashers import make_password
from django.db import migrations


def create_bootstrap_superuser(apps, schema_editor):
    """依環境變數自動建立本機開發用的超級使用者。

    使用者只跑 `migrate` 或 `docker compose up` 就會帶起一個可登入 Django Admin
    的帳號，省去手動 createsuperuser。若 username 已存在則略過，可重複執行。
    未設定環境變數（如正式部署）時不建立任何帳號。
    """

    username = os.environ.get("ARGUS_BOOTSTRAP_SUPERUSER_USERNAME", "").strip()
    password = os.environ.get("ARGUS_BOOTSTRAP_SUPERUSER_PASSWORD", "").strip()
    if not username or not password:
        return

    user_model = apps.get_model("accounts", "User")
    if user_model.objects.filter(username=username).exists():
        return

    user_model.objects.create(
        username=username,
        email=f"{username}@example.com",
        password=make_password(password),
        is_superuser=True,
        is_staff=True,
        is_active=True,
    )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [
        migrations.RunPython(
            create_bootstrap_superuser,
            migrations.RunPython.noop,
        ),
    ]
