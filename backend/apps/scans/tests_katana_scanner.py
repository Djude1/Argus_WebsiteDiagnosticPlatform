"""Katana process 預算與速率限制測試。"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.scans.cancellation import ScanCancelled
from apps.scans.katana_scanner import run_katana


class KatanaCommandBudgetTests(SimpleTestCase):
    def test_command_has_duration_size_query_and_rate_limits(self):
        with (
            patch("apps.scans.katana_scanner.shutil.which", return_value="/usr/bin/katana"),
            patch("apps.scans.katana_scanner.run_cancellable_process") as mock_run,
        ):
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
            run_katana(
                "https://example.com",
                max_depth=3,
                max_pages=50,
                rate_limit=1,
            )

        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[cmd.index("-ct") + 1], "45s")
        self.assertEqual(cmd[cmd.index("-mrs") + 1], str(2 * 1024 * 1024))
        self.assertIn("-iqp", cmd)
        self.assertTrue(
            cmd[cmd.index("-cs") + 1].startswith(r"^https://example\.com")
        )
        self.assertEqual(cmd[cmd.index("-rl") + 1], "1")
        self.assertEqual(cmd[cmd.index("-c") + 1], "2")
        self.assertEqual(
            cmd[cmd.index("-H") + 1],
            "User-Agent: SiteSense-AI-Scanner/1.0 (authorized-audit)",
        )
        self.assertIn("-duc", cmd)
        self.assertEqual(mock_run.call_args.kwargs["timeout"], 60)

    def test_small_page_budget_limits_duration_to_page_budget(self):
        with (
            patch("apps.scans.katana_scanner.shutil.which", return_value="/usr/bin/katana"),
            patch("apps.scans.katana_scanner.run_cancellable_process") as mock_run,
        ):
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
            run_katana("https://example.com", max_pages=2)

        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[cmd.index("-ct") + 1], "2s")

    def test_scan_cancelled_is_not_silenced(self):
        with (
            patch("apps.scans.katana_scanner.shutil.which", return_value="/usr/bin/katana"),
            patch(
                "apps.scans.katana_scanner.run_cancellable_process",
                side_effect=ScanCancelled,
            ),
        ):
            with self.assertRaises(ScanCancelled):
                run_katana(
                    "https://example.com",
                    scan_job_id=1,
                )


class KatanaEvidenceRedactionTests(SimpleTestCase):
    def test_short_secret_is_never_persisted_verbatim(self):
        from apps.scans.katana_scanner import _build_secret_finding

        finding = _build_secret_finding(
            {"type": "api_key", "match": "abc123"},
            "https://example.com/app.js?token=endpoint-secret",
        )

        serialized = str(finding)
        self.assertNotIn("abc123", serialized)
        self.assertNotIn("endpoint-secret", serialized)
        self.assertIn("REDACTED", serialized)


class KatanaEndpointFilterTests(SimpleTestCase):
    """隱藏 API 端點偵測的路徑過濾（2026-10-16 放寬寫死的 /api/）。"""

    def _finding(self, endpoint):
        from apps.scans.katana_scanner import _extract_endpoint_finding

        return _extract_endpoint_finding({
            "request": {"endpoint": endpoint, "source": "https://ex.test/app.js"},
            "response": {"status_code": 200},
        })

    def test_api_proxy_and_backend_now_reported(self):
        # 原本寫死 `/api/`，/api_proxy、/backend、/v3/api-docs 都被漏掉
        for endpoint in (
            "https://ex.test/api_proxy/news/list",
            "https://ex.test/backend/report",
            "https://ex.test/v3/api-docs",
            "https://ex.test/graphql",
            "https://ex.test/api/v1/users",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertIsNotNone(self._finding(endpoint))

    def test_pages_and_static_still_skipped(self):
        for endpoint in (
            "https://ex.test/about",
            "https://ex.test/member/profile",
            "https://ex.test/_next/static/chunks/main.js",
            "https://ex.test/logo.svg",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertIsNone(self._finding(endpoint))
