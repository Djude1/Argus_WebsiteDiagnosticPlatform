"""UX 假按鈕檢查（scanners._ux_fake_buttons，借鑑 claude-seo MIT）。"""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.scans.scanners import PageAnalysisInput, analyze_ux


def _page(html: str) -> PageAnalysisInput:
    return PageAnalysisInput(
        url="https://example.com/", final_url="https://example.com/", title="t",
        html=html, headers={}, element_boxes={},
    )


def _fake_button(page: PageAnalysisInput):
    return next((f for f in analyze_ux(page) if f["rule_id"] == "ux-fake-button"), None)


class FakeButtonTests(SimpleTestCase):
    def test_div_onclick_without_role_flagged(self):
        html = "<html><body><div onclick=\"go()\">送出</div></body></html>"
        f = _fake_button(_page(html))
        self.assertIsNotNone(f)
        self.assertEqual(f["severity"], "low")
        self.assertEqual(f["category"], "ux")

    def test_span_onclick_flagged(self):
        html = "<html><body><span onclick='x()'>點我</span></body></html>"
        self.assertIsNotNone(_fake_button(_page(html)))

    def test_real_button_not_flagged(self):
        html = (
            "<html><body><button onclick=\"go()\">送出</button>"
            "<a href='/x'>連結</a></body></html>"
        )
        self.assertIsNone(_fake_button(_page(html)))

    def test_div_with_role_button_not_flagged(self):
        # 有 role 代表作者有意識處理語意 → 不列入（壓低誤報）
        html = (
            "<html><body><div role=\"button\" tabindex=\"0\" "
            "onclick=\"go()\">送出</div></body></html>"
        )
        self.assertIsNone(_fake_button(_page(html)))

    def test_plain_div_without_onclick_not_flagged(self):
        html = "<html><body><div class='card'>內容</div></body></html>"
        self.assertIsNone(_fake_button(_page(html)))

    def test_count_and_samples(self):
        html = "<html><body>" + "".join(
            f"<div onclick='f{i}()'>btn{i}</div>" for i in range(10)
        ) + "</body></html>"
        f = _fake_button(_page(html))
        self.assertIn("10 個", f["description"])
