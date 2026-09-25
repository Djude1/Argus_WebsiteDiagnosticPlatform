"""網域所有權驗證（VerifiedDomain）測試。

驗證引擎一律 mock（DNS 查 `_query_txt`、HTTP 抓 `_fetch_body`），
不打真網路；掃描建立 API 沿用既有測試慣例使用 example.com 假資料。
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admin_api.models import AdminAuditLog
from apps.billing.models import CoinWallet
from apps.scans.domain_verification import (
    generate_token,
    normalize_domain,
    run_verification,
    verify_dns_txt,
    verify_html_file,
    verify_meta_tag,
)
from apps.scans.models import ScanJob, VerifiedDomain


def _make_verified(user, domain="example.com", **kwargs):
    """建立假的已驗證網域（測試用；token 為明顯假資料）。"""
    defaults = {
        "token": "0f1e2d3c4b5a69788796a5b4c3d2e1f0",
        "status": VerifiedDomain.Status.VERIFIED,
        "method": VerifiedDomain.Method.DNS_TXT,
        "verified_at": timezone.now(),
        "expires_at": timezone.now() + timedelta(days=90),
    }
    defaults.update(kwargs)
    return VerifiedDomain.objects.create(user=user, domain=domain, **defaults)


class TokenAndNormalizeTests(TestCase):
    def test_generate_token_is_32_char_hex_and_unique(self):
        token_a = generate_token()
        token_b = generate_token()
        self.assertEqual(len(token_a), 32)
        int(token_a, 16)  # 必須是合法 hex
        self.assertNotEqual(token_a, token_b)

    def test_normalize_domain_handles_case_scheme_and_path(self):
        self.assertEqual(normalize_domain("Example.COM"), "example.com")
        self.assertEqual(normalize_domain("https://Example.com/some/path"), "example.com")
        self.assertEqual(normalize_domain(" http://www.example.com?q=1 "), "www.example.com")
        self.assertEqual(normalize_domain("example.com."), "example.com")

    def test_normalize_domain_rejects_ip_localhost_and_non_fqdn(self):
        from apps.scans.domain_verification import DomainValidationError

        for raw in ("192.0.2.10", "127.0.0.1", "localhost", "intranet", "", "not a domain"):
            with self.assertRaises(DomainValidationError, msg=raw):
                normalize_domain(raw)


class DnsTxtVerificationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="dns-user",
            email="dns-user@example.com",
            password="safe-test-password",
        )
        self.vd = VerifiedDomain.objects.create(
            user=self.user,
            domain="example.com",
            token="0f1e2d3c4b5a69788796a5b4c3d2e1f0",
        )

    def test_dns_txt_with_matching_record_verifies(self):
        with patch(
            "apps.scans.domain_verification._query_txt",
            return_value=["argus-site-verification=0f1e2d3c4b5a69788796a5b4c3d2e1f0"],
        ):
            ok = run_verification(self.vd, VerifiedDomain.Method.DNS_TXT)

        self.assertTrue(ok)
        self.vd.refresh_from_db()
        self.assertEqual(self.vd.status, VerifiedDomain.Status.VERIFIED)
        self.assertEqual(self.vd.method, VerifiedDomain.Method.DNS_TXT)
        self.assertIsNotNone(self.vd.verified_at)
        self.assertGreater(self.vd.expires_at, timezone.now())
        self.assertEqual(self.vd.last_error, "")
        self.assertIsNotNone(self.vd.last_checked_at)

    def test_dns_txt_with_unrelated_record_fails_with_error(self):
        with patch(
            "apps.scans.domain_verification._query_txt",
            return_value=["v=spf1 include:_spf.example.com ~all"],
        ):
            ok = run_verification(self.vd, VerifiedDomain.Method.DNS_TXT)

        self.assertFalse(ok)
        self.vd.refresh_from_db()
        self.assertEqual(self.vd.status, VerifiedDomain.Status.PENDING)
        self.assertIn("未包含", self.vd.last_error)

    def test_dns_txt_nxdomain_keeps_failing_and_records_error(self):
        # 連續查無記錄（NXDOMAIN / 解析失敗都視為空）→ 不過且 last_error 有值
        with patch("apps.scans.domain_verification._query_txt", return_value=[]):
            ok = run_verification(self.vd, VerifiedDomain.Method.DNS_TXT)

        self.assertFalse(ok)
        self.vd.refresh_from_db()
        self.assertEqual(self.vd.status, VerifiedDomain.Status.PENDING)
        self.assertTrue(self.vd.last_error)

    def test_dns_txt_accepts_record_at_domain_root(self):
        # 底線前綴查不到、但網域本身 TXT 有驗證值 → 仍應通過
        def fake_query(name: str):
            if name == "example.com":
                return ["argus-site-verification=0f1e2d3c4b5a69788796a5b4c3d2e1f0"]
            return []

        with patch("apps.scans.domain_verification._query_txt", side_effect=fake_query):
            ok, detail = verify_dns_txt("example.com", "0f1e2d3c4b5a69788796a5b4c3d2e1f0")

        self.assertTrue(ok)
        self.assertIn("成功", detail)


class MetaTagVerificationTests(TestCase):
    def setUp(self):
        self.token = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"

    def test_meta_tag_with_tag_and_token_passes(self):
        html = (
            "<html><head>"
            f'<meta name="argus-site-verification" content="{self.token}">'
            "</head><body>ok</body></html>"
        )
        with patch(
            "apps.scans.domain_verification._fetch_body", return_value=(200, html)
        ):
            ok, detail = verify_meta_tag("example.com", self.token)
        self.assertTrue(ok)

    def test_meta_tag_tolerates_attribute_order_and_quotes(self):
        html = f"<meta content='{self.token}' NAME=argus-site-verification>"
        with patch(
            "apps.scans.domain_verification._fetch_body", return_value=(200, html)
        ):
            ok, _ = verify_meta_tag("example.com", self.token)
        self.assertTrue(ok)

    def test_meta_tag_without_tag_fails(self):
        html = "<html><head><title>example</title></head></html>"
        with patch(
            "apps.scans.domain_verification._fetch_body", return_value=(200, html)
        ):
            ok, detail = verify_meta_tag("example.com", self.token)
        self.assertFalse(ok)
        self.assertTrue(detail)

    def test_meta_tag_missing_token_only_fails(self):
        # 有標籤名但沒有 token（或反之）都不得通過
        html = '<meta name="argus-site-verification" content="other-value">'
        with patch(
            "apps.scans.domain_verification._fetch_body", return_value=(200, html)
        ):
            ok, _ = verify_meta_tag("example.com", self.token)
        self.assertFalse(ok)

    def test_meta_tag_ssrf_blocked_url_fails_without_request(self):
        # SSRF 禁止的目標（IP）→ 直接不過，且不發出任何 HTTP 請求
        with patch("apps.scans.domain_verification._fetch_body") as fetch_mock:
            ok, detail = verify_meta_tag("192.0.2.10", self.token)
        self.assertFalse(ok)
        fetch_mock.assert_not_called()
        self.assertTrue(detail)


class HtmlFileVerificationTests(TestCase):
    def setUp(self):
        self.token = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
        self.user = get_user_model().objects.create_user(
            username="file-user",
            email="file-user@example.com",
            password="safe-test-password",
        )

    def test_html_file_with_exact_token_passes(self):
        self.vd = VerifiedDomain.objects.create(
            user=self.user, domain="example.com", token=self.token
        )
        with patch(
            "apps.scans.domain_verification._fetch_body",
            return_value=(200, f"  {self.token}\n"),
        ):
            ok = run_verification(self.vd, VerifiedDomain.Method.HTML_FILE)
        self.assertTrue(ok)
        self.vd.refresh_from_db()
        self.assertEqual(self.vd.status, VerifiedDomain.Status.VERIFIED)
        self.assertEqual(self.vd.method, VerifiedDomain.Method.HTML_FILE)

    def test_html_file_with_different_content_fails(self):
        self.vd = VerifiedDomain.objects.create(
            user=self.user, domain="example.com", token=self.token
        )
        with patch(
            "apps.scans.domain_verification._fetch_body",
            return_value=(200, "totally-different-content"),
        ):
            ok = run_verification(self.vd, VerifiedDomain.Method.HTML_FILE)
        self.assertFalse(ok)
        self.vd.refresh_from_db()
        self.assertEqual(self.vd.status, VerifiedDomain.Status.PENDING)
        self.assertIn("不符", self.vd.last_error)

    def test_html_file_non_200_fails(self):
        with patch(
            "apps.scans.domain_verification._fetch_body", return_value=(404, "")
        ):
            ok, detail = verify_html_file("example.com", self.token)
        self.assertFalse(ok)
        self.assertIn("200", detail)


class VerifiedDomainApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="domain-owner",
            email="owner@example.com",
            password="safe-test-password",
        )
        self.client.force_authenticate(self.user)
        self.list_url = reverse("verified-domain-list")

    def test_create_returns_token_and_instructions(self):
        response = self.client.post(
            self.list_url, {"domain": "Example.com"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["domain"], "example.com")
        self.assertEqual(len(response.data["token"]), 32)
        instructions = response.data["instructions"]
        self.assertEqual(
            instructions["dns_txt"]["record_name"], "_argus-verification.example.com"
        )
        self.assertEqual(
            instructions["dns_txt"]["value"],
            f"argus-site-verification={response.data['token']}",
        )
        self.assertIn("argus-site-verification", instructions["meta_tag"]["snippet"])
        self.assertEqual(instructions["html_file"]["path"], "/.well-known/argus-verification.txt")
        # 回應必須帶待驗證狀態
        self.assertEqual(response.data["status"], VerifiedDomain.Status.PENDING)

    def test_create_duplicate_returns_409_with_current_state(self):
        _make_verified(self.user, domain="example.com")
        response = self.client.post(self.list_url, {"domain": "example.com"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["domain"]["domain"], "example.com")
        self.assertEqual(response.data["domain"]["status"], VerifiedDomain.Status.VERIFIED)

    def test_create_rejects_ip_domain(self):
        response = self.client.post(
            self.list_url, {"domain": "192.0.2.10"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_shows_effective_state_and_days_to_expiry(self):
        _make_verified(self.user, domain="example.com")
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["is_effectively_verified"])
        self.assertIsNotNone(results[0]["days_until_expiry"])

    def test_other_users_domains_invisible_and_undeletable(self):
        other = get_user_model().objects.create_user(
            username="other-user",
            email="other@example.com",
            password="safe-test-password",
        )
        vd = _make_verified(other, domain="example.com")

        response = self.client.get(self.list_url)
        self.assertEqual(response.data["results"], [])

        detail_url = reverse("verified-domain-detail", args=[vd.id])
        self.assertEqual(
            self.client.delete(detail_url).status_code, status.HTTP_404_NOT_FOUND
        )

    def test_verify_action_updates_state(self):
        vd = VerifiedDomain.objects.create(
            user=self.user, domain="example.com", token="0f1e2d3c4b5a69788796a5b4c3d2e1f0"
        )
        with patch(
            "apps.scans.domain_verification._query_txt",
            return_value=["argus-site-verification=0f1e2d3c4b5a69788796a5b4c3d2e1f0"],
        ):
            response = self.client.post(
                reverse("verified-domain-verify", args=[vd.id]),
                {"method": "dns_txt"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["verified"])
        self.assertEqual(response.data["status"], VerifiedDomain.Status.VERIFIED)

    def test_delete_own_domain(self):
        vd = _make_verified(self.user, domain="example.com")
        response = self.client.delete(reverse("verified-domain-detail", args=[vd.id]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(VerifiedDomain.objects.filter(pk=vd.pk).exists())


@override_settings(ARGUS_AUTO_QUEUE_SCANS=False)
class ActiveScanDomainGateTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="gate-user",
            email="gate@example.com",
            password="safe-test-password",
        )
        CoinWallet.objects.filter(user=self.user).update(balance=10000)
        self.client.force_authenticate(self.user)
        self.url = reverse("scan-list")

    def _post_active(self, target="https://example.com/"):
        return self.client.post(
            self.url,
            {
                "url": target,
                "authorization_confirmed": True,
                "scan_mode": ScanJob.ScanMode.ACTIVE,
                "active_testing_authorized": True,
            },
            format="json",
        )

    def test_active_scan_without_verification_fails_with_guidance(self):
        response = self._post_active()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("網域所有權驗證", str(response.data))
        self.assertEqual(ScanJob.objects.count(), 0)

    def test_active_scan_with_valid_verification_passes(self):
        _make_verified(self.user, domain="example.com")
        response = self._post_active()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_active_scan_with_expired_verification_fails(self):
        _make_verified(
            self.user,
            domain="example.com",
            expires_at=timezone.now() - timedelta(days=1),
        )
        response = self._post_active()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("網域所有權驗證", str(response.data))

    def test_active_scan_with_admin_override_passes(self):
        _make_verified(
            self.user,
            domain="example.com",
            status=VerifiedDomain.Status.PENDING,
            verified_at=None,
            expires_at=None,
            admin_override=True,
        )
        response = self._post_active()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_active_scan_subdomain_covered_by_registered_domain(self):
        # 對 example.com 驗證 → www.example.com 子網域也可主動掃描
        _make_verified(self.user, domain="example.com")
        response = self._post_active(target="https://www.example.com/")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_passive_scan_still_works_without_verification(self):
        response = self.client.post(
            self.url,
            {"url": "https://example.com/", "authorization_confirmed": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_other_users_verification_does_not_transfer(self):
        other = get_user_model().objects.create_user(
            username="other-verified",
            email="other-verified@example.com",
            password="safe-test-password",
        )
        _make_verified(other, domain="example.com")
        response = self._post_active()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_model_clean_enforces_gate_too(self):
        scan_job = ScanJob(
            user=self.user,
            original_url="https://example.com/",
            normalized_url="https://example.com/",
            origin="https://example.com",
            scan_mode=ScanJob.ScanMode.ACTIVE,
            active_testing_authorized=True,
        )
        with self.assertRaises(ValidationError):
            scan_job.clean()

        _make_verified(self.user, domain="example.com")
        scan_job.clean()  # 有驗證後不得再 raise


@override_settings(ARGUS_AUTO_QUEUE_SCANS=False)
class StaffDomainGateBypassTests(APITestCase):
    """管理員測試旁路：staff／superuser 免網域驗證即可主動掃描。

    能力等同 admin_override 人工核准，省去建列＋後台核准兩步；
    一般使用者不受影響（對照組見 ActiveScanDomainGateTests）。
    """

    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="staff-tester",
            email="staff@example.com",
            password="safe-test-password",
            is_staff=True,
        )
        CoinWallet.objects.filter(user=self.staff).update(balance=10000)
        self.url = reverse("scan-list")

    def _post_active(self):
        return self.client.post(
            self.url,
            {
                "url": "https://example.com/",
                "authorization_confirmed": True,
                "scan_mode": ScanJob.ScanMode.ACTIVE,
                "active_testing_authorized": True,
            },
            format="json",
        )

    def test_staff_active_scan_without_verification_passes(self):
        self.client.force_authenticate(self.staff)
        response = self._post_active()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # 不得因旁路順便建立任何 VerifiedDomain 紀錄
        self.assertEqual(VerifiedDomain.objects.count(), 0)

    def test_superuser_active_scan_without_verification_passes(self):
        superuser = get_user_model().objects.create_superuser(
            username="super-tester",
            email="super@example.com",
            password="safe-test-password",
        )
        CoinWallet.objects.filter(user=superuser).update(balance=10000)
        self.client.force_authenticate(superuser)
        response = self._post_active()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_staff_model_clean_bypasses_gate_too(self):
        scan_job = ScanJob(
            user=self.staff,
            original_url="https://example.com/",
            normalized_url="https://example.com/",
            origin="https://example.com",
            scan_mode=ScanJob.ScanMode.ACTIVE,
            active_testing_authorized=True,
        )
        scan_job.clean()  # staff 不得 raise

    def test_staff_flag_alone_does_not_skip_declaration_gate(self):
        # 旁路只略過網域驗證；宣告式授權勾選（active_testing_authorized）仍必須
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            self.url,
            {
                "url": "https://example.com/",
                "authorization_confirmed": True,
                "scan_mode": ScanJob.ScanMode.ACTIVE,
                "active_testing_authorized": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("額外取得授權", str(response.data))


class AdminDomainOverrideTests(APITestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            username="site-admin",
            email="admin@example.com",
            password="safe-test-password",
            is_staff=True,
        )
        self.user = get_user_model().objects.create_user(
            username="domain-user",
            email="domain@example.com",
            password="safe-test-password",
        )
        self.vd = VerifiedDomain.objects.create(
            user=self.user,
            domain="example.com",
            token="0f1e2d3c4b5a69788796a5b4c3d2e1f0",
        )
        self.override_url = reverse("admin-domain-override", args=[self.vd.id])

    def test_domains_list_requires_staff(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(reverse("admin-domains"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_domains_list_shows_user_and_status(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse("admin-domains"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = response.data["domains"][0]
        self.assertEqual(row["domain"], "example.com")
        self.assertEqual(row["username"], "domain-user")
        self.assertIn("admin_override", row)

    def test_override_approve_sets_admin_override_and_audits(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            self.override_url,
            {"approve": True, "note": "人工審核通過"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.vd.refresh_from_db()
        self.assertTrue(self.vd.admin_override)
        self.assertEqual(self.vd.admin_actor, self.admin)
        self.assertEqual(self.vd.admin_note, "人工審核通過")
        self.assertTrue(self.vd.is_effectively_verified)
        self.assertTrue(
            AdminAuditLog.objects.filter(
                action=AdminAuditLog.Action.DOMAIN_OVERRIDE,
                admin_actor=self.admin,
                target_user=self.user,
            ).exists()
        )

    def test_override_reject_sets_status_rejected(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            self.override_url, {"approve": False}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.vd.refresh_from_db()
        self.assertEqual(self.vd.status, VerifiedDomain.Status.REJECTED)
        self.assertFalse(self.vd.admin_override)
        self.assertFalse(self.vd.is_effectively_verified)
        self.assertTrue(
            AdminAuditLog.objects.filter(
                action=AdminAuditLog.Action.DOMAIN_OVERRIDE,
                payload__approve=False,
            ).exists()
        )

    def test_override_requires_staff(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(self.override_url, {"approve": True}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
