"""網站特徵（fingerprint.py、tasks.stage_fingerprint，ADR-0004 階段 1）。"""

from __future__ import annotations

import json
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from apps.scans import tasks
from apps.scans.fingerprint import build_fingerprint, fingerprint_snapshot
from apps.scans.fingerprint_benchmark import THRESHOLDS, run_fingerprint_benchmark
from apps.scans.fingerprint_gold import GOLD_CASES, HOLDOUT_CASES, page
from apps.scans.models import ScanJob
from apps.scans.scan_plan import build_scan_execution_plan

B = "https://example.com"


class BenchmarkTests(SimpleTestCase):
    def test_thresholds_locked(self):
        self.assertEqual(THRESHOLDS, {"precision": 0.95, "recall": 0.95})

    def test_gold_and_holdout_meet_thresholds_without_requests(self):
        for cases in (GOLD_CASES, HOLDOUT_CASES):
            with self.subTest(size=len(cases)):
                result = run_fingerprint_benchmark(cases)
                self.assertEqual(result.failed_thresholds(), [], result.mismatches)
                self.assertEqual(result.metrics()["requests"], 0)

    def test_connection_attempts_are_counted(self):
        def _phone_home(*_args, **_kwargs):
            import socket
            socket.create_connection(("example.com", 80))

        with mock.patch("apps.scans.fingerprint_benchmark.build_fingerprint",
                        side_effect=lambda *a, **k: (_phone_home(), build_fingerprint(*a, **k))[1]):
            with self.assertRaises(OSError):
                run_fingerprint_benchmark(GOLD_CASES[:1])

    def test_command_reports_metrics(self):
        out = StringIO()
        call_command("fingerprint_benchmark", "--json", stdout=out)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["metrics"]["requests"], 0)
        self.assertEqual(payload["mismatches"], [])


class BuildFingerprintTests(SimpleTestCase):
    def test_not_seen_is_unknown_not_false(self):
        fp = build_fingerprint([page(f"{B}/", "<h1>hi</h1>")], [])
        self.assertIsNone(fp.has_login)
        self.assertIsNone(fp.has_api)
        self.assertEqual(fp.completeness["has_login"], "not_observed")
        # API 只在瀏覽器執行到的流程裡看得到，沒看到一律是部分資料
        self.assertEqual(fp.completeness["has_api"], "partial")
        # 這個階段只看標頭、沒查 DNS
        self.assertEqual(fp.completeness["edge"], "partial")

    def test_incomplete_crawl_marks_partial(self):
        fp = build_fingerprint([page(f"{B}/", "<h1>hi</h1>")], [], crawl_complete=False)
        self.assertEqual(fp.completeness["has_login"], "partial")
        self.assertEqual(fp.completeness["cms"], "partial")

    def test_no_usable_pages_is_unavailable(self):
        fp = build_fingerprint([page(f"{B}/", "<input type=password>", status=500)], [])
        self.assertIsNone(fp.has_login)
        self.assertEqual(set(fp.completeness.values()), {"unavailable"})

    def test_confidence_reflects_independent_evidence(self):
        one = build_fingerprint([page(f"{B}/", '<img src="/wp-content/a.png">')], [])
        two = build_fingerprint([
            page(f"{B}/", '<img src="/wp-content/a.png">'),
            page(f"{B}/b", '<img src="/wp-content/b.png">'),
        ], [])
        self.assertEqual(one.cms, "WordPress")
        self.assertLess(one.confidence["cms"], 0.8)
        self.assertGreaterEqual(two.confidence["cms"], 0.8)
        self.assertTrue(one.evidence["cms"])

    def test_snapshot_is_json_serialisable(self):
        snapshot = fingerprint_snapshot(
            [page(f"{B}/login", '<input type="password" name="p">')], [f"{B}/api/me"],
        )
        json.dumps(snapshot)
        self.assertEqual(snapshot["version"], 1)
        self.assertEqual(snapshot["phase"], "pre_scan")
        self.assertEqual(snapshot["login_urls"], [f"{B}/login"])
        self.assertEqual(snapshot["api_urls"], [f"{B}/api/me"])
        self.assertIn("elapsed_ms", snapshot)


class StageTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="fp", password="safe-test-password")
        self.scan = ScanJob.objects.create(
            user=user, original_url=f"{B}/", normalized_url=f"{B}/", origin=B, max_pages=5,
        )
        self.ctx = tasks.ScanRunContext(
            scan_job=self.scan, execution_plan=build_scan_execution_plan(self.scan), steps=[],
            crawl_phase_started="",
        )
        self.ctx.crawled_pages = [page(f"{B}/", '<link rel="stylesheet" href="/wp-content/x.css">')]
        self.ctx.discovered_endpoints = [f"{B}/wp-json/wp/v2/posts"]

    def test_records_fingerprint_without_changing_plan(self):
        before = self.ctx.execution_plan
        tasks.stage_fingerprint(self.ctx)
        self.scan.refresh_from_db()
        self.assertEqual(self.scan.fingerprint["cms"], "WordPress")
        self.assertTrue(self.scan.fingerprint["has_api"])
        self.assertTrue(self.scan.fingerprint["crawl_complete"])
        # 階段 1 只記錄：執行計畫與覆蓋紀錄都不受影響
        self.assertIs(self.ctx.execution_plan, before)
        self.assertEqual(self.ctx.execution_plan, build_scan_execution_plan(self.scan))
        self.assertEqual(self.ctx.coverage._checks, {})

    def test_page_limit_or_failures_mean_incomplete_crawl(self):
        self.scan.max_pages = 1
        tasks.stage_fingerprint(self.ctx)
        self.scan.refresh_from_db()
        self.assertFalse(self.scan.fingerprint["crawl_complete"])
        self.scan.max_pages = 5
        self.ctx.warnings = {"failed_urls": [f"{B}/x"]}
        tasks.stage_fingerprint(self.ctx)
        self.scan.refresh_from_db()
        self.assertFalse(self.scan.fingerprint["crawl_complete"])

    def test_errors_do_not_fail_the_scan(self):
        with mock.patch("apps.scans.tasks.fingerprint_snapshot", side_effect=ValueError("x")):
            tasks.stage_fingerprint(self.ctx)
        self.scan.refresh_from_db()
        self.assertEqual(self.scan.fingerprint["error"], "ValueError")
