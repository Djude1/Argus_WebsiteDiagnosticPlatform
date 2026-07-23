"""security/kali_tools.py 的單元測試。

策略：mock subprocess、reserve_sqlmap_targets 與 _container_running，不實際呼叫
docker 或 Redis；重點驗證新增的加法式安全契約——DockerSqlmapExecutor 不外露 raw
stdout、run_sqlmap/run_sqlmap_batch 經 reserve_sqlmap_targets 預算後派發、
validate_findings_with_kali 僅信任 confirmed 並遮罩 query value、metasploit 在
kubernetes backend 上不得啟動。
"""
import json
import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.scans.cancellation import ScanCancelled
from apps.scans.models import ScanJob
from apps.scans.security import kali_tools, owasp_mapper
from apps.scans.security.kali_contracts import (
    KaliResult,
    ReservationOutcome,
    ReservedSqlmapTarget,
    SqlmapExecution,
)


def _make_scan(scan_mode="active", authorized=True):
    user = get_user_model().objects.create_user(
        username=f"user_{uuid.uuid4().hex[:8]}",
        password="testpass123",
    )
    return ScanJob.objects.create(
        user=user,
        original_url="https://target.local/",
        normalized_url="https://target.local/",
        origin="https://target.local",
        scan_mode=scan_mode,
        active_testing_authorized=authorized,
    )


def _admitted_outcome(*urls):
    """模擬 reserve_sqlmap_targets 成功保留每個 URL 的 outcome。"""
    targets = tuple(
        ReservedSqlmapTarget(index=i, url=url, fingerprint=f"fp-{i}")
        for i, url in enumerate(urls)
    )
    return ReservationOutcome(targets=targets)


_VULN_RAW = (
    "Parameter: id (GET)\n"
    "    Type: boolean-based blind\n"
    "Parameter 'id' is vulnerable\n"
    "back-end DBMS: MySQL"
)


# ---------------------------------------------------------------------------
# _docker_exec 仍負責把 egress proxy 環境變數傳入 kali container
# ---------------------------------------------------------------------------
class TestDockerExecProxy(TestCase):
    @override_settings(
        ARGUS_EGRESS_PROXY_URL="http://egress-proxy:3128",
        ARGUS_KALI_CONTAINER="argus-kali-1",
    )
    @mock.patch.dict("os.environ", {"NO_PROXY": "localhost,db,redis"}, clear=False)
    @mock.patch("apps.scans.security.kali_tools.subprocess.run")
    def test_proxy_environment_is_forwarded_into_kali_container(self, run_mock):
        run_mock.return_value = mock.Mock(returncode=0, stdout="", stderr="")

        kali_tools._docker_exec(["sqlmap", "--version"], 10)

        command = run_mock.call_args.args[0]
        self.assertEqual(command[:2], ["docker", "exec"])
        self.assertIn("HTTP_PROXY=http://egress-proxy:3128", command)
        self.assertIn("HTTPS_PROXY=http://egress-proxy:3128", command)
        self.assertIn("NO_PROXY=localhost,db,redis", command)
        self.assertIn("http_proxy=http://egress-proxy:3128", command)
        self.assertIn("https_proxy=http://egress-proxy:3128", command)
        self.assertIn("no_proxy=localhost,db,redis", command)
        self.assertEqual(command[-3:], ["argus-kali-1", "sqlmap", "--version"])


