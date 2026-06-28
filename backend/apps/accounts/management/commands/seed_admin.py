"""建立或更新「種子管理員」帳號。

設計原則（呼應專案規則「禁止硬編碼任何敏感資訊」）：
- 密碼一律由 `--password` 參數或環境變數 `SEED_ADMIN_PASSWORD` 提供，
  程式碼內**不**出現任何明碼密碼。
- email 同樣可由 `--email` 或 `SEED_ADMIN_EMAIL` 提供。
- 冪等：帳號已存在時更新其密碼與權限旗標，不重複建立。

本機 / 部署機用法（密碼只存在於當下 shell 或 .env，不進 git）：

    uv run python backend/manage.py seed_admin \
        --email 115401@gmail.com --password "<密碼>"

或在 .env 設定 SEED_ADMIN_EMAIL / SEED_ADMIN_PASSWORD 後直接：

    uv run python backend/manage.py seed_admin
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "建立或更新種子管理員帳號（預設 superuser）；密碼由參數或環境變數提供，不硬編碼。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            default=os.getenv("SEED_ADMIN_EMAIL", ""),
            help="管理員 email（亦可用環境變數 SEED_ADMIN_EMAIL）。",
        )
        parser.add_argument(
            "--password",
            default=os.getenv("SEED_ADMIN_PASSWORD", ""),
            help="管理員密碼（亦可用環境變數 SEED_ADMIN_PASSWORD）；至少 8 碼。",
        )
        parser.add_argument(
            "--staff-only",
            action="store_true",
            help="只設為一般管理員（is_staff），不授予 superuser。",
        )

    def handle(self, *args, **options):
        email = (options["email"] or "").strip().lower()
        password = options["password"] or ""

        if not email or "@" not in email:
            raise CommandError(
                "請以 --email 或環境變數 SEED_ADMIN_EMAIL 提供有效的 email。"
            )
        if len(password) < 8:
            raise CommandError(
                "請以 --password 或環境變數 SEED_ADMIN_PASSWORD 提供至少 8 碼的密碼。"
            )

        is_super = not options["staff_only"]
        user_model = get_user_model()

        # username 與 email 一致（本專案 User.username 採 email 慣例）
        user, created = user_model.objects.get_or_create(
            username=email,
            defaults={"email": email},
        )
        user.email = email
        user.is_staff = True
        user.is_superuser = is_super
        user.set_password(password)
        user.save()

        role = "超級管理員（superuser）" if is_super else "一般管理員（staff）"
        action = "建立" if created else "更新"
        self.stdout.write(
            self.style.SUCCESS(f"已{action}{role}：{email}")
        )
