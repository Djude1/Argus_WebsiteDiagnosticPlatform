"""Google PageSpeed Insights（pagespeed.py、tasks.stage_pagespeed，roadmap P1）。

不連線 Google：回應以 PSI v5 的格式手寫成 fixture。
"""

from __future__ import annotations

from unittest import mock

import httpx
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings

from apps.scans import pagespeed, tasks
from apps.scans.coverage import COMPLETED, FAILED
from apps.scans.models import ScanJob
from apps.scans.scan_plan import build_scan_execution_plan

PSI_RESPONSE = {
    "lighthouseResult": {
        "lighthouseVersion": "12.6.0",
        "fetchTime": "2026-10-07T08:00:00.000Z",
        "finalDisplayedUrl": "https://example.com/",
        "categories": {
            "performance": {"score": 0.72},
            "accessibility": {"score": 0.9},
            "best-practices": {"score": 0.96},
            "seo": {"score": 0.92},
        },
        "audits": {
            "largest-contentful-paint": {"numericValue": 3120.5, "displayValue": "3.1 s",
                                         "score": 0.6},
            "cumulative-layout-shift": {"numericValue": 0.02, "displayValue": "0.02", "score": 1},
            "render-blocking-resources": {
                "title": "Eliminate render-blocking resources", "score": 0.3,
                "displayValue": "Potential savings of 900 ms",
                "details": {"type": "opportunity", "overallSavingsMs": 900},
            },
            "unused-javascript": {
                "title": "Reduce unused JavaScript", "score": 0.5,
                "details": {"type": "opportunity", "overallSavingsMs": 1200},
            },
            "uses-text-compression": {
                "title": "Enable text compression", "score": 1,
                "details": {"type": "opportunity", "overallSavingsMs": 0},
            },
        },
    },
    "loadingExperience": {
        "id": "https://example.com/",
        "overall_category": "AVERAGE",
        "metrics": {
            "LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 2600, "category": "AVERAGE"},
            "INTERACTION_TO_NEXT_PAINT": {"percentile": 180, "category": "FAST"},
            "CUMULATIVE_LAYOUT_SHIFT_SCORE": {"percentile": 5, "category": "FAST"},
        },
    },
}


class ParseTests(SimpleTestCase):
    def test_lab_scores_metrics_and_opportunities(self):
        report = pagespeed.parse(PSI_RESPONSE)
        lab = report["lab"]
        self.assertEqual(
            lab["scores"], {"performance": 72, "accessibility": 90, "best-practices": 96, "seo": 92}
        )
        self.assertEqual(lab["metrics"]["largest-contentful-paint"]["display"], "3.1 s")
        # 只列分數未達標的改善機會，依可省時間排序
        self.assertEqual(
            [o["id"] for o in lab["opportunities"]],
            ["unused-javascript", "render-blocking-resources"],
        )
        self.assertEqual(lab["version"], "12.6.0")

    def test_field_prefers_url_level_and_converts_cls(self):
        field = pagespeed.parse(PSI_RESPONSE)["field"]
        self.assertEqual(field["scope"], "url")
        self.assertEqual(field["period"], "過去 28 天")
        self.assertEqual(field["metrics"]["CLS"]["p75"], 0.05)
        self.assertEqual(field["metrics"]["INP"]["category_label"], "良好")

    def test_origin_fallback_is_labelled(self):
        data = {
            **PSI_RESPONSE,
            "loadingExperience": {"origin_fallback": True, **PSI_RESPONSE["loadingExperience"]},
            "originLoadingExperience": PSI_RESPONSE["loadingExperience"],
        }
        self.assertEqual(pagespeed.parse(data)["field"]["scope"], "origin")

    def test_no_field_data_gives_reason_not_numbers(self):
        data = {"lighthouseResult": PSI_RESPONSE["lighthouseResult"]}
        field = pagespeed.parse(data)["field"]
        self.assertEqual(field["scope"], "none")
        self.assertIn("沒有這個網站足夠的真實使用者資料", field["reason"])
        self.assertNotIn("metrics", field)

    def test_summary_lines_for_report(self):
        lines = pagespeed.summary_lines(pagespeed.parse(PSI_RESPONSE))
        lab_line = lines["Lighthouse（行動版、實驗室單次量測）"]
        self.assertIn("效能 72", lab_line)
        self.assertIn("不計入 Argus 分數", lab_line)
        field_line = lines["真實使用者體驗（CrUX，過去 28 天）"]
        self.assertIn("LCP 2.6 秒（需改善）", field_line)
        self.assertIn("CLS 0.05（良好）", field_line)
        self.assertEqual(pagespeed.summary_lines({}), {})