# ---------------------------------------------------------------------------
# DockerSqlmapExecutor：raw stdout 只在 process 內解析，輸出固定為安全 summary
# ---------------------------------------------------------------------------
@override_settings(ARGUS_KALI_BACKEND="docker", ARGUS_KALI_CONTAINER="argus-kali-1")
class TestDockerSqlmapExecutor(TestCase):
    def test_returns_safe_summary_without_raw_stdout(self):
        target = ReservedSqlmapTarget(0, "https://t.local/?id=1", "fp")
        with mock.patch.object(
            kali_tools, "_docker_exec", return_value=(0, _VULN_RAW, "")
        ):
            results = kali_tools.DockerSqlmapExecutor().execute(1, [target])

        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertIsInstance(result, KaliResult)
        self.assertTrue(result.confirmed)
        self.assertEqual(result.stdout, "")
        summary = result.evidence_summary
        self.assertEqual(summary["parameter"], "id")
        self.assertEqual(summary["techniques"], ["boolean-based blind"])
        self.assertEqual(summary["dbms"], "MySQL")
        # 結果不可帶 raw 輸出字串
        dumped = json.dumps(result.as_dict())
        self.assertNotIn("vulnerable", dumped)
        self.assertNotIn("raw", dumped)

    def test_target_failure_does_not_abort_batch(self):
        targets = [
            ReservedSqlmapTarget(0, "https://t.local/?id=1", "fp0"),
            ReservedSqlmapTarget(1, "https://t.local/?p=2", "fp1"),
        ]
        side_effects = [
            (None, "", "timeout"),          # 第一個目標失敗
            (0, _VULN_RAW, ""),             # 第二個目標仍執行並確認
        ]
        with mock.patch.object(kali_tools, "_docker_exec", side_effect=side_effects):
            results = kali_tools.DockerSqlmapExecutor().execute(1, targets)

        self.assertEqual(len(results), 2)
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "timeout")
        self.assertTrue(results[1].confirmed)

    def test_clean_stdout_produces_unconfirmed_result(self):
        target = ReservedSqlmapTarget(0, "https://t.local/?id=1", "fp")
        clean = "all tested parameters do not appear to be injectable"
        with mock.patch.object(kali_tools, "_docker_exec", return_value=(0, clean, "")):
            results = kali_tools.DockerSqlmapExecutor().execute(1, [target])

        result = results[0]
        self.assertFalse(result.confirmed)
        self.assertEqual(result.evidence_summary["parameter"], "")
        self.assertEqual(result.stdout, "")


# ---------------------------------------------------------------------------
# run_sqlmap：reserve max_count=1，經 executor 派發，輸出 dict 形狀與 agent 相容
# ---------------------------------------------------------------------------
@override_settings(ARGUS_KALI_ENABLED=True, ARGUS_KALI_BACKEND="docker")
class TestRunSqlmap(TestCase):
    def setUp(self):
        self.scan = _make_scan()

    def test_reserves_single_target_then_dispatches_via_executor(self):
        with mock.patch.object(
            kali_tools, "reserve_sqlmap_targets",
            return_value=_admitted_outcome("https://target.local/?id=1"),
        ) as reserve, mock.patch.object(
            kali_tools, "_docker_exec", return_value=(0, _VULN_RAW, ""),
        ):
            result = kali_tools.run_sqlmap(
                "https://target.local/?id=1", self.scan.id,
            )

        # brief：run_sqlmap 一律保留 max_count=1
        self.assertEqual(reserve.call_args.kwargs["max_count"], 1)
        self.assertTrue(result["confirmed"])
        self.assertEqual(result["stdout"], "")
        self.assertEqual(result["evidence_summary"]["parameter"], "id")
        # 與 agent/tools.py 的契約：dict 須含 ok / blocked_reason / stdout / error
        for key in ("ok", "tool", "blocked_reason", "returncode",
                    "stdout", "error", "confirmed", "evidence_summary"):
            self.assertIn(key, result)
        # 安全：不可外露 raw
        self.assertNotIn("raw", json.dumps(result))
        self.assertNotIn("vulnerable", json.dumps(result))

    def test_blocked_reservation_propagates_reason(self):
        with mock.patch.object(
            kali_tools, "reserve_sqlmap_targets",
            return_value=ReservationOutcome(blocked_reason="kali_disabled"),
        ) as reserve, mock.patch.object(kali_tools, "_docker_exec") as exec_mock:
            result = kali_tools.run_sqlmap(
                "https://target.local/?id=1", self.scan.id,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["blocked_reason"], "kali_disabled")
        self.assertEqual(result["stdout"], "")
        exec_mock.assert_not_called()
        self.assertEqual(reserve.call_args.kwargs["max_count"], 1)

    def test_no_admitted_target_returns_blocked(self):
        with mock.patch.object(
            kali_tools, "reserve_sqlmap_targets",
            return_value=ReservationOutcome(blocked_reason="target_already_tested"),
        ), mock.patch.object(kali_tools, "_docker_exec") as exec_mock:
            result = kali_tools.run_sqlmap(
                "https://target.local/?id=1", self.scan.id,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["blocked_reason"], "target_already_tested")
        exec_mock.assert_not_called()

    # ---- Finding 2 audit log：facade blocked branch 必須寫安全 audit log ----

    def _assert_safe_audit(self, log_mock, expected_reason: str) -> None:
        """log 必須被呼叫恰好一次，且文案只含 structured reason，不帶 URL/query value。"""
        log_mock.assert_called_once()
        # args: (scan_job_id, message, ...); 只把 message 與 kwargs 文字化檢查
        rendered = " ".join(str(arg) for arg in log_mock.call_args.args[1:])
        rendered += " " + " ".join(f"{k}={v}" for k, v in log_mock.call_args.kwargs.items())
        self.assertIn(expected_reason, rendered)
        # 安全：不可外露目標 URL 或 query value
        self.assertNotIn("secret-value", rendered)
        self.assertNotIn("target.local", rendered)

    def test_blocked_reservation_writes_safe_audit_log(self):
        """Kali 全域關閉時，run_sqlmap 必須把決策寫進 scan_log，留下 audit trail。"""
        with mock.patch.object(
            kali_tools, "reserve_sqlmap_targets",
            return_value=ReservationOutcome(blocked_reason="kali_disabled"),
        ), mock.patch.object(kali_tools, "append_log") as log_mock:
            result = kali_tools.run_sqlmap(
                "https://target.local/?id=secret-value", self.scan.id,
            )

        self.assertEqual(result["blocked_reason"], "kali_disabled")
        self._assert_safe_audit(log_mock, "kali_disabled")

    def test_backend_misconfigured_writes_safe_audit_log(self):
        """reserve 通過但 backend 未知時，也必須留下 audit log（level=warn）。"""
        with mock.patch.object(
            kali_tools, "reserve_sqlmap_targets",
            return_value=_admitted_outcome("https://target.local/?id=secret-value"),
        ), mock.patch.object(
            kali_tools, "_executor_for_backend", return_value=None,
        ), mock.patch.object(kali_tools, "append_log") as log_mock:
            result = kali_tools.run_sqlmap(
                "https://target.local/?id=secret-value", self.scan.id,
            )

        self.assertEqual(result["blocked_reason"], "backend_misconfigured")
        self._assert_safe_audit(log_mock, "backend_misconfigured")
        self.assertEqual(log_mock.call_args.kwargs.get("level"), "warn")


