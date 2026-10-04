import logging

from config.client_ip import resolve_client_ip
from config.throttling import ScopedRateThrottle
from django.conf import settings
from django.contrib.auth import authenticate as django_authenticate
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import permissions, status, views
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.avatars import AvatarError, avatar_url, process_avatar
from apps.accounts.deletion import delete_account
from apps.accounts.emails import send_password_reset_email
from apps.accounts.models import LoginEvent, PasswordResetToken
from apps.accounts.signup import (
    GoogleTokenError,
    find_login_user,
    handle_error,
    make_signup_token,
    normalize_handle,
    read_signup_token,
    suggest_handle,
    verify_google_credential,
)
from apps.accounts.turnstile import turnstile_enabled, turnstile_rejection
from apps.billing.ecpay import EcpayActionError
from apps.billing.services import grant_monthly_bonus_if_needed, settle_subscription_safe
from apps.scans.demo.seed import create_demo_project_safely

logger = logging.getLogger(__name__)


def _record_login_event(request, user, method: str) -> None:
    """登入成功後寫一筆 LoginEvent；失敗只記 log，不影響登入回應。"""
    try:
        LoginEvent.objects.create(
            user=user,
            method=method,
            ip_address=resolve_client_ip(request) or None,
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
    except Exception:  # noqa: BLE001 — 紀錄失敗不該擋登入
        logger.exception("寫入 LoginEvent 失敗（user_pk=%s）", getattr(user, "pk", None))


def _auth_response(user, *, response_status: int) -> Response:
    refresh = RefreshToken.for_user(user)
    response = Response(
        {"access": str(refresh.access_token)},
        status=response_status,
    )
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        str(refresh),
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=settings.AUTH_REFRESH_COOKIE_SECURE,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
        path="/api/auth/",
    )
    return response


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        path="/api/auth/",
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
    )


def _finish_login(request, user, method: str, *, response_status=status.HTTP_200_OK) -> Response:
    """登入成功的共同收尾：最後登入時間、月贈點、登入紀錄、訂閱結算、JWT。"""
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    grant_monthly_bonus_if_needed(user)
    _record_login_event(request, user, method)
    settle_subscription_safe(user)
    get_token(request)
    return _auth_response(user, response_status=response_status)


