"""掃描流程的階段化結構（tasks.SCAN_PIPELINE 與各 stage_* 函式）。

run_scan_job 由一支上千行的函式拆成依序執行的階段函式；這裡鎖定：
- 階段順序（與進度條 planned_scan_steps 的語意一致）
- 失敗時 log 標出是哪一個階段
- 計分用的「有測到的維度」規則可以單獨驗證
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase

from apps.scans import tasks
from apps.scans.models import ScanJob
from apps.scans.scan_plan import build_scan_execution_plan

User = get_user_model()


def _scan(user, **kw) -> ScanJob:
    base = dict(
        user=user,
        original_url="https://example.com/",
        normalized_url="https://example.com/",
        origin="https://example.com",
        status=ScanJob.Status.QUEUED,
        max_pages=1,
        max_depth=1,
    )
    base.update(kw)
    return ScanJob.objects.create(**base)


class PipelineShapeTests(TestCase):
    def test_stage_order(self):
        names = [name for name, _ in tasks.SCAN_PIPELINE]
        self.assertEqual(
            names,
            [
                "target_validation", "crawl", "enter_scanning", "page_analysis",
                "aeo_answers", "site_security", "active_probe", "deep_security", "exposure",
                "geo_site", "seo_links", "favicon", "agent", "kali", "scoring",
            ],
        )
        # 每個階段都是可單獨呼叫的函式
        for _, stage in tasks.SCAN_PIPELINE:
            self.assertTrue(callable(stage))

    def test_tested_categories_rules(self):
        user = User.objects.create_user(username="pipe-cat", password="safe-test-password")
        scan = _scan(user, categories=["seo", "ux", "security"])
        plan = build_scan_execution_plan(scan)
        ctx = tasks.ScanRunContext(
            scan_job=scan, execution_plan=plan, steps=[], crawl_phase_started=""
        )
        # 0 頁：只有站台層級檢查算有測，且與勾選維度取交集（geo 沒勾）
        self.assertEqual(tasks.tested_categories_for(ctx), {"security"})
        ctx.crawled_pages = [{"layout_metrics": {}}]
        self.assertEqual(tasks.tested_categories_for(ctx), {"security", "seo"})
        # 有量到行動版版面才算 UX 有測
        ctx.crawled_pages = [{"layout_metrics": {"overflow": False}}]
        self.assertEqual(tasks.tested_categories_for(ctx), {"security", "seo", "ux"})
        # Agent 出錯不算有測
        ctx.crawled_pages = [{"layout_metrics": {}}]
        ctx.agent_meta = {"status": "error"}
        self.assertNotIn("ux", tasks.tested_categories_for(ctx))


class PipelineFailureLabelTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="pipe-fail", password="safe-test-password")
        self.scan_job = _scan(self.user)
        for target, kwargs in [
            ("assert_public_http_url", {"return_value": "https://example.com/"}),
            ("crawl_site", {"new": mock.AsyncMock(return_value=([], {}, {}, []))}),
            ("analyze_ssl", {"return_value": []}),
            ("build_link_report", {"return_value": {}}),
            ("analyze_cookies", {"return_value": []}),
            ("analyze_headers", {"return_value": []}),
            ("analyze_sri", {"return_value": []}),
            ("analyze_js_libraries", {"return_value": []}),
            ("analyze_security_site_level", {"return_value": []}),
            ("analyze_site_signals", {"return_value": []}),
            ("owasp_mapper.backfill", {}),
        ]:
            mock.patch(f"apps.scans.tasks.{target}", **kwargs).start()
        self.refund = mock.patch("apps.scans.tasks.refund_full_for_scan").start()

    def tearDown(self):
        mock.patch.stopall()

    def test_failure_log_names_the_failing_stage_and_refunds(self):
        with mock.patch("apps.scans.tasks.analyze_dns", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                tasks.run_scan_job.run(self.scan_job.id)
        self.scan_job.refresh_from_db()
        self.assertEqual(self.scan_job.status, ScanJob.Status.FAILED)
        messages = [entry["msg"] for entry in self.scan_job.scan_log]
        self.assertIn("掃描執行失敗 [deep_security:RuntimeError]", messages)
        self.refund.assert_called_once()