# ---------------------------------------------------------------------------
# run_sqlmap_batch：預算編排與 runner_failed fallback
# ---------------------------------------------------------------------------
@override_settings(ARGUS_KALI_ENABLED=True, ARGUS_KALI_BACKEND="docker")
class TestRunSqlmapBatch(TestCase):
    def setUp(self):
        self.scan = _make_scan()

    def _mock_reserve(self, urls):
        return mock.patch.object(
            kali_tools, "reserve_sqlmap_targets",
            return_value=_admitted_outcome(*urls),
        )

    def test_budget_is_min_of_max_targets_and_three(self):
        urls = [f"https://t.local/?id={i}" for i in range(10)]
        with self._mock_reserve(urls) as reserve, mock.patch.object(
            kali_tools, "_docker_exec", return_value=(0, "", ""),
        ):
            kali_tools.run_sqlmap_batch(self.scan.id, urls, max_targets=5)

        # brief：max_count = min(max_targets, 3)
        self.assertEqual(reserve.call_args.kwargs["max_count"], 3)

    def test_executes_each_admitted_target_once(self):
        urls = ["https://t.local/?id=1", "https://t.local/?p=2"]
        with self._mock_reserve(urls), mock.patch.object(
            kali_tools, "_docker_exec", return_value=(0, "", ""),
        ) as exec_mock:
            batch = kali_tools.run_sqlmap_batch(self.scan.id, urls, max_targets=3)

        self.assertEqual(exec_mock.call_count, 2)
        self.assertEqual(batch["blocked_reason"], "")
        self.assertEqual(len(batch["executions"]), 2)
        for execution in batch["executions"]:
            self.assertIsInstance(execution, SqlmapExecution)
            self.assertIsInstance(execution.target, ReservedSqlmapTarget)
            self.assertIsInstance(execution.result, KaliResult)

    def test_count_mismatch_returns_runner_failed_for_every_admitted_target(self):
        urls = ["https://t.local/?id=1", "https://t.local/?p=2"]
        # Executor 故意只回 1 個結果 → 與 2 個 target 數不符
        bad_executor = mock.Mock()
        bad_executor.execute.return_value = (KaliResult(ok=True, confirmed=True),)
        with self._mock_reserve(urls), mock.patch.object(
            kali_tools, "_executor_for_backend", return_value=bad_executor,
        ):
            batch = kali_tools.run_sqlmap_batch(self.scan.id, urls, max_targets=3)

        self.assertEqual(len(batch["executions"]), 2)
        for execution in batch["executions"]:
            self.assertFalse(execution.result.ok)
            self.assertEqual(execution.result.error, "runner_failed")

    def test_blocked_reservation_short_circuits_batch(self):
        with mock.patch.object(
            kali_tools, "reserve_sqlmap_targets",
            return_value=ReservationOutcome(blocked_reason="scan_mode_not_active"),
        ), mock.patch.object(kali_tools, "_docker_exec") as exec_mock:
            batch = kali_tools.run_sqlmap_batch(
                self.scan.id, ["https://t.local/?id=1"], max_targets=3,
            )

        self.assertEqual(batch["blocked_reason"], "scan_mode_not_active")
        self.assertEqual(batch["executions"], ())
        exec_mock.assert_not_called()

    # ---- Finding 2 audit log：batch facade blocked branch 必須寫安全 audit log ----

    def _assert_safe_audit(self, log_mock, expected_reason: str) -> None:
        log_mock.assert_called_once()
        rendered = " ".join(str(arg) for arg in log_mock.call_args.args[1:])
        rendered += " " + " ".join(f"{k}={v}" for k, v in log_mock.call_args.kwargs.items())
        self.assertIn(expected_reason, rendered)
        self.assertNotIn("secret-value", rendered)
        self.assertNotIn("t.local", rendered)

    def test_batch_blocked_reservation_writes_safe_audit_log(self):
        """batch 在授權鎖被擋下時也必須寫 audit log（policy 本身不寫）。"""
        with mock.patch.object(
            kali_tools, "reserve_sqlmap_targets",
            return_value=ReservationOutcome(blocked_reason="active_testing_unauthorized"),
        ), mock.patch.object(kali_tools, "append_log") as log_mock:
            batch = kali_tools.run_sqlmap_batch(
                self.scan.id, ["https://t.local/?id=secret-value"], max_targets=3,
            )

        self.assertEqual(batch["blocked_reason"], "active_testing_unauthorized")
        self.assertEqual(batch["executions"], ())
        self._assert_safe_audit(log_mock, "active_testing_unauthorized")

    def test_batch_backend_misconfigured_writes_safe_audit_log(self):
        """batch 在 backend 未知時必須寫 warn-level audit log，不留無聲失敗。"""
        with mock.patch.object(
            kali_tools, "reserve_sqlmap_targets",
            return_value=_admitted_outcome("https://t.local/?id=secret-value"),
        ), mock.patch.object(
            kali_tools, "_executor_for_backend", return_value=None,
        ), mock.patch.object(kali_tools, "append_log") as log_mock:
            batch = kali_tools.run_sqlmap_batch(
                self.scan.id, ["https://t.local/?id=secret-value"], max_targets=3,
            )

        self.assertEqual(batch["blocked_reason"], "backend_misconfigured")
        self.assertEqual(batch["executions"], ())
        self._assert_safe_audit(log_mock, "backend_misconfigured")
        self.assertEqual(log_mock.call_args.kwargs.get("level"), "warn")


