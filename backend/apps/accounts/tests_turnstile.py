"""Cloudflare Turnstile：設定端點、四個受保護的公開表單、siteverify 判定與部署檢查。"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import yaml
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.checks import check_turnstile_settings

ENABLED = {
    "TURNSTILE_SITE_KEY": "0x4AAAAAAA-test-site-key",
    "TURNSTILE_SECRET": "test-secret-value",
    "TURNSTILE_HOSTNAMES": ["xn--gst.tw", "www.xn--gst.tw"],
}
DISABLED = {"TURNSTILE_SITE_KEY": "", "TURNSTILE_SECRET": "", "TURNSTILE_HOSTNAMES": []}

SITEVERIFY = "apps.accounts.turnstile.httpx.post"
MEMBER = "member@example.com"
TOKEN = "cf-turnstile-response"


def siteverify_result(**fields):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = fields
    return response


@override_settings(**DISABLED)
class TurnstileConfigTests(APITestCase):
    def test_disabled_without_keys(self):
        response = self.client.get("/api/auth/turnstile/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"enabled": False, "site_key": ""})

    @override_settings(**ENABLED)
    def test_enabled_returns_public_site_key_only(self):
        response = self.client.get("/api/auth/turnstile/")
        expected = {"enabled": True, "site_key": ENABLED["TURNSTILE_SITE_KEY"]}
        self.assertEqual(response.json(), expected)
        self.assertNotIn(ENABLED["TURNSTILE_SECRET"], response.content.decode())

    @override_settings(TURNSTILE_SITE_KEY="only-site-key", TURNSTILE_SECRET="")
    def test_half_configured_counts_as_disabled(self):
        self.assertEqual(self.client.get("/api/auth/turnstile/").json()["enabled"], False)


@override_settings(**ENABLED)
class TurnstileProtectedFormsTests(APITestCase):
    def setUp(self):
        cache.clear()
        get_user_model().objects.create_user(
            username=MEMBER, email=MEMBER, password="StrongPass123!"
        )

    def surfaces(self):
        password = "StrongPass123!"
        return [
            ("/api/auth/register/", {"email": "new@example.com", "password": password}, "signup"),
            ("/api/auth/email-login/", {"email": MEMBER, "password": password}, "login"),
            ("/api/auth/password-reset/request/", {"email": MEMBER}, "password_reset"),
            (
                "/api/content/partner-inquiries/",
                {
                    "name": "王小明", "company": "範例數位", "email": "ming@example.com",
                    "partner_type": "agency", "message": "想在交付客戶網站前加入健檢報告。",
                },
                "contact",
            ),
        ]

    def test_missing_token_is_rejected_without_calling_siteverify(self):
        for url, payload, _action in self.surfaces():
            with self.subTest(url=url), patch(SITEVERIFY) as post:
                response = self.client.post(url, payload, format="json")
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["code"], "turnstile_failed")
                post.assert_not_called()

    def test_valid_token_with_matching_action_and_hostname_passes(self):
        expected_status = {"signup": 201, "login": 200, "password_reset": 200, "contact": 201}
        for url, payload, action in self.surfaces():
            cache.clear()
            result = siteverify_result(success=True, action=action, hostname="www.xn--gst.tw")
            with self.subTest(url=url), patch(SITEVERIFY, return_value=result) as post:
                response = self.client.post(
                    url, {**payload, TOKEN: "token-1"}, format="json",
                    REMOTE_ADDR="203.0.113.9",
                )
                self.assertEqual(response.status_code, expected_status[action], response.content)
                sent = post.call_args.kwargs["data"]
                self.assertEqual(sent["secret"], ENABLED["TURNSTILE_SECRET"])
                self.assertEqual(sent["response"], "token-1")
                self.assertEqual(sent["remoteip"], "203.0.113.9")

    def test_wrong_action_hostname_or_failure_is_rejected(self):
        bad_results = [
            siteverify_result(success=True, action="signup", hostname="xn--gst.tw"),
            siteverify_result(success=True, action="login", hostname="evil.example"),
            siteverify_result(success=False, **{"error-codes": ["timeout-or-duplicate"]}),
            siteverify_result(success="true", action="login", hostname="xn--gst.tw"),
        ]
        for result in bad_results:
            cache.clear()
            body = {
                "email": MEMBER, "password": "StrongPass123!", TOKEN: "t",
            }
            fields = result.json.return_value
            with self.subTest(result=fields), patch(SITEVERIFY, return_value=result):
                response = self.client.post("/api/auth/email-login/", body, format="json")
                self.assertEqual(response.status_code, 403)

    def test_network_error_and_oversized_token_are_rejected(self):
        with patch(SITEVERIFY, side_effect=httpx.ConnectTimeout("timeout")):
            response = self.client.post(
                "/api/auth/email-login/",
                {"email": MEMBER, "password": "x", TOKEN: "t"},
                format="json",
            )
        self.assertEqual(response.status_code, 403)
        with patch(SITEVERIFY) as post:
            response = self.client.post(
                "/api/auth/email-login/",
                {"email": MEMBER, "password": "x", TOKEN: "a" * 2049},
                format="json",
            )
        self.assertEqual(response.status_code, 403)
        post.assert_not_called()

    def test_testing_key_result_is_only_accepted_in_debug(self):
        testing = siteverify_result(
            success=True, hostname="example.com", metadata={"result_with_testing_key": True}
        )
        body = {"email": MEMBER, "password": "StrongPass123!", TOKEN: "t"}

        def login():
            return self.client.post("/api/auth/email-login/", body, format="json").status_code

        with patch(SITEVERIFY, return_value=testing):
            self.assertEqual(login(), 403)
            with override_settings(DEBUG=True):
                self.assertEqual(login(), 200)


@override_settings(**DISABLED)
class TurnstileDisabledTests(APITestCase):
    def test_forms_work_without_token_when_disabled(self):
        cache.clear()
        with patch(SITEVERIFY) as post:
            response = self.client.post(
                "/api/auth/register/",
                {"email": "plain@example.com", "password": "StrongPass123!"},
                format="json",
            )
        self.assertEqual(response.status_code, 201)
        post.assert_not_called()


class TurnstileDeployCheckTests(APITestCase):
    def ids(self):
        return [error.id for error in check_turnstile_settings(None)]

    def test_consistent_settings_pass(self):
        with override_settings(**ENABLED, DEBUG=False):
            self.assertEqual(self.ids(), [])
        with override_settings(**DISABLED, DEBUG=False):
            self.assertEqual(self.ids(), [])

    def test_half_configured_and_empty_hostnames_fail(self):
        half = {"TURNSTILE_SITE_KEY": "k", "TURNSTILE_SECRET": "", "TURNSTILE_HOSTNAMES": ["a.tw"]}
        with override_settings(**half):
            self.assertIn("accounts.W001", self.ids())
        with override_settings(**{**ENABLED, "TURNSTILE_HOSTNAMES": []}):
            self.assertIn("accounts.E002", self.ids())

    def test_localhost_not_allowed_in_production_hostnames(self):
        hostnames = ["xn--gst.tw", "localhost"]
        with override_settings(**{**ENABLED, "TURNSTILE_HOSTNAMES": hostnames}, DEBUG=False):
            self.assertIn("accounts.E003", self.ids())
        with override_settings(**{**ENABLED, "TURNSTILE_HOSTNAMES": hostnames}, DEBUG=True):
            self.assertNotIn("accounts.E003", self.ids())


class TurnstileHostnameSettingTests(APITestCase):
    def test_urls_in_setting_become_bare_hostnames(self):
        # siteverify 回傳的 hostname 不含協定；設定誤填成網址時不能讓整個網域的驗證都失敗
        from config.settings import _bare_hostname

        self.assertEqual(_bare_hostname("https://xn--gst.tw"), "xn--gst.tw")
        self.assertEqual(_bare_hostname("www.xn--gst.tw"), "www.xn--gst.tw")
        self.assertEqual(
            _bare_hostname("HTTPS://Argus.Clouda.dpdns.org:443/"), "argus.clouda.dpdns.org"
        )
        self.assertEqual(_bare_hostname("localhost:8000"), "localhost")
        self.assertEqual(_bare_hostname("  "), "")


class TurnstileK8sConfigTests(APITestCase):
    """正式 ConfigMap 的 TURNSTILE_HOSTNAMES 必須是純主機名。

    siteverify 回傳的 hostname 不含協定與連接埠；寫成 https://xn--gst.tw 會讓該網域的
    登入、註冊、忘記密碼與洽談在補上 secret 後全部被 403 擋下（2026-10-03 曾發生）。
    """

    def test_configmap_hostnames_are_bare_public_hostnames(self):
        manifest = Path(__file__).resolve().parents[3] / "k8s" / "01-namespace-config.yaml"
        config = next(
            document
            for document in yaml.safe_load_all(manifest.read_text(encoding="utf-8"))
            if document and document.get("kind") == "ConfigMap"
            and "TURNSTILE_HOSTNAMES" in document.get("data", {})
        )
        raw = config["data"]["TURNSTILE_HOSTNAMES"]
        hostnames = [h.strip() for h in raw.split(",") if h.strip()]
        self.assertTrue(hostnames)
        for hostname in hostnames:
            with self.subTest(hostname=hostname):
                self.assertNotIn("://", hostname)
                self.assertNotIn("/", hostname)
                self.assertNotIn(":", hostname)
                self.assertEqual(hostname, hostname.lower())
                self.assertNotIn(hostname, {"localhost", "127.0.0.1"})
