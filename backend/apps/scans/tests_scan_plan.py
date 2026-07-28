"""單頁／全網站與被動／主動授權的執行計畫測試。"""

import json
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TransactionTestCase, override_settings

from apps.scans.cancellation import ScanCancelled
from apps.scans.models import ScanJob
from apps.scans.scan_plan import build_scan_execution_plan
from apps.scans.tasks import run_scan_job


def _job(*, single_page: bool, active: bool) -> SimpleNamespace:
    return SimpleNamespace(
        max_pages=1 if single_page else 50,
        max_depth=1 if single_page else 3,
        scan_mode=ScanJob.ScanMode.ACTIVE if active else ScanJob.ScanMode.PASSIVE,
        active_testing_authorized=active,
    )


class ScanExecutionPlanTests(SimpleTestCase):
    def test_passive_single_page_runs_no_active_tools(self):
        plan = build_scan_execution_plan(_job(single_page=True, active=False))

        self.assertEqual(plan.scope, "single")
        self.assertFalse(plan.run_nuclei)
        self.assertFalse(plan.run_katana)
        self.assertFalse(plan.run_exposure)
        self.assertFalse(plan.run_agent)
        self.assertFalse(plan.run_kali)

    def test_active_single_page_keeps_all_tools_inside_single_page_scope(self):
        plan = build_scan_execution_plan(_job(single_page=True, active=True))

        self.assertEqual(plan.scope, "single")
        self.assertTrue(plan.run_nuclei)
        self.assertTrue(plan.run_kali)
        self.assertFalse(plan.run_katana)
        self.assertFalse(plan.run_exposure)
        self.assertFalse(plan.run_agent)

    def test_passive_site_runs_no_active_tools(self):
        plan = build_scan_execution_plan(_job(single_page=False, active=False))

        self.assertEqual(plan.scope, "site")
        self.assertFalse(plan.active_authorized)
        self.assertFalse(plan.run_nuclei)
        self.assertFalse(plan.run_katana)
        self.assertFalse(plan.run_exposure)
        self.assertFalse(plan.run_agent)
        self.assertFalse(plan.run_kali)

    def test_active_site_enables_authorized_site_tools(self):
        plan = build_scan_execution_plan(_job(single_page=False, active=True))

        self.assertEqual(plan.scope, "site")
        self.assertTrue(plan.active_authorized)
        self.assertTrue(plan.run_nuclei)
        self.assertTrue(plan.run_katana)
        self.assertTrue(plan.run_exposure)
        self.assertTrue(plan.run_agent)
        self.assertTrue(plan.run_kali)

    def test_active_without_authorization_runs_no_active_tools(self):
        job = _job(single_page=False, active=True)
        job.active_testing_authorized = False

        plan = build_scan_execution_plan(job)

        self.assertFalse(plan.active_authorized)
        self.assertFalse(plan.run_nuclei)
        self.assertFalse(plan.run_katana)
        self.assertFalse(plan.run_exposure)
        self.assertFalse(plan.run_agent)
        self.assertFalse(plan.run_kali)


