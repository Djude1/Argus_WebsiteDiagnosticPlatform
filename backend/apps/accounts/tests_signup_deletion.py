"""2026-10-04：Google 授權註冊＋用戶名與密碼、用戶名登入、舊帳號補設、使用者自行刪除帳號。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import LoginEvent
from apps.accounts.signup import SIGNUP_SALT, make_signup_token
from apps.billing.models import CoinTransaction, PricingPlan, PurchaseOrder
from apps.billing.services import admin_adjust, get_or_create_wallet
from apps.mcp_access.models import McpApiKey
from apps.reviews.models import PlatformReview
from apps.scans.models import (
    Page,
    ScanJob,
    SearchConsoleConnection,
    SiteProject,
    VerifiedDomain,
)
from apps.scans.seo import gsc

User = get_user_model()
GOOGLE = "apps.accounts.signup.id_token.verify_oauth2_token"
PASSWORD = "StrongPass123!"


def google_info(email):
    return {"email": email, "email_verified": True, "given_name": "小明", "family_name": "王"}


@override_settings(GOOGLE_OAUTH_CLIENT_ID="fake-client-id")
class GoogleRegistrationTests(APITestCase):
    def setUp(self):
        cache.clear()

    def start(self, email):
        with patch(GOOGLE, return_value=google_info(email)):
            return self.client.post(
                "/api/auth/register/google/", {"credential": "c"}, format="json"
            )

    def test_full_flow_creates_account_with_handle_password_and_google_name(self):
        started = self.start("ming@example.com")
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.data["email"], "ming@example.com")
        self.assertFalse(User.objects.filter(email="ming@example.com").exists())

        response = self.client.post("/api/auth/register/", {
            "signup_token": started.data["signup_token"], "handle": " Ming_01 ",
            "password": PASSWORD,
        }, format="json")

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="ming@example.com")
        self.assertEqual((user.handle, user.first_name, user.last_name), ("ming_01", "小明", "王"))
        self.assertTrue(user.check_password(PASSWORD))
        self.assertTrue(response.cookies["argus_refresh_token"]["httponly"])

    def test_registered_google_account_is_told_to_log_in(self):
        User.objects.create_user(username="old@example.com", email="old@example.com")
        response = self.start("old@example.com")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "already_registered")

    def test_handle_rules(self):
        User.objects.create_user(username="a@example.com", email="a@example.com", handle="taken")
        token = make_signup_token({"email": "b@example.com"})
        for handle in ("ab", "has space", "x@y", "admin", "taken", "-start", "a" * 31):
            with self.subTest(handle=handle):
                response = self.client.post("/api/auth/register/", {
                    "signup_token": token, "handle": handle, "password": PASSWORD,
                }, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn("handle", response.data)

    def test_weak_password_and_forged_or_expired_token_are_rejected(self):
        token = make_signup_token({"email": "c@example.com"})
        weak = self.client.post("/api/auth/register/", {
            "signup_token": token, "handle": "charlie", "password": "short",
        }, format="json")
        self.assertIn("password", weak.data)
        forged = signing.dumps({"email": "c@example.com"}, salt="other-salt")
        response = self.client.post("/api/auth/register/", {
            "signup_token": forged, "handle": "charlie", "password": PASSWORD,
        }, format="json")
        self.assertIn("signup_token", response.data)
        with patch("apps.accounts.signup.SIGNUP_MAX_AGE", -1):
            expired = self.client.post("/api/auth/register/", {
                "signup_token": signing.dumps({"email": "c@example.com"}, salt=SIGNUP_SALT),
                "handle": "charlie", "password": PASSWORD,
            }, format="json")
        self.assertIn("signup_token", expired.data)
        self.assertFalse(User.objects.filter(email="c@example.com").exists())

    def test_suggested_handle_avoids_taken_names(self):
        User.objects.create_user(username="x@example.com", email="x@example.com", handle="ming")
        self.assertEqual(self.start("ming@example.com").data["suggested_handle"], "ming2")


class HandleLoginAndSetupTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_login_with_email_or_handle(self):
        User.objects.create_user(
            username="dan@example.com", email="dan@example.com", password=PASSWORD, handle="dan"
        )
        for identifier in ("dan", "DAN", "dan@example.com", "Dan@Example.com"):
            with self.subTest(identifier=identifier):
                cache.clear()
                response = self.client.post(
                    "/api/auth/email-login/", {"email": identifier, "password": PASSWORD},
                    format="json",
                )
                self.assertEqual(response.status_code, 200)
        wrong = self.client.post(
            "/api/auth/email-login/", {"email": "dan", "password": "nope"}, format="json"
        )
        self.assertEqual(wrong.status_code, 401)

    def test_legacy_google_account_must_set_handle_and_password(self):
        user = User.objects.create_user(username="g@example.com", email="g@example.com")
        self.client.force_authenticate(user)
        self.assertTrue(self.client.get("/api/auth/me/").data["needs_setup"])

        bad = self.client.post("/api/auth/me/setup/", {"handle": "gina"}, format="json")
        self.assertIn("password", bad.data)
        ok = self.client.post(
            "/api/auth/me/setup/", {"handle": "Gina", "password": PASSWORD}, format="json"
        )
        self.assertEqual(ok.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.handle, "gina")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertFalse(self.client.get("/api/auth/me/").data["needs_setup"])
        again = self.client.post("/api/auth/me/setup/", {"handle": "other"}, format="json")
        self.assertEqual(again.status_code, 400)

    def test_legacy_email_account_only_needs_handle(self):
        user = User.objects.create_user(
            username="e@example.com", email="e@example.com", password=PASSWORD
        )
        self.client.force_authenticate(user)
        response = self.client.post("/api/auth/me/setup/", {"handle": "eve"}, format="json")
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password(PASSWORD))


@override_settings(MEDIA_ROOT=Path(settings.BASE_DIR) / "media" / "test-account-deletion")
class DeleteAccountTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="del@example.com", email="del@example.com", password=PASSWORD,
            handle="deleteme", first_name="刪",
        )
        self.client.force_authenticate(self.user)

    def tearDown(self):
        import shutil

        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)

    def _populate(self):
        admin = User.objects.create_superuser("root@example.com", "root@example.com", PASSWORD)
        admin_adjust(target_user=self.user, delta=100, admin_actor=admin, note="test")
        scan = ScanJob.objects.create(
            user=self.user, original_url="https://del.example.com/",
            normalized_url="https://del.example.com/", origin="https://del.example.com",
            status=ScanJob.Status.COMPLETED,
        )
        shot = Path(settings.MEDIA_ROOT) / "scans" / str(scan.id) / "page-1.png"
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_bytes(b"png")
        Page.objects.create(
            scan_job=scan, url="https://del.example.com/", final_url="https://del.example.com/",
            origin="https://del.example.com", screenshot_path=str(shot),
        )
        SearchConsoleConnection.objects.create(
            project=scan.project, user=self.user,
            refresh_token_encrypted=gsc.encrypt_token("r"), property_url="sc-domain:x",
        )
        VerifiedDomain.objects.create(user=self.user, domain="del.example.com", token="t" * 32)
        McpApiKey.objects.create(user=self.user, name="k", prefix="argus_mcp_x", key_hash="h")
        PlatformReview.objects.create(user=self.user, rating=5, title="t", comment="c")
        LoginEvent.objects.create(user=self.user, method=LoginEvent.Method.PASSWORD)
        plan = PricingPlan.objects.first()
        if plan:
            PurchaseOrder.objects.create(
                user=self.user, plan=plan, price_ntd=100, coin_amount=100,
                buyer_name="王小明", buyer_email="del@example.com", tax_id="12345678",
            )
        RefreshToken.for_user(self.user)
        return scan, shot

    def delete(self, **data):
        body = {"password": PASSWORD, "confirm": "刪除帳號", **data}
        return self.client.post("/api/auth/me/delete/", body, format="json")

    def test_requires_password_and_confirmation(self):
        self.assertIn("confirm", self.delete(confirm="").data)
        self.assertIn("password", self.delete(password="wrong").data)
        self.assertTrue(User.objects.get(pk=self.user.pk).is_active)

    def test_staff_can_delete_themselves_and_lose_admin(self):
        User.objects.filter(pk=self.user.pk).update(is_staff=True)
        self.user.refresh_from_db()
        self.client.force_authenticate(self.user)
        self.assertEqual(self.delete().status_code, 204)
        user = User.objects.get(pk=self.user.pk)
        self.assertFalse(user.is_staff or user.is_superuser or user.is_active)

    def test_last_superuser_cannot_delete_but_one_of_two_can(self):
        User.objects.filter(pk=self.user.pk).update(is_staff=True, is_superuser=True)
        self.user.refresh_from_db()
        self.client.force_authenticate(self.user)
        response = self.delete()
        self.assertEqual(response.status_code, 403)
        self.assertIn("最後一位超級管理員", response.data["detail"])
        User.objects.create_superuser("root2@example.com", "root2@example.com", PASSWORD)
        self.assertEqual(self.delete().status_code, 204)

    def test_deletes_personal_data_and_keeps_anonymous_billing(self):
        scan, shot = self._populate()
        wallet = get_or_create_wallet(self.user)
        transactions_before = list(
            CoinTransaction.objects.filter(wallet=wallet).values_list("id", "amount", "kind")
        )

        with patch("apps.scans.seo.gsc.httpx.post") as revoke, \
                self.captureOnCommitCallbacks(execute=True):
            response = self.delete()

        self.assertEqual(response.status_code, 204)
        revoke.assert_called_once()
        user = User.objects.get(pk=self.user.pk)
        self.assertFalse(user.is_active)
        self.assertTrue(user.deleted_at)
        self.assertEqual((user.email, user.first_name, user.handle), ("", "", None))
        self.assertTrue(user.username.startswith(f"deleted-{user.pk}-"))
        self.assertFalse(user.has_usable_password())
        for model, field in (
            (ScanJob, "user"), (SiteProject, "user"), (SearchConsoleConnection, "user"),
            (VerifiedDomain, "user"), (McpApiKey, "user"), (PlatformReview, "user"),
            (LoginEvent, "user"),
        ):
            with self.subTest(model=model.__name__):
                self.assertFalse(model.objects.filter(**{field: user}).exists())
        self.assertFalse(shot.exists())
        # 帳務：交易筆數、金額、種類完全不變
        self.assertEqual(
            list(CoinTransaction.objects.filter(wallet=wallet).values_list("id", "amount", "kind")),
            transactions_before,
        )
        for order in PurchaseOrder.objects.filter(user=user):
            self.assertEqual((order.buyer_name, order.tax_id), ("已刪除用戶", ""))
            self.assertNotIn("del@example.com", order.buyer_email)
        tokens = OutstandingToken.objects.filter(user=user)
        self.assertEqual(BlacklistedToken.objects.filter(token__in=tokens).count(), tokens.count())

    def test_deleted_account_cannot_log_in_and_google_email_can_register_again(self):
        self.delete()
        cache.clear()
        login = self.client.post(
            "/api/auth/email-login/", {"email": "deleteme", "password": PASSWORD}, format="json"
        )
        self.assertEqual(login.status_code, 401)
        self.client.force_authenticate(None)
        token = make_signup_token({"email": "del@example.com"})
        again = self.client.post("/api/auth/register/", {
            "signup_token": token, "handle": "deleteme", "password": PASSWORD,
        }, format="json")
        self.assertEqual(again.status_code, 201)


@override_settings(GOOGLE_OAUTH_CLIENT_ID="fake-client-id")
class SuspendedAccountLoginTests(APITestCase):
    """被管理員停用的帳號：密碼正確或 Google 驗證後回 403 account_suspended。"""

    def setUp(self):
        cache.clear()
        User.objects.create_user(
            username="ban@example.com", email="ban@example.com", password=PASSWORD,
            handle="banned", is_active=False,
        )

    def test_password_login(self):
        right = self.client.post(
            "/api/auth/email-login/", {"email": "banned", "password": PASSWORD}, format="json"
        )
        self.assertEqual((right.status_code, right.data["code"]), (403, "account_suspended"))
        cache.clear()
        wrong = self.client.post(
            "/api/auth/email-login/", {"email": "banned", "password": "nope"}, format="json"
        )
        self.assertEqual(wrong.status_code, 401)

    def test_google_login_and_register_start(self):
        for url in ("/api/auth/google/", "/api/auth/register/google/"):
            with self.subTest(url=url), patch(GOOGLE, return_value=google_info("ban@example.com")):
                response = self.client.post(url, {"credential": "c"}, format="json")
                self.assertEqual(response.status_code, 403)