def _google_unavailable() -> Response | None:
    if not settings.GOOGLE_OAUTH_CLIENT_ID:
        return Response(
            {"config": "伺服器尚未設定 GOOGLE_OAUTH_CLIENT_ID，無法使用 Google 授權。"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return None


def _registration_payload(profile: dict) -> dict:
    return {
        "code": "registration_required",
        "detail": "這個 Google 帳號還沒有註冊，請設定用戶名與密碼完成註冊。",
        "signup_token": make_signup_token(profile),
        "email": profile["email"],
        "suggested_handle": suggest_handle(profile["email"]),
    }


def _suspended_response() -> Response:
    """被管理員停用的帳號：明確告知，不當成帳密錯誤或未註冊。"""
    return Response(
        {"code": "account_suspended", "detail": "此帳號已被停用，如有疑問請聯絡我們。"},
        status=status.HTTP_403_FORBIDDEN,
    )


@method_decorator(ensure_csrf_cookie, name="dispatch")
class GoogleLoginView(views.APIView):
    """以 Google ID Token 登入既有帳號。

    2026-10-04 起不再自動建立帳號：Google 帳號尚未註冊時回 409 `registration_required`
    並附 signup_token，前端直接切到「設定用戶名與密碼」完成註冊。
    本端點不簽發 superuser/staff 權限（staff/superuser 僅由 seed_admin 設定）。
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        if unavailable := _google_unavailable():
            return unavailable
        try:
            profile = verify_google_credential(request.data.get("credential"))
        except GoogleTokenError as exc:
            return Response({"credential": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        user = find_login_user(profile["email"])
        if user is None:
            if find_login_user(profile["email"], suspended=True):
                return _suspended_response()
            return Response(_registration_payload(profile), status=status.HTTP_409_CONFLICT)
        return _finish_login(request, user, LoginEvent.Method.GOOGLE)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class GoogleRegisterStartView(views.APIView):
    """註冊第一步：Google 授權確認 Email，回傳 signup_token（此時尚未建立帳號）。"""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def post(self, request):
        if unavailable := _google_unavailable():
            return unavailable
        try:
            profile = verify_google_credential(request.data.get("credential"))
        except GoogleTokenError as exc:
            return Response({"credential": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if find_login_user(profile["email"], suspended=True):
            return _suspended_response()
        if find_login_user(profile["email"]) is not None:
            return Response(
                {"code": "already_registered", "detail": "這個 Google 帳號已經註冊，請直接登入。"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(_registration_payload(profile))


class TurnstileConfigView(views.APIView):
    """公開：前端是否要顯示 Turnstile 元件，以及要用的 site key（公開值）。"""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        enabled = turnstile_enabled()
        site_key = settings.TURNSTILE_SITE_KEY if enabled else ""
        return Response({"enabled": enabled, "site_key": site_key})


@method_decorator(ensure_csrf_cookie, name="dispatch")
class EmailRegisterView(views.APIView):
    """註冊第二步：帶 Google 簽發的 signup_token 設定用戶名與密碼，建立帳號並登入。

    不再接受只填 Email＋密碼的註冊：Email 一律由 Google 驗證（新帳號必經 Google 授權）。
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def post(self, request):
        try:
            profile = read_signup_token(request.data.get("signup_token"))
        except signing.BadSignature:
            return Response(
                {"signup_token": "Google 授權已過期，請重新以 Google 授權註冊。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        email = profile["email"]
        handle = normalize_handle(request.data.get("handle"))
        password = request.data.get("password") or ""
        if error := handle_error(handle):
            return Response({"handle": error}, status=status.HTTP_400_BAD_REQUEST)
        user_model = get_user_model()
        try:
            validate_password(password, user=user_model(username=email, email=email))
        except DjangoValidationError as exc:
            return Response({"password": list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        if find_login_user(email) is not None or user_model.objects.filter(username=email).exists():
            return Response(
                {"detail": "這個 Google 帳號已經註冊，請直接登入。"},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            with transaction.atomic():
                user = user_model.objects.create_user(
                    username=email,
                    email=email,
                    password=password,
                    handle=handle,
                    first_name=profile.get("first_name", ""),
                    last_name=profile.get("last_name", ""),
                )
        except IntegrityError:
            return Response({"handle": "這個用戶名已被使用。"}, status=status.HTTP_400_BAD_REQUEST)
        response = _finish_login(
            request, user, LoginEvent.Method.REGISTER, response_status=status.HTTP_201_CREATED
        )
        # 新帳號先有一個示範專案，進來就看得到完整的分析結果（失敗不影響註冊）
        create_demo_project_safely(user)
        return response


@method_decorator(ensure_csrf_cookie, name="dispatch")
class EmailLoginView(views.APIView):
    """以 Email 或用戶名＋密碼登入，回傳 JWT（欄位沿用 email，也接受 identifier）。"""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        if rejection := turnstile_rejection(request, "login"):
            return rejection
        identifier = request.data.get("identifier") or request.data.get("email") or ""
        password = request.data.get("password") or ""

        if not identifier.strip() or not password:
            return Response(
                {"detail": "請提供 Email 或用戶名與密碼。"}, status=status.HTTP_400_BAD_REQUEST
            )

        candidate = find_login_user(identifier)
        user = (
            django_authenticate(request, username=candidate.username, password=password)
            if candidate
            else None
        )
        if not user and (suspended := find_login_user(identifier, suspended=True)):
            # 停用帳號只有在密碼正確時才說明，避免被拿來探測帳號是否存在
            if suspended.check_password(password):
                return _suspended_response()
        if not user:
            # 認證失敗回 401 而非 400：400 與 DisallowedHost、CSRF 等設定層錯誤同碼，
            # 排查時無法從狀態碼分辨是「帳密錯」還是「環境壞了」。欄位缺漏才是 400。
            return Response(
                {"detail": "帳號或密碼錯誤。"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return _finish_login(request, user, LoginEvent.Method.PASSWORD)


@method_decorator(csrf_protect, name="dispatch")
class CookieTokenRefreshView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        raw_refresh = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
        if not raw_refresh:
            return Response({"detail": "登入狀態已失效。"}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            with transaction.atomic():
                old_refresh = RefreshToken(raw_refresh)
                outstanding = OutstandingToken.objects.select_for_update().get(
                    jti=old_refresh["jti"]
                )
                if BlacklistedToken.objects.filter(token=outstanding).exists():
                    raise TokenError("refresh token 已使用")
                user = get_user_model().objects.get(
                    pk=old_refresh["user_id"],
                    is_active=True,
                )
                BlacklistedToken.objects.create(token=outstanding)
        except (
            IntegrityError,
            OutstandingToken.DoesNotExist,
            TokenError,
            get_user_model().DoesNotExist,
            KeyError,
        ):
            response = Response(
                {"detail": "登入狀態已失效。"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            _clear_refresh_cookie(response)
            return response
        return _auth_response(user, response_status=status.HTTP_200_OK)


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        raw_refresh = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
        if raw_refresh:
            try:
                RefreshToken(raw_refresh).blacklist()
            except TokenError:
                pass
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_refresh_cookie(response)
        return response


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
            "avatar_url": avatar_url(user),
            "handle": user.handle or "",
            "has_password": user.has_usable_password(),
            # 舊帳號缺用戶名或密碼：前端導到「完成帳號設定」，設定好才能使用其他功能
            "needs_setup": user.needs_setup,
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


class AccountSetupView(views.APIView):
    """舊帳號補設用戶名與（沒有密碼時）密碼；兩者都已設定時回 400。"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if not user.needs_setup:
            return Response({"detail": "帳號已完成設定。"}, status=status.HTTP_400_BAD_REQUEST)
        # 全部驗證通過才寫入：只改一半會讓下一次請求誤以為用戶名已設定
        handle = None
        if not user.handle:
            handle = normalize_handle(request.data.get("handle"))
            if error := handle_error(handle, exclude_pk=user.pk):
                return Response({"handle": error}, status=status.HTTP_400_BAD_REQUEST)
        password = None
        if not user.has_usable_password():
            password = request.data.get("password") or ""
            try:
                validate_password(password, user=user)
            except DjangoValidationError as exc:
                return Response(
                    {"password": list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST
                )
        update_fields = []
        if handle:
            user.handle = handle
            update_fields.append("handle")
        if password is not None:
            user.set_password(password)
            update_fields.append("password")
        try:
            user.save(update_fields=update_fields)
        except IntegrityError:
            return Response({"handle": "這個用戶名已被使用。"}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "帳號設定完成。", "handle": user.handle})


@method_decorator(csrf_protect, name="dispatch")
class DeleteAccountView(views.APIView):
    """使用者自行刪除帳號（不可復原）：需要密碼與輸入確認文字，規則見 accounts/deletion.py。"""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"
    CONFIRM_TEXT = "刪除帳號"

    def post(self, request):
        user = request.user
        if (request.data.get("confirm") or "").strip() != self.CONFIRM_TEXT:
            return Response(
                {"confirm": f"請輸入「{self.CONFIRM_TEXT}」確認。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not user.check_password(request.data.get("password") or ""):
            return Response({"password": "密碼錯誤。"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            delete_account(user)
        except (PermissionError, EcpayActionError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_refresh_cookie(response)
        return response


class MeAvatarView(views.APIView):
    """上傳（POST，multipart 欄位 `avatar`）或移除（DELETE）自己的大頭貼。

    圖片由 `apps.accounts.avatars.process_avatar` 解碼後重新編碼成 256×256 PNG；
    換圖或移除時一併刪掉舊檔。
    """

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "avatar_upload"

    def post(self, request):
        upload = request.FILES.get("avatar")
        if upload is None:
            return Response({"detail": "請選擇一張圖片。"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            content = process_avatar(upload)
        except AvatarError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        user = request.user
        old = user.avatar.name if user.avatar else None
        user.avatar.save(content.name, content, save=False)
        user.save(update_fields=["avatar"])
        if old:
            user.avatar.storage.delete(old)
        return Response({"avatar_url": avatar_url(user)})

    def delete(self, request):
        user = request.user
        if user.avatar:
            name = user.avatar.name
            user.avatar = None
            user.save(update_fields=["avatar"])
            user._meta.get_field("avatar").storage.delete(name)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    GENERIC_OK = {
        "detail": (
            "若該 Email 已註冊本平台帳號（且設有密碼），重設信已寄出，"
            "請至信箱收信並於 60 分鐘內完成重設。"
        ),
    }

    def post(self, request):
        if rejection := turnstile_rejection(request, "password_reset"):
            return rejection
        email = (request.data.get("email") or "").strip().lower()
        if not email or "@" not in email:
            # 連格式都不對也回成功（不暗示 email 是否註冊）
            return Response(self.GENERIC_OK)

        user_model = get_user_model()
        user = user_model.objects.filter(username=email).first()

        # 只對 email 帳號（has_usable_password）寄信；Google 帳號無密碼，寄了也沒意義
        if user and user.has_usable_password():
            token = PasswordResetToken.create_for_user(
                user,
                request_ip=resolve_client_ip(request),
            )
            base_url = request.build_absolute_uri("/")[:-1]
            send_password_reset_email(
                user_email=user.email or email,
                token=token.raw_token,
                base_url=base_url,
                expires_minutes=PasswordResetToken.DEFAULT_LIFETIME_MINUTES,
            )

        # 不論寄信成功或失敗、user 存不存在，都回相同訊息
        return Response(self.GENERIC_OK)


class PasswordResetConfirmView(views.APIView):
    """忘記密碼 step 2：用 token 設定新密碼。"""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        token_value = (request.data.get("token") or "").strip()
        new_password = request.data.get("new_password") or ""

        if not token_value:
            return Response(
                {"token": "缺少重設 token。"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            token = (
                PasswordResetToken.objects.select_for_update()
                .select_related("user")
                .filter(token_digest=PasswordResetToken.digest_token(token_value))
                .first()
            )
            if token is None or not token.is_valid():
                return Response(
                    {"token": "重設連結無效或已過期，請重新申請。"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # 在鎖定 token 後才驗證並更新，避免並行 request 同時通過單次使用檢查。
            try:
                validate_password(new_password, user=token.user)
            except DjangoValidationError as exc:
                return Response(
                    {"new_password": list(exc.messages)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = token.user
            user.set_password(new_password)
            user.save(update_fields=["password"])
            token.mark_used()
            for outstanding in OutstandingToken.objects.filter(user=user):
                BlacklistedToken.objects.get_or_create(token=outstanding)
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
        try:
            validate_password(new_password, user=request.user)
        except DjangoValidationError as exc:
            return Response(
                {"new_password": list(exc.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
            user.set_password(new_password)
            user.save(update_fields=["password"])
            for outstanding in OutstandingToken.objects.filter(user=user):
                BlacklistedToken.objects.get_or_create(token=outstanding)
        response = Response({"detail": "密碼已更新，請重新登入。"})
        _clear_refresh_cookie(response)
        return response
