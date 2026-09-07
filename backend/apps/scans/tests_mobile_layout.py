"""行動版版面診斷（UX 分類的第一個確定性檢查）。

在此之前 UX 分類只有 Hermes-Agent 會產出，而它預設不啟用、且要 active 模式
＋主動授權＋非單頁掃描才會被觸發——實務上使用者從來沒看過 UX finding。
"""

from __future__ import annotations

from django.test import TestCase

from apps.scans.models import Finding
from apps.scans.scanners import PageAnalysisInput, analyze_page, analyze_ux


def _input(metrics):
    return PageAnalysisInput(
        url="https://example.com/",
        final_url="https://example.com/",
        title="示範頁面標題足夠長",
        html="<html><head><title>t</title></head><body><h1>x</h1></body></html>",
        headers={},
        element_boxes={},
        layout_metrics=metrics,
    )


class MobileOverflowTests(TestCase):
    def test_unmeasured_is_not_a_pass(self):
        """量測失敗或舊資料時 layout_metrics 是空的。

        空＝沒量到，不能當成「沒問題」——這與本專案對 category_scores 的
        既有原則一致（缺鍵代表未評估，不是滿分）。
        """
        self.assertEqual(analyze_ux(_input({})), [])
        self.assertEqual(analyze_ux(_input(None)), [])

    def test_no_overflow_produces_nothing(self):
        self.assertEqual(
            analyze_ux(
                _input(
                    {"viewport_width": 375, "scroll_width": 375, "overflow_px": 0, "offenders": []}
                )
            ),
            [],
        )

    def test_subpixel_rounding_is_not_reported(self):
        """瀏覽器的次像素捨入常造成幾 px 誤差，回報那個只會製造雜訊。"""
        self.assertEqual(
            analyze_ux(
                _input(
                    {"viewport_width": 375, "scroll_width": 378, "overflow_px": 3, "offenders": []}
                )
            ),
            [],
        )

    def test_severe_overflow_is_medium(self):
        """超出半個螢幕寬以上，手機上已經是明顯破版。"""
        findings = analyze_ux(
            _input(
                {
                    "viewport_width": 375,
                    "scroll_width": 900,
                    "overflow_px": 525,
                    "offenders": [{"selector": "div.banner", "overflow_px": 525, "width_px": 900}],
                }
            )
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], Finding.Severity.MEDIUM)
        self.assertEqual(findings[0]["category"], Finding.Category.UX)
        self.assertEqual(findings[0]["selector"], "div.banner")

    def test_mild_overflow_is_low(self):
        findings = analyze_ux(
            _input(
                {
                    "viewport_width": 375,
                    "scroll_width": 405,
                    "overflow_px": 30,
                    "offenders": [{"selector": "p.long", "overflow_px": 30}],
                }
            )
        )
        self.assertEqual(findings[0]["severity"], Finding.Severity.LOW)

    def test_offending_elements_appear_in_evidence(self):
        """使用者要能直接知道去改哪個元素，不然這個 finding 沒有可操作性。"""
        findings = analyze_ux(
            _input(
                {
                    "viewport_width": 375,
                    "scroll_width": 700,
                    "overflow_px": 325,
                    "offenders": [
                        {"selector": "table#price", "overflow_px": 325},
                        {"selector": "div.wide", "overflow_px": 120},
                    ],
                }
            )
        )
        self.assertIn("table#price", findings[0]["evidence"])
        self.assertIn("div.wide", findings[0]["evidence"])

    def test_analyze_page_includes_ux(self):
        """接線測試：analyze_page 沒串上的話，這個檢查等於不存在。"""
        findings = analyze_page(
            _input(
                {
                    "viewport_width": 375,
                    "scroll_width": 900,
                    "overflow_px": 525,
                    "offenders": [{"selector": "div.banner", "overflow_px": 525}],
                }
            )
        )
        self.assertTrue(
            any(f["category"] == Finding.Category.UX for f in findings),
            "analyze_page 必須包含 UX 檢查",
        )
