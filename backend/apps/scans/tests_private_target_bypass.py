"""ARGUS_ALLOW_PRIVATE_TARGETS 開發旁路的行為鎖定。

旁路只放行「目標位址屬性」（私網、localhost、單標籤 hostname、非標準 port），
userinfo、無法解析的 hostname 等安全屬性不因旁路放寬；
正式（非 DEBUG）環境由 scans.E002 部署檢查擋下。
"""

from django.test import SimpleTestCase, override_settings

from apps.scans.checks import check_private_targets_is_debug_only
from apps.scans.domain_verification import DomainValidationError, normalize_domain
from apps.scans.services import PublicScanTargetError, assert_public_http_url


class PrivateTargetBypassDisabledTests(SimpleTestCase):
    """預設（旁路關閉）維持原本公開目標政策。"""

    def test_localhost_rejected(self):
        with self.assertRaises(PublicScanTargetError):
            assert_public_http_url("http://localhost:3000/")

    def test_loopback_ip_rejected(self):
        with self.assertRaises(PublicScanTargetError):
            assert_public_http_url("http://127.0.0.1:3000/")

    def test_private_ip_rejected(self):
        with self.assertRaises(PublicScanTargetError):
            assert_public_http_url("http://192.168.1.10/")


@override_settings(ARGUS_ALLOW_PRIVATE_TARGETS=True, DEBUG=True)
class PrivateTargetBypassEnabledTests(SimpleTestCase):
    """旁路開啟（僅 DEBUG）放行 Docker 網路內的受控測試目標。"""

    def test_localhost_with_port_allowed(self):
        self.assertEqual(
            assert_public_http_url("http://localhost:3000/"),
            "http://localhost:3000/",
        )

    def test_loopback_ip_with_port_allowed(self):
        self.assertEqual(
            assert_public_http_url("http://127.0.0.1:3000/"),
            "http://127.0.0.1:3000/",
        )

    def test_ipv6_loopback_allowed(self):
        self.assertEqual(
            assert_public_http_url("http://[::1]:3000/"),
            "http://[::1]:3000/",
        )

    def test_single_label_hostname_allowed(self):
        # 單標籤 hostname（如 Docker 服務名 juice-shop）不因缺少 dot 被拒；
        # 此處以必可解析的 localhost 代表，避免測試依賴 Docker DNS。
        self.assertEqual(
            assert_public_http_url("http://localhost/"),
            "http://localhost/",
        )

    def test_unresolvable_hostname_still_rejected(self):
        # DNS 仍須可解析：拼錯或不存在的主機名不得因旁路放行。
        with self.assertRaises(PublicScanTargetError):
            assert_public_http_url("http://argus-no-such-host-xyz:3000/")

    def test_userinfo_still_rejected(self):
        # userinfo 屬安全屬性，旁路不得放寬。
        with self.assertRaises(PublicScanTargetError):
            assert_public_http_url("http://user:pass@localhost:3000/")

    def test_non_http_scheme_still_rejected(self):
        with self.assertRaises((PublicScanTargetError, ValueError)):
            assert_public_http_url("ftp://localhost:3000/")


@override_settings(ARGUS_ALLOW_PRIVATE_TARGETS=True, DEBUG=True)
class DomainVerificationBypassTests(SimpleTestCase):
    """網域驗證閘門在旁路開啟時放行 Docker 服務名等受控目標。"""

    def test_single_label_hostname_normalized(self):
        self.assertEqual(normalize_domain("juice-shop"), "juice-shop")

    def test_localhost_allowed(self):
        self.assertEqual(normalize_domain("http://localhost:3000/"), "localhost")

    def test_ip_allowed(self):
        self.assertEqual(normalize_domain("172.18.0.5"), "172.18.0.5")

    def test_url_input_extracts_hostname(self):
        self.assertEqual(
            normalize_domain("http://juice-shop:3000/#/about"),
            "juice-shop",
        )


class DomainVerificationNoBypassTests(SimpleTestCase):
    """旁路關閉時網域驗證維持原本 FQDN 政策。"""

    def test_single_label_rejected(self):
        with self.assertRaises(DomainValidationError):
            normalize_domain("juice-shop")

    def test_localhost_rejected(self):
        with self.assertRaises(DomainValidationError):
            normalize_domain("localhost")

    def test_ip_rejected(self):
        with self.assertRaises(DomainValidationError):
            normalize_domain("127.0.0.1")


class PrivateTargetDeployCheckTests(SimpleTestCase):
    """scans.E002：旁路開啟且非 DEBUG 時必須報錯。"""

    def test_error_when_enabled_without_debug(self):
        with override_settings(ARGUS_ALLOW_PRIVATE_TARGETS=True, DEBUG=False):
            errors = check_private_targets_is_debug_only(None)
            self.assertTrue(any(e.id == "scans.E002" for e in errors))

    def test_no_error_when_enabled_with_debug(self):
        with override_settings(ARGUS_ALLOW_PRIVATE_TARGETS=True, DEBUG=True):
            self.assertEqual(check_private_targets_is_debug_only(None), [])

    def test_no_error_when_disabled(self):
        with override_settings(ARGUS_ALLOW_PRIVATE_TARGETS=False, DEBUG=False):
            self.assertEqual(check_private_targets_is_debug_only(None), [])
