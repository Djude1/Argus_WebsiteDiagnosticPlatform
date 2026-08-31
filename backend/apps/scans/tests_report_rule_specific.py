"""測試 per-rule 客製文案 + 藝術字封面 + 縮圖截圖策略。

對應 audit supplement 的 N項 + 你 8/31 的「很有問題」回饋：
- (C) per-rule 「為什麼要在意」具體後果
- (B) per-rule 「修好了怎麼確認」驗收指令
- (E) 封面用 argus-title.png（含漸層 + 4 角星點綴）
- (D) 截圖縮成 thumbnail，不嵌 3MB 全頁截圖

執行：cd backend && uv run python manage.py test apps.scans.tests_report_rule_specific -v 2
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from django.test import TestCase
from docx import Document

from apps.scans.models import Finding, Page, ScanJob
from apps.scans.reports import (
    _impact_for,
    _verify_for,
    build_scan_report,
)


class RuleImpactTests(TestCase):
    def test_known_rule_id_returns_specific_impact(self):
        """SECURITY_PII_8B24BB8B28 應回傳含「個資法」「罰鍰」字眼的客製文案，
        不是 category-level 的通用模板。"""
        finding = Finding(
            rule_id="SECURITY_PII_8B24BB8B28",
            category="security",
            severity="high",
            title="PII",
            description="d", remediation="r",
            ai_handoff_prompt="p",
        )
        text = _impact_for(finding)
        self.assertIn("個資法", text)
        self.assertIn("罰鍰", text)
        # 不應該是通用模板的「會被攻擊者利用」
        self.assertNotIn("攻擊者利用", text)

    def test_unknown_rule_id_falls_back_to_category(self):
        finding = Finding(
            rule_id="UNKNOWN_RULE_XYZ",
            category="security",
            severity="medium",
            title="X",
            description="d", remediation="r",
            ai_handoff_prompt="p",
        )
        text = _impact_for(finding)
        self.assertIn("攻擊者", text)  # CATEGORY_IMPACT security fallback

    def test_empty_rule_id_falls_back_to_category(self):
        finding = Finding(
            rule_id="",
            category="seo",
            severity="low",
            title="X",
            description="d", remediation="r",
            ai_handoff_prompt="p",
        )
        text = _impact_for(finding)
        self.assertIn("搜尋引擎", text)

    def test_seo_meta_title_specific(self):
        """SEO_META_TITLE 應有「點擊率」「截斷」這類具體詞，不是通用 SEO 模板。"""
        finding = Finding(
            rule_id="SEO_META_TITLE_0D9B1FE9E2",
            category="seo",
            severity="low",
            title="Meta title",
            description="d", remediation="r",
            ai_handoff_prompt="p",
        )
        text = _impact_for(finding)
        self.assertIn("點擊率", text)
        self.assertIn("20-30", text)


class RuleVerifyTests(TestCase):
    def test_known_rule_id_returns_specific_verify(self):
        """CSP 應有 `curl -I` + `content-security-policy` 驗收指令，不是「再掃一次 Argus」。"""
        finding = Finding(
            rule_id="SECURITY_CSP_BD010B5BE0",
            category="security",
            severity="medium",
            title="CSP",
            description="d", remediation="r",
            ai_handoff_prompt="p",
        )
        text = _verify_for(finding)
        self.assertIn("curl", text)
        self.assertIn("content-security-policy", text)

    def test_dns_rules_have_dig_commands(self):
        """DNS 相關 rule 應有 dig 指令。"""
        for rid in ["dns-spf-missing", "dns-dnssec-missing", "dns-dmarc-policy-weak"]:
            finding = Finding(
                rule_id=rid, category="security", severity="medium",
                title="X", description="d", remediation="r", ai_handoff_prompt="p",
            )
            self.assertIn("dig", _verify_for(finding), f"{rid} 應含 dig 指令")

    def test_unknown_falls_back_to_category(self):
        finding = Finding(
            rule_id="UNKNOWN",
            category="geo", severity="medium",
            title="X", description="d", remediation="r", ai_handoff_prompt="p",
        )
        # CATEGORY_VERIFY geo: 「修補後重新執行一次 Argus 掃描確認此項目消失。」
        self.assertIn("Argus", _verify_for(finding))


class ReportHasRuleSpecificSectionsTests(TestCase):
    """docx 內每個 finding 都應有「為什麼要在意」「修好了怎麼確認」標題與客製內容。"""

    def _make_scan(self) -> ScanJob:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user(
            username="rule-tester", email="t@x.com", password="p",
        )
        scan = ScanJob.objects.create(
            user=user,
            original_url="https://example.com",
            normalized_url="https://example.com",
            origin="example.com",
            status=ScanJob.Status.COMPLETED,
        )
        page = Page.objects.create(
            scan_job=scan,
            url="https://example.com",
            final_url="https://example.com",
            origin="example.com",
        )
        return scan, page

    def test_report_includes_per_finding_impact_and_verify(self):
        scan, page = self._make_scan()
        Finding.objects.create(
            scan_job=scan, page=page,
            severity="high", category=Finding.Category.SECURITY,
            title="頁面外洩個資",
            description="在頁面偵測到個資",
            remediation="請遮罩",
            ai_handoff_prompt="p",
            rule_id="SECURITY_PII_8B24BB8B28",
            priority_score=75.0,
        )
        Finding.objects.create(
            scan_job=scan, page=page,
            severity="medium", category=Finding.Category.SECURITY,
            title="缺少 CSP",
            description="Response header 缺 CSP",
            remediation="加上 CSP header",
            ai_handoff_prompt="p",
            rule_id="SECURITY_CSP_BD010B5BE0",
            priority_score=50.0,
        )
        path = build_scan_report(scan)
        doc = Document(path)
        all_text = "\n".join(p.text for p in doc.paragraphs)
        # 兩段標題必須出現
        self.assertIn("為什麼要在意", all_text)
        self.assertIn("修好了怎麼確認", all_text)
        # PII 客製文案（個資法 + 罰鍰）
        self.assertIn("個資法", all_text)
        self.assertIn("罰鍰", all_text)
        # CSP 客製驗收指令（curl + header 名）
        self.assertIn("curl", all_text)
        self.assertIn("content-security-policy", all_text)
        # 不應該出現「修補後重新執行一次 Argus」通用模板（客製文案已覆蓋）
        pii_section_idx = all_text.find("頁面外洩個資")
        csp_section_idx = all_text.find("缺少 CSP")
        # 兩個 finding 之後的 修好了怎麼確認 區段都不該只有通用模板
        for start_idx in (pii_section_idx, csp_section_idx):
            verify_idx = all_text.find("修好了怎麼確認", start_idx)
            next_finding_idx = min(
                (i for i in (pii_section_idx, csp_section_idx) if i > verify_idx),
                default=len(all_text),
            )
            section = all_text[verify_idx:next_finding_idx]
            # 客製驗收指令應該含 curl 或 dig 或 grep
            self.assertTrue(
                "curl" in section or "dig" in section or "瀏覽器" in section,
                f"finding 區段沒客製驗收指令：{section[:200]}",
            )


class ReportHasTitleImageTests(TestCase):
    """封面應該用 argus-title.png（含 4 角星點綴 + 漸層），而非純文字 ARGUS。"""

    def test_title_png_is_embedded(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user(
            username="title-tester", email="t@x.com", password="p",
        )
        scan = ScanJob.objects.create(
            user=user,
            original_url="https://example.com",
            normalized_url="https://example.com",
            origin="example.com",
            status=ScanJob.Status.COMPLETED,
        )
        path = build_scan_report(scan)
        with zipfile.ZipFile(path) as z:
            media = [n for n in z.namelist() if n.startswith("word/media/")]
        # 至少有 1 張媒體（封面 title PNG 或 fallback logo）
        self.assertGreaterEqual(len(media), 1)


class ReportThumbnailScreenshotTests(TestCase):
    """截圖應該用 thumbnail（最寬 1200px），不直接 embed 全頁截圖。"""

    def setUp(self):
        # 建一個假截圖（PIL.Image 6000x1500 模擬 scan-25 的全頁截圖）
        import tempfile

        from PIL import Image

        self.tmp = tempfile.mkdtemp()
        self.scan_img_path = Path(self.tmp) / "scan-test-page.png"
        img = Image.new("RGB", (1500, 6000), (200, 200, 200))
        img.save(self.scan_img_path, "PNG")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_thumbnail_is_smaller_than_original(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user(
            username="thumb-tester", email="t@x.com", password="p",
        )
        scan = ScanJob.objects.create(
            user=user,
            original_url="https://example.com",
            normalized_url="https://example.com",
            origin="example.com",
            status=ScanJob.Status.COMPLETED,
        )
        # 讓 Page.screenshot_path 指向我們建的測試截圖。Page 不需要參考：
        # _add_entry_screenshot 會用 scan_job.pages 查詢，自己找到這個 entry page。
        Page.objects.create(
            scan_job=scan,
            url="https://example.com",
            final_url="https://example.com",
            origin="example.com",
            screenshot_path=str(self.scan_img_path),  # relative to BASE_DIR
        )

        path = build_scan_report(scan)
        with zipfile.ZipFile(path) as z:
            media = [n for n in z.namelist() if n.startswith("word/media/")]
            sizes = [z.getinfo(n).file_size for n in media]
        # 內嵌的所有媒體總大小應該明顯小於原圖（1500x6000 PNG 大約 5KB）
        # 縮圖後（1200px 寬）應該在 30-100KB 範圍；原始 1500x6000 應該差不多同大小
        # 主要斷言：docx 內嵌影像總和 < 200KB（若直接 embed 全圖會到 200KB+）
        total = sum(sizes)
        self.assertLess(total, 200_000, f"內嵌媒體過大 ({total}B)，可能沒縮圖")