"""Google Search Console 網域驗證測試。

OAuth 流程不打真網路：token 交換與 sites 清單都 mock（httpx.post/get），
state 單次性與過期以簽署機制本身測試。沿用 tests_domain_verification 的
example.com 假資料慣例。
"""

import time as time_module
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.cache import cache
from django.core.cache.backends.locmem import LocMemCache
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.scans.google_site_verification import (
    _STATE_SALT,
    GoogleSiteVerificationError,
    _state_cache_key,
    build_authorization_url,
    build_state,
    consume_state,
    fetch_verified_site_entries,
    is_gsc_verification_enabled,
    resolve_redirect_uri,
    run_google_verification,
    site_url_matches_domain,
)
from apps.scans.models import VerifiedDomain

User = get_user_model()

_GSC_ON = override_settings(
    GOOGLE_OAUTH_CLIENT_ID="test-client-id.apps.googleusercontent.com",
    GOOGLE_OAUTH_CLIENT_SECRET="test-client-secret",
    ARGUS_GSC_REDIRECT_URI="",
)


def _fake_token_response():
    """模擬 Google token 端點的成功回應物件（httpx.Response 介面子集）。"""

    class _Response:
        status_code = 200

        def json(self):
            return {"access_token": "fake-access-token", "expires_in": 3599}

    return _Response()


def _fake_sites_response(entries):
    class _Response:
        status_code = 200

        def json(self):
            return {"siteEntry": entries}

    return _Response()


class EnabledFlagTests(TestCase):
    def test_disabled_without_secret(self):
        with override_settings(GOOGLE_OAUTH_CLIENT_ID="id", GOOGLE_OAUTH_CLIENT_SECRET=""):
            self.assertFalse(is_gsc_verification_enabled())

    def test_disabled_without_client_id(self):
        with override_settings(GOOGLE_OAUTH_CLIENT_ID="", GOOGLE_OAUTH_CLIENT_SECRET="s"):
            self.assertFalse(is_gsc_verification_enabled())

    def test_enabled_with_both(self):
        with _GSC_ON:
            self.assertTrue(is_gsc_verification_enabled())


class RedirectUriTests(SimpleTestCase):
    @override_settings(ARGUS_GSC_REDIRECT_URI="")
    def test_default_redirect_uses_registered_callback_route(self):
        request = RequestFactory().get("/", HTTP_HOST="127.0.0.1:8000")
        self.assertEqual(
            resolve_redirect_uri(request),
            "http://127.0.0.1:8000" + reverse("verified-domain-google-callback"),
        )

    @override_settings(ARGUS_GSC_REDIRECT_URI="https://example.com/api/domains/google/callback/")
    def test_explicit_redirect_override_is_preserved(self):
        request = RequestFactory().get("/", HTTP_HOST="127.0.0.1:8000")
        self.assertEqual(
            resolve_redirect_uri(request),
            "https://example.com/api/domains/google/callback/",
        )


