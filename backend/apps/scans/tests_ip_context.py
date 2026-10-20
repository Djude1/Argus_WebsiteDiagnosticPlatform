"""IP 證據判讀（security/ip_context.py）：0.0.0.0 這類未指定位址不算內網外洩（2026-10-18）。"""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from apps.scans.security.ip_context import describe_ips, only_scanner_ips, private_ips


class IpContextTests(SimpleTestCase):
    def test_unspecified_zero_ip_not_internal(self):
        # /api/Users 的 lastLoginIp 預設 0.0.0.0（從未登入）不是內網拓樸外洩
        self.assertEqual(private_ips('{"lastLoginIp":"0.0.0.0"}'), [])
        lines = describe_ips('{"lastLoginIp":"0.0.0.0"}', hostname="")
        self.assertEqual(len(lines), 1)
        self.assertIn("未指定位址", lines[0])
        self.assertNotIn("內部網路資訊外洩", lines[0])

    def test_real_private_ip_still_flagged(self):
        self.assertEqual(private_ips("servers: http://10.1.2.3:8080"), ["10.1.2.3"])
        lines = describe_ips("http://10.1.2.3:8080", hostname="")
        self.assertIn("內部網路資訊外洩", lines[0])

    @override_settings(ARGUS_SCANNER_EGRESS_IPS=["211.75.1.199", "198.51.100.0/28"])
    def test_scanner_egress_ip_is_recognised(self):
        # WAF 攔截頁回顯訪客來源 IP：掃描器看到自己的出口位址不是內部 IP 外洩（2026-10-19 實掃）
        page = "<div class=\"waferr\">211.75.1.199<br>2026-10-19 18:42:26</div>"
        lines = describe_ips(page, hostname="")
        self.assertIn("Argus 掃描器自己的出口位址", lines[0])
        self.assertTrue(only_scanner_ips(page))
        self.assertTrue(only_scanner_ips("from 198.51.100.7"))
        self.assertFalse(only_scanner_ips(page + " upstream 10.1.2.3"))
        self.assertFalse(only_scanner_ips("no ip here"))

    def test_without_egress_setting_nothing_is_scanner(self):
        with override_settings(ARGUS_SCANNER_EGRESS_IPS=[]):
            self.assertFalse(only_scanner_ips("211.75.1.199"))
            self.assertIn("需人工確認", describe_ips("211.75.1.199", hostname="")[0])
