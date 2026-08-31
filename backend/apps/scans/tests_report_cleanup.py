"""報告檔案保留期限（稽核第四階段：G2）。

背景：報告寫進 MEDIA_ROOT/reports/ 後永久堆積，沒有任何清理機制。
加上第四階段的快取（不再每次重產），檔案只會越積越多。
"""

from __future__ import annotations

import os
import time

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.scans.models import ReportVerification, ScanJob
from apps.scans.reports import build_scan_report, report_output_path

User = get_user_model()


class CleanupReportsCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cleanup", password="safe-test-password")

    def _scan_with_report(self, *, age_days: int) -> ScanJob:
        scan_job = ScanJob.objects.create(
            user=self.user, original_url="https://example.com/",
            normalized_url="https://example.com/", origin="example.com",
            status=ScanJob.Status.COMPLETED, overall_score=70,
        )
        build_scan_report(scan_job)
        path = report_output_path(scan_job)
        old = time.time() - age_days * 86400
        os.utime(path, (old, old))
        return scan_job

    def test_old_report_files_are_removed(self):
        stale = self._scan_with_report(age_days=120)

        call_command("cleanup_reports", "--older-than-days", "90")

        self.assertFalse(report_output_path(stale).exists())

    def test_recent_report_files_are_kept(self):
        fresh = self._scan_with_report(age_days=3)

        call_command("cleanup_reports", "--older-than-days", "90")

        self.assertTrue(report_output_path(fresh).exists())

    def test_verification_rows_survive_cleanup(self):
        """檔案清掉了，報告編號仍必須查得到。

        收件者手上的那份 .docx 不會因為伺服器清檔就失效——查驗頁要能繼續回答
        「這個編號確實是 Argus 為這個網站出具的」。
        """
        stale = self._scan_with_report(age_days=120)
        number = ReportVerification.objects.get(scan_job=stale).report_number

        call_command("cleanup_reports", "--older-than-days", "90")

        self.assertTrue(
            ReportVerification.objects.filter(report_number=number).exists()
        )

    def test_dry_run_reports_without_deleting(self):
        stale = self._scan_with_report(age_days=120)

        call_command("cleanup_reports", "--older-than-days", "90", "--dry-run")

        self.assertTrue(report_output_path(stale).exists())