@override_settings(
    SECRET_KEY="gsc-state-test-signing-key",
    CACHES={"default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "gsc-state-tests",
    }},
)
class StateTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="stateuser", password="x")

    def test_consume_valid_state_returns_payload(self):
        state = build_state(self.user.id, 42)
        payload = consume_state(state)
        self.assertEqual(payload["uid"], self.user.id)
        self.assertEqual(payload["did"], 42)

    def test_state_is_single_use(self):
        state = build_state(self.user.id, 42)
        consume_state(state)
        with self.assertRaises(GoogleSiteVerificationError):
            consume_state(state)

    def test_new_attempt_in_same_second_does_not_reenable_old_state(self):
        with patch("django.core.signing.time.time", return_value=time_module.time()):
            old_state = build_state(self.user.id, 42)
            consume_state(old_state)
            new_state = build_state(self.user.id, 42)
            self.assertNotEqual(old_state, new_state)
            consume_state(new_state)
            with self.assertRaises(GoogleSiteVerificationError):
                consume_state(old_state)

    def test_concurrent_callbacks_only_consume_state_once(self):
        state = build_state(self.user.id, 42)
        barrier = Barrier(2)
        original_get = LocMemCache.get

        def simultaneous_get(backend, key, *args, **kwargs):
            value = original_get(backend, key, *args, **kwargs)
            barrier.wait(timeout=5)
            return value

        def attempt():
            try:
                consume_state(state)
            except GoogleSiteVerificationError:
                return False
            return True

        with patch.object(LocMemCache, "get", new=simultaneous_get):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _: attempt(), range(2)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 1)

    def test_signed_state_without_nonce_is_rejected(self):
        state = signing.dumps({"uid": self.user.id, "did": 42}, salt=_STATE_SALT)
        cache.set(_state_cache_key(state), 1, 600)
        with self.assertRaises(GoogleSiteVerificationError):
            consume_state(state)

    def test_tampered_state_rejected(self):
        state = build_state(self.user.id, 42)
        with self.assertRaises(GoogleSiteVerificationError):
            consume_state(state[:-4] + "aaaa")

    def test_expired_state_rejected(self):
        with patch(
            "django.core.signing.time.time",
            return_value=time_module.time() - 700,
        ):
            old_state = signing.dumps({"uid": self.user.id, "did": 1}, salt=_STATE_SALT)
        with self.assertRaises(GoogleSiteVerificationError):
            consume_state(old_state)

    def test_authorization_url_contains_oauth_params(self):
        with _GSC_ON:
            url = build_authorization_url(
                self.user.id, 7, "http://127.0.0.1:8000/api/domains/google/callback/"
            )
        parsed = urlparse(url)
        self.assertEqual(parsed.scheme, "https")
        self.assertIn("accounts.google.com", parsed.netloc)
        query = parse_qs(parsed.query)
        self.assertEqual(query["client_id"], ["test-client-id.apps.googleusercontent.com"])
        self.assertEqual(
            query["redirect_uri"],
            ["http://127.0.0.1:8000/api/domains/google/callback/"],
        )
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(
            query["scope"], ["https://www.googleapis.com/auth/webmasters.readonly"]
        )
        self.assertEqual(query["access_type"], ["online"])
        payload = consume_state(query["state"][0])
        self.assertEqual(payload["uid"], self.user.id)
        self.assertEqual(payload["did"], 7)
        self.assertNotIn("refresh", url)


class SiteMatchTests(TestCase):
    def test_domain_resource_covers_exact_and_subdomains(self):
        self.assertTrue(site_url_matches_domain("sc-domain:example.com", "example.com"))
        self.assertTrue(site_url_matches_domain("sc-domain:example.com", "www.example.com"))
        self.assertTrue(site_url_matches_domain("sc-domain:example.com", "a.b.example.com"))

    def test_domain_resource_does_not_cover_other_domains(self):
        self.assertFalse(site_url_matches_domain("sc-domain:example.com", "notexample.com"))
        self.assertFalse(site_url_matches_domain("sc-domain:example.com", "example.org"))

    def test_url_prefix_resources_cannot_prove_domain_wide_control(self):
        for site_url in (
            "https://example.com/",
            "https://example.com/blog/",
            "http://example.com/",
            "https://www.example.com/",
        ):
            with self.subTest(site_url=site_url):
                self.assertFalse(site_url_matches_domain(site_url, "example.com"))
                self.assertFalse(site_url_matches_domain(site_url, "www.example.com"))

    def test_case_and_trailing_dot_normalized(self):
        self.assertTrue(site_url_matches_domain("SC-DOMAIN:Example.COM", "example.com."))
        self.assertTrue(site_url_matches_domain("sc-domain:Example.com.", "EXAMPLE.com"))

    def test_unicode_and_punycode_represent_the_same_domain(self):
        self.assertTrue(site_url_matches_domain("sc-domain:巧.tw", "xn--gst.tw"))
        self.assertTrue(site_url_matches_domain("sc-domain:xn--gst.tw", "www.巧.tw"))


