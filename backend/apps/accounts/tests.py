from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import PasswordResetToken


@override_settings(GOOGLE_OAUTH_CLIENT_ID="fake-client-id")
class GoogleLoginTests(APITestCase):
    def setUp(self):
        # DRF 的 ScopedRateThrottle 把計數放在 default cache（LocMemCache），
        # 而 login scope 只有 10/min，且 Google 與 email 兩個登入端點共用同一個
        # bucket。測試程序內 cache 不會自動清空，累積後會讓後面的測試回 429，
        # 失敗與否取決於執行順序與機器速度。每個測試開頭清乾淨才穩定。
        cache.clear()
        self.url = reverse("google-login")

    @patch("apps.accounts.views.id_token.verify_oauth2_token")
    def test_google_login_creates_new_user(self, mock_verify):
        mock_verify.return_value = {
            "email": "new@example.com",
            "email_verified": True,
            "given_name": "New",
            "family_name": "User",
        }

        response = self.client.post(self.url, {"credential": "fake-token"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertNotIn("refresh", response.data)
        self.assertTrue(response.cookies["argus_refresh_token"]["httponly"])
        user = get_user_model().objects.get(username="new@example.com")
        self.assertEqual(user.email, "new@example.com")
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)

    @patch("apps.accounts.views.id_token.verify_oauth2_token")
    def test_google_login_reuses_existing_user(self, mock_verify):
        get_user_model().objects.create_user(
            username="existing@example.com",
            email="existing@example.com",
        )
        mock_verify.return_value = {
            "email": "existing@example.com",
            "email_verified": True,
        }

        response = self.client.post(self.url, {"credential": "fake-token"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            get_user_model().objects.filter(username="existing@example.com").count(),
            1,
        )

    @patch("apps.accounts.views.id_token.verify_oauth2_token")
    def test_google_login_rejects_unverified_email(self, mock_verify):
        mock_verify.return_value = {
            "email": "unverified@example.com",
            "email_verified": False,
        }

        response = self.client.post(self.url, {"credential": "fake-token"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            get_user_model().objects.filter(username="unverified@example.com").exists()
        )

    @patch("apps.accounts.views.id_token.verify_oauth2_token")
    def test_google_login_rejects_invalid_token(self, mock_verify):
        mock_verify.side_effect = ValueError("Token expired")

        response = self.client.post(self.url, {"credential": "bad-token"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_google_login_requires_credential(self):
        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class GoogleLoginConfigTests(APITestCase):
    def setUp(self):
        cache.clear()

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="")
    def test_returns_503_when_client_id_missing(self):
        response = self.client.post(
            reverse("google-login"),
            {"credential": "any"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)


@override_settings(PASSWORD_RESET_TOKEN_PEPPER="independent-test-pepper")
class PasswordResetTokenTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="reset@example.com",
            email="reset@example.com",
            password="OldPassword123!",
        )

    def test_database_stores_only_digest(self):
        token = PasswordResetToken.create_for_user(self.user)

        token.refresh_from_db()
        self.assertNotEqual(token.token_digest, token.raw_token)
        self.assertEqual(
            token.token_digest,
            PasswordResetToken.digest_token(token.raw_token),
        )
        self.assertNotIn("token", [field.name for field in PasswordResetToken._meta.fields])

    @patch("apps.accounts.views.send_password_reset_email", return_value=True)
    def test_raw_token_from_email_resets_password_once(self, mock_send):
        request_response = self.client.post(
            reverse("password-reset-request"),
            {"email": self.user.email},
            format="json",
        )
        raw_token = mock_send.call_args.kwargs["token"]

        self.assertEqual(request_response.status_code, status.HTTP_200_OK)
        self.assertFalse(PasswordResetToken.objects.filter(token_digest=raw_token).exists())
        first = self.client.post(
            reverse("password-reset-confirm"),
            {"token": raw_token, "new_password": "NewPassword456!"},
            format="json",
        )
        second = self.client.post(
            reverse("password-reset-confirm"),
            {"token": raw_token, "new_password": "AnotherPassword789!"},
            format="json",
        )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPassword456!"))

    def test_database_digest_cannot_be_used_as_raw_token(self):
        token = PasswordResetToken.create_for_user(self.user)

        response = self.client.post(
            reverse("password-reset-confirm"),
            {"token": token.token_digest, "new_password": "NewPassword456!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

class EmailAuthTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()

    def test_dev_login_route_is_removed(self):
        resp = self.client.post(
            "/api/auth/dev-login/",
            {"username": "dev-user"},
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 404)

    def test_register_creates_user(self):
        resp = self.client.post(
            "/api/auth/register/",
            {"email": "newuser@example.com", "password": "StrongPass123!"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.assertTrue(User.objects.filter(username="newuser@example.com").exists())

    def test_register_duplicate_email_fails(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.create_user(username="dup@example.com", email="dup@example.com", password="pw")
        resp = self.client.post(
            "/api/auth/register/",
            {"email": "dup@example.com", "password": "AnotherPass123!"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_email_login_returns_token(self):
        User = get_user_model()
        User.objects.create_user(
            username="logintest@example.com",
            email="logintest@example.com",
            password="MyPass999!",
        )
        resp = self.client.post(
            "/api/auth/email-login/",
            {"email": "logintest@example.com", "password": "MyPass999!"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.json())
        self.assertNotIn("refresh", resp.json())
        self.assertIn("argus_refresh_token", resp.cookies)

    def test_http_only_refresh_cookie_can_rotate_and_logout(self):
        User = get_user_model()
        User.objects.create_user(
            username="cookie@example.com",
            email="cookie@example.com",
            password="MyPass999!",
        )
        login = self.client.post(
            "/api/auth/email-login/",
            {"email": "cookie@example.com", "password": "MyPass999!"},
            content_type="application/json",
        )
        old_refresh = login.cookies["argus_refresh_token"].value

        refreshed = self.client.post("/api/auth/refresh/", content_type="application/json")
        new_refresh = refreshed.cookies["argus_refresh_token"].value
        logged_out = self.client.post("/api/auth/logout/", content_type="application/json")

        self.assertEqual(refreshed.status_code, 200)
        self.assertIn("access", refreshed.json())
        self.assertNotEqual(old_refresh, new_refresh)
        self.assertEqual(logged_out.status_code, 204)
        self.assertEqual(logged_out.cookies["argus_refresh_token"].value, "")

    def test_rotated_refresh_cookie_cannot_be_replayed(self):
        user = get_user_model().objects.create_user(
            username="replay@example.com",
            email="replay@example.com",
            password="MyPass999!",
        )
        old_refresh = str(RefreshToken.for_user(user))
        self.client.cookies["argus_refresh_token"] = old_refresh

        first = self.client.post("/api/auth/refresh/", content_type="application/json")
        self.client.cookies["argus_refresh_token"] = old_refresh
        replay = self.client.post("/api/auth/refresh/", content_type="application/json")

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(replay.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_change_password_revokes_all_refresh_tokens_and_clears_cookie(self):
        user = get_user_model().objects.create_user(
            username="change@example.com",
            email="change@example.com",
            password="OldPassword123!",
        )
        refresh = RefreshToken.for_user(user)
        self.client.cookies["argus_refresh_token"] = str(refresh)

        response = self.client.post(
            "/api/auth/change-password/",
            {"old_password": "OldPassword123!", "new_password": "NewPassword456!"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.cookies["argus_refresh_token"].value, "")
        outstanding = OutstandingToken.objects.get(jti=refresh["jti"])
        self.assertTrue(BlacklistedToken.objects.filter(token=outstanding).exists())

    def test_refresh_cookie_requires_csrf_header(self):
        csrf_client = Client(enforce_csrf_checks=True)
        User = get_user_model()
        User.objects.create_user(
            username="csrf@example.com",
            email="csrf@example.com",
            password="MyPass999!",
        )
        login = csrf_client.post(
            "/api/auth/email-login/",
            {"email": "csrf@example.com", "password": "MyPass999!"},
            content_type="application/json",
        )
        csrf_token = login.cookies["csrftoken"].value

        rejected = csrf_client.post("/api/auth/refresh/", content_type="application/json")
        accepted = csrf_client.post(
            "/api/auth/refresh/",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(rejected.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(accepted.status_code, status.HTTP_200_OK)

    def test_email_login_wrong_password_fails(self):
        User = get_user_model()
        User.objects.create_user(
            username="badpw@example.com",
            email="badpw@example.com",
            password="correct",
        )
        resp = self.client.post(
            "/api/auth/email-login/",
            {"email": "badpw@example.com", "password": "wrong"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_email_login_missing_field_is_bad_request_not_unauthorized(self):
        """欄位缺漏是請求格式問題（400），與帳密錯誤（401）必須分得開。"""
        resp = self.client.post(
            "/api/auth/email-login/",
            {"email": "nofields@example.com"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
