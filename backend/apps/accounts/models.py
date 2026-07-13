import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models, transaction
from django.utils import timezone


class User(AbstractUser):
    pass


class PasswordResetToken(models.Model):
    """忘記密碼用的單次有效 token。

    業界標準：
    - 32 bytes URL-safe random（≈ 256 bits 熵）
    - 預設 1 小時過期
    - 單次使用（mark used_at 後失效）
    - 同 user 產生新 token 時自動失效舊 token
    """

    DEFAULT_LIFETIME_MINUTES = 60

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
    )
    token_digest = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    request_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
        ]

    @classmethod
    def create_for_user(
        cls,
        user,
        request_ip: str | None = None,
        lifetime_minutes: int = DEFAULT_LIFETIME_MINUTES,
    ) -> "PasswordResetToken":
        with transaction.atomic():
            locked_user = type(user).objects.select_for_update().get(pk=user.pk)
            # 同 user 所有未用過的舊 token 全部失效（避免一帳號多 token 增加爆破面積）
            cls.objects.filter(user=locked_user, used_at__isnull=True).update(
                used_at=timezone.now()
            )
            raw_token = secrets.token_urlsafe(32)
            instance = cls.objects.create(
                user=locked_user,
                token_digest=cls.digest_token(raw_token),
                expires_at=timezone.now() + timedelta(minutes=lifetime_minutes),
                request_ip=request_ip,
            )
        # raw token 僅存在於本次 request 的記憶體，不寫入資料庫。
        instance.raw_token = raw_token
        return instance

    @staticmethod
    def digest_token(raw_token: str) -> str:
        return hmac.new(
            settings.PASSWORD_RESET_TOKEN_PEPPER.encode("utf-8"),
            raw_token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def is_valid(self) -> bool:
        return self.used_at is None and self.expires_at > timezone.now()

    def mark_used(self) -> None:
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])

    def __str__(self) -> str:
        return f"reset {self.user.username} exp={self.expires_at:%Y-%m-%d %H:%M}"