class FetchSitesTests(TestCase):
    def test_only_owner_permission_entries_are_accepted(self):
        response = _fake_sites_response(
            [
                {"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"},
                {"siteUrl": "https://unverified.example/", "permissionLevel": "siteUnverifiedUser"},
                {"siteUrl": "sc-domain:full.example", "permissionLevel": "siteFullUser"},
                {
                    "siteUrl": "sc-domain:restricted.example",
                    "permissionLevel": "siteRestrictedUser",
                },
                {"siteUrl": "", "permissionLevel": "siteOwner"},
                "not-a-dict",
            ]
        )
        with patch(
            "apps.scans.google_site_verification.httpx.get", return_value=response
        ) as mock_get:
            urls = fetch_verified_site_entries("token")
        mock_get.assert_called_once()
        self.assertEqual(
            urls,
            ["sc-domain:example.com"],
        )


class RunGoogleVerificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="gscuser", password="x")
        self.vd = VerifiedDomain.objects.create(
            user=self.user, domain="example.com", token="0f1e2d3c4b5a69788796a5b4c3d2e1f0"
        )

    def test_success_marks_verified_with_gsc_method(self):
        with _GSC_ON, patch(
            "apps.scans.google_site_verification.httpx.post",
            return_value=_fake_token_response(),
        ), patch(
            "apps.scans.google_site_verification.httpx.get",
            return_value=_fake_sites_response(
                [
                    {"siteUrl": "https://other.example/", "permissionLevel": "siteOwner"},
                    {"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"},
                ]
            ),
        ):
            run_google_verification(self.vd, "auth-code", "http://127.0.0.1:8000/api/domains/google/callback/")
        self.vd.refresh_from_db()
        self.assertEqual(self.vd.status, VerifiedDomain.Status.VERIFIED)
        self.assertEqual(self.vd.method, VerifiedDomain.Method.GOOGLE_SEARCH_CONSOLE)
        self.assertIsNotNone(self.vd.verified_at)
        self.assertIsNotNone(self.vd.expires_at)
        self.assertEqual(self.vd.last_error, "")
        self.assertTrue(self.vd.is_effectively_verified)

    def test_no_matching_site_raises_and_keeps_pending(self):
        with _GSC_ON, patch(
            "apps.scans.google_site_verification.httpx.post",
            return_value=_fake_token_response(),
        ), patch(
            "apps.scans.google_site_verification.httpx.get",
            return_value=_fake_sites_response(
                [{"siteUrl": "https://other.example/", "permissionLevel": "siteOwner"}]
            ),
        ):
            with self.assertRaises(GoogleSiteVerificationError):
                run_google_verification(self.vd, "auth-code", "http://127.0.0.1:8000/api/domains/google/callback/")
        self.vd.refresh_from_db()
        self.assertEqual(self.vd.status, VerifiedDomain.Status.PENDING)
        self.assertIsNone(self.vd.verified_at)