# ---------------------------------------------------------------------------
# run_metasploit：僅 docker backend 支援；kubernetes / 未知 backend 一律擋下
# ---------------------------------------------------------------------------
@override_settings(ARGUS_KALI_ENABLED=True, ARGUS_KALI_CONTAINER="argus-kali-1")
class TestRunMetasploitBackendGate(TestCase):
    def setUp(self):
        self.scan = _make_scan()

    @override_settings(ARGUS_KALI_BACKEND="kubernetes")
    def test_metasploit_is_not_started_on_kubernetes(self):
        with mock.patch.object(kali_tools, "_docker_exec") as exec_mock:
            result = kali_tools.run_metasploit(
                "exploit/example", {}, self.scan.id,
            )

        self.assertEqual(result["blocked_reason"], "tool_not_supported_by_backend")
        exec_mock.assert_not_called()

    @override_settings(ARGUS_KALI_BACKEND="disabled")
    def test_metasploit_is_not_started_on_unknown_backend(self):
        with mock.patch.object(kali_tools, "_docker_exec") as exec_mock:
            result = kali_tools.run_metasploit(
                "exploit/example", {}, self.scan.id,
            )

        self.assertEqual(result["blocked_reason"], "tool_not_supported_by_backend")
        exec_mock.assert_not_called()

    @override_settings(ARGUS_KALI_BACKEND="docker")
    def test_metasploit_runs_on_docker_backend_with_authorization(self):
        with mock.patch.object(kali_tools, "_container_running", return_value=True), \
                mock.patch.object(
                    kali_tools, "_docker_exec", return_value=(0, "session opened", ""),
                ) as m:
            result = kali_tools.run_metasploit(
                "exploit/multi/misc/log4shell",
                {"RHOSTS": "10.0.0.5", "LHOST": "10.0.0.1"},
                self.scan.id,
            )

        self.assertTrue(result["ok"])
        called_args = m.call_args[0][0]
        resource = called_args[-1]
        self.assertIn("use exploit/multi/misc/log4shell", resource)
        self.assertIn("set RHOSTS 10.0.0.5", resource)
        self.assertIn("run; exit", resource)

    @override_settings(ARGUS_KALI_BACKEND="docker")
    def test_invalid_module_rejected_on_docker_backend(self):
        with mock.patch.object(kali_tools, "_container_running", return_value=True), \
                mock.patch.object(kali_tools, "_docker_exec") as m:
            result = kali_tools.run_metasploit(
                "evil; rm -rf /", {}, self.scan.id,
            )

        self.assertEqual(result["error"], "invalid_module")
        m.assert_not_called()

    @override_settings(ARGUS_KALI_BACKEND="docker")
    def test_injection_in_option_rejected_on_docker_backend(self):
        with mock.patch.object(kali_tools, "_container_running", return_value=True), \
                mock.patch.object(kali_tools, "_docker_exec") as m:
            result = kali_tools.run_metasploit(
                "exploit/multi/misc/log4shell",
                {"RHOSTS": "1.2.3.4; cat /etc/passwd"},
                self.scan.id,
            )

        self.assertEqual(result["error"], "invalid_option")
        m.assert_not_called()


