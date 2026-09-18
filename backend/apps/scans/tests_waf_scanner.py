"""WAF／防護機制封鎖偵測（waf_scanner）單元測試：純 DB 假資料，不依賴網路。"""
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.scans.models import Finding, Page, ScanJob
from apps.scans.security import waf_scanner
from apps.scans.security.waf_scanner import detect_waf_block


def _make_scan():
    """建立測試用 ScanJob（含必填 user / normalized_url / origin）。"""
    user = get_user_model().objects.create_user(
        username=f"user_{uuid.uuid4().hex[:8]}",
        password="testpass123",
    )
    return ScanJob.objects.create(
        user=user,
        original_url="https://example.com/",
        normalized_url="https://example.com/",
        origin="https://example.com",
    )


def _make_page(scan, *, url, status_code=200, title="", html=""):
    """建立測試用 Page（其餘欄位用 model 預設值）。"""
    return Page.objects.create(
        scan_job=scan,
        url=url,
        final_url=url,
        origin="https://example.com",
        status_code=status_code,
        title=title,
        html=html,
    )


class TestWafBlockDetection(TestCase):
    def test_below_threshold_no_finding(self):
        # 10 頁中僅 1 頁 403（10% < 30%）、無 challenge 頁 → 不產生 finding
        scan = _make_scan()
        for i in range(9):
            _make_page(scan, url=f"https://example.com/page-{i}", title=f"正常頁面 {i}")
        _make_page(scan, url="https://example.com/blocked", status_code=403)
        self.assertIsNone(detect_waf_block(scan))
        self.assertEqual(
            Finding.objects.filter(
                scan_job=scan, rule_id="waf_block_detected"
            ).count(),
            0,
        )

    def test_403_ratio_over_threshold_produces_finding_with_stats(self):
        # 10 頁中 4 頁 403（40% ≥ 30%）→ 一則 finding，description 含實際統計
        scan = _make_scan()
        for i in range(6):
            _make_page(scan, url=f"https://example.com/page-{i}", title=f"正常頁面 {i}")
        for i in range(4):
            _make_page(scan, url=f"https://example.com/blocked-{i}", status_code=403)
        finding = detect_waf_block(scan)
        self.assertIsNotNone(finding)
        self.assertEqual(finding["rule_id"], "waf_block_detected")
        self.assertEqual(finding["category"], "security")
        self.assertEqual(finding["severity"], "info")
        self.assertEqual(finding["confidence"], 1.0)
        self.assertIn("10 個頁面", finding["description"])
        self.assertIn("4 頁回傳 HTTP 403", finding["description"])
        self.assertEqual(finding["evidence_json"]["pages_403"], 4)
        self.assertEqual(finding["evidence_json"]["pages_total"], 10)

    def test_challenge_pages_at_least_two_produces_finding(self):
        # 2 頁 title 含 challenge 特徵（HTTP 200）即觸發；單頁 429 不觸發
        scan = _make_scan()
        for i in range(8):
            _make_page(scan, url=f"https://example.com/page-{i}", title=f"正常頁面 {i}")
        _make_page(scan, url="https://example.com/challenge-1", title="Just a moment...")
        _make_page(
            scan,
            url="https://example.com/challenge-2",
            title="Attention Required! | Cloudflare",
        )
        _make_page(
            scan, url="https://example.com/rate-limited", status_code=429
        )
        finding = detect_waf_block(scan)
        self.assertIsNotNone(finding)
        self.assertEqual(finding["evidence_json"]["pages_challenge"], 2)
        self.assertEqual(finding["evidence_json"]["pages_429"], 1)

    def test_403_and_challenge_combined_still_single_idempotent(self):
        # 403 比例與 challenge 特徵同時達閾值 → 回傳仍只有一則；
        # 落地後再偵測（冪等）→ None，DB 中維持一筆
        scan = _make_scan()
        for i in range(5):
            _make_page(scan, url=f"https://example.com/page-{i}", title=f"正常頁面 {i}")
        for i in range(3):
            _make_page(
                scan,
                url=f"https://example.com/blocked-{i}",
                status_code=403,
                html='<script src="/cdn-cgi/challenge-platform/h/b/orchestrate/jsl/v1"></script>',
            )
        _make_page(scan, url="https://example.com/blocked-3", status_code=429)
        finding = detect_waf_block(scan)
        self.assertIsNotNone(finding)
        Finding.objects.create(scan_job=scan, page=None, **finding)
        self.assertIsNone(detect_waf_block(scan))
        self.assertEqual(
            Finding.objects.filter(
                scan_job=scan, rule_id="waf_block_detected"
            ).count(),
            1,
        )

    def test_no_pages_and_normal_content_no_finding(self):
        # 0 頁（避免除零）與正常內容頁（含表單驗證碼字樣）都不觸發
        empty_scan = _make_scan()
        self.assertIsNone(detect_waf_block(empty_scan))

        scan = _make_scan()
        for i in range(4):
            _make_page(
                scan,
                url=f"https://example.com/contact-{i}",
                title=f"聯絡我們 {i}",
                html='<form action="/contact"><div class="g-recaptcha"></div></form>',
            )
        self.assertIsNone(detect_waf_block(scan))


class TestChallengeSignatureHelpers(TestCase):
    """純函式層級的特徵偵測：不碰 DB、不依賴網路。"""

    def test_title_markers_detected_case_insensitive(self):
        for title in (
            "Just a moment...",
            "Attention Required! | Cloudflare",
            "Access denied | example.com",
            "Too Many Requests",
            "DDoS Protection By Cloudflare",
        ):
            self.assertTrue(waf_scanner._has_challenge_signature(title, ""))

    def test_body_markers_detected(self):
        for html in (
            '<div class="cf-chl-bypass"></div>',
            '<script src="/cdn-cgi/challenge-platform/h/b/orchestrate"></script>',
            "<div id='cf_captcha' ></div>",
        ):
            self.assertTrue(waf_scanner._has_challenge_signature("", html))

    def test_normal_content_not_detected(self):
        # 正常文章正文提到這些短語、或表單內嵌驗證碼，都不應誤判
        self.assertFalse(
            waf_scanner._has_challenge_signature("服務條款", "請稍後再試（just a moment later）")
        )
        self.assertFalse(
            waf_scanner._has_challenge_signature("聯絡我們", '<div class="g-recaptcha"></div>')
        )
        self.assertFalse(waf_scanner._has_challenge_signature("", ""))

    def test_summarize_and_thresholds(self):
        stats = waf_scanner._summarize(
            [
                (200, "首頁", "<html></html>"),
                (403, "Access denied", ""),
                (429, "Too Many Requests", ""),
                (200, "Just a moment...", ""),
            ]
        )
        self.assertEqual(stats["pages_total"], 4)
        self.assertEqual(stats["pages_403"], 1)
        self.assertEqual(stats["pages_429"], 1)
        self.assertEqual(stats["blocked_ratio"], 0.5)
        self.assertEqual(stats["pages_challenge"], 3)
        self.assertTrue(waf_scanner._should_report(stats))

        low_stats = waf_scanner._summarize(
            [(200, "頁面", "")] * 9 + [(403, "Access denied", "")]
        )
        self.assertFalse(waf_scanner._should_report(low_stats))

        empty_stats = waf_scanner._summarize([])
        self.assertFalse(waf_scanner._should_report(empty_stats))
