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


class PreciseAnnotationTests(TestCase):
    """標註要框住實際過小的元素本身（行動版文件座標），而不是整個區塊（2026-10-06）。"""

    def test_each_small_target_gets_its_own_mobile_box(self):
        findings = analyze_ux(_input(ux_signals={"small_tap_targets": [
            {"selector": "button.slick-prev", "label": "", "width_px": 20, "height_px": 20,
             "box": {"x": 12, "y": 640, "width": 20, "height": 20}},
            {"selector": "a.more", "label": "See All", "width_px": 122, "height_px": 30,
             "box": {"x": 200, "y": 900, "width": 122, "height": 30}},
        ]}))
        annotations = findings[0]["evidence_json"]["annotations"]
        self.assertEqual(annotations["viewport"], "mobile")
        self.assertEqual(
            [(b["x"], b["y"], b["width"], b["height"], b["label"]) for b in annotations["boxes"]],
            [(12, 640, 20, 20, "20×20px"), (200, 900, 122, 30, "122×30px")],
        )

    def test_old_data_without_boxes_has_no_annotations(self):
        findings = analyze_ux(_input(ux_signals={"small_tap_targets": [
            {"selector": "a", "label": "x", "width_px": 20, "height_px": 20},
        ]}))
        self.assertIsNone(findings[0]["evidence_json"]["annotations"])


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


def _page(html: str, url: str = "https://example.com/management/login"):
    return PageAnalysisInput(
        url=url,
        final_url=url,
        title="登入",
        html=html,
        headers={},
        element_boxes={},
        layout_metrics={},
        ux_signals={},
        js_errors=[],
    )


# 未完成佔位頁：無 <form>、欄位只有 class（無 name／id／autocomplete）、密碼欄明文、按鈕無 type
_INERT_LOGIN_HTML = """
<html><body><div class="Login_wrap">
  <img src="/logo.png" alt="logo">
  <p>帳號</p><input class="InputField_field__gNamL">
  <p>密碼</p><input type="text" class="InputField_field__gNamL">
  <button class="Login_button__TYHrd">登入</button>
  <a href="/management/register">沒有帳號?立即註冊</a>
</div></body></html>
"""


class InertAuthFormTests(TestCase):
    def test_inert_placeholder_login_form_reported(self):
        findings = analyze_ux(_page(_INERT_LOGIN_HTML))
        inert = [f for f in findings if f["rule_id"] == "ux-auth-form-inert"]
        self.assertEqual(len(inert), 1, findings)
        self.assertEqual(inert[0]["severity"], Finding.Severity.LOW)
        self.assertEqual(inert[0]["category"], Finding.Category.UX)

    def test_working_spa_form_with_named_inputs_not_reported(self):
        # 欄位有 name／autocomplete＝接得上狀態與密碼管理員，不判為未完成
        html = """
        <html><body><div>
          <p>帳號</p><input name="account" autocomplete="username">
          <p>密碼</p><input type="password" name="password" autocomplete="current-password">
          <button>登入</button>
        </div></body></html>
        """
        findings = analyze_ux(_page(html))
        self.assertEqual([f for f in findings if f["rule_id"] == "ux-auth-form-inert"], [])

    def test_form_element_with_action_not_reported(self):
        # 有原生 <form> 提交路徑，即使欄位無 name 也不判為 inert
        html = """
        <html><body><form action="/login" method="post">
          <p>帳號</p><input class="x">
          <p>密碼</p><input type="text" class="x">
          <button type="submit">登入</button>
        </form></body></html>
        """
        findings = analyze_ux(_page(html))
        self.assertEqual([f for f in findings if f["rule_id"] == "ux-auth-form-inert"], [])

    def test_non_auth_page_with_unbound_input_not_reported(self):
        # 非登入頁（搜尋框），且無密碼欄：不該誤報
        html = """
        <html><body><div>
          <input class="search" placeholder="搜尋課程">
          <input class="x">
          <button>搜尋</button>
        </div></body></html>
        """
        findings = analyze_ux(_page(html, url="https://example.com/course"))
        self.assertEqual([f for f in findings if f["rule_id"] == "ux-auth-form-inert"], [])

    def test_single_input_not_reported(self):
        # 只有一個欄位（不是帳號＋密碼的表單形狀）
        html = """
        <html><body><div>
          <p>密碼</p><input type="text" class="x">
          <button>登入</button>
        </div></body></html>
        """
        findings = analyze_ux(_page(html))
        self.assertEqual([f for f in findings if f["rule_id"] == "ux-auth-form-inert"], [])
