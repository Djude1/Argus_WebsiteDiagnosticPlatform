"""後台系統健康的 Kubernetes 叢集視角：不需要真叢集，用 SimpleNamespace 假 API 物件。"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from apps.admin_api import cluster_status


def _cond(type_name, status):
    return SimpleNamespace(type=type_name, status=status)


def _node(
    name, *, role_label=None, ready="True", cpu="4", memory="8Gi", pressures=(), unschedulable=False
):
    labels = {role_label: ""} if role_label else {}
    conditions = [_cond("Ready", ready)] + [_cond(p, "True") for p in pressures]
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name, labels=labels),
        spec=SimpleNamespace(unschedulable=unschedulable),
        status=SimpleNamespace(
            conditions=conditions,
            capacity={"cpu": cpu, "memory": memory, "pods": "110"},
            allocatable={"cpu": cpu, "memory": memory, "pods": "110"},
            node_info=SimpleNamespace(kubelet_version="v1.35.6", os_image="Ubuntu 24.04"),
            addresses=[SimpleNamespace(type="InternalIP", address="10.0.0.1")],
        ),
    )


def _pod(
    name,
    namespace,
    node,
    *,
    app=None,
    phase="Running",
    ready=True,
    restarts=0,
    waiting_reason=None,
    cpu="500m",
    memory="1Gi",
):
    state = SimpleNamespace(
        waiting=SimpleNamespace(reason=waiting_reason) if waiting_reason else None, terminated=None
    )
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name, namespace=namespace, labels={"app": app} if app else {}
        ),
        spec=SimpleNamespace(
            node_name=node,
            containers=[
                SimpleNamespace(resources=SimpleNamespace(requests={"cpu": cpu, "memory": memory}))
            ],
        ),
        status=SimpleNamespace(
            phase=phase,
            reason=None,
            start_time=datetime(2026, 10, 19, 1, 0, tzinfo=UTC),
            container_statuses=[SimpleNamespace(ready=ready, restart_count=restarts, state=state)],
        ),
    )


class ClusterSummaryTests(SimpleTestCase):
    def setUp(self):
        self.nodes = [
            _node("worker1", cpu="8", memory="16Gi"),
            _node("master", role_label="node-role.kubernetes.io/control-plane"),
            _node("worker2", ready="False"),
        ]
        self.pods = [
            _pod("web-a", "argus", "worker1", app="web"),
            _pod(
                "web-b",
                "argus",
                "worker1",
                app="web",
                ready=False,
                waiting_reason="CrashLoopBackOff",
                restarts=5,
            ),
            _pod("worker-a", "argus", "worker2", app="worker", cpu="1", memory="2Gi"),
            _pod("coredns-x", "kube-system", "master", app="kube-dns", cpu="100m", memory="70Mi"),
            _pod("job-done", "argus", "worker1", app="migrate", phase="Succeeded"),
        ]

    def test_master_first_and_requests_summed_per_node(self):
        data = cluster_status.summarize(
            self.nodes, self.pods, {}, {"available": False, "reason": "沒裝"}
        )
        names = [n["name"] for n in data["nodes"]]
        self.assertEqual(names, ["master", "worker1", "worker2"])
        worker1 = data["nodes"][1]
        # web-a 0.5 核 + web-b 0.5 核；Succeeded 的 job 不算
        self.assertEqual(worker1["cpu"]["requests"], 1.0)
        self.assertEqual(worker1["cpu"]["requests_percent"], 13)  # 1 / 8
        self.assertEqual(worker1["memory"]["requests_bytes"], 2 * 1024**3)
        self.assertEqual(worker1["pods"], 2)
        self.assertEqual(data["nodes"][0]["role"], "master")
        self.assertIsNone(worker1["cpu"]["usage_percent"])
        self.assertFalse(data["metrics"]["available"])

    def test_usage_from_metrics_server_when_available(self):
        usage = {"worker1": {"cpu": 2.0, "memory": 4 * 1024**3}}
        data = cluster_status.summarize(
            self.nodes, self.pods, usage, {"available": True, "reason": ""}
        )
        worker1 = next(n for n in data["nodes"] if n["name"] == "worker1")
        self.assertEqual(worker1["cpu"]["usage_percent"], 25)
        self.assertEqual(worker1["memory"]["usage_percent"], 25)

    def test_workloads_only_argus_namespaces_with_ready_counts(self):
        data = cluster_status.summarize(
            self.nodes, self.pods, {}, {"available": False, "reason": ""}
        )
        apps = {(w["namespace"], w["app"]): w for w in data["workloads"]}
        self.assertNotIn(("kube-system", "kube-dns"), apps)
        web = apps[("argus", "web")]
        self.assertEqual((web["ready"], web["total"]), (1, 2))
        crashing = next(p for p in web["pods"] if p["name"] == "web-b")
        self.assertEqual(crashing["reason"], "CrashLoopBackOff")
        self.assertEqual(crashing["restarts"], 5)
        # 跑完的 Job pod 列出但不計入 total
        self.assertEqual(apps[("argus", "migrate")]["total"], 0)
        self.assertEqual(data["totals"], {"nodes": 3, "nodes_ready": 2, "pods": 4, "argus_pods": 3})

    def test_health_check_prefers_not_ready_over_degraded_workloads(self):
        data = cluster_status.summarize(
            self.nodes, self.pods, {}, {"available": False, "reason": ""}
        )
        check = cluster_status.health_check(data)
        self.assertEqual(check["status"], "bad")
        self.assertIn("worker2", check["detail"])

    def test_health_check_warns_on_degraded_workload_when_nodes_ready(self):
        nodes = [_node("master", role_label="node-role.kubernetes.io/master"), _node("worker1")]
        data = cluster_status.summarize(
            nodes, self.pods[:2], {}, {"available": False, "reason": ""}
        )
        check = cluster_status.health_check(data)
        self.assertEqual(check["status"], "warn")
        self.assertIn("argus/web 1/2", check["detail"])

    def test_health_check_ok_and_pressure_warn(self):
        nodes = [_node("master", role_label="node-role.kubernetes.io/master"), _node("worker1")]
        healthy = [_pod("web-a", "argus", "worker1", app="web")]
        ok = cluster_status.health_check(
            cluster_status.summarize(nodes, healthy, {}, {"available": False, "reason": ""})
        )
        self.assertEqual(ok["status"], "ok")
        pressured = [
            _node("master", role_label="node-role.kubernetes.io/master"),
            _node("worker1", pressures=("MemoryPressure",)),
        ]
        warn = cluster_status.health_check(
            cluster_status.summarize(pressured, healthy, {}, {"available": False, "reason": ""})
        )
        self.assertEqual(warn["status"], "warn")
        self.assertIn("MemoryPressure", warn["detail"])


class ClusterCollectTests(SimpleTestCase):
    def test_outside_cluster_reports_unavailable_without_calling_api(self):
        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("KUBERNETES_SERVICE_HOST", None)
            data = cluster_status.collect()
        self.assertFalse(data["available"])
        self.assertIn("未在 Kubernetes", data["reason"])
        self.assertEqual(cluster_status.health_check(data)["status"], "unknown")

    def test_forbidden_api_reports_rbac_hint(self):
        class Forbidden(Exception):
            status = 403

        class Core:
            def list_node(self, **_):
                raise Forbidden()

            def list_pod_for_all_namespaces(self, **_):
                raise Forbidden()

        data = cluster_status.collect(core_api=Core(), custom_api=None)
        self.assertFalse(data["available"])
        self.assertIn("13-cluster-status-rbac", data["reason"])

    def test_metrics_404_means_no_metrics_server(self):
        class NotFound(Exception):
            status = 404

        class Custom:
            def list_cluster_custom_object(self, *_, **__):
                raise NotFound()

        class Core:
            def list_node(self, **_):
                return SimpleNamespace(
                    items=[_node("master", role_label="node-role.kubernetes.io/master")]
                )

            def list_pod_for_all_namespaces(self, **_):
                return SimpleNamespace(items=[])

        data = cluster_status.collect(core_api=Core(), custom_api=Custom())
        self.assertTrue(data["available"])
        self.assertEqual(data["metrics"]["reason"], "叢集沒有安裝 metrics-server")


class ClusterSnapshotTests(SimpleTestCase):
    """讀取失敗時用最近一次成功的快照墊著（2026-10-21）：健康頁每 15 秒輪詢，API Server
    偶發慢回應就整塊變「無法取得叢集狀態」，像叢集壞了。"""

    def setUp(self):
        cache.delete(cluster_status.SNAPSHOT_CACHE_KEY)

    class _Good:
        def list_node(self, **_):
            return SimpleNamespace(
                items=[_node("master", role_label="node-role.kubernetes.io/master")]
            )

        def list_pod_for_all_namespaces(self, **_):
            return SimpleNamespace(items=[])

    class _Timeout:
        def list_node(self, **_):
            raise TimeoutError()

        def list_pod_for_all_namespaces(self, **_):
            raise TimeoutError()

    def test_success_is_cached_and_marked_fresh(self):
        data = cluster_status.collect(core_api=self._Good(), custom_api=None)
        self.assertTrue(data["available"])
        self.assertFalse(data["stale"])
        self.assertIn("snapshot_at", data)
        self.assertEqual(cache.get(cluster_status.SNAPSHOT_CACHE_KEY)["totals"]["nodes"], 1)

    def test_failure_falls_back_to_snapshot_with_reason(self):
        cluster_status.collect(core_api=self._Good(), custom_api=None)
        data = cluster_status.collect(core_api=self._Timeout(), custom_api=None)
        self.assertTrue(data["available"])
        self.assertTrue(data["stale"])
        self.assertIn("TimeoutError", data["stale_reason"])
        self.assertEqual(data["totals"]["nodes"], 1)
        check = cluster_status.health_check(data)
        self.assertEqual(check["status"], "warn")
        self.assertIn("最近一次讀取失敗", check["detail"])
        self.assertIn("快照", check["detail"])

    def test_failure_without_snapshot_is_unavailable(self):
        data = cluster_status.collect(core_api=self._Timeout(), custom_api=None)
        self.assertFalse(data["available"])
        self.assertIn("TimeoutError", data["reason"])
        self.assertEqual(cluster_status.health_check(data)["status"], "unknown")

    def test_timeout_is_connect_and_read_pair(self):
        connect, read = cluster_status.REQUEST_TIMEOUT
        self.assertLessEqual(connect, 5)
        self.assertGreaterEqual(read, 5)