@override_settings(ARGUS_PAGESPEED_ENABLED=True, ARGUS_PAGESPEED_API_KEY="test-secret-key")
class FetchTests(SimpleTestCase):
    def _response(self, status, payload=None):
        return httpx.Response(status, json=payload or {}, request=httpx.Request("GET", "https://x"))

    def test_success(self):
        with mock.patch("apps.scans.pagespeed.httpx.get",
                        return_value=self._response(200, PSI_RESPONSE)) as get:
            report = pagespeed.fetch("https://example.com/")
        self.assertEqual(report["lab"]["scores"]["performance"], 72)
        params = dict(p for p in get.call_args.kwargs["params"] if p[0] != "category")
        self.assertEqual(params["strategy"], "mobile")

    def test_errors_never_leak_the_key(self):
        cases = [
            (self._response(429), "配額用完"),
            (self._response(500), "HTTP 500"),
            (httpx.ReadTimeout("timed out"), "逾時"),
        ]
        for outcome, expected in cases:
            with self.subTest(expected=expected):
                kwargs = (
                    {"side_effect": outcome}
                    if isinstance(outcome, Exception)
                    else {"return_value": outcome}
                )
                with mock.patch("apps.scans.pagespeed.httpx.get", **kwargs):
                    with self.assertRaises(pagespeed.PageSpeedError) as raised:
                        pagespeed.fetch("https://example.com/")
                self.assertIn(expected, str(raised.exception))
                self.assertNotIn("test-secret-key", str(raised.exception))

    @override_settings(ARGUS_PAGESPEED_API_KEY="")
    def test_disabled_without_key(self):
        self.assertFalse(pagespeed.enabled())


class StageTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="psi", password="safe-test-password")
        self.scan = ScanJob.objects.create(
            user=user, original_url="https://example.com/", normalized_url="https://example.com/",
            origin="https://example.com", categories=["ux"],
        )
        self.ctx = tasks.ScanRunContext(
            scan_job=self.scan, execution_plan=build_scan_execution_plan(self.scan), steps=[],
            crawl_phase_started="",
        )

    @override_settings(ARGUS_PAGESPEED_ENABLED=True, ARGUS_PAGESPEED_API_KEY="k")
    def test_success_writes_report_and_coverage(self):
        with mock.patch("apps.scans.tasks.fetch_pagespeed",
                        return_value=pagespeed.parse(PSI_RESPONSE)):
            tasks.stage_pagespeed(self.ctx)
        self.scan.refresh_from_db()
        self.assertEqual(self.scan.performance_report["lab"]["scores"]["performance"], 72)
        self.assertEqual(self.ctx.coverage.status_of("pagespeed"), COMPLETED)
        self.assertIn("pagespeed", tasks.planned_scan_steps(self.scan, self.ctx.execution_plan))

    @override_settings(ARGUS_PAGESPEED_ENABLED=True, ARGUS_PAGESPEED_API_KEY="k")
    def test_failure_is_recorded_and_scan_continues(self):
        with mock.patch("apps.scans.tasks.fetch_pagespeed",
                        side_effect=pagespeed.PageSpeedError("PageSpeed Insights 配額用完")):
            tasks.stage_pagespeed(self.ctx)
        self.scan.refresh_from_db()
        self.assertEqual(self.scan.performance_report, {})
        self.assertEqual(self.ctx.coverage.status_of("pagespeed"), FAILED)

    @override_settings(ARGUS_PAGESPEED_API_KEY="")
    def test_skipped_without_key_or_ux(self):
        with mock.patch("apps.scans.tasks.fetch_pagespeed") as fetch:
            tasks.stage_pagespeed(self.ctx)
        fetch.assert_not_called()
        self.assertIsNone(self.ctx.coverage.status_of("pagespeed"))
        self.assertNotIn("pagespeed", tasks.planned_scan_steps(self.scan, self.ctx.execution_plan))
