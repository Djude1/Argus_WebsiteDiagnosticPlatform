"""Task 9：Isolated Calico + kind 整合攻擊鏈端對端測試。

涵蓋範圍（brief Step 4/5）：
  1. ``ToolExecutor._probe_sql_injection`` → ``kali_tools.run_sqlmap`` →
     ``KubernetesSqlmapExecutor``（真實 BatchV1Api/CoreV1Api + 真實 Redis）→
     真實 K8s Job + Secret + Watch + ``parse_runner_result`` + cleanup。
  2. ``persist_agent_security_findings`` 落地 rule_id=kali-sqlmap-sqli 的 Finding。
  3. ``calculate_scores``：security<100 且 overall<100（critical finding 必須扣分）。
  4. 並發：兩個 ScanJob 同時跑，argus-kali 同一時間最多 1 個 Running 的
     app=kali-sqlmap Pod（Redis global lock + ResourceQuota 雙重保險）。
  5. 取消：Job 出現後將 ScanJob.status=CANCELLED，``raise_if_cancelled`` 在下個
     checkpoint 拋 ScanCancelled，finally 清掉 Job/Secret；事後 jobs/secrets/pods
     全部 0。
  6. 每個測試結束後：argus-kali 內 jobs / secrets (label argus.io/managed-by=argus)
     與 pods (label app=kali-sqlmap) 三項資源皆為 0（brief Step 5 清單）。

Skip 規則：
  本檔案只在工作流程提供的 CI 環境內執行；單元測試 runner 不會啟動真實叢集。
  ``KALI_INTEGRATION_IMAGE`` 與 ``KALI_TEST_REDIS_URL`` 兩個 env 任一未設，
  整個測試類會以 skipUnless 跳過（不 fail）。
"""

# ---------------------------------------------------------------------------
# Django bootstrap——本檔案位於 backend/ 之外，必須在 import apps.* 之前手動 setup。
# 順序：sys.path → DJANGO_SETTINGS_MODULE → django.setup() → 才能引入 apps.*。
# 下列 lint noqa 都是 E402（module level import not at top of file）。
# ---------------------------------------------------------------------------

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_DIR = _REPO_ROOT / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

import asyncio  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from unittest import mock  # noqa: E402

from apps.agent.findings import persist_agent_security_findings  # noqa: E402
from apps.agent.tools import ToolExecutor  # noqa: E402
from apps.scans.cancellation import ScanCancelled  # noqa: E402
from apps.scans.models import ScanJob  # noqa: E402
from apps.scans.scanners import calculate_scores  # noqa: E402
from apps.scans.security.kali_kubernetes import KubernetesSqlmapExecutor  # noqa: E402
from apps.scans.security.kali_tools import run_sqlmap  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.test import TransactionTestCase, override_settings  # noqa: E402
from kubernetes import client, config  # noqa: E402
from redis import Redis  # noqa: E402

User = get_user_model()

# ---------------------------------------------------------------------------
# 環境設定：CI workflow 必須提供這兩個 env；其中任一缺失就 skip 整個 TestCase。
# ---------------------------------------------------------------------------

RUNNER_IMAGE = os.environ.get(
    "KALI_INTEGRATION_IMAGE",
    # placeholder：skipUnless 會在同一時間確保不會被真的使用。
    "shijie85/argus-kali-runner@sha256:"
    + "0" * 64,
)
REDIS_URL = os.environ.get("KALI_TEST_REDIS_URL", "redis://127.0.0.1:6379/15")
INTEGRATION_ENABLED = bool(os.environ.get("KALI_INTEGRATION_IMAGE")) and bool(
    os.environ.get("KALI_TEST_REDIS_URL")
)

NAMESPACE = "argus-kali"
FIXTURE_ORIGIN = "http://fixture.argus.test"
FIXTURE_URL = f"{FIXTURE_ORIGIN}/?q=phone"

# SQLmap ~150s + Job scheduling + cleanup；上限抓 360s 給單次 run。
SINGLE_RUN_TIMEOUT = 360
# 兩個 run 序號執行（global lock）→ 720s 上限。
CONCURRENT_RUN_TIMEOUT = 720


