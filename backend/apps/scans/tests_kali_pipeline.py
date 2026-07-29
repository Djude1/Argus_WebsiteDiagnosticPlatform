"""Task 6 pipeline 回歸：agent → Kali fallback → scoring 的順序與資料流。

策略（沿用 tests_cancel.py 的依賴 mock 模式）：
- mock 所有外部依賴（crawler、scanners、agent、Kali、billing），
  不執行任何真正的掃描或工具呼叫。
- 重點驗證：
  1. Hermes-Agent 在 Kali fallback 之前執行。
  2. agent_result.security_findings 送達 calculate_scores。
  3. Agent 停用／失敗時 fallback 仍執行。
  4. ScanCancelled 正確傳遞到 cancelled/refund 分支（不被 silent-fail 吞掉）。
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings

from apps.agent.loop import AgentRunResult
from apps.scans.cancellation import ScanCancelled
from apps.scans.models import ScanJob
from apps.scans.tasks import run_scan_job

User = get_user_model()


def _make_active_authorized_scan() -> ScanJob:
    return ScanJob.objects.create(
        user=User.objects.create_user(
            username=f"pipeline_{ScanJob.objects.count()}", password="safe-test-password"
        ),
        original_url="https://example.com/",
        normalized_url="https://example.com/",
        origin="https://example.com",
        status=ScanJob.Status.QUEUED,
        scan_mode=ScanJob.ScanMode.ACTIVE,
        active_testing_authorized=True,
    )


@override_settings(ARGUS_AGENT_ENABLED=True)
class KaliPipelineOrderingTests(TransactionTestCase):
    """Task 6：agent → Kali fallback → scoring 順序與資料流迴歸。"""

    def setUp(self):
        self.scan_job = _make_active_authorized_scan()
        # 通用 mocks：所有外部依賴 silent-empty，不執行真正的爬蟲／掃描／連線
        self._patches = [
            mock.patch(
                "apps.scans.tasks.assert_public_http_url",
                return_value="https://example.com/",
            ),
            mock.patch(
                "apps.scans.tasks.crawl_site",
                new=mock.AsyncMock(return_value=([], {}, {})),
            ),
            mock.patch("apps.scans.tasks.run_katana", return_value=([], [])),
            mock.patch("apps.scans.tasks.run_nuclei", return_value=[]),
            mock.patch("apps.scans.tasks.analyze_ssl", return_value=[]),
            mock.patch("apps.scans.tasks.analyze_cookies", return_value=[]),
            mock.patch("apps.scans.tasks.analyze_headers", return_value=[]),
            mock.patch("apps.scans.tasks.analyze_sri", return_value=[]),
            mock.patch("apps.scans.tasks.analyze_dns", return_value=[]),
            mock.patch("apps.scans.tasks.analyze_js_libraries", return_value=[]),
            mock.patch(
                "apps.scans.tasks.exposure_scanner.probe_paths",
                new=mock.AsyncMock(return_value=[]),
            ),
            mock.patch(
                "apps.scans.tasks.exposure_scanner.analyze_probe_results",
                return_value=[],
            ),
            mock.patch(
                "apps.scans.tasks.exposure_scanner.analyze_robots_disclosure",
                return_value=[],
            ),
            mock.patch("apps.scans.tasks.analyze_site_signals", return_value=[]),
            mock.patch("apps.scans.tasks.owasp_mapper.backfill"),
            mock.patch("apps.scans.tasks.settle_scan_actual"),
            mock.patch("apps.scans.tasks.refund_full_for_scan"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    # ------------------------------------------------------------------
    # Step 7：agent 在 Kali fallback 之前執行
    # ------------------------------------------------------------------
    def test_agent_precedes_kali_fallback(self):
        call_order: list[str] = []

        def _track_agent(*args, **kwargs):
            call_order.append("agent")
            return AgentRunResult(
                session_id=0, status="completed", steps=1, total_tokens=10
            )

        def _track_kali(*args, **kwargs):
            call_order.append("kali")
            return []

        with mock.patch(
            "apps.agent.runner.run_agent_for_scan",
            new=mock.AsyncMock(side_effect=_track_agent),
        ), mock.patch(
            "apps.scans.tasks.validate_findings_with_kali", side_effect=_track_kali
        ):
            run_scan_job.run(self.scan_job.id)

        self.assertIn("agent", call_order)
        self.assertIn("kali", call_order)
        self.assertLess(call_order.index("agent"), call_order.index("kali"))

    # ------------------------------------------------------------------
    # Step 7：agent_result.security_findings 送達 calculate_scores
    # ------------------------------------------------------------------
    def test_agent_security_findings_reach_calculate_scores(self):
        security_finding = {
            "category": "security",
            "severity": "critical",
            "title": "SQL Injection (agent-confirmed)",
            "rule_id": "kali-sqlmap-sqli",
            "description": "redacted",
            "remediation": "use prepared statements",
            "evidence": "{}",
            "impact_area": "vulnerability",
            "confidence": 1.0,
        }
        agent_result = AgentRunResult(
            session_id=0,
            status="completed",
            steps=1,
            total_tokens=10,
            security_findings=[security_finding],
        )

        captured: list[dict] = []

        def _capture(findings, tested_categories=None):
            captured.extend(findings)
            return (50, {"security": 0}, [])

        with mock.patch(
            "apps.agent.runner.run_agent_for_scan",
            new=mock.AsyncMock(return_value=agent_result),
        ), mock.patch(
            "apps.scans.tasks.validate_findings_with_kali", return_value=[]
        ), mock.patch(
            "apps.scans.tasks.calculate_scores", side_effect=_capture
        ):
            run_scan_job.run(self.scan_job.id)

        titles = [f.get("title") for f in captured]
        self.assertIn("SQL Injection (agent-confirmed)", titles)

    # ------------------------------------------------------------------
    # 掃描有效性：爬蟲 0 頁（目標不可達/全 timeout）時 seo/aeo 不計入 overall_score
    # ------------------------------------------------------------------
    def test_zero_pages_excludes_seo_aeo_from_tested_categories(self):
        """爬蟲 0 頁時，seo/aeo 只來自 analyze_page（頁面層級），根本沒頁面可分析；
        若仍計入 overall_score 平均，等於把「沒測」誤當「零問題」灌高總分（與上方
        UX 的 tested_categories 把關同理）。setUp 的 crawl_site 預設回 ([], {}, {})。
        """
        captured: dict = {}

        def _capture(findings, tested_categories=None):
            captured["tested"] = set(tested_categories or [])
            return (100, {}, [])

        with mock.patch(
            "apps.agent.runner.run_agent_for_scan",
            new=mock.AsyncMock(
                return_value=AgentRunResult(
                    session_id=0, status="completed", steps=1, total_tokens=10
                )
            ),
        ), mock.patch(
            "apps.scans.tasks.validate_findings_with_kali", return_value=[]
        ), mock.patch(
            "apps.scans.tasks.calculate_scores", side_effect=_capture
        ):
            run_scan_job.run(self.scan_job.id)

        tested = captured["tested"]
        self.assertNotIn("seo", tested, "0 頁時 seo 不該計入 overall（無頁面可分析）")
        self.assertNotIn("aeo", tested, "0 頁時 aeo 不該計入 overall（無頁面可分析）")
        # security/geo 有站台層級檢查（DNS/SSL/site_signals），ux 因 agent completed 納入
        self.assertIn("security", tested)
        self.assertIn("geo", tested)
        self.assertIn("ux", tested)

    def test_with_pages_includes_seo_aeo_in_tested_categories(self):
        """正常掃描（有頁）時 seo/aeo 恢復計入 overall_score，行為與修復前一致。"""
        captured: dict = {}

        def _capture(findings, tested_categories=None):
            captured["tested"] = set(tested_categories or [])
            return (100, {}, [])

        fake_pages = [{
            "url": "https://example.com/",
            "final_url": "https://example.com/",
            "origin": "https://example.com",
            "status_code": 200,
            "title": "Example",
            "html": "<html><body></body></html>",
            "rendered_dom": "",
            "html_only": "",
            "screenshot_path": "",
            "load_time_ms": 100,
            "depth": 0,
            "blocked_reason": "",
            "outgoing_links": [],
            "headers": {},
            "element_boxes": [],
        }]
        with mock.patch(
            "apps.scans.tasks.crawl_site",
            new=mock.AsyncMock(return_value=(fake_pages, {}, {})),
        ), mock.patch(
            "apps.scans.tasks.analyze_page", return_value=[]
        ), mock.patch(
            "apps.agent.runner.run_agent_for_scan",
            new=mock.AsyncMock(
                return_value=AgentRunResult(
                    session_id=0, status="completed", steps=1, total_tokens=10
                )
            ),
        ), mock.patch(
            "apps.scans.tasks.validate_findings_with_kali", return_value=[]
        ), mock.patch(
            "apps.scans.tasks.calculate_scores", side_effect=_capture
        ):
            run_scan_job.run(self.scan_job.id)

        tested = captured["tested"]
        self.assertIn("seo", tested)
        self.assertIn("aeo", tested)

    # ------------------------------------------------------------------
    # UX tested_categories 邊界：agent 第一輪呼叫 provider 就失敗（steps=0）
    # ------------------------------------------------------------------
    def test_agent_zero_steps_excludes_ux_from_tested_categories(self):
        """status="failed" 但 steps=0（例如所有 provider API Key 同時失效，
        第一輪呼叫就結束）代表 UX 根本沒被真正測過；category_scores["ux"] 只是
        恰好維持 100（沒有 UX finding），不該計入 overall_score 平均。
        """
        captured: dict = {}

        def _capture(findings, tested_categories=None):
            captured["tested"] = set(tested_categories or [])
            return (100, {}, [])

        with mock.patch(
            "apps.agent.runner.run_agent_for_scan",
            new=mock.AsyncMock(
                return_value=AgentRunResult(
                    session_id=0,
                    status="failed",
                    steps=0,
                    total_tokens=0,
                    error="provider_error:minimax:401",
                )
            ),
        ), mock.patch(
            "apps.scans.tasks.validate_findings_with_kali", return_value=[]
        ), mock.patch(
            "apps.scans.tasks.calculate_scores", side_effect=_capture
        ):
            run_scan_job.run(self.scan_job.id)

        self.assertNotIn(
            "ux", captured["tested"], "steps=0 代表沒有實際測過，不應計入 overall"
        )

    # ------------------------------------------------------------------
    # UX tested_categories 邊界：agent 中途因 max_steps/token 預算中止但已測過
    # ------------------------------------------------------------------
    def test_agent_failed_with_steps_still_counts_ux_as_tested(self):
        """status="failed" 但 steps>0（例如 max_steps_reached，過程中已真正執行過
        且可能發現真實問題）仍算「有測」，不應被排除在 overall_score 平均之外，
        否則已知的真實 UX 問題會被隱藏在總分之外（矯枉過正）。
        """
        captured: dict = {}

        def _capture(findings, tested_categories=None):
            captured["tested"] = set(tested_categories or [])
            return (100, {}, [])

        with mock.patch(
            "apps.agent.runner.run_agent_for_scan",
            new=mock.AsyncMock(
                return_value=AgentRunResult(
                    session_id=0,
                    status="failed",
                    steps=20,
                    total_tokens=5000,
                    error="max_steps_reached(20)",
                )
            ),
        ), mock.patch(
            "apps.scans.tasks.validate_findings_with_kali", return_value=[]
        ), mock.patch(
            "apps.scans.tasks.calculate_scores", side_effect=_capture
        ):
            run_scan_job.run(self.scan_job.id)

        self.assertIn(
            "ux", captured["tested"], "steps>0 代表確實測過，即使未乾淨完成也應計入"
        )

    # ------------------------------------------------------------------
    # 沿用 test_fallback_runs_when_agent_fails：外層例外（status="error"）
    # 本就不應計入，這裡明確斷言 tested_categories 沒有 ux
    # ------------------------------------------------------------------
    def test_agent_outer_exception_excludes_ux_from_tested_categories(self):
        captured: dict = {}

        def _capture(findings, tested_categories=None):
            captured["tested"] = set(tested_categories or [])
            return (100, {}, [])

        with mock.patch(
            "apps.agent.runner.run_agent_for_scan",
            new=mock.AsyncMock(side_effect=RuntimeError("agent crash")),
        ), mock.patch(
            "apps.scans.tasks.validate_findings_with_kali", return_value=[]
        ), mock.patch(
            "apps.scans.tasks.calculate_scores", side_effect=_capture
        ):
            run_scan_job.run(self.scan_job.id)

        self.assertNotIn("ux", captured["tested"])

    # ------------------------------------------------------------------
    # Step 7：fallback 在 Agent 停用時仍執行
    # ------------------------------------------------------------------
    @override_settings(ARGUS_AGENT_ENABLED=False)
    def test_fallback_runs_when_agent_disabled(self):
        with mock.patch(
            "apps.agent.runner.run_agent_for_scan"
        ) as agent_mock, mock.patch(
            "apps.scans.tasks.validate_findings_with_kali", return_value=[]
        ) as kali_mock:
            run_scan_job.run(self.scan_job.id)

        agent_mock.assert_not_called()
        kali_mock.assert_called_once()

    # ------------------------------------------------------------------
    # Step 7：fallback 在 Agent 失敗時仍執行
    # ------------------------------------------------------------------
    def test_fallback_runs_when_agent_fails(self):
        with mock.patch(
            "apps.agent.runner.run_agent_for_scan",
            new=mock.AsyncMock(side_effect=RuntimeError("agent crash")),
        ), mock.patch(
            "apps.scans.tasks.validate_findings_with_kali", return_value=[]
        ) as kali_mock:
            run_scan_job.run(self.scan_job.id)

        kali_mock.assert_called_once()
        self.scan_job.refresh_from_db()
        self.assertEqual(self.scan_job.status, ScanJob.Status.COMPLETED)

    # ------------------------------------------------------------------
    # Step 7：ScanCancelled 傳遞到 cancelled/refund 分支
    # ------------------------------------------------------------------
    def test_scan_cancelled_during_fallback_reaches_refund(self):
        with mock.patch(
            "apps.agent.runner.run_agent_for_scan",
            new=mock.AsyncMock(return_value=None),
        ), mock.patch(
            "apps.scans.tasks.validate_findings_with_kali",
            side_effect=ScanCancelled(),
        ), mock.patch(
            "apps.scans.tasks.refund_full_for_scan"
        ) as refund_mock:
            result = run_scan_job.run(self.scan_job.id)

        self.assertEqual(result, {"status": "cancelled"})
        refund_mock.assert_called_once()
        self.scan_job.refresh_from_db()
        self.assertEqual(self.scan_job.status, ScanJob.Status.CANCELLED)
