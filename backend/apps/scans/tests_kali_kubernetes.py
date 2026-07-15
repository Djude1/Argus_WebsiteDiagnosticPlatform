"""security/kali_kubernetes.py 的單元測試。

策略：完全注入 batch_api / core_api / redis_client / watch_factory / cancel_check /
monotonic，不呼叫任何外部 DNS、Redis 或 Kubernetes cluster。重點驗證 brief 指定的
lifecycle 與取消安全性——Job 先於 Secret 建立、global lock 單一 owner token、bounded
watch、cleanup 一律執行、append_log 只記 correlation_id/phase/safe code。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone
from kubernetes.client import ApiException

from apps.scans.cancellation import ScanCancelled
from apps.scans.security import kali_kubernetes
from apps.scans.security.kali_contracts import ReservedSqlmapTarget
from apps.scans.security.kali_kubernetes import KubernetesSqlmapExecutor

SECRET_KEY_VALUE = "test-secret-key-for-hmac"

# Task 4 Fix 3A：executor outward error 固定 allowlist（與 production _OUTWARD_ERROR_CODES 對齊）
OUTWARD_ERROR_ALLOWLIST = frozenset({
    "capacity_timeout",
    "job_create_failed",
    "secret_create_failed",
    "job_deadline_exceeded",
    "runner_failed",
    "invalid_result",
    "cleanup_failed",
})


class FakeClock:
    """可手動推進的 monotonic 替身；測試不依賴真實時間。"""

    def __init__(self, start: int = 1_000_000) -> None:
        self.t = start

    def __call__(self) -> int:
        return self.t


def _valid_result(index: int = 0) -> dict:
    return {
        "index": index,
        "ok": True,
        "confirmed": False,
        "returncode": 0,
        "parameter": "",
        "techniques": [],
        "dbms": "",
        "error_code": "clean",
    }


def _valid_payload(count: int = 1) -> bytes:
    document = {
        "schema_version": 1,
        "tool": "sqlmap",
        "results": [_valid_result(i) for i in range(count)],
    }
    return json.dumps(document, separators=(",", ":")).encode()


def _result_payload(
    *, ok: bool = True, confirmed: bool = False, error_code: str = "clean",
) -> bytes:
    """產生單一 target 的合法 runner payload，供 Fix 4A 一致性測試客製 ok/confirmed/error_code。

    所有欄位皆符合 kali_contracts.parse_runner_result 的契約，確保 payload 能通過契約驗證、
    進入 executor outward 邊界的一致性檢查，而非在 parse 階段就被擋下。
    """
    document = {
        "schema_version": 1,
        "tool": "sqlmap",
        "results": [{
            "index": 0,
            "ok": ok,
            "confirmed": confirmed,
            "returncode": 0,
            "parameter": "",
            "techniques": [],
            "dbms": "",
            "error_code": error_code,
        }],
    }
    return json.dumps(document, separators=(",", ":")).encode()


@override_settings(
    SECRET_KEY=SECRET_KEY_VALUE,
    ARGUS_KALI_TIMEOUT=120,
    ARGUS_KALI_NAMESPACE="argus-kali",
    ARGUS_KALI_RUNNER_IMAGE="argus/kali-runner:test",
    ARGUS_KALI_LOCK_WAIT_SECONDS=420,
    ARGUS_KALI_LOCK_LEASE_SECONDS=450,
    ARGUS_KALI_SQLMAP_VERSION="1.10",
)
class KubernetesSqlmapExecutorTests(TestCase):
    def setUp(self) -> None:
        self.calls: list[str] = []
        self.target = ReservedSqlmapTarget(
            0, "https://target.example/?id=secret-value", "fp-0",
        )

        self.batch = mock.Mock()
        self.core = mock.Mock()
        self.redis = mock.Mock()
        self.cancel_check = mock.Mock(return_value=None)
        self.clock = FakeClock()

        # 預設 happy-path 回值
        self.redis.set.return_value = True  # global lock 首次即取到
        self.redis.eval.return_value = 1   # renew / release 比對成功

        job_resp = mock.Mock()
        job_resp.metadata.uid = "job-uid-123"
        self.batch.create_namespaced_job.side_effect = (
            lambda *a, **k: (self.calls.append("create_job") or job_resp)
        )
        self.core.create_namespaced_secret.side_effect = (
            lambda *a, **k: (self.calls.append("create_secret") or mock.Mock())
        )
        self.batch.delete_namespaced_job.side_effect = (
            lambda *a, **k: (self.calls.append("delete_job") or None)
        )
        self.core.delete_namespaced_secret.side_effect = (
            lambda *a, **k: (self.calls.append("delete_secret") or None)
        )

        # stale cleanup 預設查無舊 Job
        self.batch.list_namespaced_job.return_value = mock.Mock(items=[])

        # watch：預設回 Succeeded Job
        self.watcher = mock.Mock()
        self.watcher.stream.return_value = [{"object": self._succeeded_job()}]
        self.watch_factory = mock.Mock(return_value=self.watcher)

        # Pod log 預設為合法 payload
        self.core.read_namespaced_pod_log.return_value = _valid_payload(1)
        pod = mock.Mock()
        pod.metadata.name = "runner-pod"
        self.core.list_namespaced_pod.return_value = mock.Mock(items=[pod])

    def make_executor(self) -> KubernetesSqlmapExecutor:
        return KubernetesSqlmapExecutor(
            batch_api=self.batch,
            core_api=self.core,
            redis_client=self.redis,
            watch_factory=self.watch_factory,
            cancel_check=self.cancel_check,
            monotonic=self.clock,
        )

    # -- 測試替身工廠 -----------------------------------------------------
    def _succeeded_job(self) -> mock.Mock:
        job = mock.Mock()
        job.status.conditions = [mock.Mock(type="Complete", status="True")]
        return job

    def _failed_job(self) -> mock.Mock:
        job = mock.Mock()
        job.status.conditions = [mock.Mock(type="Failed", status="True")]
        return job

    def _deadline_exceeded_job(self) -> mock.Mock:
        job = mock.Mock()
        cond = mock.Mock(type="Failed", status="True")
        cond.reason = "DeadlineExceeded"
        job.status.conditions = [cond]
        return job

    def _correlation_id(self, scan_job_id: int = 17) -> str:
        hmac_part = hmac.new(
            SECRET_KEY_VALUE.encode(),
            f"kali:{scan_job_id}".encode(),
            hashlib.sha256,
        ).hexdigest()[:10]
        token_part = secrets.token_hex(6)
        return f"{hmac_part}-{token_part}"

    # ------------------------------------------------------------------
    # Task 4 Fix 1 契約測試
    # ------------------------------------------------------------------
    def test_runner_pod_matches_admission_contract(self):
        corr_id = "1a2b3c4d5e-6f7a8b9c0d1e"
        with mock.patch.object(
            kali_kubernetes.KubernetesSqlmapExecutor,
            "_correlation_id",
            return_value=corr_id,
        ):
            self.make_executor().execute(17, [self.target])
            job = self.batch.create_namespaced_job.call_args.args[1]
            pod_spec = job.spec.template.spec

            # Service account
            self.assertEqual(pod_spec.service_account_name, "kali-runner")
            self.assertFalse(pod_spec.automount_service_account_token)

            # Pod security context
            pod_ctx = pod_spec.security_context
            self.assertTrue(pod_ctx.run_as_non_root)
            self.assertEqual(pod_ctx.run_as_user, 65532)
            self.assertEqual(pod_ctx.run_as_group, 65532)
            self.assertEqual(pod_ctx.fs_group, 65532)
            self.assertEqual(pod_ctx.seccomp_profile.type, "RuntimeDefault")

            # Container
            self.assertEqual(len(pod_spec.containers), 1)
            container = pod_spec.containers[0]
            self.assertEqual(container.command, ["/usr/local/bin/python"])
            self.assertEqual(container.args, ["/opt/argus/runner.py"])

            # Container security
            ctx = container.security_context
            self.assertFalse(ctx.privileged)
            self.assertFalse(ctx.allow_privilege_escalation)
            self.assertTrue(ctx.read_only_root_filesystem)
            self.assertTrue(ctx.run_as_non_root)
            self.assertEqual(ctx.run_as_user, 65532)
            self.assertEqual(ctx.run_as_group, 65532)
            self.assertIn("ALL", ctx.capabilities.drop)

            # Volumes
            self.assertEqual(len(pod_spec.volumes), 2)
            targets_vol = next(v for v in pod_spec.volumes if v.name == "targets")
            self.assertEqual(targets_vol.secret.secret_name, f"argus-targets-{corr_id}")
            self.assertEqual(targets_vol.secret.default_mode, 256)  # 0o400

            scratch_vol = next(v for v in pod_spec.volumes if v.name == "scratch")
            self.assertEqual(scratch_vol.empty_dir.size_limit, "1Gi")

            # Mounts
            self.assertEqual(len(container.volume_mounts), 2)
            targets_mount = next(m for m in container.volume_mounts if m.name == "targets")
            self.assertEqual(targets_mount.mount_path, "/run/argus-targets")
            self.assertTrue(targets_mount.read_only)

            scratch_mount = next(m for m in container.volume_mounts if m.name == "scratch")
            self.assertEqual(scratch_mount.mount_path, "/tmp")

            # Resources
            self.assertEqual(container.resources.requests["cpu"], "250m")
            self.assertEqual(container.resources.requests["memory"], "256Mi")
            self.assertEqual(container.resources.requests["ephemeral-storage"], "256Mi")
            self.assertEqual(container.resources.limits["cpu"], "1")
            self.assertEqual(container.resources.limits["memory"], "768Mi")
            self.assertEqual(container.resources.limits["ephemeral-storage"], "1Gi")

            # No extra env, envFrom, ports
            self.assertIsNone(container.env)
            self.assertIsNone(container.env_from)
            self.assertIsNone(container.ports)
            self.assertIsNone(pod_spec.host_network)
            self.assertIsNone(pod_spec.host_pid)
            self.assertIsNone(pod_spec.host_ipc)

    def test_secret_payload_matches_runner_input_schema(self):
        corr_id = "1a2b3c4d5e-6f7a8b9c0d1e"
        with mock.patch.object(
            kali_kubernetes.KubernetesSqlmapExecutor,
            "_correlation_id",
            return_value=corr_id,
        ):
            self.make_executor().execute(17, [self.target])
            secret = self.core.create_namespaced_secret.call_args.args[1]
            self.assertEqual(set(secret.string_data.keys()), {"targets.json"})

            payload = json.loads(secret.string_data["targets.json"])
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["scan_id"], 17)
            self.assertEqual(len(payload["targets"]), 1)
            target = payload["targets"][0]
            self.assertEqual(set(target.keys()), {"index", "url"})
            self.assertEqual(target["index"], 0)
            self.assertEqual(target["url"], "https://target.example/?id=secret-value")
            self.assertNotIn("fingerprint", target)

    # ------------------------------------------------------------------
    # Task 4 Fix 1B：同一 execute 只呼叫一次 _correlation_id
    # ------------------------------------------------------------------
    def test_correlation_id_called_only_once_per_execute(self):
        """修正後驗證：同一 execute 只呼叫一次 _correlation_id。"""
        corr_id = "1a2b3c4d5e-6f7a8b9c0d1e"
        with mock.patch.object(
            kali_kubernetes.KubernetesSqlmapExecutor,
            "_correlation_id",
            return_value=corr_id,
        ) as mock_corr_id:
            self.make_executor().execute(17, [self.target])
            # FIX 1B 後應只呼叫一次
            self.assertEqual(
                mock_corr_id.call_count, 1,
                f"_correlation_id 應在同一 execute 內只呼叫一次，"
                f"實際呼叫 {mock_corr_id.call_count} 次",
            )

    def test_names_and_labels_match_downstream_contracts(self):
        corr_id = "1a2b3c4d5e-6f7a8b9c0d1e"
        with mock.patch.object(
            kali_kubernetes.KubernetesSqlmapExecutor,
            "_correlation_id",
            return_value=corr_id,
        ):
            self.make_executor().execute(17, [self.target])
            job = self.batch.create_namespaced_job.call_args.args[1]
            secret = self.core.create_namespaced_secret.call_args.args[1]

            # Names
            job_pattern = r"^argus-sqlmap-[a-f0-9]{10}-[a-f0-9]{12}$"
            secret_pattern = r"^argus-targets-[a-f0-9]{10}-[a-f0-9]{12}$"
            self.assertRegex(job.metadata.name, job_pattern)
            self.assertRegex(secret.metadata.name, secret_pattern)

            self.assertEqual(job.metadata.name, f"argus-sqlmap-{corr_id}")
            self.assertEqual(secret.metadata.name, f"argus-targets-{corr_id}")

            # Labels on Job
            job_labels = job.metadata.labels
            self.assertEqual(job_labels.get("managed-by"), "argus")
            self.assertEqual(job_labels.get("component"), "kali-sqlmap")
            self.assertEqual(job_labels.get("argus.io/managed-by"), "argus")
            self.assertEqual(job_labels.get("app"), "kali-sqlmap")

            # Labels on Secret
            secret_labels = secret.metadata.labels
            self.assertEqual(secret_labels.get("managed-by"), "argus")
            self.assertEqual(secret_labels.get("component"), "kali-sqlmap")
            self.assertEqual(secret_labels.get("argus.io/managed-by"), "argus")
            self.assertEqual(secret_labels.get("app"), "kali-sqlmap")

            # Labels on Pod template
            pod_labels = job.spec.template.metadata.labels
            self.assertEqual(pod_labels.get("managed-by"), "argus")
            self.assertEqual(pod_labels.get("component"), "kali-sqlmap")
            self.assertEqual(pod_labels.get("argus.io/managed-by"), "argus")
            self.assertEqual(pod_labels.get("app"), "kali-sqlmap")

            # No sensitive data in names/labels
            blob = " ".join([
                job.metadata.name,
                secret.metadata.name,
                str(job_labels),
                str(secret_labels),
                str(pod_labels),
            ])
            self.assertNotIn("target.example", blob)
            self.assertNotIn("secret-value", blob)
            self.assertNotIn("https", blob)
            self.assertNotIn("17", blob)  # scan_id

    def test_results_enriched_with_correlation_id_and_tool_version(self):
        corr_id = "1a2b3c4d5e-6f7a8b9c0d1e"
        with mock.patch.object(
            kali_kubernetes.KubernetesSqlmapExecutor,
            "_correlation_id",
            return_value=corr_id,
        ):
            results = self.make_executor().execute(17, [self.target])
            self.assertEqual(len(results), 1)
            summary = results[0].evidence_summary
            self.assertEqual(summary["correlation_id"], corr_id)
            self.assertEqual(summary["tool_version"], "1.10")
            self.assertNotIn("sqlmap_version", summary)

    # ------------------------------------------------------------------
    # brief 指定的兩條核心 lifecycle 測試
    # ------------------------------------------------------------------
    def test_job_is_created_before_owned_secret_and_cleanup_is_finally(self):
        executor = self.make_executor()
        executor.execute(17, [self.target])
        self.assertLess(
            self.calls.index("create_job"), self.calls.index("create_secret"),
        )
        self.assertIn("delete_job", self.calls)
        self.assertIn("delete_secret", self.calls)

    def test_cancel_deletes_resources_and_propagates(self):
        def cancel_side(*a, **k):
            if "create_job" in self.calls:
                raise ScanCancelled()
            return None

        self.cancel_check.side_effect = cancel_side
        with self.assertRaises(ScanCancelled):
            self.make_executor().execute(17, [self.target])
        self.batch.delete_namespaced_job.assert_called()
        self.core.delete_namespaced_secret.assert_called()

    # ------------------------------------------------------------------
    # Task 4 Fix 4B：watch 完成後仍以取消為優先
    # watch stream 回傳 Complete / Pod list / Pod log 各 I/O 前後，以及
    # parse/enrichment 後回傳成功前，都必須有 cancellation checkpoint。
    # ScanCancelled 不得被 generic I/O exception handler 吞掉，須原樣重拋至
    # execute() finally cleanup Job/Secret + release lock。
    # ------------------------------------------------------------------
    def test_cancel_after_watch_stream_returns(self):
        """watch stream 回 Complete 時翻轉 watch_returned 旗標；旗標為 true 後
        下一個 checkpoint 拋 ScanCancelled，log 不得被讀，finally 必須
        delete Job/Secret + release lock。改用 stateful side effect，不依賴
        cancel_check 的呼叫次序（新 _control_checkpoint 在 Job create 前後加
        了兩次 checkpoint，positional side_effect 已不可靠）。"""
        executor = self.make_executor()
        state = {"watch_returned": False}

        def cancel_side(*a, **k):
            # 僅在 watch stream 已返回（旗標為 true）時才視為取消時機
            if state["watch_returned"]:
                raise ScanCancelled()
            return None

        def stream_side(*a, **k):
            # stream 回 Complete 的同時翻轉旗標，回既有 succeeded 事件
            state["watch_returned"] = True
            return [{"object": self._succeeded_job()}]

        self.cancel_check.side_effect = cancel_side
        self.watcher.stream.side_effect = stream_side

        with self.assertRaises(ScanCancelled):
            executor.execute(17, [self.target])
        # terminal 雖為 succeeded，但 checkpoint 在讀 log 前就拋出
        self.core.read_namespaced_pod_log.assert_not_called()
        self.batch.delete_namespaced_job.assert_called()
        self.core.delete_namespaced_secret.assert_called()
        self._assert_lock_released()

    def test_cancel_after_pod_list_returns(self):
        """list_namespaced_pod 返回單 Pod 時翻轉 pod_list_returned 旗標；
        旗標為 true 後下一個 checkpoint 拋 ScanCancelled，log 不得被讀，
        必須 cleanup/release + re-raise。改用 stateful side effect，不依賴
        cancel_check 的呼叫次序（新 _control_checkpoint 改變了 checkpoint
        數量，positional side_effect 已不可靠）。"""
        executor = self.make_executor()
        state = {"pod_list_returned": False}

        def cancel_side(*a, **k):
            # 僅在 Pod list 已返回（旗標為 true）時才視為取消時機
            if state["pod_list_returned"]:
                raise ScanCancelled()
            return None

        def list_pod_side(*a, **k):
            # Pod list 返回的同時翻轉旗標，回既有單 Pod response
            state["pod_list_returned"] = True
            pod = mock.Mock()
            pod.metadata.name = "runner-pod"
            return mock.Mock(items=[pod])

        self.cancel_check.side_effect = cancel_side
        self.core.list_namespaced_pod.side_effect = list_pod_side

        with self.assertRaises(ScanCancelled):
            executor.execute(17, [self.target])
        self.core.read_namespaced_pod_log.assert_not_called()
        self.batch.delete_namespaced_job.assert_called()
        self.core.delete_namespaced_secret.assert_called()
        self._assert_lock_released()

    def test_cancel_after_pod_log_read(self):
        """read_namespaced_pod_log 返回合法 payload 時翻轉 log_returned 旗標；
        旗標為 true 後下一個 checkpoint 拋 ScanCancelled，不得 parse/回成功，
        必須 cleanup/release + re-raise，且 log 確實被讀一次。改用 stateful
        side effect，不依賴 cancel_check 的呼叫次序。"""
        executor = self.make_executor()
        state = {"log_returned": False}

        def cancel_side(*a, **k):
            # 僅在 Pod log 已返回（旗標為 true）時才視為取消時機
            if state["log_returned"]:
                raise ScanCancelled()
            return None

        def read_log_side(*a, **k):
            # log 返回的同時翻轉旗標，回既有合法 payload
            state["log_returned"] = True
            return _valid_payload(1)

        self.cancel_check.side_effect = cancel_side
        self.core.read_namespaced_pod_log.side_effect = read_log_side

        with self.assertRaises(ScanCancelled):
            executor.execute(17, [self.target])
        # log 確實被讀（checkpoint 在讀完之後）
        self.core.read_namespaced_pod_log.assert_called_once()
        self.batch.delete_namespaced_job.assert_called()
        self.core.delete_namespaced_secret.assert_called()
        self._assert_lock_released()

    def test_cancel_before_success_return(self):
        """read_namespaced_pod_log 返回時翻轉 log_returned 旗標；log 返回後
        第一次 checkpoint 放行（完成 parse/enrichment），第二次 checkpoint
        （enrichment 後、回傳成功前）才拋 ScanCancelled。不得回成功，必須
        cleanup/release + re-raise，且 log 確實被讀一次。改用 stateful
        side effect，不依賴 cancel_check 的呼叫次序。"""
        executor = self.make_executor()
        state = {"log_returned": False, "post_log_checks": 0}

        def cancel_side(*a, **k):
            # log 返回後才開始計數：第一次放行，第二次（return 前）才拋
            if state["log_returned"]:
                state["post_log_checks"] += 1
                if state["post_log_checks"] >= 2:
                    raise ScanCancelled()
            return None

        def read_log_side(*a, **k):
            # log 返回的同時翻轉旗標，回既有合法 payload
            state["log_returned"] = True
            return _valid_payload(1)

        self.cancel_check.side_effect = cancel_side
        self.core.read_namespaced_pod_log.side_effect = read_log_side

        with self.assertRaises(ScanCancelled):
            executor.execute(17, [self.target])
        self.core.read_namespaced_pod_log.assert_called_once()
        self.batch.delete_namespaced_job.assert_called()
        self.core.delete_namespaced_secret.assert_called()
        self._assert_lock_released()

    # ------------------------------------------------------------------
    # Task 4 Fix 4D1A-RED：stale cleanup 與 create Job 兩階段缺少 cancel
    # checkpoint。以下兩條為「期望 RED」的反例測試——預期在進入 watch 之前就
    # 應偵測取消，因而不得建立 Job（或 Secret）；現有 production 只在 watch
    # 階段檢查取消，故 Job / Secret 仍會先被建立，下列 assert 應失敗。
    # 注意：此為 RED，不是完成修復；GREEN 實作由後續 task 補上 cancel
    # checkpoint 後才會通過。
    # ------------------------------------------------------------------
    def test_cancel_during_stale_cleanup_skips_job_creation(self):
        """list_namespaced_job（stale cleanup）返回時即標記取消：下一個
        checkpoint 必須在 create_namespaced_job 之前攔下，故 Job 不應被建立；
        finally 仍須嘗試 cleanup 並釋放 lock。現有 production 缺此 checkpoint，
        Job 會先被建立，故 create_namespaced_job 未呼叫 assert 為 RED。"""
        state = {"cancelled": False}

        def cancel_side(*a, **k):
            # 取消旗標為 true 時立即拋 ScanCancelled，模擬 stateful checkpoint
            if state["cancelled"]:
                raise ScanCancelled()
            return None

        def list_side(*a, **k):
            # stale cleanup 階段才把取消旗標翻為 true，再回空 items
            state["cancelled"] = True
            return mock.Mock(items=[])

        self.cancel_check.side_effect = cancel_side
        self.batch.list_namespaced_job.side_effect = list_side

        with self.assertRaises(ScanCancelled):
            self.make_executor().execute(17, [self.target])

        # 期望（RED）：取消應在建立 Job 前被攔下，Job 不應被建立
        self.batch.create_namespaced_job.assert_not_called()
        # finally 仍須嘗試 cleanup Job/Secret 並釋放 lock
        self.batch.delete_namespaced_job.assert_called()
        self.core.delete_namespaced_secret.assert_called()
        self._assert_lock_released()

    def test_cancel_during_job_creation_skips_secret_creation(self):
        """create_namespaced_job 建立 Job 的同時標記取消：下一個 checkpoint
        必須在 create_namespaced_secret 之前攔下，故 Secret 不應被建立；
        finally 仍須 cleanup 並釋放 lock。現有 production 缺此 checkpoint，
        會先建立 Secret，故 create_namespaced_secret 未呼叫 assert 為 RED。"""
        state = {"cancelled": False}
        job_resp = mock.Mock()
        job_resp.metadata.uid = "job-uid-4d1a"

        def cancel_side(*a, **k):
            # 取消旗標為 true 時立即拋 ScanCancelled，模擬 stateful checkpoint
            if state["cancelled"]:
                raise ScanCancelled()
            return None

        def create_job_side(*a, **k):
            # 建立 Job 的同時把取消旗標翻為 true，並回合法 response
            state["cancelled"] = True
            self.calls.append("create_job")
            return job_resp

        self.cancel_check.side_effect = cancel_side
        self.batch.create_namespaced_job.side_effect = create_job_side

        with self.assertRaises(ScanCancelled):
            self.make_executor().execute(17, [self.target])

        # 期望（RED）：取消應在建立 Secret 前被攔下，Secret 不應被建立
        self.core.create_namespaced_secret.assert_not_called()
        # finally 仍須 cleanup Job/Secret 並釋放 lock（Job 已建立，必須刪除）
        self.batch.delete_namespaced_job.assert_called()
        self.core.delete_namespaced_secret.assert_called()
        self._assert_lock_released()

    # ------------------------------------------------------------------
    # Task 4 Fix 4D1B-RED：stale cleanup 逐 I/O 缺少 cancel checkpoint。
    # 下列兩條為「期望 RED」反例測試——理想上 stale cleanup 在 list 返回後、
    # 以及每刪除一個 stale Job 之前／之間，都應有 cancel checkpoint 攔下取消；
    # 現有 production 的 _cleanup_stale_jobs 在 list_namespaced_job 返回後直接
    # 連續刪除所有 stale Job，整個 method 內無任何 cancel_check，只在 method
    # 返回後才由 _control_checkpoint 檢查取消，因此 stale name 仍會被傳給
    # delete_namespaced_job，下列 assert 應失敗（RED）。
    # ------------------------------------------------------------------
    def test_cancel_during_stale_list_skips_stale_delete(self):
        """list_namespaced_job 返回前標記取消：理想上下一個 checkpoint 應在
        刪除任何 stale Job 之前攔下，故 stale name 不應傳給 delete_namespaced_job；
        finally 刪 current deterministic Job 可以存在。現有 production 在 stale
        cleanup method 內無 checkpoint，會先刪掉 stale Job 才在 method 返回後
        checkpoint，故此 assert 為 RED。"""
        state = {"cancelled": False}

        def cancel_side(*a, **k):
            # stateful checkpoint：旗標為 true 時立即拋 ScanCancelled
            if state["cancelled"]:
                raise ScanCancelled()
            return None

        # 沿用既有 timezone.now() 與 inline old-Job mock 模式，不自行計算時間
        now = timezone.now()
        old = mock.Mock()
        old.metadata.name = "kali-stale-4d1b-a"
        old.metadata.creation_timestamp = now - timedelta(seconds=10_000)
        old.spec.active_deadline_seconds = 120

        def list_side(*a, **k):
            # 回 response 前才把取消旗標翻為 true，再回含一個 stale Job 的 list
            state["cancelled"] = True
            return mock.Mock(items=[old])

        self.cancel_check.side_effect = cancel_side
        self.batch.list_namespaced_job.side_effect = list_side

        with self.assertRaises(ScanCancelled):
            self.make_executor().execute(17, [self.target])

        # 期望（RED）：stale name 從未傳給 delete_namespaced_job
        deleted = [
            c.kwargs.get("name")
            for c in self.batch.delete_namespaced_job.call_args_list
        ]
        self.assertNotIn("kali-stale-4d1b-a", deleted)
        # finally 刪 current deterministic Job 可以存在（此處不對它 assert）
        # finally 必須 release lock
        self._assert_lock_released()

    def test_cancel_between_stale_deletes_skips_remaining_stale(self):
        """list 含兩個 stale Job；第一個 stale delete 完成後標記取消：理想上下
        一個 checkpoint 應在刪除第二個 stale Job 之前攔下，故第二個 stale name
        不應被傳給 delete_namespaced_job；finally current Job delete 可以存在。
        現有 production 連續刪完兩個 stale Job 才 checkpoint，故第二個 stale
        name assert 為 RED。"""
        state = {"cancelled": False}

        def cancel_side(*a, **k):
            # stateful checkpoint：旗標為 true 時立即拋 ScanCancelled
            if state["cancelled"]:
                raise ScanCancelled()
            return None

        # 沿用既有 timezone.now() 與 inline old-Job mock 模式，不自行計算時間
        now = timezone.now()
        old1 = mock.Mock()
        old1.metadata.name = "kali-stale-4d1b-b1"
        old1.metadata.creation_timestamp = now - timedelta(seconds=10_000)
        old1.spec.active_deadline_seconds = 120
        old2 = mock.Mock()
        old2.metadata.name = "kali-stale-4d1b-b2"
        old2.metadata.creation_timestamp = now - timedelta(seconds=10_000)
        old2.spec.active_deadline_seconds = 120

        def delete_side(*a, **k):
            # 第一個 stale delete（即第一次呼叫）完成後才把取消旗標翻為 true；
            # 後續 finally current Job delete 仍可照常呼叫，此 side effect 不阻擋。
            if not state["cancelled"]:
                state["cancelled"] = True
            return None

        self.cancel_check.side_effect = cancel_side
        self.batch.list_namespaced_job.return_value = mock.Mock(items=[old1, old2])
        self.batch.delete_namespaced_job.side_effect = delete_side

        with self.assertRaises(ScanCancelled):
            self.make_executor().execute(17, [self.target])

        # 期望（RED）：第二個 stale name 從未傳給 delete_namespaced_job
        deleted = [
            c.kwargs.get("name")
            for c in self.batch.delete_namespaced_job.call_args_list
        ]
        self.assertNotIn("kali-stale-4d1b-b2", deleted)
        # finally current Job delete 可以存在（此處不對它 assert）
        # finally 必須 release lock
        self._assert_lock_released()

    # ------------------------------------------------------------------
    # Task 4 Fix 4D1C-RED：Secret create 成功返回後、進入 watch 前缺少 cancel
    # checkpoint。下列為「期望 RED」反例測試——理想上 create_namespaced_secret
    # 成功返回後，下一個 checkpoint 應在進入 _watch_and_collect 之前攔下取消，
    # 故 _watch_and_collect 不應被呼叫、execute 必須拋 ScanCancelled；現有
    # production 在 Secret create 後只呼叫 _renew_lock(token)，沒有 cancel_check，
    # 因此會直接進入被 mock 的 _watch_and_collect 並正常返回，不會拋
    # ScanCancelled，下列 assert 應失敗（RED）。
    # ------------------------------------------------------------------
    def test_cancel_after_secret_create_skips_watch(self):
        """create_namespaced_secret 成功返回的同時標記取消：下一個 checkpoint
        必須在進入 _watch_and_collect 之前攔下，故 _watch_and_collect 不應被
        呼叫；finally 仍須 cleanup 並釋放 lock。現有 production 在 Secret create
        後只呼叫 _renew_lock(token)，沒有 cancel_check，會直接進入被 mock 的
        _watch_and_collect 並正常返回，不會拋 ScanCancelled，故此 assert 為 RED。"""
        executor = self.make_executor()
        state = {"cancelled": False}

        def cancel_side(*a, **k):
            # stateful checkpoint：旗標為 true 時立即拋 ScanCancelled
            if state["cancelled"]:
                raise ScanCancelled()
            return None

        def create_secret_side(*a, **k):
            # Secret create 成功返回的同時把取消旗標翻為 true，再回合法 response
            state["cancelled"] = True
            self.calls.append("create_secret")
            return mock.Mock()

        self.cancel_check.side_effect = cancel_side
        self.core.create_namespaced_secret.side_effect = create_secret_side

        # 隔離 _watch_and_collect：避免它內部既有 cancel check 讓測試誤綠。
        # production 缺少 Secret-create 後的 checkpoint 時，會直接呼叫這個 mock
        # 並正常返回，使「拋 ScanCancelled」與「未呼叫 _watch_and_collect」兩個
        # assert 都失敗（RED）。
        with mock.patch.object(executor, "_watch_and_collect") as watch_mock:
            with self.assertRaises(ScanCancelled):
                executor.execute(17, [self.target])

        # Secret create 必須已呼叫一次
        self.core.create_namespaced_secret.assert_called_once()
        # _watch_and_collect 必須完全未呼叫（RED：production 會呼叫它）
        watch_mock.assert_not_called()
        # finally 仍須刪 Job、刪 Secret 並釋放 lock
        self.batch.delete_namespaced_job.assert_called()
        self.core.delete_namespaced_secret.assert_called()
        self._assert_lock_released()

    # ------------------------------------------------------------------
    # Task 4 Fix 4E-RED：_watch_and_collect 內每個 Kubernetes I/O 前後都缺少
    # owner checkpoint（compare-and-PEXPIRE）。理想上 watch stream 前/後、
    # Pod list 前/後、Pod log 前/後各做一次 owner-token renew，合計恰好 6 次
    # PEXPIRE。現有 production 只有 watch loop 內的 periodic renew（每 60 秒），
    # 且 Pod list / Pod log 僅有 cancellation check；直接呼叫 _watch_and_collect
    # 走 happy path 時第一片即回 Succeeded，連 periodic renew 都不會觸發，故
    # PEXPIRE 次數為 0，下列 assertEqual(..., 6) 為 RED。不得用 >= 弱化契約。
    # ------------------------------------------------------------------
    def test_watch_and_collect_renews_lock_around_each_io(self):
        """直接呼叫 _watch_and_collect happy path，避免 execute lifecycle 的其他
        checkpoint 干擾。watch stream / Pod list / Pod log 每個 I/O 前後都必須以
        owner token compare-and-PEXPIRE 續約，合計恰好 6 次。現有 production 缺
        這些 per-I/O renew checkpoint，故 assertEqual(6) 為 RED。"""
        executor = self.make_executor()

        results = executor._watch_and_collect(
            17, "corr-4e", "argus-kali", "job-4e", 120, [self.target], "owner-4e",
        )

        # happy path 必須成功且恰有一筆結果（先確認流程跑完，才檢查 renew 次數）
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].ok)

        # 篩出 script 含 PEXPIRE 的 eval 呼叫（_RENEW_LUA 用 PEXPIRE 續約）
        renew_calls = [
            c for c in self.redis.eval.call_args_list
            if "PEXPIRE" in (c.args[0] or "")
        ]
        # 期望恰好 6 次：watch stream 前/後、Pod list 前/後、Pod log 前/後
        # RED：現有 production happy path 第一片即 Succeeded，periodic renew 不
        # 觸發；Pod list / Pod log 只有 cancel check，實際為 0 次。
        self.assertEqual(
            len(renew_calls), 6,
            f"每個 I/O 前後都須 renew，期望 6 次 PEXPIRE，實際 {len(renew_calls)} 次",
        )
        for call in renew_calls:
            self.assertEqual(
                call.args[3], "owner-4e",
                "每次 renew 必須用同一個 owner token",
            )

    def _assert_lock_released(self) -> None:
        """驗證 finally 已用 owner token 釋放 global lock（compare-and-DEL）。"""
        release_calls = [
            c for c in self.redis.eval.call_args_list
            if "DEL" in (c.args[0] or "")
        ]
        self.assertTrue(release_calls, "finally 必須 release lock（DEL）")

    # ------------------------------------------------------------------
    # capacity_timeout：lock 等待逾期 → 每個 target 回 capacity_timeout
    # ------------------------------------------------------------------
    def test_capacity_timeout_returns_safe_error_per_target(self):
        executor = self.make_executor()
        self.redis.set.return_value = False

        def set_side(*a, **k):
            self.clock.t += 200  # 累進推進，直到越過 acquire deadline
            return False

        self.redis.set.side_effect = set_side
        with mock.patch.object(kali_kubernetes.time, "sleep"):
            results = executor.execute(17, [self.target])
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "capacity_timeout")
        # 未取到 lock，不應建立任何 Job/Secret
        self.assertNotIn("create_job", self.calls)

    # ------------------------------------------------------------------
    # owner-only renewal / release：acquire / renew / release 同一 token
    # ------------------------------------------------------------------
    def test_acquire_renew_release_share_one_owner_token(self):
        executor = self.make_executor()
        start = self.clock.t
        slices = {"n": 0}

        def stream_side(*a, **k):
            slices["n"] += 1
            if slices["n"] == 1:
                self.clock.t = start + 61  # 越過 60s 續約門檻
                return []                  # 第一片未終止
            return [{"object": self._succeeded_job()}]

        self.watcher.stream.side_effect = stream_side
        executor.execute(17, [self.target])

        set_token = self.redis.set.call_args.args[1]
        renew = [c for c in self.redis.eval.call_args_list
                 if "PEXPIRE" in (c.args[0] or "")]
        release = [c for c in self.redis.eval.call_args_list
                   if "DEL" in (c.args[0] or "")]
        self.assertTrue(renew, "應在 60s 後用 owner token 續約")
        self.assertTrue(release, "應在 finally 用 owner token 釋放")
        self.assertEqual(renew[-1].args[3], set_token)
        self.assertEqual(release[-1].args[3], set_token)

    # ------------------------------------------------------------------
    # Task 4 Fix 4D2A-RED：lock acquire 成功後、回傳 owner token 前缺少 cancel
    # checkpoint。redis.set 成功取得 lock 的瞬間若取消已發生，_acquire_global_lock
    # 應在回傳 token 前偵測取消、先用剛取得的 owner token release lock 再拋
    # ScanCancelled；現有 production 只在 SET 前檢查取消，SET 成功後直接回 token，
    # 故此條為 RED，錯誤訊息為 "ScanCancelled not raised"。
    # ------------------------------------------------------------------
    def test_cancel_immediately_after_lock_acquire_releases_owner_token(self):
        """redis.set 成功取得 lock 的同時標記取消：SET 成功後必須有 cancel
        checkpoint，偵測到取消時先 release lock 再拋 ScanCancelled。現有
        production 只在 SET 前檢查取消，SET 成功後直接回 token，故 assertRaises
        為 RED（ScanCancelled not raised）。"""
        executor = self.make_executor()
        state = {"cancelled": False}

        def cancel_side(*a, **k):
            # stateful checkpoint：旗標為 true 時立即拋 ScanCancelled
            if state["cancelled"]:
                raise ScanCancelled()
            return None

        def set_side(*a, **k):
            # SET 成功的同時把取消旗標翻為 true，再回 True（取得 lock）
            state["cancelled"] = True
            return True

        self.cancel_check.side_effect = cancel_side
        self.redis.set.side_effect = set_side

        with self.assertRaises(ScanCancelled):
            executor._acquire_global_lock(17, "corr-4d2a")

        # GREEN 後期望：拋 ScanCancelled 前已用 owner token release lock
        self._assert_lock_released()
        set_token = self.redis.set.call_args.args[1]
        release = [c for c in self.redis.eval.call_args_list
                   if "DEL" in (c.args[0] or "")]
        self.assertEqual(release[-1].args[3], set_token)

    def test_lock_lua_scripts_compare_token_before_touch(self):
        # Lua 本身強制 GET == ARGV[1] 才動作；mismatched token 無法 renew/release
        self.assertIn('GET", KEYS[1]) == ARGV[1]', kali_kubernetes._RENEW_LUA)
        self.assertIn('GET", KEYS[1]) == ARGV[1]', kali_kubernetes._RELEASE_LUA)

    # ------------------------------------------------------------------
    # stale Job cleanup：建立新 Job 前刪掉超過 deadline+30 的舊 Job
    # ------------------------------------------------------------------
    def test_stale_jobs_are_deleted_before_new_job(self):
        now = timezone.now()
        old = mock.Mock()
        old.metadata.name = "kali-stale-old"
        old.metadata.creation_timestamp = now - timedelta(seconds=10_000)
        old.spec.active_deadline_seconds = 120
        fresh = mock.Mock()
        fresh.metadata.name = "kali-fresh"
        fresh.metadata.creation_timestamp = now - timedelta(seconds=5)
        fresh.spec.active_deadline_seconds = 120
        self.batch.list_namespaced_job.return_value = mock.Mock(items=[old, fresh])

        self.make_executor().execute(17, [self.target])

        deleted = [
            c.kwargs.get("name") or (c.args[0] if c.args else None)
            for c in self.batch.delete_namespaced_job.call_args_list
        ]
        self.assertIn("kali-stale-old", deleted)
        self.assertNotIn("kali-fresh", deleted)
        # 新 Job 仍在舊 Job 之後才建立
        self.assertLess(self.calls.index("create_job"), len(self.calls))

    # ------------------------------------------------------------------
    # Task 4 Fix 3B：stale cleanup 必須用「每個 Job 自己的 active_deadline_seconds」
    # ------------------------------------------------------------------
    def test_stale_cleanup_uses_each_jobs_own_active_deadline(self):
        # 固定 now，避免 boundary case 受微秒漂移影響
        fixed_now = timezone.now()

        # short：created=now-181s、active=150 → 181 > 150+30=180 → 必須刪
        short = mock.Mock()
        short.metadata.name = "kali-short"
        short.metadata.creation_timestamp = fixed_now - timedelta(seconds=181)
        short.spec.active_deadline_seconds = 150

        # long：created=now-181s、active=390 → 181 < 390+30=420 → 仍有效，不刪
        long = mock.Mock()
        long.metadata.name = "kali-long"
        long.metadata.creation_timestamp = fixed_now - timedelta(seconds=181)
        long.spec.active_deadline_seconds = 390

        # boundary：created=now-180s、active=150 → 180 == 150+30 → 剛好等於，不刪
        boundary = mock.Mock()
        boundary.metadata.name = "kali-boundary"
        boundary.metadata.creation_timestamp = fixed_now - timedelta(seconds=180)
        boundary.spec.active_deadline_seconds = 150

        # missing：active_deadline_seconds=None → 缺失，保守不刪
        missing = mock.Mock()
        missing.metadata.name = "kali-missing"
        missing.metadata.creation_timestamp = fixed_now - timedelta(seconds=10_000)
        missing.spec.active_deadline_seconds = None

        # boolean：active=True → bool 不得當 int，保守不刪
        boolean = mock.Mock()
        boolean.metadata.name = "kali-boolean"
        boolean.metadata.creation_timestamp = fixed_now - timedelta(seconds=10_000)
        boolean.spec.active_deadline_seconds = True

        self.batch.list_namespaced_job.return_value = mock.Mock(
            items=[short, long, boundary, missing, boolean],
        )

        with mock.patch.object(kali_kubernetes.timezone, "now", return_value=fixed_now):
            self.make_executor().execute(17, [self.target])

        deleted = [
            c.kwargs.get("name") or (c.args[0] if c.args else None)
            for c in self.batch.delete_namespaced_job.call_args_list
        ]
        # 只有 short 被當成 stale 刪除
        self.assertIn("kali-short", deleted)
        for keep in ("kali-long", "kali-boundary", "kali-missing", "kali-boolean"):
            self.assertNotIn(keep, deleted)
        # list selector 維持 managed-by=argus,component=kali-sqlmap
        list_call = self.batch.list_namespaced_job.call_args
        self.assertEqual(
            list_call.kwargs.get("label_selector"),
            "managed-by=argus,component=kali-sqlmap",
        )

    # ------------------------------------------------------------------
    # Secret create failure：Job 已建立 → cleanup → 回 error
    # ------------------------------------------------------------------
    def test_secret_create_failure_cleans_up_job_and_returns_error(self):
        executor = self.make_executor()
        self.core.create_namespaced_secret.side_effect = ApiException(status=500)
        results = executor.execute(17, [self.target])
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "secret_create_failed")
        self.assertIn("create_job", self.calls)
        self.assertIn("delete_job", self.calls)
        self.batch.delete_namespaced_job.assert_called()

    # ------------------------------------------------------------------
    # Failed condition：watch 看到 Failed → 回 job_failed + cleanup
    # ------------------------------------------------------------------
    def test_failed_condition_returns_error_and_cleans_up(self):
        executor = self.make_executor()
        self.watcher.stream.return_value = [{"object": self._failed_job()}]
        results = executor.execute(17, [self.target])
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "runner_failed")
        self.assertIn("delete_job", self.calls)
        self.assertIn("delete_secret", self.calls)

    # ------------------------------------------------------------------
    # watch timeout：watch 超過上限未終止 → watch_timeout
    # ------------------------------------------------------------------
    def test_watch_timeout_returns_safe_error(self):
        executor = self.make_executor()
        start = self.clock.t
        deadline = start + min(120 + 30, 390) + 30  # active deadline + 30 上限

        def stream_side(*a, **k):
            self.clock.t = deadline + 100  # 推進過 watch 上限
            return []

        self.watcher.stream.side_effect = stream_side
        results = executor.execute(17, [self.target])
        self.assertEqual(results[0].error, "job_deadline_exceeded")

    # ------------------------------------------------------------------
    # invalid log：log 超過契約上限 → parse_runner_result 拒絕
    # ------------------------------------------------------------------
    def test_oversized_log_rejected_via_contract(self):
        executor = self.make_executor()
        self.core.read_namespaced_pod_log.return_value = b"x" * 16385  # > 16384
        results = executor.execute(17, [self.target])
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "invalid_result")

    # ------------------------------------------------------------------
    # cleanup NotFound：刪除 NotFound 視為成功，不拋例外
    # ------------------------------------------------------------------
    def test_cleanup_not_found_is_success(self):
        executor = self.make_executor()
        self.batch.delete_namespaced_job.side_effect = ApiException(status=404)
        self.core.delete_namespaced_secret.side_effect = ApiException(status=404)
        # happy path 跑完後 finally 命中 NotFound，不應拋出
        results = executor.execute(17, [self.target])
        self.assertEqual(len(results), 1)

    # ------------------------------------------------------------------
    # cleanup_failed：不可把 API exception body 寫進 scan_log
    # ------------------------------------------------------------------
    def test_cleanup_failure_logs_safe_code_without_exception_body(self):
        executor = self.make_executor()
        sensitive = "INTERNAL_EXPLOSION_BODY_SECRET"
        err = ApiException(status=500, reason="Internal Server Error")
        err.body = sensitive
        self.batch.delete_namespaced_job.side_effect = err
        with mock.patch.object(kali_kubernetes, "append_log") as log_mock:
            results = executor.execute(17, [self.target])
        self.assertEqual(len(results), 1)
        # 只檢查 log message（args[1]），驗證 cleanup 那筆只含 safe code
        msgs = [(c.args[1] if len(c.args) > 1 else "") for c in log_mock.call_args_list]
        joined = " ".join(msgs)
        self.assertIn("cleanup_failed", joined)
        # 不得外洩例外 reason / body
        self.assertNotIn("Internal Server Error", joined)
        self.assertNotIn(sensitive, joined)

    # ------------------------------------------------------------------
    # 安全不變量：names / labels / logs 永不包含 URL 或 query value
    # ------------------------------------------------------------------
    def test_names_and_labels_never_contain_url_or_domain(self):
        self.make_executor().execute(17, [self.target])
        job = self.batch.create_namespaced_job.call_args.args[1]
        secret = self.core.create_namespaced_secret.call_args.args[1]
        labels = job.metadata.labels
        self.assertEqual(labels.get("managed-by"), "argus")
        self.assertEqual(labels.get("component"), "kali-sqlmap")
        blob = " ".join([job.metadata.name, secret.metadata.name, str(labels)])
        self.assertNotIn("target.example", blob)
        self.assertNotIn("secret-value", blob)
        self.assertNotIn("https", blob)

    def test_secret_is_owner_referenced_and_only_contains_targets_json(self):
        self.make_executor().execute(17, [self.target])
        secret = self.core.create_namespaced_secret.call_args.args[1]
        self.assertEqual(set(secret.string_data.keys()), {"targets.json"})
        owner_refs = secret.metadata.owner_references
        self.assertEqual(len(owner_refs), 1)
        self.assertEqual(owner_refs[0].uid, "job-uid-123")
        self.assertTrue(owner_refs[0].controller)
        self.assertEqual(owner_refs[0].kind, "Job")

    def test_append_log_only_records_correlation_id_phase_and_safe_code(self):
        corr_id = "1a2b3c4d5e-6f7a8b9c0d1e"
        with mock.patch.object(
            kali_kubernetes.KubernetesSqlmapExecutor,
            "_correlation_id",
            return_value=corr_id,
        ), mock.patch.object(kali_kubernetes, "append_log") as log_mock:
            self.make_executor().execute(17, [self.target])
        rendered = " ".join(str(c) for c in log_mock.call_args_list)
        self.assertNotIn("target.example", rendered)
        self.assertNotIn("secret-value", rendered)
        self.assertNotIn("https", rendered)
        self.assertIn(corr_id, rendered)

    # ------------------------------------------------------------------
    # 結果富化：correlation_id + sqlmap_version 進入 evidence_summary
    # ------------------------------------------------------------------
    # 已由 Task 4 Fix 1 的 test_results_enriched_with_correlation_id_and_tool_version 取代

    # ------------------------------------------------------------------
    # deadline 計算：min(targets * timeout + 30, 390)
    # ------------------------------------------------------------------
    def test_active_deadline_for_single_target(self):
        self.make_executor().execute(17, [self.target])
        job = self.batch.create_namespaced_job.call_args.args[1]
        self.assertEqual(job.spec.active_deadline_seconds, 150)  # 1*120+30

    def test_active_deadline_capped_at_390_for_many_targets(self):
        targets = [
            ReservedSqlmapTarget(i, f"https://t.example/?id={i}", f"fp-{i}")
            for i in range(5)
        ]
        self.core.read_namespaced_pod_log.return_value = _valid_payload(5)
        self.make_executor().execute(17, targets)
        job = self.batch.create_namespaced_job.call_args.args[1]
        self.assertEqual(job.spec.active_deadline_seconds, 390)  # min(630, 390)

    # ------------------------------------------------------------------
    # runner pod 必須是 restricted
    # ------------------------------------------------------------------
    def test_runner_pod_template_is_restricted(self):
        self.make_executor().execute(17, [self.target])
        job = self.batch.create_namespaced_job.call_args.args[1]
        pod_spec = job.spec.template.spec
        self.assertFalse(pod_spec.automount_service_account_token)
        self.assertTrue(pod_spec.security_context.run_as_non_root)
        container = pod_spec.containers[0]
        ctx = container.security_context
        self.assertFalse(ctx.privileged)
        self.assertFalse(ctx.allow_privilege_escalation)
        self.assertTrue(ctx.read_only_root_filesystem)
        self.assertIn("ALL", ctx.capabilities.drop)

    # ------------------------------------------------------------------
    # production 預設只走 load_incluster_config，不 fallback local kubeconfig
    # ------------------------------------------------------------------
    def test_default_construction_uses_incluster_config_only(self):
        with mock.patch.object(
            kali_kubernetes.config, "load_incluster_config",
        ) as incluster, mock.patch.object(
            kali_kubernetes.client, "BatchV1Api", return_value=self.batch,
        ), mock.patch.object(
            kali_kubernetes.client, "CoreV1Api", return_value=self.core,
        ):
            KubernetesSqlmapExecutor(redis_client=self.redis)
        incluster.assert_called_once()

    # ------------------------------------------------------------------
    # Task 4 Fix 2A：Redis lock ownership 與取消安全
    # ------------------------------------------------------------------
    def test_acquire_redis_error_silent_fails_as_capacity_timeout(self):
        """redis.set 丟出含敏感本文的例外；execute 不得外拋、不得建立 Job。"""
        executor = self.make_executor()
        sensitive = "REDIS_AUTH_TOKEN_SECRET"
        self.redis.set.side_effect = Exception(sensitive)

        with mock.patch.object(kali_kubernetes, "append_log") as log_mock:
            results = executor.execute(17, [self.target])

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "capacity_timeout")
        self.assertNotIn("create_job", self.calls)
        msgs = " ".join(str(c) for c in log_mock.call_args_list)
        self.assertNotIn(sensitive, msgs)

    def test_lost_lock_before_job_stops_without_creating_job(self):
        """acquire 成功但 stale-cleanup 後 PEXPIRE 回 0；不得建立 Job。"""
        executor = self.make_executor()
        self.redis.set.return_value = True
        self.redis.eval.return_value = 0  # PEXPIRE 回 0, DEL 回 0

        with mock.patch.object(kali_kubernetes, "append_log") as log_mock:
            results = executor.execute(17, [self.target])

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "runner_failed")
        self.assertNotIn("create_job", self.calls)
        msgs = " ".join(str(c) for c in log_mock.call_args_list)
        self.assertIn("cleanup_failed", msgs)
        self.assertNotIn("lock_released", msgs)

    def test_lost_lock_during_watch_stops_and_cleans_up(self):
        """watch 中 renew 回 0；回 runner_failed 並 cleanup。"""
        executor = self.make_executor()
        start = self.clock.t
        renew_returns = iter([1, 1, 1, 0])  # 3 checkpoints pass, watch renew fails

        def eval_side(script, *args):
            if "PEXPIRE" in (script or ""):
                return next(renew_returns)
            return 1

        self.redis.eval.side_effect = eval_side

        slice_n = {"n": 0}

        def stream_side(*a, **k):
            slice_n["n"] += 1
            self.clock.t = start + 61 * slice_n["n"]
            return []

        self.watcher.stream.side_effect = stream_side

        results = executor.execute(17, [self.target])

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "runner_failed")
        self.assertIn("create_job", self.calls)
        self.assertIn("delete_job", self.calls)
        self.assertIn("delete_secret", self.calls)

    def test_renew_redis_error_silent_fails_and_cleans_up(self):
        """compare-and-PEXPIRE 丟例外；不得外拋或記例外本文。"""
        executor = self.make_executor()
        sensitive = "REDIS_PEXPIRE_SECRET_BODY"

        def eval_side(script, *args):
            if "PEXPIRE" in (script or ""):
                raise Exception(sensitive)
            return 1

        self.redis.eval.side_effect = eval_side

        with mock.patch.object(kali_kubernetes, "append_log") as log_mock:
            results = executor.execute(17, [self.target])

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "runner_failed")
        self.assertNotIn("create_job", self.calls)
        self.assertIn("delete_job", self.calls)
        self.assertIn("delete_secret", self.calls)
        msgs = " ".join(str(c) for c in log_mock.call_args_list)
        self.assertNotIn(sensitive, msgs)

    def test_release_redis_error_does_not_mask_scan_cancelled(self):
        """finally compare-and-DEL 丟例外；仍須重拋原本 ScanCancelled。"""
        executor = self.make_executor()
        sensitive = "REDIS_DEL_SECRET_BODY"
        def cancel_side(*a, **k):
            if "create_job" in self.calls:
                raise ScanCancelled()
            return None

        self.cancel_check.side_effect = cancel_side

        def eval_side(script, *args):
            if "DEL" in (script or ""):
                raise Exception(sensitive)
            return 1

        self.redis.eval.side_effect = eval_side

        with mock.patch.object(kali_kubernetes, "append_log") as log_mock:
            with self.assertRaises(ScanCancelled):
                executor.execute(17, [self.target])

        self.batch.delete_namespaced_job.assert_called()
        self.core.delete_namespaced_secret.assert_called()
        msgs = " ".join(str(c) for c in log_mock.call_args_list)
        self.assertIn("cleanup_failed", msgs)
        self.assertNotIn(sensitive, msgs)
        self.assertNotIn("lock_released", msgs)

    # ------------------------------------------------------------------
    # Task 4 Fix 4D2A-RED：取得 global lock 後取消不得遺留 lease
    # _acquire_global_lock 在 redis.set 成功返回後必須再做一次 cancel_check；
    # 若旗標為 true 必須重拋 ScanCancelled 並以 owner token compare-and-DEL
    # 釋放 lock，不得回 token。現有 production 只在 redis.set 前檢查取消，SET
    # 成功後立刻 return token，沒有 post-SET cancel check 也沒有 release，
    # 故下列 assert 為 RED。
    # ------------------------------------------------------------------
    def test_cancel_after_lock_set_releases_and_propagates(self):
        """redis.set 成功取得 lock 的同時將 state["cancelled"] 翻為 true；注入的
        cancel_check 在旗標為 true 時必須拋 ScanCancelled。_acquire_global_lock
        必須重拋 ScanCancelled（不得回 token），並以 owner token compare-and-DEL
        釋放 lock。現有 production 缺少 post-SET cancel check 與 release，故
        assertRaises(ScanCancelled) 為 RED。"""
        executor = self.make_executor()
        state = {"cancelled": False}

        def cancel_side(*a, **k):
            # stateful checkpoint：旗標為 true 時立即拋 ScanCancelled
            if state["cancelled"]:
                raise ScanCancelled()
            return None

        def set_side(*a, **k):
            # redis.set 成功取得 lock 的同時把取消旗標翻為 true，模擬 SET 返回後取消
            state["cancelled"] = True
            return True

        self.cancel_check.side_effect = cancel_side
        self.redis.set.side_effect = set_side

        # _acquire_global_lock 必須重拋 ScanCancelled，不得回 token
        # （RED：現有 production SET 成功後直接 return token）
        with self.assertRaises(ScanCancelled):
            executor._acquire_global_lock(17, "corr-4d2a")

        # release 的 token 必須等於 redis.set 實際寫入的 token（沿用
        # _assert_lock_released 的 DEL 篩選邏輯，再精確比對 call args）
        set_token = self.redis.set.call_args.args[1]
        release_calls = [
            c for c in self.redis.eval.call_args_list
            if "DEL" in (c.args[0] or "")
        ]
        self.assertTrue(
            release_calls,
            "取消後必須以 owner token compare-and-DEL 釋放 lock",
        )
        for call in release_calls:
            self.assertEqual(
                call.args[3], set_token,
                "release token 必須等於 redis.set 寫入的 token",
            )

    # ------------------------------------------------------------------
    # Task 4 Fix 2B：lock / watch 時間硬界線
    # ------------------------------------------------------------------
    def test_lock_wait_never_retries_or_sleeps_at_deadline(self):
        """deadline 比較使用 <，不可在 deadline 當下再 SET 或 sleep。"""
        self.clock.t = 0
        set_count = {"n": 0}

        def set_side(*a, **k):
            set_count["n"] += 1
            return False

        self.redis.set.side_effect = set_side

        def sleep_side(seconds):
            self.clock.t += seconds

        with override_settings(ARGUS_KALI_LOCK_WAIT_SECONDS=2), \
                mock.patch.object(kali_kubernetes.time, "sleep", side_effect=sleep_side):
            results = self.make_executor().execute(17, [self.target])

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "capacity_timeout")
        self.assertEqual(set_count["n"], 2)
        self.assertLessEqual(self.clock.t, 2)

    def test_watch_final_slice_is_capped_to_remaining_budget(self):
        """watch 最後一片的 timeout_seconds 不超過 remaining budget。"""
        executor = self.make_executor()
        self.clock.t = 0
        call_count = {"n": 0}

        def stream_side(*a, **k):
            call_count["n"] += 1
            if call_count["n"] == 1:
                self.clock.t += 3
            else:
                self.clock.t += k.get("timeout_seconds", 5)
            return []

        self.watcher.stream.side_effect = stream_side

        results = executor._watch_and_collect(
            scan_job_id=17,
            correlation_id="test-corr-id",
            namespace="argus-kali",
            job_name="argus-sqlmap-test",
            deadline=150,
            targets=[self.target],
            token="test-token",
        )

        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "job_deadline_exceeded")
        self.assertLessEqual(self.clock.t, 180)
        # 所有 slice 必須是正整數、<= 5、且帶 _request_timeout <= slice
        for call in self.watcher.stream.call_args_list:
            timeout = call.kwargs.get("timeout_seconds")
            self.assertIsNotNone(timeout)
            self.assertIsInstance(timeout, int)
            self.assertGreaterEqual(timeout, 1)
            self.assertLessEqual(timeout, 5)
            req_timeout = call.kwargs.get("_request_timeout")
            self.assertIsNotNone(req_timeout)
            self.assertLessEqual(req_timeout, timeout)
        # 最後一片恰為 remaining = 2
        last_timeout = self.watcher.stream.call_args_list[-1].kwargs["timeout_seconds"]
        self.assertEqual(last_timeout, 2)

    # ------------------------------------------------------------------
    # Task 4 Fix 3A：固定 outward error taxonomy
    # ------------------------------------------------------------------

    def test_job_create_exception_maps_to_job_create_failed(self):
        executor = self.make_executor()
        self.batch.create_namespaced_job.side_effect = ApiException(status=500)
        results = executor.execute(17, [self.target])
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "job_create_failed")
        self.assertNotIn("create_secret", self.calls)

    def test_job_uid_missing_maps_to_job_create_failed(self):
        executor = self.make_executor()
        job_resp = mock.Mock()
        job_resp.metadata.uid = None
        self.batch.create_namespaced_job.side_effect = (
            lambda *a, **k: (self.calls.append("create_job") or job_resp)
        )
        results = executor.execute(17, [self.target])
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "job_create_failed")
        self.assertNotIn("create_secret", self.calls)

    def test_secret_create_exception_maps_to_secret_create_failed(self):
        executor = self.make_executor()
        self.core.create_namespaced_secret.side_effect = ApiException(status=500)
        results = executor.execute(17, [self.target])
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "secret_create_failed")
        self.assertIn("create_job", self.calls)
        self.assertIn("delete_job", self.calls)

    def test_failed_deadline_exceeded_maps_to_job_deadline_exceeded(self):
        executor = self.make_executor()
        self.watcher.stream.return_value = [{"object": self._deadline_exceeded_job()}]
        results = executor.execute(17, [self.target])
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "job_deadline_exceeded")

    def test_watch_api_exception_maps_to_runner_failed(self):
        executor = self.make_executor()
        self.watcher.stream.side_effect = ApiException(status=500)
        results = executor.execute(17, [self.target])
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "runner_failed")

    def test_pod_list_exception_maps_to_runner_failed(self):
        executor = self.make_executor()
        self.core.list_namespaced_pod.side_effect = ApiException(status=500)
        results = executor.execute(17, [self.target])
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "runner_failed")

    def test_pod_not_found_maps_to_runner_failed(self):
        executor = self.make_executor()
        self.core.list_namespaced_pod.return_value = mock.Mock(items=[])
        results = executor.execute(17, [self.target])
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "runner_failed")
        # Task 4 Fix 3C：零 Pod 不得讀任何 log
        self.core.read_namespaced_pod_log.assert_not_called()

    # ------------------------------------------------------------------
    # Task 4 Fix 3C：read_runner_log 前必須 exactly one named Pod
    # ------------------------------------------------------------------
    def test_multiple_job_pods_are_rejected_without_reading_log(self):
        """兩個命名 Pod 不得任選第一個；不讀任何 log，outward runner_failed。"""
        executor = self.make_executor()
        pod_a = mock.Mock()
        pod_a.metadata.name = "pod-a"
        pod_b = mock.Mock()
        pod_b.metadata.name = "pod-b"
        self.core.list_namespaced_pod.return_value = mock.Mock(items=[pod_a, pod_b])

        results = executor.execute(17, [self.target])

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "runner_failed")
        self.core.read_namespaced_pod_log.assert_not_called()

    def test_nameless_single_pod_is_rejected_without_reading_log(self):
        """唯一 Pod 的 name 為 None／非字串；不讀 log，outward runner_failed。"""
        executor = self.make_executor()
        # None 與非字串（int）兩種 case 都必須拒絕，不可靠 truthiness 判斷
        cases = [
            ("none_name", None),
            ("non_string_int_name", 12345),
            ("empty_string_name", ""),
        ]
        for label, bad_name in cases:
            with self.subTest(label):
                # 每個 subTest 重置 mock 狀態
                self.setUp()
                executor = self.make_executor()
                pod = mock.Mock()
                pod.metadata.name = bad_name
                self.core.list_namespaced_pod.return_value = mock.Mock(items=[pod])

                results = executor.execute(17, [self.target])

                self.assertEqual(len(results), 1)
                self.assertFalse(results[0].ok)
                self.assertEqual(results[0].error, "runner_failed")
                self.core.read_namespaced_pod_log.assert_not_called()

    def test_single_named_pod_is_the_only_log_read_path(self):
        """唯一命名 Pod 才能讀 log；精確斷言呼叫參數。"""
        executor = self.make_executor()
        pod = mock.Mock()
        pod.metadata.name = "pod-a"
        self.core.list_namespaced_pod.return_value = mock.Mock(items=[pod])

        results = executor.execute(17, [self.target])

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].ok)
        self.assertEqual(results[0].error, "")
        self.core.read_namespaced_pod_log.assert_called_once_with(
            name="pod-a",
            namespace="argus-kali",
            limit_bytes=16385,
            _request_timeout=5,
        )

    def test_log_read_exception_maps_to_runner_failed(self):
        executor = self.make_executor()
        self.core.read_namespaced_pod_log.side_effect = ApiException(status=500)
        results = executor.execute(17, [self.target])
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "runner_failed")

    def test_invalid_json_maps_to_invalid_result(self):
        executor = self.make_executor()
        self.core.read_namespaced_pod_log.return_value = b"not json at all"
        results = executor.execute(17, [self.target])
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "invalid_result")

    def test_runner_private_error_code_maps_to_runner_failed(self):
        """合法 runner payload 內非空且非 clean 的 error_code → outward runner_failed。"""
        executor = self.make_executor()
        document = {
            "schema_version": 1,
            "tool": "sqlmap",
            "results": [{
                "index": 0,
                "ok": False,
                "confirmed": False,
                "returncode": 1,
                "parameter": "",
                "techniques": [],
                "dbms": "",
                "error_code": "runner_output_too_large",
            }],
        }
        self.core.read_namespaced_pod_log.return_value = (
            json.dumps(document, separators=(",", ":")).encode()
        )
        results = executor.execute(17, [self.target])
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "runner_failed")
        self.assertNotIn("runner_output_too_large", results[0].error)

    def test_clean_error_code_normalized_to_empty_on_success(self):
        """runner error_code=clean 時 outward error 應為空字串（不外洩 runner taxonomy）。"""
        executor = self.make_executor()
        results = executor.execute(17, [self.target])
        self.assertTrue(results[0].ok)
        self.assertEqual(results[0].error, "")

    # ------------------------------------------------------------------
    # Task 4 Fix 4A：KaliResult 欄位一致性與 error mapping
    # parse_runner_result 成功後、加入 evidence 前，須做整批一致性檢查與映射：
    #   - confirmed=True 且 ok=False → 整批 invalid_result
    #   - ok=True 時 private error 僅可為 ""／"clean"，否則整批 invalid_result
    #   - ok=False → outward 一律 runner_failed（不論 private error_code），不得為空
    #   - 絕不產生 ok=True,error="runner_failed"，也不洩漏 private error code
    # ------------------------------------------------------------------
    def test_ok_false_with_empty_error_code_maps_to_runner_failed(self):
        """ok=False 但 private error_code 為空 → outward 必為 runner_failed，不得為空。"""
        executor = self.make_executor()
        self.core.read_namespaced_pod_log.return_value = _result_payload(
            ok=False, confirmed=False, error_code="",
        )
        results = executor.execute(17, [self.target])
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "runner_failed")

    def test_ok_false_with_clean_error_code_maps_to_runner_failed(self):
        """ok=False 但 private error_code=clean → outward 必為 runner_failed，不得為空。"""
        executor = self.make_executor()
        self.core.read_namespaced_pod_log.return_value = _result_payload(
            ok=False, confirmed=False, error_code="clean",
        )
        results = executor.execute(17, [self.target])
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "runner_failed")

    def test_ok_true_with_non_clean_private_error_is_batch_invalid_result(self):
        """ok=True 但 private error_code 非 clean／空 → 整批 invalid_result，audit 安全。"""
        executor = self.make_executor()
        self.core.read_namespaced_pod_log.return_value = _result_payload(
            ok=True, confirmed=False, error_code="runner_failure",
        )
        with mock.patch.object(kali_kubernetes, "append_log") as log_mock:
            results = executor.execute(17, [self.target])
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "invalid_result")
        msgs = " ".join(str(c) for c in log_mock.call_args_list)
        # audit code 必須是 invalid_result
        self.assertIn("invalid_result", msgs)
        # 不得外洩 runner private error code
        self.assertNotIn("runner_failure", msgs)

    def test_ok_false_with_confirmed_true_is_batch_invalid_result(self):
        """confirmed=True 且 ok=False → 矛盾狀態，整批 invalid_result。"""
        executor = self.make_executor()
        self.core.read_namespaced_pod_log.return_value = _result_payload(
            ok=False, confirmed=True, error_code="clean",
        )
        results = executor.execute(17, [self.target])
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].error, "invalid_result")

    def test_ok_true_clean_error_code_is_outward_success_empty_error(self):
        """ok=True 且 private error_code=clean → outward 成功，error 為空字串。"""
        executor = self.make_executor()
        self.core.read_namespaced_pod_log.return_value = _result_payload(
            ok=True, confirmed=False, error_code="clean",
        )
        results = executor.execute(17, [self.target])
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].ok)
        self.assertEqual(results[0].error, "")

    def test_all_outward_failure_errors_are_in_allowlist(self):
        scenarios = [
            ("capacity_timeout", self._scenario_capacity_timeout),
            ("job_create_exception", self._scenario_job_create_exception),
            ("job_uid_missing", self._scenario_job_uid_missing),
            ("secret_create_exception", self._scenario_secret_create_exception),
            ("deadline_exceeded", self._scenario_deadline_exceeded),
            ("failed_condition", self._scenario_failed_condition),
            ("watch_timeout", self._scenario_watch_timeout),
            ("watch_exception", self._scenario_watch_exception),
            ("pod_list_exception", self._scenario_pod_list_exception),
            ("pod_not_found", self._scenario_pod_not_found),
            ("log_read_exception", self._scenario_log_read_exception),
            ("invalid_json", self._scenario_invalid_json),
            ("runner_private_code", self._scenario_runner_private_code),
        ]
        for label, run in scenarios:
            with self.subTest(label):
                self.setUp()
                results = run()
                self.assertTrue(len(results) >= 1, f"{label}: 無結果")
                for r in results:
                    if not r.ok:
                        self.assertIn(
                            r.error, OUTWARD_ERROR_ALLOWLIST,
                            f"{label}: outward error='{r.error}' 不在 allowlist",
                        )

    def _scenario_capacity_timeout(self):
        executor = self.make_executor()
        self.redis.set.return_value = False
        self.redis.set.side_effect = lambda *a, **k: (
            setattr(self.clock, "t", self.clock.t + 200) or False
        )
        with mock.patch.object(kali_kubernetes.time, "sleep"):
            return executor.execute(17, [self.target])

    def _scenario_job_create_exception(self):
        executor = self.make_executor()
        self.batch.create_namespaced_job.side_effect = ApiException(status=500)
        return executor.execute(17, [self.target])

    def _scenario_job_uid_missing(self):
        executor = self.make_executor()
        job_resp = mock.Mock()
        job_resp.metadata.uid = None
        self.batch.create_namespaced_job.side_effect = (
            lambda *a, **k: job_resp
        )
        return executor.execute(17, [self.target])

    def _scenario_secret_create_exception(self):
        executor = self.make_executor()
        self.core.create_namespaced_secret.side_effect = ApiException(status=500)
        return executor.execute(17, [self.target])

    def _scenario_deadline_exceeded(self):
        executor = self.make_executor()
        self.watcher.stream.return_value = [{"object": self._deadline_exceeded_job()}]
        return executor.execute(17, [self.target])

    def _scenario_failed_condition(self):
        executor = self.make_executor()
        self.watcher.stream.return_value = [{"object": self._failed_job()}]
        return executor.execute(17, [self.target])

    def _scenario_watch_timeout(self):
        executor = self.make_executor()
        start = self.clock.t
        deadline = start + min(120 + 30, 390) + 30

        def stream_side(*a, **k):
            self.clock.t = deadline + 100
            return []

        self.watcher.stream.side_effect = stream_side
        return executor.execute(17, [self.target])

    def _scenario_watch_exception(self):
        executor = self.make_executor()
        self.watcher.stream.side_effect = ApiException(status=500)
        return executor.execute(17, [self.target])

    def _scenario_pod_list_exception(self):
        executor = self.make_executor()
        self.core.list_namespaced_pod.side_effect = ApiException(status=500)
        return executor.execute(17, [self.target])

    def _scenario_pod_not_found(self):
        executor = self.make_executor()
        self.core.list_namespaced_pod.return_value = mock.Mock(items=[])
        return executor.execute(17, [self.target])

    def _scenario_log_read_exception(self):
        executor = self.make_executor()
        self.core.read_namespaced_pod_log.side_effect = ApiException(status=500)
        return executor.execute(17, [self.target])

    def _scenario_invalid_json(self):
        executor = self.make_executor()
        self.core.read_namespaced_pod_log.return_value = b"not json"
        return executor.execute(17, [self.target])

    def _scenario_runner_private_code(self):
        executor = self.make_executor()
        document = {
            "schema_version": 1,
            "tool": "sqlmap",
            "results": [{
                "index": 0, "ok": False, "confirmed": False, "returncode": 1,
                "parameter": "", "techniques": [], "dbms": "",
                "error_code": "runner_output_too_large",
            }],
        }
        self.core.read_namespaced_pod_log.return_value = (
            json.dumps(document, separators=(",", ":")).encode()
        )
        return executor.execute(17, [self.target])

    def test_audit_log_error_codes_use_global_taxonomy(self):
        forbidden = {
            "create_job_failed", "create_secret_failed", "job_failed",
            "watch_timeout", "watch_error", "log_unavailable",
            "result_too_large", "delete_job_failed", "delete_secret_failed",
            "stale_list_failed", "pod_list_failed", "pod_not_found",
            "log_read_failed", "invalid_result_type", "invalid_top_level_fields",
            "unknown_schema", "invalid_result_fields", "unexpected_index",
            "duplicate_index", "unsafe_parameter", "invalid_techniques",
            "unsafe_dbms", "unsafe_error_code", "missing_index",
        }
        scenarios = [
            ("job_create_exception", self._scenario_job_create_exception),
            ("secret_create_exception", self._scenario_secret_create_exception),
            ("deadline_exceeded", self._scenario_deadline_exceeded),
            ("failed_condition", self._scenario_failed_condition),
            ("watch_timeout", self._scenario_watch_timeout),
            ("watch_exception", self._scenario_watch_exception),
            ("pod_list_exception", self._scenario_pod_list_exception),
            ("pod_not_found", self._scenario_pod_not_found),
            ("log_read_exception", self._scenario_log_read_exception),
            ("invalid_json", self._scenario_invalid_json),
            ("runner_private_code", self._scenario_runner_private_code),
        ]
        for label, run in scenarios:
            with mock.patch.object(kali_kubernetes, "append_log") as log_mock:
                with self.subTest(label):
                    self.setUp()
                    run()
                    for call in log_mock.call_args_list:
                        rendered = str(call)
                        for bad in forbidden:
                            self.assertNotIn(
                                f"code={bad}", rendered,
                                f"{label}: audit log 含禁止碼 '{bad}'",
                            )

    # ------------------------------------------------------------------
    # Task 4 Fix 4C2：非-watch Kubernetes I/O 一律帶 5 秒 _request_timeout
    # watcher.stream 已依 remaining budget 動態傳 1–5 秒 timeout，不在此限。
    # ------------------------------------------------------------------
    def test_k8s_io_timeout_seconds_constant_is_five(self):
        """executor 對外揭露單一固定 I/O timeout 常數為 5 秒。"""
        self.assertEqual(
            KubernetesSqlmapExecutor.K8S_IO_TIMEOUT_SECONDS, 5,
        )

    def test_lifecycle_non_watch_calls_carry_5s_io_timeout(self):
        """成功 lifecycle 的 create/list/log/delete 全部帶 _request_timeout=5。

        涵蓋：create_namespaced_job、create_namespaced_secret、
        list_namespaced_pod、read_namespaced_pod_log、
        finally 的 delete_namespaced_job 與 delete_namespaced_secret。
        watcher.stream 不在此測試範圍（另以動態值測試保護）。
        """
        self.make_executor().execute(17, [self.target])

        expected = 5
        self.assertEqual(
            self.batch.create_namespaced_job.call_args.kwargs.get("_request_timeout"),
            expected,
            "create_namespaced_job 必須帶 _request_timeout=5",
        )
        self.assertEqual(
            self.core.create_namespaced_secret.call_args.kwargs.get("_request_timeout"),
            expected,
            "create_namespaced_secret 必須帶 _request_timeout=5",
        )
        self.assertEqual(
            self.core.list_namespaced_pod.call_args.kwargs.get("_request_timeout"),
            expected,
            "list_namespaced_pod 必須帶 _request_timeout=5",
        )
        self.assertEqual(
            self.core.read_namespaced_pod_log.call_args.kwargs.get("_request_timeout"),
            expected,
            "read_namespaced_pod_log 必須帶 _request_timeout=5",
        )
        # finally 的 delete_namespaced_job / delete_namespaced_secret 也帶 5 秒
        delete_job_calls = self.batch.delete_namespaced_job.call_args_list
        self.assertTrue(delete_job_calls, "finally 必須刪除 Job")
        for call in delete_job_calls:
            self.assertEqual(
                call.kwargs.get("_request_timeout"), expected,
                "delete_namespaced_job 必須帶 _request_timeout=5",
            )
        delete_secret_calls = self.core.delete_namespaced_secret.call_args_list
        self.assertTrue(delete_secret_calls, "finally 必須刪除 Secret")
        for call in delete_secret_calls:
            self.assertEqual(
                call.kwargs.get("_request_timeout"), expected,
                "delete_namespaced_secret 必須帶 _request_timeout=5",
            )

    def test_stale_cleanup_list_and_delete_carry_5s_io_timeout(self):
        """stale cleanup 的 list_namespaced_job 與 delete_namespaced_job 也帶 5 秒 timeout。"""
        now = timezone.now()
        old = mock.Mock()
        old.metadata.name = "kali-stale-old"
        old.metadata.creation_timestamp = now - timedelta(seconds=10_000)
        old.spec.active_deadline_seconds = 120
        # 只放舊 Job，避免新建立的 Job 在這次 list 中被誤判
        self.batch.list_namespaced_job.return_value = mock.Mock(items=[old])

        self.make_executor().execute(17, [self.target])

        # stale list 帶 5 秒
        self.assertEqual(
            self.batch.list_namespaced_job.call_args.kwargs.get("_request_timeout"),
            5,
            "list_namespaced_job(stale cleanup) 必須帶 _request_timeout=5",
        )
        # stale delete 為 delete_namespaced_job 第一個 call，name 為 stale job
        stale_delete_call = self.batch.delete_namespaced_job.call_args_list[0]
        self.assertEqual(
            stale_delete_call.kwargs.get("name"), "kali-stale-old",
        )
        self.assertEqual(
            stale_delete_call.kwargs.get("_request_timeout"), 5,
            "delete_namespaced_job(stale cleanup) 必須帶 _request_timeout=5",
        )

    def test_watch_stream_keeps_dynamic_request_timeout_after_fix(self):
        """Fix 4C2 後 watcher.stream 仍用動態 _request_timeout，不可固定為 5。"""
        self.clock.t = 0
        call_count = {"n": 0}

        def stream_side(*a, **k):
            call_count["n"] += 1
            if call_count["n"] == 1:
                self.clock.t += 3
            else:
                self.clock.t += k.get("timeout_seconds", 5)
            return []

        self.watcher.stream.side_effect = stream_side

        self.make_executor()._watch_and_collect(
            scan_job_id=17,
            correlation_id="test-corr-id",
            namespace="argus-kali",
            job_name="argus-sqlmap-test",
            deadline=150,
            targets=[self.target],
            token="test-token",
        )

        # 每片 _request_timeout 必須 <= 該片 timeout_seconds（動態）
        for call in self.watcher.stream.call_args_list:
            req_timeout = call.kwargs.get("_request_timeout")
            timeout_seconds = call.kwargs.get("timeout_seconds")
            self.assertIsNotNone(req_timeout, "watch _request_timeout 不可缺失")
            self.assertIsNotNone(timeout_seconds, "watch timeout_seconds 不可缺失")
            self.assertLessEqual(
                req_timeout, timeout_seconds,
                "watch _request_timeout 不得超過該片 timeout_seconds",
            )
        # 最後一片 remaining=2：明確驗證動態值，非固定 5
        last_call = self.watcher.stream.call_args_list[-1]
        self.assertEqual(last_call.kwargs["timeout_seconds"], 2)
        self.assertEqual(last_call.kwargs["_request_timeout"], 2)