# ---------------------------------------------------------------------------
# validate_findings_with_kali：batch 編排 + query value 遮罩 + ScanCancelled 重拋
# ---------------------------------------------------------------------------
@override_settings(ARGUS_KALI_ENABLED=True, ARGUS_KALI_BACKEND="docker")
class TestValidateFindingsWithKali(TestCase):
    def setUp(self):
        self.scan = _make_scan()

    def _batch_with(self, execution):
        return mock.patch.object(
            kali_tools, "run_sqlmap_batch",
            return_value={"blocked_reason": "", "executions": (execution,)},
        )

    # ---- Finding 1 regression：fallback 候選必須先挑具 query 的 URL ----

    def test_filters_to_query_candidates_before_batch(self):
        """入口頁（無 query）排第一筆時，必須被挑掉，讓後面的帶 query URL 仍能進 batch。

        對應 review finding 1：current code 把完整 crawl-order list 原樣交給 batch，
        policy 截到第一筆無 query 即整批回 no_query_parameter，後續合法 URL 永遠不會跑。
        """
        candidate_urls = [
            "https://t.local/",          # 入口頁，無 query
            "https://t.local/about",     # mid-page，無 query
            "https://t.local/?id=1",     # 帶 query，應被採用
            "https://t.local/?p=2",      # 帶 query，應被採用
        ]
        with mock.patch.object(
            kali_tools, "run_sqlmap_batch",
            return_value={"blocked_reason": "", "executions": ()},
        ) as batch_mock:
            kali_tools.validate_findings_with_kali(
                self.scan.id, candidate_urls, max_targets=3,
            )

        # batch 必須只收到帶 query 的候選；不該把無 query URL 帶進 policy
        actual_urls = batch_mock.call_args.args[1]
        self.assertEqual(
            actual_urls, ["https://t.local/?id=1", "https://t.local/?p=2"],
        )

    def test_no_query_candidates_does_not_call_batch(self):
        """全部候選都沒有 query parameter → 不該呼叫 batch，安全地回 []。"""
        candidate_urls = ["https://t.local/", "https://t.local/about"]
        with mock.patch.object(
            kali_tools, "run_sqlmap_batch",
            return_value={"blocked_reason": "", "executions": ()},
        ) as batch_mock:
            findings = kali_tools.validate_findings_with_kali(
                self.scan.id, candidate_urls, max_targets=3,
            )

        self.assertEqual(findings, [])
        batch_mock.assert_not_called()

    def test_calls_batch_once_and_trusts_confirmed_flag(self):
        confirmed = KaliResult(
            ok=True, confirmed=True,
            evidence_summary={"parameter": "id", "techniques": [], "dbms": ""},
        )
        execution = SqlmapExecution(
            target=ReservedSqlmapTarget(0, "https://t.local/?id=secret", "fp"),
            result=confirmed,
        )
        with self._batch_with(execution) as batch_mock:
            findings = kali_tools.validate_findings_with_kali(
                self.scan.id, ["https://t.local/?id=secret"], max_targets=3,
            )

        self.assertEqual(batch_mock.call_count, 1)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "critical")
        self.assertEqual(findings[0]["rule_id"], "kali-sqlmap-sqli")
        self.assertEqual(findings[0]["category"], "security")

    def test_redacts_query_values_in_description(self):
        confirmed = KaliResult(
            ok=True, confirmed=True,
            evidence_summary={"parameter": "id", "techniques": [], "dbms": ""},
        )
        execution = SqlmapExecution(
            target=ReservedSqlmapTarget(
                0, "https://t.local/?id=secret-token&ref=x", "fp",
            ),
            result=confirmed,
        )
        with self._batch_with(execution):
            findings = kali_tools.validate_findings_with_kali(
                self.scan.id,
                ["https://t.local/?id=secret-token&ref=x"],
                max_targets=3,
            )

        description = findings[0]["description"]
        self.assertNotIn("secret-token", description)
        # query key 仍保留，方便排查；只遮罩 value
        self.assertIn("id", description)

    def test_serializes_only_evidence_summary_into_finding(self):
        confirmed = KaliResult(
            ok=True, confirmed=True,
            stdout="raw should not leak",
            evidence_summary={
                "parameter": "id",
                "techniques": ["boolean-based blind"],
                "dbms": "MySQL",
                "sqlmap_version": "1.10",
            },
        )
        execution = SqlmapExecution(
            target=ReservedSqlmapTarget(0, "https://t.local/?id=1", "fp"),
            result=confirmed,
        )
        with self._batch_with(execution):
            findings = kali_tools.validate_findings_with_kali(
                self.scan.id, ["https://t.local/?id=1"], max_targets=3,
            )

        dumped = json.dumps(findings[0])
        # raw stdout 不可外洩到 Finding
        self.assertNotIn("raw should not leak", dumped)
        # evidence_json 只放 evidence_summary
        evidence_json = findings[0].get("evidence_json", {})
        self.assertIn("evidence_summary", evidence_json)
        summary = evidence_json["evidence_summary"]
        self.assertEqual(summary["parameter"], "id")
        self.assertEqual(summary["techniques"], ["boolean-based blind"])
        self.assertEqual(summary["dbms"], "MySQL")

    def test_scan_cancelled_is_reraised_before_silent_fail(self):
        with mock.patch.object(
            kali_tools, "run_sqlmap_batch", side_effect=ScanCancelled(),
        ):
            with self.assertRaises(ScanCancelled):
                kali_tools.validate_findings_with_kali(
                    self.scan.id, ["https://t.local/?id=1"], max_targets=3,
                )

    def test_unconfirmed_results_produce_no_finding(self):
        clean = KaliResult(ok=True, confirmed=False)
        execution = SqlmapExecution(
            target=ReservedSqlmapTarget(0, "https://t.local/?id=1", "fp"),
            result=clean,
        )
        with self._batch_with(execution):
            findings = kali_tools.validate_findings_with_kali(
                self.scan.id, ["https://t.local/?id=1"], max_targets=3,
            )

        self.assertEqual(findings, [])

    def test_other_exceptions_stay_silent_fail(self):
        with mock.patch.object(
            kali_tools, "run_sqlmap_batch", side_effect=RuntimeError("boom"),
        ):
            findings = kali_tools.validate_findings_with_kali(
                self.scan.id, ["https://t.local/?id=1"], max_targets=3,
            )

        self.assertEqual(findings, [])


# ---------------------------------------------------------------------------
# OWASP 對映（不變）
# ---------------------------------------------------------------------------
class TestKaliOwaspMapping(TestCase):
    def test_sqlmap_finding_maps_to_a03(self):
        self.assertEqual(owasp_mapper._lookup("kali-sqlmap-sqli"), ("A03", "CWE-89"))
