"""連結檢查覆蓋與健康度趨勢（seo/link_trend.py，roadmap §11 第 2、3 項）。"""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

import httpx
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.scans import tasks
from apps.scans.models import Page, ScanJob
from apps.scans.seo import link_check
from apps.scans.seo.link_trend import (
    coverage_text,
    crawled_verdicts,
    effective_verdicts,
    link_coverage,
    link_trend,
)
from apps.scans.seo.report import project_seo
from apps.scans.seo.site_findings import broken_internal_links

User = get_user_model()
ORIGIN = "https://shop.example.tw"


def _row(verdict, status=None):
    return {"verdict": verdict, "status": status, "chain": [], "note": ""}


class LinkCoverageTests(SimpleTestCase):
    def test_counts_each_state_and_unchecked_reasons(self):
        report = {
            "links": {
                "a": _row("ok"), "b": _row("redirect"), "c": _row("broken", 404),
                "d": _row("restricted", 403), "e": _row("timeout"), "f": _row("error"),
                "g": _row("skipped"),
            },
            "unchecked": 5, "unchecked_reasons": {"over_limit": 3, "budget_exhausted": 2},
        }
        counts = link_coverage(report)
        self.assertEqual(counts, {
            "checked": 3, "restricted": 1, "timeout": 1, "error": 1, "skipped": 1,
            "over_limit": 3, "budget_exhausted": 2,
        })
        self.assertEqual(
            coverage_text(counts),
            "對方限制檢查 1、逾時 1、無法連線 1、非公開位址 1、超過數量上限 3、時間用完 2",
        )

    def test_old_report_without_reasons_counts_unchecked_as_over_limit(self):
        counts = link_coverage({"links": {}, "unchecked": 4})
        self.assertEqual(counts["over_limit"], 4)
        self.assertEqual(counts["budget_exhausted"], 0)


class LinkTrendTests(SimpleTestCase):
    def _trend(self, current, previous):
        return link_trend(current, previous, previous_scan_id=7, previous_checked_at="t")

    def test_labels_new_persisting_recovered_and_unconfirmed(self):
        previous = {
            "/still": "broken", "/fixed": "broken", "/timeout-now": "broken",
            "/gone-from-site": "loop", "/was-ok": "ok",
        }
        current = {
            "/still": "broken", "/fixed": "redirect", "/timeout-now": "timeout",
            "/was-ok": "broken", "/brand-new": "broken",
        }
        trend = self._trend(current, previous)
        self.assertEqual(trend["items"], {
            "/brand-new": "new", "/fixed": "recovered", "/gone-from-site": "unconfirmed",
            "/still": "persisting", "/timeout-now": "unconfirmed", "/was-ok": "new",
        })
        self.assertEqual(trend["counts"],
                         {"new": 2, "persisting": 1, "recovered": 1, "unconfirmed": 2})
        self.assertEqual(trend["previous_scan_id"], 7)

    def test_restricted_or_unchecked_is_never_recovered(self):
        trend = self._trend({"/a": "restricted"}, {"/a": "broken", "/b": "broken"})
        self.assertEqual(trend["items"], {"/a": "unconfirmed", "/b": "unconfirmed"})

    def test_crawled_pages_supply_verdicts_link_check_skipped(self):
        crawled = crawled_verdicts([
            ("/ok", "/ok", 200), ("/404", "/404", 404), ("/moved", "/new", 200),
            ("/none", "/none", None),
        ])
        self.assertEqual(crawled, {"/ok": "ok", "/404": "broken"})
        # 連結檢查結果優先於爬蟲狀態
        merged = effective_verdicts({"links": {"/ok": _row("timeout")}}, crawled)
        self.assertEqual(merged, {"/ok": "timeout", "/404": "broken"})


@mock.patch("apps.scans.seo.link_check.assert_public_http_url", side_effect=lambda url: url)
class LinkCheckCoverageTests(SimpleTestCase):
    def test_timeout_has_its_own_verdict(self, _assert):
        client = mock.Mock()
        client.head.side_effect = httpx.ReadTimeout("slow")
        client.get.side_effect = httpx.ReadTimeout("slow")
        result = link_check.check_url("https://a.tw/slow", client)
        self.assertEqual(result["verdict"], "timeout")

    def test_unchecked_split_into_over_limit_and_budget(self, _assert):
        with mock.patch.object(link_check, "check_url", return_value=_row("ok")):
            results, reasons = link_check.check_links(
                [f"https://a.tw/{i}" for i in range(5)], limit=3, budget_seconds=60,
            )
        self.assertEqual(len(results), 3)
        self.assertEqual(reasons, {"over_limit": 2, "budget_exhausted": 0})
        results, reasons = link_check.check_links(
            [f"https://a.tw/{i}" for i in range(5)], limit=3, budget_seconds=-1,
        )
        self.assertEqual(results, {})
        self.assertEqual(reasons, {"over_limit": 2, "budget_exhausted": 3})


class BrokenLinkFindingTrendTests(SimpleTestCase):
    def test_finding_says_how_many_are_new(self):
        report = {
            "links": {f"{ORIGIN}/a": _row("broken", 404), f"{ORIGIN}/b": _row("broken", 404)},
            "trend": {"items": {f"{ORIGIN}/a": "new", f"{ORIGIN}/b": "persisting"}},
        }
        finding = broken_internal_links(report, [], "shop.example.tw")
        self.assertIn("1 個是新壞掉、1 個持續失效", finding["description"])
        self.assertIn("HTTP 404，新壞掉", finding["evidence"])
        self.assertEqual(finding["evidence_json"]["broken_links"][1]["trend"], "persisting")

    def test_no_comparison_without_previous_scan(self):
        report = {"links": {f"{ORIGIN}/a": _row("broken", 404)}}
        finding = broken_internal_links(report, [], "shop.example.tw")
        self.assertNotIn("上一次掃描", finding["description"])


