"""掃描覆蓋契約（coverage.py，docs/scan-upgrade-roadmap.md P0-A）。

鎖定三件事：
- 工具失敗會留下紀錄，不能被呈現成「0 項問題」；整個維度都沒測到就不評分
- 前次有、本次沒有的問題，只有同一項檢查完整重跑且頁面有重新分析時才算已修好
- 覆蓋紀錄會寫進 ScanJob.coverage
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.utils import timezone

from apps.scans import tasks
from apps.scans.coverage import (
    COMPLETED,
    FAILED,
    NOT_OBSERVED,
    NOT_TESTED,
    PARTIAL,
    RESOLVED,
    SKIPPED,
    ScanCoverage,
    absent_issue_status,
    category_status,
    incomplete_checks,
)
from apps.scans.models import Finding, Page, ScanJob
from apps.scans.projects import compare_issues
from apps.scans.scan_plan import build_scan_execution_plan

User = get_user_model()


def _checks(**statuses) -> dict:
    coverage = ScanCoverage()
    for name, status in statuses.items():
        coverage.mark(name, status)
    return coverage.to_json(())["checks"]


class CategoryStatusTests(SimpleTestCase):
    def test_all_checks_completed(self):
        checks = _checks(crawl=COMPLETED, site_security=COMPLETED, deep_security=COMPLETED)
        self.assertEqual(category_status(checks, "security"), COMPLETED)

    def test_failed_tool_makes_category_partial(self):
        checks = _checks(crawl=COMPLETED, site_security=COMPLETED, nuclei=FAILED)
        self.assertEqual(category_status(checks, "security"), PARTIAL)

    def test_skipped_tool_does_not_lower_coverage(self):
        """被動掃描本來就不跑 Nuclei，不能因此算部分評估。"""
        checks = _checks(crawl=COMPLETED, site_security=COMPLETED, nuclei=SKIPPED)
        self.assertEqual(category_status(checks, "security"), COMPLETED)

    def test_every_check_failed_means_not_tested(self):
        checks = _checks(crawl=COMPLETED, seo_links=FAILED)
        self.assertEqual(category_status(checks, "seo"), "not_tested")

    def test_partial_crawl_makes_page_categories_partial(self):
        checks = _checks(crawl=PARTIAL, page_seo=COMPLETED)
        self.assertEqual(category_status(checks, "seo"), PARTIAL)

    def test_incomplete_checks_lists_only_unfinished(self):
        coverage = ScanCoverage()
        coverage.mark("nuclei", FAILED, "TimeoutError")
        coverage.mark("katana", SKIPPED)
        coverage.mark("site_security", COMPLETED)
        items = incomplete_checks(coverage.to_json(()))
        self.assertEqual([item["check"] for item in items], ["nuclei"])
        self.assertEqual(items[0]["label"], "Nuclei 主動弱點掃描")


class AbsentIssueStatusTests(SimpleTestCase):
    """前次有、本次沒有的問題是什麼狀態。"""

    def _coverage(self, status, keys=()) -> dict:
        coverage = ScanCoverage()
        coverage.mark("nuclei", status)
        coverage.add_findings(
            "nuclei", [{"rule_id": key, "category": "security", "title": ""} for key in keys]
        )
        return coverage.to_json(["security"])

    def _status(self, current_status, *, urls=(), analysed=frozenset()):
        return absent_issue_status(
            previous_coverage=self._coverage(COMPLETED, ["nuclei-xss"]),
            current_coverage=self._coverage(current_status),
            key="nuclei-xss",
            category="security",
            urls=urls,
            analysed_urls=set(analysed),
        )

    def test_same_check_completed_means_resolved(self):
        self.assertEqual(self._status(COMPLETED), RESOLVED)

    def test_tool_failure_is_not_resolved(self):
        self.assertEqual(self._status(FAILED), "inconclusive")

    def test_tool_not_run_this_time_is_not_tested(self):
        self.assertEqual(self._status(SKIPPED), NOT_TESTED)

    def test_partial_run_is_not_observed(self):
        self.assertEqual(self._status(PARTIAL), NOT_OBSERVED)

    def test_page_not_reanalysed_is_not_observed(self):
        """問題在 /a，本次根本沒爬到 /a：不能說修好了。"""
        self.assertEqual(
            self._status(COMPLETED, urls=["https://example.com/a"],
                         analysed={"https://example.com/b"}),
            NOT_OBSERVED,
        )
        self.assertEqual(
            self._status(COMPLETED, urls=["https://example.com/a"],
                         analysed={"https://example.com/a"}),
            RESOLVED,
        )

    def test_legacy_current_scan_without_coverage(self):
        status = absent_issue_status(
            previous_coverage={}, current_coverage={}, key="x", category="seo",
            urls=(), analysed_urls=set(),
        )
        self.assertEqual(status, NOT_OBSERVED)

    def test_legacy_previous_scan_falls_back_to_category(self):
        current = ScanCoverage()
        current.mark("page_seo", COMPLETED)
        current.mark("crawl", COMPLETED)
        status = absent_issue_status(
            previous_coverage={}, current_coverage=current.to_json(["seo"]),
            key="seo-title-missing", category="seo", urls=(), analysed_urls=set(),
        )
        self.assertEqual(status, RESOLVED)

    def test_agent_findings_map_by_rule_prefix(self):
        """agent 的 finding 由 runner 直接落 DB，不經覆蓋紀錄；以規則前綴對回 agent 檢查。"""
        current = ScanCoverage()
        current.mark("agent_ux", SKIPPED)
        status = absent_issue_status(
            previous_coverage={}, current_coverage=current.to_json(["ux"]),
            key="AGENT_UX_ABC", category="ux", urls=(), analysed_urls=set(),
        )
        self.assertEqual(status, NOT_TESTED)


def _scan(user, **kw) -> ScanJob:
    base = dict(
        user=user, original_url="https://example.com/", normalized_url="https://example.com/",
        origin="https://example.com", status=ScanJob.Status.QUEUED, max_pages=1, max_depth=1,
    )
    base.update(kw)
    return ScanJob.objects.create(**base)


class CompareIssuesCoverageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cov-cmp", password="safe-test-password")

    def _completed(self, coverage, days_ago):
        return _scan(
            self.user, status=ScanJob.Status.COMPLETED, coverage=coverage,
            completed_at=timezone.now() - timezone.timedelta(days=days_ago),
        )

    def test_missing_issue_status_follows_coverage(self):
        previous_cov = ScanCoverage()
        previous_cov.mark("nuclei", COMPLETED)
        previous_cov.add_findings(
            "nuclei", [{"rule_id": "nuclei-xss", "category": "security", "title": "XSS"}]
        )
        previous_cov.mark("site_security", COMPLETED)
        previous_cov.add_findings(
            "site_security",
            [{"rule_id": "header-hsts-missing", "category": "security", "title": "HSTS"}],
        )
        previous = self._completed(previous_cov.to_json(["security"]), 7)
        for rule, title in (("nuclei-xss", "XSS"), ("header-hsts-missing", "HSTS")):
            Finding.objects.create(
                scan_job=previous, category="security", severity="medium", title=title,
                rule_id=rule,
            )
        current_cov = ScanCoverage()
        current_cov.mark("nuclei", FAILED, "TimeoutError")
        current_cov.mark("site_security", COMPLETED)
        current = self._completed(current_cov.to_json(["security"]), 0)

        _issues, missing = compare_issues(current, previous)

        by_rule = {item["rule_id"]: item for item in missing}
        self.assertEqual(by_rule["header-hsts-missing"]["status"], RESOLVED)
        self.assertEqual(by_rule["header-hsts-missing"]["status_label"], "已修好")
        self.assertEqual(by_rule["nuclei-xss"]["status"], "inconclusive")

    def test_page_level_issue_requires_page_reanalysed(self):
        cov = ScanCoverage()
        cov.mark("crawl", COMPLETED)
        cov.mark("page_seo", COMPLETED)
        previous = self._completed(cov.to_json(["seo"]), 7)
        page = Page.objects.create(
            scan_job=previous, url="https://example.com/a", final_url="https://example.com/a",
            origin="https://example.com", status_code=200, depth=1,
        )
        Finding.objects.create(
            scan_job=previous, page=page, category="seo", severity="low", title="缺 H1",
            rule_id="seo-h1-missing",
        )
        current = self._completed(cov.to_json(["seo"]), 0)
        Page.objects.create(
            scan_job=current, url="https://example.com/b", final_url="https://example.com/b",
            origin="https://example.com", status_code=200, depth=1,
        )

        _issues, missing = compare_issues(current, previous)

        self.assertEqual(missing[0]["status"], NOT_OBSERVED)


class TestedCategoriesCoverageTests(TestCase):
    def test_category_with_every_check_failed_is_not_scored(self):
        user = User.objects.create_user(username="cov-cat", password="safe-test-password")
        scan = _scan(user, categories=["seo", "security"])
        ctx = tasks.ScanRunContext(
            scan_job=scan, execution_plan=build_scan_execution_plan(scan), steps=[],
            crawl_phase_started="",
        )
        ctx.crawled_pages = [{"layout_metrics": {}}]
        ctx.coverage.mark("crawl", COMPLETED)
        ctx.coverage.mark("site_security", COMPLETED)
        ctx.coverage.mark("seo_links", FAILED, "RuntimeError")

        tested = tasks.tested_categories_for(ctx)

        self.assertEqual(tested, {"security"})
        coverage = tasks.coverage_for(ctx, tested)
        self.assertEqual(coverage["categories"], {"security": COMPLETED, "seo": "not_tested"})


class ActiveProbeCoverageTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="cov-probe", password="safe-test-password")
        self.scan = _scan(
            user, scan_mode=ScanJob.ScanMode.ACTIVE, active_testing_authorized=True,
            categories=["security"],
        )
        self.ctx = tasks.ScanRunContext(
            scan_job=self.scan, execution_plan=build_scan_execution_plan(self.scan), steps=[],
            crawl_phase_started="",
        )
        mock.patch(
            "apps.scans.tasks.assert_public_http_url", side_effect=lambda url: url
        ).start()
        self.addCleanup(mock.patch.stopall)

    def test_nuclei_failure_is_recorded_not_hidden(self):
        with mock.patch("apps.scans.tasks.run_nuclei", side_effect=TimeoutError()):
            tasks.stage_active_probe(self.ctx)
        self.assertEqual(self.ctx.coverage.status_of("nuclei"), FAILED)
        self.assertEqual(self.ctx.coverage.status_of("katana"), SKIPPED)

    def test_nuclei_success_records_its_findings(self):
        finding = {
            "category": "security", "severity": "medium", "title": "XSS", "rule_id": "nuclei-xss",
        }
        with mock.patch("apps.scans.tasks.run_nuclei", return_value=[finding]):
            tasks.stage_active_probe(self.ctx)
        coverage = self.ctx.coverage.to_json(["security"])
        self.assertEqual(coverage["checks"]["nuclei"]["status"], COMPLETED)
        self.assertEqual(coverage["checks"]["nuclei"]["keys"], ["nuclei-xss"])


class PipelineWritesCoverageTests(TransactionTestCase):
    def test_completed_scan_has_coverage(self):
        user = User.objects.create_user(username="cov-run", password="safe-test-password")
        scan = _scan(user, categories=["seo", "security"])
        page = {
            "url": "https://example.com/", "final_url": "https://example.com/",
            "origin": "https://example.com", "status_code": 200, "title": "t",
            "html": "<html><head><title>t</title></head><body><h1>t</h1></body></html>",
            "rendered_dom": "", "html_only": "", "screenshot_path": "", "load_time_ms": 10,
            "depth": 0, "blocked_reason": "", "outgoing_links": [], "headers": {},
            "element_boxes": [],
        }
        patches = {
            "assert_public_http_url": {"side_effect": lambda url: url},
            "crawl_site": {"new": mock.AsyncMock(return_value=([page], {}, {}, []))},
            "build_site_profile": {"return_value": {}},
            "analyze_ssl": {"return_value": []},
            "analyze_dns": {"return_value": []},
            "build_link_report": {"side_effect": RuntimeError("link check down")},
            "refund_full_for_scan": {},
            "settle_scan_actual": {},
            "grant_fixgen_entitlement": {},
        }
        for target, kwargs in patches.items():
            mock.patch(f"apps.scans.tasks.{target}", **kwargs).start()
        self.addCleanup(mock.patch.stopall)

        tasks.run_scan_job.run(scan.id)

        scan.refresh_from_db()
        self.assertEqual(scan.status, ScanJob.Status.COMPLETED)
        checks = scan.coverage["checks"]
        self.assertEqual(checks["crawl"]["status"], COMPLETED)
        self.assertEqual(checks["page_seo"]["status"], COMPLETED)
        self.assertEqual(checks["seo_links"]["status"], FAILED)
        self.assertEqual(checks["nuclei"]["status"], SKIPPED)
        # SEO 的連結檢查失敗了，但逐頁分析有跑完：部分評估，不是完整
        self.assertEqual(scan.coverage["categories"]["seo"], PARTIAL)
        # 評分與規則版本也一起寫入（versions.py）
        from apps.scans.versions import RULESET_VERSION, SCORING_VERSION

        self.assertEqual((scan.scoring_version, scan.ruleset_version),
                         (SCORING_VERSION, RULESET_VERSION))
