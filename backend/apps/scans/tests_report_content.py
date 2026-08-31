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

from apps.scans.models import AuthorizationConsent, Finding, Page, ScanJob
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

    def test_finding_carries_a_pasteable_ai_prompt(self):
        """報告要給使用者可直接貼進 AI 工具的提示詞。

        ai_handoff_prompt 每筆 Finding 都已經有值（scanners.build_ai_handoff_prompt），
        但舊報告完全沒用它——等於既沒有 AI 解釋、也沒把現成的替代方案交出去。
        """
        Finding.objects.create(
            scan_job=self.scan_job, page=None, severity="medium",
            category=Finding.Category.SECURITY, title="缺少 CSP",
            description="未設定 Content-Security-Policy。", remediation="加上 CSP header。",
            ai_handoff_prompt=(
                "我網站有以下問題，請協助我分析並提供修復方向：\n- 問題類型：security"
            ),
            rule_id="header-csp-missing", priority_score=50.0,
        )

        text = self._text()

        self.assertIn("AI 提示詞", text)
        self.assertIn("我網站有以下問題，請協助我分析並提供修復方向", text)

    def test_ai_prompt_is_pii_masked_like_evidence(self):
        """ai_handoff_prompt 內嵌了原始 evidence，不遮罩等於從後門把個資漏回報告。"""
        Finding.objects.create(
            scan_job=self.scan_job, page=None, severity="high",
            category=Finding.Category.SECURITY, title="頁面外洩個人資料",
            description="偵測到個資。", remediation="下架該頁。",
            evidence="台灣手機：0912345678",
            ai_handoff_prompt="請協助分析：\n- 相關證據：\n台灣手機：0912345678",
            rule_id="SECURITY_PII_TEST", priority_score=75.0,
        )

        text = self._text()

        self.assertNotIn("0912345678", text)

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
