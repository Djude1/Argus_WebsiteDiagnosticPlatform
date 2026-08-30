"""報告內容完整性測試：對外陳述、授權聲明、掃描範圍與掃描警告。

背景（docs/scan-report-quality-audit-2026-08-30.md 第二階段：F1、E5、F2、F3）：

- F1：附錄聲稱「交由 AI 進行自然語言解釋與改善建議撰寫」，但 ai_explanation /
  ai_remediation 在整個 backend 只被寫入空字串，該功能從未實作。一份對外交付的
  文件不能有不實陳述。
- E5：專案定位是「授權式」掃描，AuthorizationConsent 存了授權網域與聲明，
  但報告完全沒讀，等於放棄最核心的合規賣點。
- F2：報告沒說掃了幾頁、什麼模式、多深，收件者無從判斷涵蓋範圍。
- F3：warning_summary 一個字都沒進報告，包括 scan_effectiveness=no_pages_crawled
  這個「掃描實質失效」旗標——一次爬 0 頁的掃描會產出看起來正常的報告。
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from docx import Document

from apps.scans.models import AuthorizationConsent, Page, ScanJob
from apps.scans.reports import build_scan_report

User = get_user_model()


class ReportContentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="reporter", password="safe-test-password")
        self.scan_job = ScanJob.objects.create(
            user=self.user,
            original_url="https://example.com/",
            normalized_url="https://example.com/",
            origin="https://example.com",
            status=ScanJob.Status.COMPLETED,
            scan_mode=ScanJob.ScanMode.PASSIVE,
            max_depth=2,
            max_pages=20,
            overall_score=61,
            category_scores={"seo": 70, "security": 14},
        )

    def _text(self) -> str:
        document = Document(build_scan_report(self.scan_job))
        return "\n".join(p.text for p in document.paragraphs)

    # --- F1 對外陳述 -------------------------------------------------
    def test_appendix_does_not_claim_ai_wrote_explanations(self):
        """ai_explanation / ai_remediation 從未被填值，不能聲稱 AI 寫了解釋。"""
        self.assertNotIn("交由 AI 進行自然語言解釋", self._text())

    # --- E5 授權聲明 -------------------------------------------------
    def test_authorization_consent_is_recorded_in_report(self):
        AuthorizationConsent.objects.create(
            scan_job=self.scan_job, user=self.user,
            ip_address="203.0.113.10", user_agent="Mozilla/5.0 (TestAgent)",
            authorized_domain="example.com",
            statement="本人確認擁有 example.com 的管理權限並授權掃描。",
            active_testing_authorized=False,
        )

        text = self._text()

        self.assertIn("授權", text)
        self.assertIn("example.com", text)
        self.assertIn("本人確認擁有 example.com 的管理權限並授權掃描。", text)

    def test_authorization_section_never_leaks_ip_or_user_agent(self):
        """報告會被下載、轉寄給第三方，授權人的 IP 與 UA 是個資／指紋資訊，不得寫入。"""
        AuthorizationConsent.objects.create(
            scan_job=self.scan_job, user=self.user,
            ip_address="203.0.113.10", user_agent="Mozilla/5.0 (TestAgent)",
            authorized_domain="example.com", statement="授權聲明",
        )

        text = self._text()

        self.assertNotIn("203.0.113.10", text)
        self.assertNotIn("TestAgent", text)
        self.assertNotIn(self.user.username, text)

    def test_missing_consent_is_stated_not_silently_omitted(self):
        """沒有授權紀錄時要明講，不能讓章節消失讓人以為「有授權只是沒印」。"""
        self.assertIn("查無授權紀錄", self._text())

    # --- F2 掃描範圍 -------------------------------------------------
    def test_scan_scope_is_reported(self):
        for i in range(3):
            Page.objects.create(
                scan_job=self.scan_job, url=f"https://example.com/p{i}",
                final_url=f"https://example.com/p{i}", origin="https://example.com",
            )

        text = self._text()

        self.assertIn("掃描範圍", text)
        self.assertIn("全網站", text)          # max_pages=20 -> site
        self.assertIn("被動偵測", text)         # scan_mode=passive
        self.assertIn("實際掃描頁數：3", text)

    def test_single_page_scope_is_labelled(self):
        self.scan_job.max_pages = 1
        self.scan_job.save(update_fields=["max_pages"])

        self.assertIn("單頁", self._text())

    # --- F3 掃描警告 -------------------------------------------------
    def test_zero_pages_effectiveness_warning_reaches_the_report(self):
        """爬 0 頁代表掃描實質失效，分數只反映站台層級檢查，必須在報告裡講明。"""
        self.scan_job.warning_summary = {"scan_effectiveness": "no_pages_crawled"}
        self.scan_job.save(update_fields=["warning_summary"])

        text = self._text()

        self.assertIn("掃描有效性警示", text)
        self.assertIn("未抓到任何頁面", text)

    def test_blocked_and_failed_urls_are_summarised(self):
        self.scan_job.warning_summary = {
            "blocked_urls": [{"url": "https://example.com/a", "reason": "robots.txt"}],
            "failed_urls": [
                {"url": "https://example.com/b", "reason": "timeout"},
                {"url": "https://example.com/c", "reason": "timeout"},
            ],
        }
        self.scan_job.save(update_fields=["warning_summary"])

        text = self._text()

        self.assertIn("略過 1 個頁面", text)
        self.assertIn("2 個頁面擷取失敗", text)

    def test_internal_billing_error_is_not_exposed_to_the_customer(self):
        """settlement_error 是內部計費問題，不該出現在給客戶的報告裡。"""
        self.scan_job.warning_summary = {"settlement_error": "CoinWalletDoesNotExist"}
        self.scan_job.save(update_fields=["warning_summary"])

        self.assertNotIn("CoinWalletDoesNotExist", self._text())
