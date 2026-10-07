"""axe-core 無障礙檢查（accessibility.py、scanners._ux_axe，roadmap P1）。

真實瀏覽器測試需要 Chromium：設 ARGUS_TEST_CHROMIUM_PATH 指向執行檔，沒有就略過。
"""

from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings

from apps.scans import tasks
from apps.scans.accessibility import AXE_PATH, DISABLED_RULES, run_axe
from apps.scans.coverage import COMPLETED, FAILED, PARTIAL, SKIPPED
from apps.scans.crawler import _CrawlState
from apps.scans.models import Finding, ScanJob
from apps.scans.reports import AXE_BASIS, _source_label
from apps.scans.scan_plan import build_scan_execution_plan
from apps.scans.scanners import PageAnalysisInput, analyze_ux

CHROMIUM = os.environ.get("ARGUS_TEST_CHROMIUM_PATH", "")

VIOLATION = {
    "id": "image-alt",
    "impact": "critical",
    "help": "Images must have alternative text",
    "description": "Ensure <img> elements have alternative text",
    "help_url": "https://dequeuniversity.com/rules/axe/4.14/image-alt",
    "tags": ["wcag2a", "wcag111"],
    "count": 3,
    "nodes": [
        {"target": "img.hero", "html": '<img class="hero" src="a.png">', "summary": "Fix",
         "box": {"x": 10, "y": 20, "width": 300, "height": 200}},
    ],
}


def _input(a11y):
    return PageAnalysisInput(
        url="https://example.com/", final_url="https://example.com/", title="t", html="",
        headers={}, element_boxes={}, a11y=a11y,
    )


class AxeFindingTests(SimpleTestCase):
    def test_violation_becomes_ux_finding(self):
        findings = [f for f in analyze_ux(_input({"version": "4.14.0", "violations": [VIOLATION]}))
                    if f["rule_id"].startswith("axe-")]
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding["rule_id"], "axe-image-alt")
        self.assertEqual(finding["category"], Finding.Category.UX)
        self.assertEqual(finding["severity"], Finding.Severity.HIGH)
        self.assertEqual(finding["title"], "圖片缺少替代文字")
        self.assertIn("3 個元素", finding["description"])
        self.assertIn("dequeuniversity.com", finding["remediation"])
        self.assertEqual(finding["bounding_box"], VIOLATION["nodes"][0]["box"])
        self.assertEqual(finding["evidence_source"], "axe-core 4.14.0")

    def test_unknown_rule_falls_back_to_axe_help(self):
        violation = {**VIOLATION, "id": "scrollable-region-focusable", "impact": "serious",
                     "help": "Scrollable region must have keyboard access"}
        finding = analyze_ux(_input({"violations": [violation]}))[0]
        self.assertEqual(finding["title"], "無障礙：Scrollable region must have keyboard access")
        self.assertEqual(finding["severity"], Finding.Severity.MEDIUM)

    def test_not_run_or_failed_produces_nothing(self):
        self.assertEqual(analyze_ux(_input({})), [])
        self.assertEqual(analyze_ux(_input({"error": "TimeoutError"})), [])

    def test_report_labels_axe_source_and_basis(self):
        finding = Finding(rule_id="axe-image-alt", evidence_source="axe-core 4.14.0")
        self.assertIn("axe-core", _source_label(finding))
        self.assertIn("沒有違規不代表網站符合 WCAG", AXE_BASIS)

    def test_overlapping_rules_are_disabled(self):
        """與自建觸控目標、表單標籤檢查重疊的規則關掉，避免同一件事報兩次。"""
        self.assertEqual(set(DISABLED_RULES), {"target-size", "label", "select-name"})

    def test_vendored_axe_is_present_with_license(self):
        self.assertTrue(AXE_PATH.exists())
        self.assertTrue((AXE_PATH.parent / "LICENSE").exists())
        self.assertIn("axe v4.14.0", AXE_PATH.read_text(encoding="utf-8")[:40])


class CrawlStateSlotTests(SimpleTestCase):
    @override_settings(ARGUS_AXE_MAX_PAGES=2)
    def test_accessibility_runs_are_capped(self):
        state = _CrawlState("https://example.com/", "https://example.com", 2, 10)
        self.assertFalse(state.take_accessibility_slot())  # 沒勾 UX
        state.run_accessibility = True
        self.assertEqual([state.take_accessibility_slot() for _ in range(3)], [True, True, False])


class AxeCoverageTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="axe-cov", password="safe-test-password"
        )
        self.scan = ScanJob.objects.create(
            user=user, original_url="https://example.com/", normalized_url="https://example.com/",
            origin="https://example.com", categories=["ux"],
        )

    def _ctx(self, pages):
        ctx = tasks.ScanRunContext(
            scan_job=self.scan, execution_plan=build_scan_execution_plan(self.scan), steps=[],
            crawl_phase_started="",
        )
        ctx.crawled_pages = pages
        return ctx

    def _status(self, pages):
        ctx = self._ctx(pages)
        tasks._mark_axe_coverage(ctx)
        return ctx.coverage.status_of("axe")

    def test_statuses(self):
        ok = {"a11y": {"violations": []}}
        bad = {"a11y": {"error": "TimeoutError"}}
        skipped = {"a11y": {}}
        blocked = {"blocked_reason": "403", "a11y": {}}
        self.assertEqual(self._status([ok, ok, blocked]), COMPLETED)
        self.assertEqual(self._status([ok, bad]), PARTIAL)
        self.assertEqual(self._status([ok, skipped]), PARTIAL)
        self.assertEqual(self._status([bad]), FAILED)

    @override_settings(ARGUS_AXE_ENABLED=False)
    def test_disabled(self):
        self.assertEqual(self._status([{"a11y": {}}]), SKIPPED)

    def test_ux_not_selected_records_nothing(self):
        ScanJob.objects.filter(id=self.scan.id).update(categories=["seo"])
        self.scan.refresh_from_db()
        self.assertIsNone(self._status([{"a11y": {"violations": []}}]))


@unittest.skipUnless(
    CHROMIUM and Path(CHROMIUM).exists(), "需要 Chromium（ARGUS_TEST_CHROMIUM_PATH）"
)
class AxeRealBrowserTests(SimpleTestCase):
    HTML = """<html lang="zh-Hant"><head><meta http-equiv="Content-Security-Policy"
      content="script-src 'none'"><title>t</title></head><body>
      <img src="x.png"><button></button><input type="text"></body></html>"""

    def test_runs_under_strict_csp_and_skips_overlapping_rules(self):
        from playwright.async_api import async_playwright

        async def run():
            async with async_playwright() as p:
                browser = await p.chromium.launch(executable_path=CHROMIUM)
                page = await browser.new_page()
                await page.set_content(self.HTML)
                result = await run_axe(page, timeout_seconds=30)
                await browser.close()
                return result

        result = asyncio.run(run())
        ids = {v["id"] for v in result["violations"]}
        self.assertIn("image-alt", ids)
        self.assertIn("button-name", ids)
        self.assertNotIn("label", ids)  # 交給自建表單標籤檢查
        node = next(v for v in result["violations"] if v["id"] == "image-alt")["nodes"][0]
        self.assertEqual(node["target"], "img")
