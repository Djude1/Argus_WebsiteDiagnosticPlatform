"""掃描完成後的點數結算失敗回歸測試。

背景：結算（settle_scan_actual）發生在 ScanJob 已被寫成 completed 之後。
早期實作在結算失敗時把例外往上拋，落到 run_scan_job 的通用 except，
結果把已完成的掃描改成 failed 並「全額」退款——頁面與 findings 都還在 DB，
狀態卻是失敗，退的也不是差額。

這裡鎖定修正後的契約：結算失敗時掃描維持 completed、不觸發全額退款，
並在 warning_summary 留下 settlement_error 供後續補結算。

策略沿用 tests_kali_pipeline.py：mock 掉所有外部依賴，不做真正的爬取或掃描。
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from apps.scans.models import ScanJob
from apps.scans.tasks import run_scan_job

User = get_user_model()


class ScanSettlementFailureTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="settlement_user", password="safe-test-password"
        )
        self.scan_job = ScanJob.objects.create(
            user=self.user,
            original_url="https://example.com/",
            normalized_url="https://example.com/",
            origin="https://example.com",
            status=ScanJob.Status.QUEUED,
            max_pages=1,
            max_depth=1,
        )
        # 通用 mocks：所有外部依賴 silent-empty，只留結算與退款可被斷言
        self._patches = [
            mock.patch(
                "apps.scans.tasks.assert_public_http_url",
                return_value="https://example.com/",
            ),
            mock.patch(
                "apps.scans.tasks.crawl_site",
                new=mock.AsyncMock(return_value=([], {}, {})),
            ),
            mock.patch("apps.scans.tasks.analyze_ssl", return_value=[]),
            mock.patch("apps.scans.tasks.analyze_cookies", return_value=[]),
            mock.patch("apps.scans.tasks.analyze_headers", return_value=[]),
            mock.patch("apps.scans.tasks.analyze_sri", return_value=[]),
            mock.patch("apps.scans.tasks.analyze_dns", return_value=[]),
            mock.patch("apps.scans.tasks.analyze_js_libraries", return_value=[]),
            mock.patch("apps.scans.tasks.analyze_security_site_level", return_value=[]),
            mock.patch("apps.scans.tasks.analyze_site_signals", return_value=[]),
            mock.patch("apps.scans.tasks.owasp_mapper.backfill"),
            mock.patch(
                "apps.scans.tasks.calculate_scores",
                return_value=(100, {}, []),
            ),
        ]
        for patcher in self._patches:
            patcher.start()
        self.settle = mock.patch("apps.scans.tasks.settle_scan_actual").start()
        self.refund = mock.patch("apps.scans.tasks.refund_full_for_scan").start()
        self._patches.extend([self.settle, self.refund])

    def tearDown(self):
        mock.patch.stopall()

    def test_settlement_failure_keeps_scan_completed_and_skips_full_refund(self):
        self.settle.side_effect = RuntimeError("wallet unavailable")

        result = run_scan_job.run(self.scan_job.id)

        self.scan_job.refresh_from_db()
        self.assertEqual(self.scan_job.status, ScanJob.Status.COMPLETED)
        self.assertEqual(result["status"], ScanJob.Status.COMPLETED)
        self.assertEqual(result["settlement_error"], "RuntimeError")
        # 關鍵：不得因為結算失敗就退全額（正常結算只退差額）
        self.refund.assert_not_called()
        self.assertEqual(
            self.scan_job.warning_summary.get("settlement_error"), "RuntimeError"
        )

    def test_successful_settlement_reports_no_settlement_error(self):
        result = run_scan_job.run(self.scan_job.id)

        self.scan_job.refresh_from_db()
        self.assertEqual(self.scan_job.status, ScanJob.Status.COMPLETED)
        self.assertIsNone(result["settlement_error"])
        self.settle.assert_called_once_with(self.user, mock.ANY, 0)
        self.refund.assert_not_called()
        self.assertNotIn("settlement_error", self.scan_job.warning_summary)