def _html(body=""):
    return (
        "<html><head><title>晨光咖啡｜首頁</title></head>"
        f"<body><main>{body}</main></body></html>"
    )


class LinkTrendStageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="trend", email="trend@example.com", password="safe-test-password"
        )
        self.previous = ScanJob.objects.create(
            user=self.user, original_url=f"{ORIGIN}/", normalized_url=f"{ORIGIN}/",
            origin=ORIGIN, status=ScanJob.Status.COMPLETED, categories=["seo"],
            completed_at=timezone.now() - timedelta(days=1),
            seo_report={"checked_at": "2026-10-07T00:00:00+00:00", "unchecked": 0, "links": {
                f"{ORIGIN}/old": _row("broken", 404),
                f"{ORIGIN}/fixed": _row("broken", 404),
            }},
        )
        # 上一次由爬蟲直接造訪、回 404 的頁面也算失效
        Page.objects.create(scan_job=self.previous, url=f"{ORIGIN}/crawled-404",
                            final_url=f"{ORIGIN}/crawled-404", origin=ORIGIN, status_code=404)
        ScanJob.objects.filter(id=self.previous.id).update(
            created_at=timezone.now() - timedelta(days=1)
        )
        self.scan = ScanJob.objects.create(
            user=self.user, original_url=f"{ORIGIN}/", normalized_url=f"{ORIGIN}/",
            origin=ORIGIN, categories=["seo"],
        )
        body = "".join(f"<a href='/{p}'>{p}</a>" for p in ("old", "fixed", "new-broken"))
        self.page = Page.objects.create(scan_job=self.scan, url=f"{ORIGIN}/",
                                        final_url=f"{ORIGIN}/", origin=ORIGIN, status_code=200,
                                        html=_html(body))
        self.ctx = mock.Mock(scan_job=self.scan, scan_job_id=self.scan.id,
                             pages=[(self.page, {})], deep_scan_total=1, site_signals={})

    def _run(self, links, reasons=None):
        report = {"checked_at": "t", "links": links,
                  "unchecked": sum((reasons or {}).values()), "unchecked_reasons": reasons or {}}
        with mock.patch("apps.scans.tasks.build_link_report", return_value=report):
            tasks.stage_seo_links(self.ctx)
        self.scan.refresh_from_db()
        return self.scan.seo_report

    def test_trend_and_coverage_are_saved(self):
        report = self._run({
            f"{ORIGIN}/old": _row("broken", 404),
            f"{ORIGIN}/fixed": _row("ok", 200),
            f"{ORIGIN}/new-broken": _row("broken", 404),
        }, {"over_limit": 2, "budget_exhausted": 1})
        self.assertEqual(report["trend"]["previous_scan_id"], self.previous.id)
        self.assertEqual(report["trend"]["items"], {
            f"{ORIGIN}/crawled-404": "unconfirmed",
            f"{ORIGIN}/fixed": "recovered",
            f"{ORIGIN}/new-broken": "new",
            f"{ORIGIN}/old": "persisting",
        })
        self.assertEqual(report["coverage"]["checked"], 3)
        self.assertEqual(report["coverage"]["budget_exhausted"], 1)
        detail = self.ctx.coverage.mark.call_args.args
        self.assertEqual(detail[1], tasks.PARTIAL)
        self.assertIn("超過數量上限 2、時間用完 1", detail[2])
        finding = next(f for f in self.ctx.record.call_args.args[0]
                       if f["rule_id"] == "seo-broken-internal-links")
        self.assertIn("1 個是新壞掉、1 個持續失效", finding["description"])

    def test_first_scan_has_no_trend(self):
        self.previous.delete()
        report = self._run({f"{ORIGIN}/old": _row("broken", 404)})
        self.assertNotIn("trend", report)
        self.assertEqual(self.ctx.coverage.mark.call_args.args[1], tasks.COMPLETED)

    def test_report_rows_carry_trend_and_timeout_is_an_issue(self):
        self._run({
            f"{ORIGIN}/old": _row("broken", 404),
            f"{ORIGIN}/fixed": _row("timeout"),
            f"{ORIGIN}/new-broken": _row("broken", 404),
        })
        self.scan.status = ScanJob.Status.COMPLETED
        self.scan.completed_at = timezone.now()
        self.scan.save(update_fields=["status", "completed_at"])
        data = project_seo(self.scan.project, self.scan)
        rows = {row["url"]: row for row in data["links"]["rows"]}
        self.assertEqual(rows[f"{ORIGIN}/old"]["trend"], "persisting")
        self.assertEqual(rows[f"{ORIGIN}/fixed"]["trend"], "unconfirmed")
        self.assertEqual(rows[f"{ORIGIN}/fixed"]["verdict"], "timeout")
        self.assertEqual(data["links"]["coverage"]["timeout"], 1)
        self.assertEqual(data["links"]["trend"]["counts"]["new"], 1)
        self.assertNotIn("items", data["links"]["trend"])
        self.assertTrue(any(issue["title"] == "連結檢查逾時" for issue in data["issues"]))
