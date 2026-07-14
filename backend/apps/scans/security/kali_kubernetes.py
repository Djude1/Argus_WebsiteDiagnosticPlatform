"""Kubernetes backend 的 SQLmap executor（Task 4）。

在受限的 Kubernetes Job 中執行 SQLmap runner，取代直接 docker exec。設計目標：

- **可注入**：batch_api / core_api / redis_client / watch_factory / cancel_check /
  monotonic 全部可注入，方便單元測試 mock；production 預設只 ``load_incluster_config()``，
  不 fallback 本機 kubeconfig。
- **單一 owner global lock**：``argus:kali:global-lock`` 以 ``SET NX PX`` 取得，renew /
  release 都用 compare-and-* Lua 比對 owner token；mismatched token 無法續約或釋放。
- **Job-first / Secret-second**：先建 Job 取得 UID，再建一把 owner-referenced Secret，
  內容**只有** ``targets.json``；絕不 read / list Secret。
- **bounded watch**：每片最多 5 秒、每片之間檢查取消，整體上限
  ``min(active_deadline + 30, 420)``；log 以 ``limit_bytes=16385`` 讀取，超過契約上限
  （16384）由 ``parse_runner_result`` 拒絕。
- **cancellation-safe**：取消時 cleanup Job/Secret、釋放自己持有的 lock，並重拋
  ``ScanCancelled``。
- **安全日誌**：``append_log`` 只記 correlation_id、lifecycle phase 與固定 safe error
  code，絕不記 target URL / query value / API exception body / runner raw log。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from kubernetes import client, config, watch

from apps.scans.cancellation import raise_if_cancelled
from apps.scans.scan_logger import append_log

from .kali_contracts import (
    KaliResult,
    KaliResultContractError,
    ReservedSqlmapTarget,
    parse_runner_result,
)

# executor outward KaliResult.error 與 audit code= 固定 taxonomy。
# runner private error_code（如 runner_output_too_large、clean）不在此列——由
# executor 邊界映射為 runner_failed 或空字串，不外洩 runner 自訂分類。
_OUTWARD_ERROR_CODES = frozenset({
    "capacity_timeout",
    "job_create_failed",
    "secret_create_failed",
    "job_deadline_exceeded",
    "runner_failed",
    "invalid_result",
    "cleanup_failed",
})

# owner-token 比對後才允許續約 / 釋放；mismatched token 一律 no-op。
_RENEW_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("PEXPIRE", KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
end
return 0
"""


def build_restricted_runner_pod(secret_name: str, labels: dict[str, str]):
    """建構受限的 runner Pod template（Task 4 Fix 1 契約）。

    - service_account_name="kali-runner"、automount_service_account_token=False
    - Pod security context：runAsNonRoot、UID/GID/fsGroup 全為 65532、RuntimeDefault
    - Container：command=["/usr/local/bin/python"]、args=["/opt/argus/runner.py"]
    - Container security：非 privileged、不可 privilege escalation、read-only root、
      runAsNonRoot、UID/GID 65532、drop ALL
    - 兩個 volumes：targets Secret (default_mode=0o400)、scratch emptyDir (size_limit="1Gi")
    - 兩個 mounts：targets → /run/argus-targets (read-only)、scratch → /tmp
    - resources：cpu/memory/ephemeral-storage requests (250m/256Mi/256Mi) 與 limits (1/768Mi/1Gi)
    """
    return client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels=labels),
        spec=client.V1PodSpec(
            restart_policy="Never",
            service_account_name="kali-runner",
            automount_service_account_token=False,
            security_context=client.V1PodSecurityContext(
                run_as_non_root=True,
                run_as_user=65532,
                run_as_group=65532,
                fs_group=65532,
                seccomp_profile=client.V1SeccompProfile(type="RuntimeDefault"),
            ),
            volumes=[
                client.V1Volume(
                    name="targets",
                    secret=client.V1SecretVolumeSource(
                        secret_name=secret_name,
                        default_mode=256,  # 0o400
                    ),
                ),
                client.V1Volume(
                    name="scratch",
                    empty_dir=client.V1EmptyDirVolumeSource(
                        size_limit="1Gi",
                    ),
                ),
            ],
            containers=[
                client.V1Container(
                    name="sqlmap-runner",
                    image=settings.ARGUS_KALI_RUNNER_IMAGE,
                    image_pull_policy="IfNotPresent",
                    command=["/usr/local/bin/python"],
                    args=["/opt/argus/runner.py"],
                    volume_mounts=[
                        client.V1VolumeMount(
                            name="targets",
                            mount_path="/run/argus-targets",
                            read_only=True,
                        ),
                        client.V1VolumeMount(
                            name="scratch",
                            mount_path="/tmp",
                        ),
                    ],
                    security_context=client.V1SecurityContext(
                        privileged=False,
                        allow_privilege_escalation=False,
                        read_only_root_filesystem=True,
                        run_as_non_root=True,
                        run_as_user=65532,
                        run_as_group=65532,
                        capabilities=client.V1Capabilities(drop=["ALL"]),
                    ),
                    resources=client.V1ResourceRequirements(
                        limits={
                            "cpu": "1",
                            "memory": "768Mi",
                            "ephemeral-storage": "1Gi",
                        },
                        requests={
                            "cpu": "250m",
                            "memory": "256Mi",
                            "ephemeral-storage": "256Mi",
                        },
                    ),
                ),
            ],
        ),
    )


