"""結果可重現：掃描記下實際用到的外部工具版本，報告「掃描範圍」列出（versions.tool_versions）。"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.scans import versions
from apps.scans.models import ScanJob
from apps.scans.reports import _scan_scope_rows


class ToolVersionsTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="tool-ver", password="safe-test-password"
        )
        self.scan = ScanJob.objects.create(
            user=user, original_url="https://example.com/",
            normalized_url="https://example.com/", origin="https://example.com",
            categories=["ux", "security"],
        )

    def test_collects_versions_from_each_source(self):
        self.scan.warning_summary = {
            "tools": {"Chromium": "140.0.7339.16", "axe-core": "4.14.0", "OWASP ZAP": ""},
            "nuclei": {
                "engine": "v3.4.10", "templates_version": "v10.4.9", "templates": 511,
                "sha256": "abcdef1234567890",
            },
        }
        self.scan.performance_report = {"lab": {"version": "12.8.2"}}
        tools = versions.tool_versions(self.scan)
        self.assertEqual(tools["Chromium"], "140.0.7339.16")
        self.assertEqual(tools["axe-core"], "4.14.0")
        self.assertNotIn("OWASP ZAP", tools)  # 沒有版本的不列
        self.assertIn("12.8.2", tools["Lighthouse"])
        self.assertIn("v10.4.9", tools["Nuclei"])
        self.assertIn("abcdef123456", tools["Nuclei"])

    def test_report_scope_lists_tools_only_when_known(self):
        self.assertNotIn("檢測工具版本", _scan_scope_rows(self.scan))  # 舊掃描沒有紀錄
        self.scan.warning_summary = {"tools": {"Chromium": "140.0.7339.16"}}
        self.assertEqual(_scan_scope_rows(self.scan)["檢測工具版本"], "Chromium 140.0.7339.16")
