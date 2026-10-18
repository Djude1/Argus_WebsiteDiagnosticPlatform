"""IP 證據判讀（security/ip_context.py）：0.0.0.0 這類未指定位址不算內網外洩（2026-10-18）。"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.scans.security.ip_context import describe_ips, private_ips


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