class KubernetesSqlmapExecutor:
    """在受限 Kubernetes Job 中執行 SQLmap runner 的 executor。

    一個 ScanJob 一次 execute 對應一個 Job + 一把 owner Secret；所有 target 的結果
    在同一個 runner process 內產出，由 Pod log 回傳後交給 ``parse_runner_result``。
    """

    LOCK_KEY = "argus:kali:global-lock"
    WATCH_SLICE_SECONDS = 5
    RENEW_INTERVAL_SECONDS = 60
    LOG_LIMIT_BYTES = 16385

    def __init__(
        self,
        *,
        batch_api=None,
        core_api=None,
        redis_client=None,
        watch_factory=watch.Watch,
        cancel_check: Callable[[int], None] = raise_if_cancelled,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        # production 預設只走 in-cluster config；測試與整合環境注入已設定的 client。
        if batch_api is None or core_api is None:
            config.load_incluster_config()
        self.batch = batch_api or client.BatchV1Api()
        self.core = core_api or client.CoreV1Api()
        self.redis = redis_client or _default_redis()
        self.watch_factory = watch_factory
        self.cancel_check = cancel_check
        self.monotonic = monotonic

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def execute(
        self,
        scan_job_id: int,
        targets: Sequence[ReservedSqlmapTarget],
    ) -> tuple[KaliResult, ...]:
        namespace = settings.ARGUS_KALI_NAMESPACE
        correlation_id = self._correlation_id(scan_job_id)
        deadline = self._compute_deadline(targets)

        token = self._acquire_global_lock(scan_job_id, correlation_id)
        if token is None:
            self._safe_log(scan_job_id, correlation_id, "lock", "capacity_timeout")
            return tuple(
                KaliResult(ok=False, error="capacity_timeout") for _ in targets
            )

        job_name = self._job_name(correlation_id)
        secret_name = self._secret_name(job_name)
        labels = {
            "managed-by": "argus",
            "component": "kali-sqlmap",
            "argus.io/managed-by": "argus",
            "app": "kali-sqlmap",
        }
        job_uid: str | None = None
        try:
            self._cleanup_stale_jobs(scan_job_id, correlation_id, namespace)
            if not self._renew_lock(token):
                self._safe_log(scan_job_id, correlation_id, "lock", "runner_failed")
                return tuple(
                    KaliResult(ok=False, error="runner_failed") for _ in targets
                )
            job_uid = self._create_job(
                scan_job_id, correlation_id, namespace, job_name, secret_name, labels, deadline,
            )
            if job_uid is None:
                return tuple(
                    KaliResult(ok=False, error="job_create_failed") for _ in targets
                )
            if not self._renew_lock(token):
                self._safe_log(scan_job_id, correlation_id, "lock", "runner_failed")
                return tuple(
                    KaliResult(ok=False, error="runner_failed") for _ in targets
                )
            if not self._create_secret(
                scan_job_id, correlation_id, namespace, secret_name, labels,
                job_name, job_uid, targets,
            ):
                return tuple(
                    KaliResult(ok=False, error="secret_create_failed") for _ in targets
                )
            if not self._renew_lock(token):
                self._safe_log(scan_job_id, correlation_id, "lock", "runner_failed")
                return tuple(
                    KaliResult(ok=False, error="runner_failed") for _ in targets
                )
            return self._watch_and_collect(
                scan_job_id, correlation_id, namespace, job_name, deadline, targets, token,
            )
        finally:
            # 不論成功、失敗或取消，一律嘗試刪除 Job/Secret 並釋放自己持有的 lock。
            self._delete_job(scan_job_id, correlation_id, namespace, job_name)
            self._delete_secret(scan_job_id, correlation_id, namespace, secret_name)
            self._release_lock(scan_job_id, correlation_id, token)

    # ------------------------------------------------------------------
    # Global lock ownership
    # ------------------------------------------------------------------
    def _acquire_global_lock(
        self, scan_job_id: int, correlation_id: str,
    ) -> str | None:
        token = secrets.token_hex(16)
        wait_seconds = settings.ARGUS_KALI_LOCK_WAIT_SECONDS
        lease_ms = settings.ARGUS_KALI_LOCK_LEASE_SECONDS * 1000
        deadline = self.monotonic() + wait_seconds
        self._safe_log(scan_job_id, correlation_id, "lock_acquire")
        while self.monotonic() < deadline:
            self.cancel_check(scan_job_id)
            try:
                if self.redis.set(self.LOCK_KEY, token, nx=True, px=lease_ms):
                    return token
            except Exception:
                return None
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(1, remaining))
        return None

    def _renew_lock(self, token: str) -> bool:
        lease_ms = settings.ARGUS_KALI_LOCK_LEASE_SECONDS * 1000
        try:
            result = self.redis.eval(_RENEW_LUA, 1, self.LOCK_KEY, token, lease_ms)
        except Exception:
            return False
        return result == 1

    def _release_lock(
        self, scan_job_id: int, correlation_id: str, token: str,
    ) -> None:
        try:
            result = self.redis.eval(_RELEASE_LUA, 1, self.LOCK_KEY, token)
        except Exception:
            self._safe_log(scan_job_id, correlation_id, "lock", "cleanup_failed")
            return
        if result == 1:
            self._safe_log(scan_job_id, correlation_id, "lock_released")
        else:
            self._safe_log(scan_job_id, correlation_id, "lock", "cleanup_failed")

    # ------------------------------------------------------------------
    # Naming & deadline
    # ------------------------------------------------------------------
    def _correlation_id(self, scan_job_id: int) -> str:
        hmac_part = hmac.new(
            settings.SECRET_KEY.encode(),
            f"kali:{scan_job_id}".encode(),
            hashlib.sha256,
        ).hexdigest()[:10]
        token_part = secrets.token_hex(6)
        return f"{hmac_part}-{token_part}"

    def _job_name(self, correlation_id: str) -> str:
        return f"argus-sqlmap-{correlation_id}"

    def _secret_name(self, job_name: str) -> str:
        # secret_name 不再依賴 job_name，直接用 correlation_id
        # 從 job_name 提取 correlation_id: argus-sqlmap-{corr_id}
        correlation_id = job_name.replace("argus-sqlmap-", "")
        return f"argus-targets-{correlation_id}"

    def _compute_deadline(
        self, targets: Sequence[ReservedSqlmapTarget],
    ) -> int:
        return min(len(targets) * settings.ARGUS_KALI_TIMEOUT + 30, 390)

    # ------------------------------------------------------------------
    # Stale Job cleanup（建立新 Job 之前）
    # ------------------------------------------------------------------
    def _cleanup_stale_jobs(
        self, scan_job_id: int, correlation_id: str, namespace: str,
    ) -> None:
        try:
            resp = self.batch.list_namespaced_job(
                namespace, label_selector="managed-by=argus,component=kali-sqlmap",
            )
        except Exception:
            self._safe_log(scan_job_id, correlation_id, "stale_list", "cleanup_failed")
            return
        now = timezone.now()
        for item in (getattr(resp, "items", None) or []):
            meta = getattr(item, "metadata", None)
            if meta is None:
                continue
            spec = getattr(item, "spec", None)
            created = getattr(meta, "creation_timestamp", None)
            name = getattr(meta, "name", None)
            # 每個 Job 用自己的 active_deadline_seconds 判斷，不得套用新請求的 deadline。
            # 嚴格 type(active_deadline_seconds) is int（bool 不算）且 > 0 才有效。
            active = (
                getattr(spec, "active_deadline_seconds", None)
                if spec is not None else None
            )
            if not name or created is None:
                continue
            if type(active) is not int or active <= 0:
                continue
            expires_at = created + timedelta(seconds=active + 30)
            # 剛好等於 boundary 不刪，必須嚴格 now > expires_at。
            if now > expires_at:
                self._delete_job(scan_job_id, correlation_id, namespace, name)

    # ------------------------------------------------------------------
    # Job-first / Secret-second lifecycle
    # ------------------------------------------------------------------
    def _create_job(
        self, scan_job_id, correlation_id, namespace, job_name, secret_name, labels, deadline,
    ) -> str | None:
        job_obj = client.V1Job(
            metadata=client.V1ObjectMeta(
                name=job_name, namespace=namespace, labels=labels,
            ),
            spec=client.V1JobSpec(
                parallelism=1,
                completions=1,
                backoff_limit=0,
                ttl_seconds_after_finished=settings.ARGUS_KALI_TTL_AFTER_FINISHED_SECONDS,
                active_deadline_seconds=deadline,
                template=build_restricted_runner_pod(secret_name, labels),
            ),
        )
        try:
            response = self.batch.create_namespaced_job(namespace, job_obj)
        except Exception:
            self._safe_log(scan_job_id, correlation_id, "create", "job_create_failed")
            return None
        uid = self._extract_uid(response)
        if uid is None:
            self._safe_log(scan_job_id, correlation_id, "create", "job_create_failed")
            return None
        self._safe_log(scan_job_id, correlation_id, "job_created")
        return uid

    def _create_secret(
        self, scan_job_id, correlation_id, namespace, secret_name, labels,
        job_name, job_uid, targets,
    ) -> bool:
        # 契約格式：{"schema_version": 1, "scan_id": N, "targets": [{"index": 0, "url": "..."}]}
        # 不得包含 fingerprint
        targets_json = json.dumps(
            {
                "schema_version": 1,
                "scan_id": scan_job_id,
                "targets": [
                    {"index": t.index, "url": t.url}
                    for t in targets
                ],
            },
            separators=(",", ":"),  # compact separators
        )
        owner_ref = client.V1OwnerReference(
            api_version="batch/v1",
            kind="Job",
            name=job_name,
            uid=job_uid,
            controller=True,
            block_owner_deletion=True,
        )
        secret_obj = client.V1Secret(
            metadata=client.V1ObjectMeta(
                name=secret_name, namespace=namespace, labels=labels,
                owner_references=[owner_ref],
            ),
            string_data={"targets.json": targets_json},
        )
        try:
            self.core.create_namespaced_secret(namespace, secret_obj)
        except Exception:
            self._safe_log(scan_job_id, correlation_id, "create", "secret_create_failed")
            return False
        self._safe_log(scan_job_id, correlation_id, "secret_created")
        return True

    @staticmethod
    def _extract_uid(response) -> str | None:
        if response is None:
            return None
        meta = getattr(response, "metadata", None)
        return getattr(meta, "uid", None) if meta is not None else None

    # ------------------------------------------------------------------
    # Bounded watch + log collection
    # ------------------------------------------------------------------
    def _watch_and_collect(
        self, scan_job_id, correlation_id, namespace, job_name, deadline, targets, token,
    ) -> tuple[KaliResult, ...]:
        start = self.monotonic()
        watch_limit = min(deadline + 30, 420)
        watch_deadline = start + watch_limit
        last_renew = start
        watcher = self.watch_factory()
        terminal: str | None = None
        while True:
            now = self.monotonic()
            remaining = watch_deadline - now
            if remaining < 1:
                break
            slice_seconds = min(self.WATCH_SLICE_SECONDS, int(remaining))
            self.cancel_check(scan_job_id)
            try:
                events = list(
                    watcher.stream(
                        self.batch.list_namespaced_job,
                        namespace=namespace,
                        field_selector=f"metadata.name={job_name}",
                        label_selector="managed-by=argus,component=kali-sqlmap",
                        timeout_seconds=slice_seconds,
                        _request_timeout=slice_seconds,
                    )
                )
            except Exception:
                self._safe_log(scan_job_id, correlation_id, "watch", "runner_failed")
                return tuple(KaliResult(ok=False, error="runner_failed") for _ in targets)
            for event in events:
                obj = event.get("object") if isinstance(event, dict) else None
                terminal = self._terminal_condition(obj)
                if terminal:
                    break
            if terminal:
                break
            post = self.monotonic()
            if post - last_renew >= self.RENEW_INTERVAL_SECONDS:
                if not self._renew_lock(token):
                    self._safe_log(scan_job_id, correlation_id, "watch", "runner_failed")
                    return tuple(
                        KaliResult(ok=False, error="runner_failed") for _ in targets
                    )
                last_renew = post

        if terminal != "succeeded":
            if terminal == "failed":
                code = "runner_failed"
            else:
                code = "job_deadline_exceeded"
            self._safe_log(scan_job_id, correlation_id, "watch", code)
            return tuple(KaliResult(ok=False, error=code) for _ in targets)

        payload = self._read_runner_log(scan_job_id, correlation_id, namespace, job_name)
        if payload is None:
            return tuple(KaliResult(ok=False, error="runner_failed") for _ in targets)
        try:
            results = parse_runner_result(payload, targets)
        except KaliResultContractError:
            self._safe_log(scan_job_id, correlation_id, "result", "invalid_result")
            return tuple(KaliResult(ok=False, error="invalid_result") for _ in targets)

        # executor 邊界：runner private error_code（空或 "clean" 視為無錯誤；
        # 其他值一律映射為 runner_failed，不外洩 runner 自訂 taxonomy）。
        mapped = tuple(
            replace(
                result,
                error="" if not result.error or result.error == "clean" else "runner_failed",
            )
            for result in results
        )

        enriched = tuple(
            replace(
                result,
                evidence_summary={
                    **result.evidence_summary,
                    "correlation_id": correlation_id,
                    "tool_version": settings.ARGUS_KALI_SQLMAP_VERSION,
                },
            )
            for result in mapped
        )
        self._safe_log(scan_job_id, correlation_id, "completed")
        return enriched

    @staticmethod
    def _terminal_condition(job) -> str | None:
        if job is None:
            return None
        status = getattr(job, "status", None)
        if status is None:
            return None
        conditions = getattr(status, "conditions", None) or []
        for cond in conditions:
            if getattr(cond, "status", None) == "True":
                cond_type = getattr(cond, "type", "")
                if cond_type == "Complete":
                    return "succeeded"
                if cond_type == "Failed":
                    reason = getattr(cond, "reason", "") or ""
                    if reason == "DeadlineExceeded":
                        return "deadline_exceeded"
                    return "failed"
        return None

    def _read_runner_log(self, scan_job_id, correlation_id, namespace, job_name):
        try:
            pods = self.core.list_namespaced_pod(
                namespace, label_selector=f"job-name={job_name}",
            )
        except Exception:
            self._safe_log(scan_job_id, correlation_id, "pod_list", "runner_failed")
            return None
        items = getattr(pods, "items", None) or []
        # Task 4 Fix 3C：只有 exactly one named Pod 才能讀 log。
        # len(items) != 1（零或多於一）一律 outward runner_failed，不讀任何 log。
        # 多於一個時不得任選 items[0]，以免讀到非預期 Pod。
        if len(items) != 1:
            self._safe_log(scan_job_id, correlation_id, "pod_list", "runner_failed")
            return None
        pod_name = getattr(getattr(items[0], "metadata", None), "name", None)
        # 嚴格 type 檢查：必須是 str 且非空。truthiness（not pod_name）無法擋住
        # 非字串值（如 int 12345），會誤把非字串 name 傳給 read_namespaced_pod_log。
        if not isinstance(pod_name, str) or not pod_name:
            self._safe_log(scan_job_id, correlation_id, "pod_list", "runner_failed")
            return None
        try:
            raw = self.core.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                limit_bytes=self.LOG_LIMIT_BYTES,
            )
        except Exception:
            self._safe_log(scan_job_id, correlation_id, "log_read", "runner_failed")
            return None
        if hasattr(raw, "read"):
            return raw.read()
        if isinstance(raw, str):
            return raw.encode("utf-8")
        return raw  # 已是 bytes（測試或 _preload_content=False 的情況）

    # ------------------------------------------------------------------
    # Cleanup（finally）
    # ------------------------------------------------------------------
    def _delete_job(
        self, scan_job_id, correlation_id, namespace, name,
    ) -> None:
        try:
            self.batch.delete_namespaced_job(
                name=name,
                namespace=namespace,
                body=client.V1DeleteOptions(propagation_policy="Foreground"),
            )
        except Exception as exc:
            if self._is_not_found(exc):
                return
            self._safe_log(scan_job_id, correlation_id, "cleanup", "cleanup_failed")

    def _delete_secret(
        self, scan_job_id, correlation_id, namespace, name,
    ) -> None:
        try:
            self.core.delete_namespaced_secret(name=name, namespace=namespace)
        except Exception as exc:
            if self._is_not_found(exc):
                return
            self._safe_log(scan_job_id, correlation_id, "cleanup", "cleanup_failed")

    @staticmethod
    def _is_not_found(exc) -> bool:
        return getattr(exc, "status", None) == 404

    # ------------------------------------------------------------------
    # Safe audit log：只記 correlation_id / phase / safe code
    # ------------------------------------------------------------------
    def _safe_log(
        self, scan_job_id: int, correlation_id: str, phase: str, code: str = "",
    ) -> None:
        msg = f"kali correlation_id={correlation_id} phase={phase}"
        level = "info"
        if code:
            msg += f" code={code}"
            level = "warn"
        append_log(scan_job_id, msg, level=level)


def _default_redis():
    # 延遲 import 避免在模組載入時就要求 Redis 連線設定。
    from .kali_policy import get_kali_redis

    return get_kali_redis()
