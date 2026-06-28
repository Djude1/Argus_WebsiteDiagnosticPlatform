from django.conf import settings
from django.contrib.auth import authenticate as django_authenticate
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from rest_framework import permissions, status, views
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.emails import send_password_reset_email
from apps.accounts.models import PasswordResetToken
from apps.billing.services import grant_monthly_bonus_if_needed


def _client_ip(request) -> str | None:
    """從 request 取最可信的 client IP（信任 X-Forwarded-For 第一段）。"""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class GoogleLoginView(views.APIView):
    """以 Google ID Token 完成登入或註冊（一般使用者登入方式之一，另有 email/密碼）。

    首次成功驗證的 Google 帳號會自動建立對應的 User（username=email）。
    管理員亦以前台 email 登入後進 React /admin（django-admin 已移除）；
    本端點不簽發 superuser/staff 權限（staff/superuser 僅由 seed_admin 設定）。
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        credential = request.data.get("credential")
        if not credential:
            return Response(
                {"credential": "缺少 Google ID Token。"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        client_id = settings.GOOGLE_OAUTH_CLIENT_ID
        if not client_id:
            return Response(
                {"config": "伺服器尚未設定 GOOGLE_OAUTH_CLIENT_ID，無法驗證 Google 登入。"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            info = id_token.verify_oauth2_token(
                credential,
                google_requests.Request(),
                client_id,
                # 容忍 ±10 秒的本機/Google 時鐘漂移（WSL2 host 從 sleep/hibernate
                # 恢復後 vm 時鐘不會自動 NTP sync，曾觀察到固定慢 2 秒導致
                # "Token used too early"。預設為 0 太嚴格）。
                clock_skew_in_seconds=10,
            )
        except ValueError:
            return Response(
                {"credential": "Google ID Token 無效或已過期。"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = info.get("email")
        if not email or not info.get("email_verified"):
            return Response(
                {"credential": "Google 帳號 email 未驗證，無法登入。"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_model = get_user_model()
        user, _ = user_model.objects.get_or_create(
            username=email,
            defaults={
                "email": email,
                "first_name": (info.get("given_name") or "")[:150],
                "last_name": (info.get("family_name") or "")[:150],
            },
        )
        # 每次登入：更新最後登入時間 + 本月若未領則自動補發 200 coin
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        grant_monthly_bonus_if_needed(user)
        refresh = RefreshToken.for_user(user)
        return Response(
            {"access": str(refresh.access_token), "refresh": str(refresh)},
            status=status.HTTP_200_OK,
        )


class EmailRegisterView(views.APIView):
    """以 email + password 建立帳號。"""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        password = request.data.get("password") or ""

        if not email or "@" not in email:
            return Response(
                {"email": "請輸入有效的 Email。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(password) < 8:
            return Response(
                {"password": "密碼至少需要 8 個字元。"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_model = get_user_model()
        if user_model.objects.filter(username=email).exists():
            return Response({"email": "此 Email 已被註冊。"}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user = user_model.objects.create_user(
                username=email,
                email=email,
                password=password,
            )
            user.last_login = timezone.now()
            user.save(update_fields=["last_login"])
            grant_monthly_bonus_if_needed(user)
        refresh = RefreshToken.for_user(user)
        return Response(
            {"access": str(refresh.access_token), "refresh": str(refresh)},
            status=status.HTTP_201_CREATED,
        )


class EmailLoginView(views.APIView):
    """以 email + password 登入，回傳 JWT。"""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        password = request.data.get("password") or ""

        if not email or not password:
            return Response({"detail": "請提供 email 與密碼。"}, status=status.HTTP_400_BAD_REQUEST)

        user = django_authenticate(request, username=email, password=password)
        if not user:
            return Response({"detail": "Email 或密碼錯誤。"}, status=status.HTTP_400_BAD_REQUEST)

        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        grant_monthly_bonus_if_needed(user)
        refresh = RefreshToken.for_user(user)
        return Response(
            {"access": str(refresh.access_token), "refresh": str(refresh)},
            status=status.HTTP_200_OK,
        )


class MeView(views.APIView):
    """取得或更新目前登入使用者的個人資料。"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "display_name": f"{user.first_name} {user.last_name}".strip() or user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_staff": user.is_staff,
            "date_joined": user.date_joined,
            "last_login": user.last_login,
            # 若管理員在 Django Admin 手動為 Google 使用者設密碼，這裡會判成 email。
            "auth_provider": "google" if not user.has_usable_password() else "email",
        })

    def patch(self, request):
        user = request.user
        first_name = request.data.get("first_name")
        last_name = request.data.get("last_name")
        if first_name is not None:
            user.first_name = first_name[:150]
        if last_name is not None:
            user.last_name = last_name[:150]
        user.save(update_fields=["first_name", "last_name"])
        return Response({"detail": "已更新。"})