@override_settings(SECRET_KEY="gsc-api-test-signing-key")
class GoogleVerificationAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="apiuser", password="x")
        self.other = User.objects.create_user(username="otheruser", password="x")
        self.vd = VerifiedDomain.objects.create(
            user=self.user, domain="example.com", token="0f1e2d3c4b5a69788796a5b4c3d2e1f0"
        )
        self.client.force_authenticate(self.user)
        self.start_url = reverse("verified-domain-google-start", args=[self.vd.id])
        self.callback_url = reverse("verified-domain-google-callback")

    @override_settings(GOOGLE_OAUTH_CLIENT_SECRET="")
    def test_start_returns_503_when_not_configured(self):
        response = self.client.post(self.start_url)
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("未啟用", response.data["detail"])

    def test_start_returns_authorization_url(self):
        with _GSC_ON:
            response = self.client.post(self.start_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        url = response.data["authorization_url"]
        self.assertIn("accounts.google.com", url)
        self.assertIn("webmasters.readonly", url)
        self.assertEqual(
            parse_qs(urlparse(url).query)["redirect_uri"],
            ["http://testserver" + self.callback_url],
        )

    def test_callback_rejects_non_owner_and_url_prefix_resources(self):
        for entry in (
            {"siteUrl": "sc-domain:example.com", "permissionLevel": "siteFullUser"},
            {"siteUrl": "sc-domain:example.com", "permissionLevel": "siteRestrictedUser"},
            {"siteUrl": "https://example.com/blog/", "permissionLevel": "siteOwner"},
            {"siteUrl": "https://example.com/", "permissionLevel": "siteOwner"},
        ):
            with self.subTest(entry=entry):
                state = build_state(self.user.id, self.vd.id)
                with _GSC_ON, patch(
                    "apps.scans.google_site_verification.httpx.post",
                    return_value=_fake_token_response(),
                ), patch(
                    "apps.scans.google_site_verification.httpx.get",
                    return_value=_fake_sites_response([entry]),
                ):
                    response = self.client.get(self.callback_url, {"code": "c", "state": state})
                self.assertEqual(response.status_code, 302)
                self.assertIn("gsc=fail", response["Location"])
                self.vd.refresh_from_db()
                self.assertEqual(self.vd.status, VerifiedDomain.Status.PENDING)
                self.assertIsNone(self.vd.verified_at)

    def test_start_hides_other_users_domains(self):
        self.client.force_authenticate(self.other)
        with _GSC_ON:
            response = self.client.post(self.start_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_callback_success_redirects_with_ok(self):
        state = build_state(self.user.id, self.vd.id)
        with _GSC_ON, patch(
            "apps.scans.google_site_verification.httpx.post",
            return_value=_fake_token_response(),
        ), patch(
            "apps.scans.google_site_verification.httpx.get",
            return_value=_fake_sites_response(
                [{"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"}]
            ),
        ):
            response = self.client.get(self.callback_url, {"code": "c", "state": state})
        self.assertEqual(response.status_code, 302)
        self.assertIn("gsc=ok", response["Location"])
        self.assertIn("domain=example.com", response["Location"])
        self.vd.refresh_from_db()
        self.assertEqual(self.vd.method, VerifiedDomain.Method.GOOGLE_SEARCH_CONSOLE)

    def test_callback_denied_redirects(self):
        state = build_state(self.user.id, self.vd.id)
        response = self.client.get(self.callback_url, {"error": "access_denied", "state": state})
        self.assertEqual(response.status_code, 302)
        self.assertIn("gsc=denied", response["Location"])
        self.vd.refresh_from_db()
        self.assertEqual(self.vd.status, VerifiedDomain.Status.PENDING)

    def test_callback_bad_state_redirects_expired(self):
        response = self.client.get(self.callback_url, {"code": "c", "state": "garbage"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("gsc=expired", response["Location"])

    def test_callback_missing_record_redirects_missing(self):
        state = build_state(self.user.id, 99999)
        response = self.client.get(self.callback_url, {"code": "c", "state": state})
        self.assertEqual(response.status_code, 302)
        self.assertIn("gsc=missing", response["Location"])

    def test_callback_failure_records_last_error(self):
        state = build_state(self.user.id, self.vd.id)
        with _GSC_ON, patch(
            "apps.scans.google_site_verification.httpx.post",
            return_value=_fake_token_response(),
        ), patch(
            "apps.scans.google_site_verification.httpx.get",
            return_value=_fake_sites_response(
                [{"siteUrl": "https://other.example/", "permissionLevel": "siteOwner"}]
            ),
        ):
            response = self.client.get(self.callback_url, {"code": "c", "state": state})
        self.assertEqual(response.status_code, 302)
        self.assertIn("gsc=fail", response["Location"])
        self.assertIn("reason=", response["Location"])
        self.vd.refresh_from_db()
        self.assertEqual(self.vd.status, VerifiedDomain.Status.PENDING)
        self.assertIn("example.com", self.vd.last_error)

    def test_token_verify_action_rejects_gsc_method(self):
        response = self.client.post(
            reverse("verified-domain-verify", args=[self.vd.id]),
            {"method": "google_search_console"},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
