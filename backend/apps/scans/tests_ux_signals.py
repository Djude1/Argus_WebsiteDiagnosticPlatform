"""UX 互動可用性檢查：觸控目標過小、表單欄位缺可及標籤、JavaScript 執行期錯誤。

在行動版水平溢出（tests_mobile_layout）之外，補上這三項確定性 UX 檢查。
判準都是客觀量測，各來源為空一律代表「未量測或無問題」，不硬湊 finding。
"""

from __future__ import annotations

from django.test import TestCase

from apps.scans.models import Finding
from apps.scans.scanners import PageAnalysisInput, analyze_ux


def _input(*, ux_signals=None, js_errors=None, layout_metrics=None):
    return PageAnalysisInput(
        url="https://example.com/",
        final_url="https://example.com/",
        title="示範頁面標題足夠長",
        html="<html><head><title>t</title></head><body><h1>x</h1></body></html>",
        headers={},
        element_boxes={},
        layout_metrics=layout_metrics or {},
        ux_signals=ux_signals or {},
        js_errors=js_errors or [],
    )


def _titles(findings):
    return {f["title"] for f in findings}


class TapTargetTests(TestCase):
    def test_empty_is_not_a_finding(self):
        self.assertEqual(analyze_ux(_input()), [])
        self.assertEqual(analyze_ux(_input(ux_signals={"small_tap_targets": []})), [])

    def test_small_targets_reported(self):
        findings = analyze_ux(
            _input(
                ux_signals={
                    "small_tap_targets": [
                        {"selector": "a.x", "label": "買", "width_px": 20, "height_px": 18},
                    ]
                }
            )
        )
        self.assertIn("觸控目標過小", _titles(findings))
        tap = next(f for f in findings if f["title"] == "觸控目標過小")
        self.assertEqual(tap["category"], Finding.Category.UX)
        self.assertEqual(tap["severity"], Finding.Severity.LOW)

    def test_many_small_targets_escalate_to_medium(self):
        offenders = [
            {"selector": f"a.n{i}", "label": "", "width_px": 20, "height_px": 20}
            for i in range(6)
        ]
        findings = analyze_ux(_input(ux_signals={"small_tap_targets": offenders}))
        tap = next(f for f in findings if f["title"] == "觸控目標過小")
        self.assertEqual(tap["severity"], Finding.Severity.MEDIUM)


class UnlabeledFieldTests(TestCase):
    def test_empty_is_not_a_finding(self):
        self.assertEqual(analyze_ux(_input(ux_signals={"unlabeled_fields": []})), [])

    def test_unlabeled_fields_reported_as_medium(self):
        findings = analyze_ux(
            _input(
                ux_signals={
                    "unlabeled_fields": [
                        {"selector": "input.q", "type": "text", "name": "q"},
                    ]
                }
            )
        )
        field = next(f for f in findings if f["title"] == "表單欄位缺少可及標籤")
        self.assertEqual(field["severity"], Finding.Severity.MEDIUM)
        self.assertEqual(field["impact_area"], "accessibility")


class JsErrorTests(TestCase):
    def test_empty_is_not_a_finding(self):
        self.assertEqual(analyze_ux(_input(js_errors=[])), [])

    def test_js_errors_reported(self):
        findings = analyze_ux(
            _input(js_errors=["TypeError: Cannot read properties of null (reading 'x')"])
        )
        err = next(f for f in findings if f["title"] == "頁面出現 JavaScript 執行期錯誤")
        self.assertEqual(err["severity"], Finding.Severity.MEDIUM)
        self.assertIn("TypeError", err["evidence"])


class CombinedTests(TestCase):
    def test_multiple_ux_sources_all_surface(self):
        findings = analyze_ux(
            _input(
                layout_metrics={
                    "viewport_width": 375,
                    "scroll_width": 700,
                    "overflow_px": 324,
                    "offenders": [{"selector": "div.wide", "overflow_px": 324, "width_px": 700}],
                },
                ux_signals={
                    "small_tap_targets": [
                        {"selector": "a.x", "label": "買", "width_px": 20, "height_px": 18}
                    ],
                    "unlabeled_fields": [{"selector": "input.q", "type": "text", "name": "q"}],
                },
                js_errors=["ReferenceError: foo is not defined"],
            )
        )
        titles = _titles(findings)
        self.assertIn("行動版出現水平捲動（破版）", titles)
        self.assertIn("觸控目標過小", titles)
        self.assertIn("表單欄位缺少可及標籤", titles)
        self.assertIn("頁面出現 JavaScript 執行期錯誤", titles)
        self.assertTrue(all(f["category"] == Finding.Category.UX for f in findings))