class PasswordResetRequestView(views.APIView):
    """忘記密碼 step 1：寄出含 token 的重設信。

    安全規格（業界標準）：
    - 永遠回相同的 200（不論 email 是否註冊）→ 防 account enumeration
    - token 用 secrets.token_urlsafe(32)（≈256 bit 熵）
    - 同 user 舊未用 token 全部失效（model 內處理）
    - 預設 60 分鐘過期
    - Google-only 帳號（無可用密碼）不寄信（避免使用者誤以為設好了密碼）
    """

    permission_classes = [permissions.AllowAny]

    GENERIC_OK = {
        "detail": "若該 Email 已註冊本平台帳號（且設有密碼），重設信已寄出，請至信箱收信並於 60 分鐘內完成重設。",
    }

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        if not email or "@" not in email:
            # 連格式都不對也回成功（不暗示 email 是否註冊）
            return Response(self.GENERIC_OK)

        user_model = get_user_model()
        user = user_model.objects.filter(username=email).first()

        # 只對 email 帳號（has_usable_password）寄信；Google 帳號無密碼，寄了也沒意義
        if user and user.has_usable_password():
            token = PasswordResetToken.create_for_user(user, request_ip=_client_ip(request))
            base_url = request.build_absolute_uri("/")[:-1]
            send_password_reset_email(
                user_email=user.email or email,
                token=token.token,
                base_url=base_url,
                expires_minutes=PasswordResetToken.DEFAULT_LIFETIME_MINUTES,
            )

        # 不論寄信成功或失敗、user 存不存在，都回相同訊息
        return Response(self.GENERIC_OK)


class PasswordResetConfirmView(views.APIView):
    """忘記密碼 step 2：用 token 設定新密碼。"""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        token_value = (request.data.get("token") or "").strip()
        new_password = request.data.get("new_password") or ""

        if not token_value:
            return Response(
                {"token": "缺少重設 token。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(new_password) < 8:
            return Response(
                {"new_password": "新密碼至少需要 8 個字元。"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        token = (
            PasswordResetToken.objects.select_related("user")
            .filter(token=token_value)
            .first()
        )
        if token is None or not token.is_valid():
            return Response(
                {"token": "重設連結無效或已過期，請重新申請。"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 設密碼 + 失效 token + JWT 不簽發（讓使用者主動回登入頁登入，確認密碼可用）
        user = token.user
        with transaction.atomic():
            user.set_password(new_password)
            user.save(update_fields=["password"])
            token.mark_used()
        return Response({"detail": "密碼已重設，請用新密碼登入。"})


class ChangePasswordView(views.APIView):
    """變更密碼（僅 email 帳號）。"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # Google 帳號沒有可用密碼，不支援此端點
        if not request.user.has_usable_password():
            return Response(
                {"detail": "Google 帳號不支援密碼變更，請透過 Google 帳號設定管理密碼。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        old_password = request.data.get("old_password") or ""
        new_password = request.data.get("new_password") or ""
        if not request.user.check_password(old_password):
            return Response({"detail": "目前密碼錯誤。"}, status=status.HTTP_400_BAD_REQUEST)
        if len(new_password) < 8:
            return Response(
                {"detail": "新密碼至少需要 8 個字元。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        request.user.set_password(new_password)
        request.user.save(update_fields=["password"])
        return Response({"detail": "密碼已更新。"})