@override_settings(ARGUS_AGENT_ENABLED=True, ARGUS_ACTIVE_MAX_RPS=2)
class ScanTaskPlanIntegrationTests(TransactionTestCase):
    """確認 Celery 編排確實遵守執行計畫，不只測純函式結果。"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="scan-plan-user",
            password="safe-test-password",
        )
        patch_specs = {
            "target": mock.patch(
                "apps.scans.tasks.assert_public_http_url",
                return_value="https://example.com/",
            ),
            "crawl": mock.patch(
                "apps.scans.tasks.crawl_site",
                new=mock.AsyncMock(return_value=([], {}, {})),
            ),
            "katana": mock.patch(
                "apps.scans.tasks.run_katana",
                return_value=([], []),
            ),
            "nuclei": mock.patch(
                "apps.scans.tasks.run_nuclei",
                return_value=[],
            ),
            "ssl": mock.patch("apps.scans.tasks.analyze_ssl", return_value=[]),
            "cookies": mock.patch("apps.scans.tasks.analyze_cookies", return_value=[]),
            "headers": mock.patch("apps.scans.tasks.analyze_headers", return_value=[]),
            "sri": mock.patch("apps.scans.tasks.analyze_sri", return_value=[]),
            "dns": mock.patch("apps.scans.tasks.analyze_dns", return_value=[]),
            "js": mock.patch("apps.scans.tasks.analyze_js_libraries", return_value=[]),
            "exposure": mock.patch(
                "apps.scans.tasks.exposure_scanner.probe_paths",
                new=mock.AsyncMock(return_value=[]),
            ),
            "exposure_analysis": mock.patch(
                "apps.scans.tasks.exposure_scanner.analyze_probe_results",
                return_value=[],
            ),
            "robots": mock.patch(
                "apps.scans.tasks.exposure_scanner.analyze_robots_disclosure",
                return_value=[],
            ),
            "site": mock.patch("apps.scans.tasks.analyze_site_signals", return_value=[]),
            "owasp": mock.patch("apps.scans.tasks.owasp_mapper.backfill"),
            "agent": mock.patch(
                "apps.agent.runner.run_agent_for_scan",
                new=mock.AsyncMock(return_value=None),
            ),
            "kali": mock.patch(
                "apps.scans.tasks.validate_findings_with_kali",
                return_value=[],
            ),
            "score": mock.patch(
                "apps.scans.tasks.calculate_scores",
                return_value=(100, {}, []),
            ),
            "settle": mock.patch("apps.scans.tasks.settle_scan_actual"),
            "refund": mock.patch("apps.scans.tasks.refund_full_for_scan"),
        }
        self.mocks = {name: patcher.start() for name, patcher in patch_specs.items()}
        self.patchers = list(patch_specs.values())

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()

    def _create_scan(self, *, single_page: bool, active: bool) -> ScanJob:
        return ScanJob.objects.create(
            user=self.user,
            original_url="https://example.com/",
            normalized_url="https://example.com/",
            origin="https://example.com",
            status=ScanJob.Status.QUEUED,
            scan_mode=ScanJob.ScanMode.ACTIVE if active else ScanJob.ScanMode.PASSIVE,
            active_testing_authorized=active,
            max_pages=1 if single_page else 50,
            max_depth=1 if single_page else 3,
        )

    def test_passive_site_does_not_call_active_tools(self):
        scan = self._create_scan(single_page=False, active=False)

        run_scan_job.run(scan.id)

        self.mocks["nuclei"].assert_not_called()
        self.mocks["katana"].assert_not_called()
        self.mocks["exposure"].assert_not_called()
        self.mocks["agent"].assert_not_called()
        self.mocks["kali"].assert_not_called()

    def test_active_single_page_only_calls_single_url_active_tools(self):
        scan = self._create_scan(single_page=True, active=True)

        run_scan_job.run(scan.id)

        self.mocks["nuclei"].assert_called_once_with(
            "https://example.com/",
            scan.id,
            deep=True,
            extra_urls=[],
            rate_limit=2,
        )
        self.mocks["kali"].assert_called_once_with(scan.id, [])
        self.mocks["katana"].assert_not_called()
        self.mocks["exposure"].assert_not_called()
        self.mocks["agent"].assert_not_called()

    def test_active_site_calls_authorized_site_tools(self):
        scan = self._create_scan(single_page=False, active=True)

        run_scan_job.run(scan.id)

        self.mocks["nuclei"].assert_called_once()
        self.mocks["katana"].assert_called_once()
        self.mocks["exposure"].assert_called_once()
        self.mocks["agent"].assert_called_once()
        self.mocks["kali"].assert_called_once()

    def test_exposure_cancellation_immediately_enters_cancelled_branch(self):
        scan = self._create_scan(single_page=False, active=True)
        self.mocks["exposure"].side_effect = ScanCancelled()

        result = run_scan_job.run(scan.id)

        scan.refresh_from_db()
        self.assertEqual(result, {"status": "cancelled"})
        self.assertEqual(scan.status, ScanJob.Status.CANCELLED)
        self.mocks["refund"].assert_called_once()
        self.mocks["agent"].assert_not_called()
        self.mocks["kali"].assert_not_called()
        self.mocks["score"].assert_not_called()

    @override_settings(ARGUS_ACTIVE_MAX_RPS=1)
    def test_active_site_with_one_rps_runs_external_tools_sequentially(self):
        scan = self._create_scan(single_page=False, active=True)

        with mock.patch("apps.scans.tasks.ThreadPoolExecutor") as executor:
            run_scan_job.run(scan.id)

        executor.assert_not_called()
        self.assertEqual(self.mocks["katana"].call_args.kwargs["rate_limit"], 1)
        self.assertEqual(self.mocks["nuclei"].call_args.kwargs["rate_limit"], 1)

    def test_scan_log_redacts_target_query_values(self):
        scan = self._create_scan(single_page=True, active=False)
        scan.normalized_url = "https://example.com/?token=private-marker"
        scan.save(update_fields=["normalized_url"])

        run_scan_job.run(scan.id)

        scan.refresh_from_db()
        serialized_log = json.dumps(scan.scan_log, ensure_ascii=False)
        self.assertNotIn("private-marker", serialized_log)
        self.assertIn("REDACTED", serialized_log)
