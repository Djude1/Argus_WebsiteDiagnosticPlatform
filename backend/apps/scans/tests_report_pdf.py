"""PDF 報告：轉檔流程、失敗處理與下載回應。

LibreOffice 轉一份報告要好幾秒，其他報告測試以 fake_convert_docx_to_pdf 代替；
真正呼叫 soffice 的測試只在機器上有 LibreOffice 時執行（Docker image 必裝）。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.scans.models import Finding, ReportVerification, ScanJob
from apps.scans.report_pdf import ReportConversionError, convert_docx_to_pdf
from apps.scans.reports import build_scan_report, report_output_path

User = get_user_model()
FAKE_PDF_HEADER = b"%PDF-1.7\n% argus test double\n"


def fake_convert_docx_to_pdf(docx_path: Path, pdf_path: Path) -> None:
    """測試替身：內容含 .docx 位元組，雜湊仍隨報告內容變動。"""
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(FAKE_PDF_HEADER + Path(docx_path).read_bytes())


fake_pdf_conversion = mock.patch(
    "apps.scans.reports.convert_docx_to_pdf", fake_convert_docx_to_pdf
)


def _completed_scan(username: str) -> ScanJob:
    user = User.objects.create_user(username=username, password="safe-test-password")
    scan_job = ScanJob.objects.create(
        user=user, original_url="https://example.com/",
        normalized_url="https://example.com/", origin="example.com",
        status=ScanJob.Status.COMPLETED, overall_score=70,
        category_scores={"security": 70},
    )
    Finding.objects.create(
        scan_job=scan_job, page=None, severity="high",
        category=Finding.Category.SECURITY, title="缺少 HSTS",
        description="d", remediation="r", rule_id="hsts",
        ai_handoff_prompt="p", priority_score=75.0,
    )
    return scan_job


@fake_pdf_conversion
class PdfReportFlowTests(TestCase):
    def setUp(self):
        self.scan_job = _completed_scan("pdf-flow")

    def test_report_is_a_pdf_and_no_docx_is_left_behind(self):
        # 其他內容測試會用 render_report_docx 在同目錄寫 .docx，先清掉同編號的殘留
        stale = report_output_path(self.scan_job).with_suffix(".docx")
        stale.unlink(missing_ok=True)

        path = Path(build_scan_report(self.scan_job))

        self.assertEqual(path, report_output_path(self.scan_job))
        self.assertEqual(path.suffix, ".pdf")
        self.assertTrue(path.read_bytes().startswith(b"%PDF"))
        self.assertFalse(stale.exists())

    def test_download_is_served_as_pdf(self):
        client = APIClient()
        client.force_authenticate(user=self.scan_job.user)

        response = client.get(f"/api/scans/{self.scan_job.id}/report/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(".pdf", response["Content-Disposition"])
        self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF"))

    def test_conversion_failure_does_not_record_a_verification_row(self):
        """轉檔失敗時不能留下指向不存在檔案的防偽紀錄。"""
        with mock.patch(
            "apps.scans.reports.convert_docx_to_pdf",
            side_effect=ReportConversionError("boom"),
        ), self.assertRaises(ReportConversionError):
            build_scan_report(self.scan_job)

        self.assertFalse(ReportVerification.objects.filter(scan_job=self.scan_job).exists())


class ConverterErrorTests(TestCase):
    def test_missing_libreoffice_raises(self):
        with mock.patch("apps.scans.report_pdf.shutil.which", return_value=None), \
                self.assertRaises(ReportConversionError):
            convert_docx_to_pdf(Path("a.docx"), Path("a.pdf"))

    def test_timeout_raises(self):
        with mock.patch("apps.scans.report_pdf.shutil.which", return_value="/usr/bin/soffice"), \
                mock.patch(
                    "apps.scans.report_pdf.subprocess.run",
                    side_effect=subprocess.TimeoutExpired("soffice", 1),
                ), self.assertRaises(ReportConversionError):
            convert_docx_to_pdf(Path("a.docx"), Path("a.pdf"))

    def test_no_output_raises(self):
        with mock.patch("apps.scans.report_pdf.shutil.which", return_value="/usr/bin/soffice"), \
                mock.patch("apps.scans.report_pdf.subprocess.run"), \
                self.assertRaises(ReportConversionError):
            convert_docx_to_pdf(Path("a.docx"), Path("a.pdf"))


class RealLibreOfficeTests(TestCase):
    def setUp(self):
        if not (shutil.which("soffice") or shutil.which("libreoffice")):
            self.skipTest("此機器沒有 LibreOffice；Docker image 內才有")

    def test_real_conversion_produces_a_pdf_with_report_text(self):
        scan_job = _completed_scan("pdf-real")
        path = Path(build_scan_report(scan_job))

        data = path.read_bytes()
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertGreater(len(data), 20_000)
        pdftotext = shutil.which("pdftotext")
        if pdftotext:
            text = subprocess.run(
                [pdftotext, str(path), "-"], capture_output=True, check=True
            ).stdout.decode("utf-8", "replace")
            record = ReportVerification.objects.get(scan_job=scan_job)
            self.assertIn(record.report_number, text)
            self.assertIn("HSTS", text)