@unittest.skipUnless(
    INTEGRATION_ENABLED,
    "KALI_INTEGRATION_IMAGE / KALI_TEST_REDIS_URL 未設定；"
    "整合測試只在 CI workflow kali-integration.yml 內執行。",
)
@override_settings(
    ARGUS_KALI_ENABLED=True,
    ARGUS_KALI_BACKEND="kubernetes",
    ARGUS_KALI_RUNNER_IMAGE=RUNNER_IMAGE,
    ARGUS_KALI_REDIS_URL=REDIS_URL,
    ARGUS_KALI_NAMESPACE=NAMESPACE,
)
class KaliIntegrationTests(TransactionTestCase):
    """K8s + Calico + 真實 runner 的整合測試。

    用 TransactionTestCase：避免 SQLite 在 asyncio.to_thread 跨 thread 寫入時
    ``database table is locked``（TestCase 會把每個 test 包進單一 transaction）。
    """

    # ------------------------------------------------------------------
    # setUp / tearDown
    # ------------------------------------------------------------------
    def setUp(self) -> None:
        # brief Step 4：明確載入 kubeconfig（production executor 走 in-cluster config）。
        config.load_kubeconfig()
        self.batch_api = client.BatchV1Api()
        self.core_api = client.CoreV1Api()
        self.redis = Redis.from_url(
            REDIS_URL, socket_connect_timeout=5, socket_timeout=5,
        )
        # 清掉前次失敗留下的 Redis 狀態（global lock / scan 預算）。
        self.redis.flushdb()
        # 清掉叢集中前次失敗留下的 Jobs / Secrets，避免干擾本輪觀測。
        self._cleanup_labelled_resources()

        suffix = f"{int(time.time() * 1000)}"
        self.user = User.objects.create_user(
            username=f"kali_intg_{suffix}", password="x",
        )
        self.scan_job = self._make_scan_job(self.user)

    def tearDown(self) -> None:
        # best-effort 清理；每個 test 結尾會再用 _assert_namespace_clean 精確驗證。
        self._cleanup_labelled_resources()
        try:
            self.redis.flushdb()
        except Exception:  # noqa: BLE001 - teardown 不可擲
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _make_scan_job(user) -> ScanJob:
        """建立一個授權過、scan_mode=active、origin=fixture.argus.test 的 ScanJob。"""
        return ScanJob.objects.create(
            user=user,
            original_url=FIXTURE_URL,
            normalized_url=FIXTURE_URL,
            origin=FIXTURE_ORIGIN,
            status=ScanJob.Status.QUEUED,
            scan_mode=ScanJob.ScanMode.ACTIVE,
            active_testing_authorized=True,
        )

    def _make_executor(self) -> KubernetesSqlmapExecutor:
        """產生一個接到真實 batch/core API + 真實 Redis 的 K8s executor。"""
        return KubernetesSqlmapExecutor(
            batch_api=self.batch_api,
            core_api=self.core_api,
            redis_client=self.redis,
        )

    def _cleanup_labelled_resources(self) -> None:
        """刪除 argus-kali 內所有 argus.io/managed-by=argus 的 Job/Secret（best-effort）。"""
        propagation = client.V1DeleteOptions(propagation_policy="Foreground")
        try:
            jobs = self.batch_api.list_namespaced_job(
                NAMESPACE, label_selector="argus.io/managed-by=argus",
                _request_timeout=10,
            )
            for item in jobs.items or []:
                name = item.metadata.name
                try:
                    self.batch_api.delete_namespaced_job(
                        name=name, namespace=NAMESPACE, body=propagation,
                        _request_timeout=10,
                    )
                except Exception:  # noqa: BLE001 - best-effort
                    pass
        except Exception:  # noqa: BLE001 - best-effort
            pass
        try:
            secrets = self.core_api.list_namespaced_secret(
                NAMESPACE, label_selector="argus.io/managed-by=argus",
                _request_timeout=10,
            )
            for item in secrets.items or []:
                name = item.metadata.name
                try:
                    self.core_api.delete_namespaced_secret(
                        name=name, namespace=NAMESPACE, _request_timeout=10,
                    )
                except Exception:  # noqa: BLE001 - best-effort
                    pass
        except Exception:  # noqa: BLE001 - best-effort
            pass

    def _wait_pod_count_zero(
        self, label_selector: str, timeout: float = 60.0,
    ) -> None:
        """輪詢直到指定 label 的 Pod 數為 0；超時即讓後續 assert 失敗。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            pods = self.core_api.list_namespaced_pod(
                NAMESPACE, label_selector=label_selector, _request_timeout=10,
            )
            if not (pods.items or []):
                return
            time.sleep(2)

    def _assert_namespace_clean(self) -> None:
        """brief Step 5：每個 test 結束後 jobs/secrets/pods 三項資源皆為 0。"""
        # 等待 Pod 終止（Foreground deletion 可能花數秒）。
        self._wait_pod_count_zero("app=kali-sqlmap", timeout=90)

        jobs = self.batch_api.list_namespaced_job(
            NAMESPACE, label_selector="argus.io/managed-by=argus", _request_timeout=10,
        )
        secrets = self.core_api.list_namespaced_secret(
            NAMESPACE, label_selector="argus.io/managed-by=argus", _request_timeout=10,
        )
        pods = self.core_api.list_namespaced_pod(
            NAMESPACE, label_selector="app=kali-sqlmap", _request_timeout=10,
        )
        job_names = [j.metadata.name for j in (jobs.items or [])]
        secret_names = [s.metadata.name for s in (secrets.items or [])]
        pod_names = [p.metadata.name for p in (pods.items or [])]
        assert not job_names, f"殘留 Jobs: {job_names}"
        assert not secret_names, f"殘留 Secrets: {secret_names}"
        assert not pod_names, f"殘留 Pods: {pod_names}"

    def _patched_executor_for_backend(self, real_executor: KubernetesSqlmapExecutor):
        """把 apps.scans.security.kali_tools._executor_for_backend 換成 real_executor。"""
        return mock.patch(
            "apps.scans.security.kali_tools._executor_for_backend",
            return_value=real_executor,
        )

    # ------------------------------------------------------------------
    # Step 4：Agent tool → 真實 K8s Job → Finding → scoring
    # ------------------------------------------------------------------
    def test_agent_tool_creates_real_job_finding_and_score(self) -> None:
        page = mock.MagicMock()
        page.url = f"{FIXTURE_ORIGIN}/"
        executor = ToolExecutor(
            page=page,
            screenshot_dir=str(_REPO_ROOT / ".tmp" / "agent_screenshots"),
            scan_job=self.scan_job,
        )
        real_executor = self._make_executor()
        with self._patched_executor_for_backend(real_executor):
            outcome = asyncio.run(
                executor.run("probe_sql_injection", {"url": FIXTURE_URL})
            )

        # 1. sqlmap 必須確認可注入。
        self.assertTrue(
            outcome.result.get("confirmed"),
            f"expected confirmed=True, got outcome={outcome.result!r}",
        )
        self.assertIsNotNone(outcome.security_finding)

        # 2. 落地成 Finding，rule_id 必須是 kali-sqlmap-sqli（A03/CWE-89）。
        created = persist_agent_security_findings(
            self.scan_job, [outcome.security_finding],
        )
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].rule_id, "kali-sqlmap-sqli")
        self.assertEqual(created[0].category, "security")
        self.assertEqual(created[0].severity, "critical")

        # 3. calculate_scores：security<100 且 overall<100（critical -35 至少）。
        overall, categories, _actions = calculate_scores(
            [outcome.security_finding],
        )
        self.assertLess(categories["security"], 100)
        self.assertLess(overall, 100)

        # 4. zero-resource cleanup。
        self._assert_namespace_clean()

    # ------------------------------------------------------------------
    # Step 5：並發——同時兩個 ScanJob，max concurrent Running=1
    # ------------------------------------------------------------------
    def test_concurrent_scans_max_one_running_pod(self) -> None:
        user2 = User.objects.create_user(
            username=f"kali_intg_c2_{int(time.time())}", password="x",
        )
        scan2 = self._make_scan_job(user2)

        real_executor = self._make_executor()
        results: list[dict] = []
        errors: list[BaseException] = []

        def _run(scan_job_id: int) -> None:
            try:
                with self._patched_executor_for_backend(real_executor):
                    res = run_sqlmap(FIXTURE_URL, scan_job_id)
                    results.append(res)
            except BaseException as exc:  # noqa: BLE001 - 紀錄後由 assert 判定
                errors.append(exc)

        t1 = threading.Thread(target=_run, args=(self.scan_job.id,), name="scan-1")
        t2 = threading.Thread(target=_run, args=(scan2.id,), name="scan-2")
        t1.start()
        t2.start()

        max_running = 0
        deadline = time.time() + CONCURRENT_RUN_TIMEOUT
        while time.time() < deadline and (t1.is_alive() or t2.is_alive()):
            try:
                pods = self.core_api.list_namespaced_pod(
                    NAMESPACE, label_selector="app=kali-sqlmap", _request_timeout=10,
                )
                running = sum(
                    1
                    for pod in (pods.items or [])
                    if getattr(pod.status, "phase", None) == "Running"
                )
                if running > max_running:
                    max_running = running
            except Exception:  # noqa: BLE001 - 觀測期的 API 例外不中斷 polling
                pass
            time.sleep(3)

        t1.join(timeout=60)
        t2.join(timeout=60)

        self.assertFalse(
            errors, f"threaded run_sqlmap 拋出例外: {errors!r}",
        )
        self.assertEqual(
            len(results), 2, f"expected 2 run_sqlmap results, got {results!r}",
        )
        # 同一時間最多一個 Running 的 runner Pod（global lock + quota）。
        self.assertLessEqual(
            max_running,
            1,
            f"expected max 1 concurrent Running pod, observed {max_running}",
        )
        # 兩個 target 都必須被 sqlmap 確認可注入。
        self.assertTrue(
            all(r.get("confirmed") for r in results),
            f"expected both confirmed, got {results!r}",
        )

        self._assert_namespace_clean()

    # ------------------------------------------------------------------
    # Step 5：取消——Job 出現後 cancel，ScanCancelled + 無殘留
    # ------------------------------------------------------------------
    def test_cancellation_cleans_up_resources(self) -> None:
        real_executor = self._make_executor()
        captured: list[BaseException] = []

        def _run() -> None:
            try:
                with self._patched_executor_for_backend(real_executor):
                    run_sqlmap(FIXTURE_URL, self.scan_job.id)
            except BaseException as exc:  # noqa: BLE001 - 紀錄後由 assert 判定
                captured.append(exc)

        thread = threading.Thread(target=_run, name="scan-cancel")
        thread.start()

        # 等 Job 出現（label argus.io/managed-by=argus）。
        job_appeared = False
        deadline = time.time() + 90
        while time.time() < deadline:
            try:
                jobs = self.batch_api.list_namespaced_job(
                    NAMESPACE,
                    label_selector="argus.io/managed-by=argus",
                    _request_timeout=10,
                )
                if jobs.items:
                    job_appeared = True
                    break
            except Exception:  # noqa: BLE001 - polling 期例外繼續重試
                pass
            time.sleep(1)

        self.assertTrue(
            job_appeared,
            "Job 從未出現；無法驗證取消流程（可能是 lock 等待過久或 ImagePull 失敗）",
        )

        # 將 ScanJob 設為 CANCELLED；executor 下個 checkpoint 會 raise ScanCancelled。
        ScanJob.objects.filter(pk=self.scan_job.id).update(
            status=ScanJob.Status.CANCELLED,
        )

        thread.join(timeout=SINGLE_RUN_TIMEOUT + 60)

        self.assertFalse(
            thread.is_alive(),
            "run_sqlmap thread 在 cancel 後未於時限內結束",
        )
        self.assertTrue(
            any(isinstance(exc, ScanCancelled) for exc in captured),
            f"預期 ScanCancelled，實際收到: {captured!r}",
        )

        # brief Step 5：cancel 後 jobs / secrets / pods 全部 0。
        self._assert_namespace_clean()


if __name__ == "__main__":
    unittest.main(verbosity=2)
