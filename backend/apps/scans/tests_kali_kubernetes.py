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
        self.cancel_check.side_effect = [None, ScanCancelled()]
        with self.assertRaises(ScanCancelled):
            self.make_executor().execute(17, [self.target])
        self.batch.delete_namespaced_job.assert_called()
        self.core.delete_namespaced_secret.assert_called()

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
        self.cancel_check.side_effect = [None, ScanCancelled()]

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
