"""後台「系統健康」的 Kubernetes 叢集視角：節點與 Argus 工作負載。

為什麼要有：正式環境是 1 master + 3 worker 的 K8s，原本的系統資源卡只量「回應這個請求的
那一個 web pod 容器」，看不出叢集整體——某個 worker 節點 NotReady、worker pod 一直
CrashLoopBackOff，舊頁面一樣全綠。

設計：
- 只讀：nodes、pods（全叢集，list/get）與 metrics.k8s.io（有裝 metrics-server 才有實際用量，
  沒裝就退回 requests 佔比，並明講「requests」不是「使用量」）。
  RBAC 在 k8s/13-cluster-status-rbac.yaml。
- 不在 Kubernetes 內（本機 runserver、CI）時回 ``available=False`` 並寫明原因，不噴錯。
- API 物件只走屬性存取，測試用 SimpleNamespace 假物件即可，不需要真叢集。
- 每次呼叫都是即時探測，逾時短（``REQUEST_TIMEOUT_SECONDS``），避免健康頁被 API Server 卡住。
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from decimal import Decimal

from kubernetes.utils import parse_quantity

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 3
# 這些 namespace 的 pod 列為「Argus 工作負載」；其他 namespace 的 pod 只計入節點負載
ARGUS_NAMESPACES = ("argus", "argus-zap", "argus-kali")
# 節點標籤：有任一就是 control plane
CONTROL_PLANE_LABELS = ("node-role.kubernetes.io/control-plane", "node-role.kubernetes.io/master")


def in_cluster() -> bool:
    """pod 內一定有這個環境變數（kubelet 注入）；沒有就不是在叢集裡。"""
    return bool(os.environ.get("KUBERNETES_SERVICE_HOST"))


def _cpu(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(parse_quantity(value))
    except (ValueError, ArithmeticError):
        return None


def _bytes(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(Decimal(parse_quantity(value)))
    except (ValueError, ArithmeticError):
        return None


def _percent(part, whole) -> int | None:
    if part is None or not whole:
        return None
    # 四捨五入（不用 round 的銀行家捨入：12.5% 應顯示 13%）
    return max(0, min(100, int(part / whole * 100 + 0.5)))


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value)


def _node_role(labels: dict | None) -> str:
    labels = labels or {}
    return "master" if any(key in labels for key in CONTROL_PLANE_LABELS) else "worker"


def _condition(conditions, type_name: str):
    for cond in conditions or []:
        if getattr(cond, "type", None) == type_name:
            return cond
    return None


def _pod_requests(pod) -> tuple[float, int]:
    """一個 pod 的 CPU（核）與記憶體（bytes）requests 合計；init container 不算（跑完就釋放）。"""
    cpu = 0.0
    mem = 0
    for container in getattr(pod.spec, "containers", None) or []:
        resources = getattr(container, "resources", None)
        requests = getattr(resources, "requests", None) or {}
        cpu += _cpu(requests.get("cpu")) or 0.0
        mem += _bytes(requests.get("memory")) or 0
    return cpu, mem


def _pod_app(pod) -> str:
    labels = getattr(pod.metadata, "labels", None) or {}
    return (
        labels.get("app")
        or labels.get("app.kubernetes.io/name")
        or labels.get("job-name")
        or pod.metadata.name
    )


def _pod_status(pod) -> tuple[str, str, bool, int]:
    """回 (phase, 原因, 是否全部 ready, 重啟次數合計)。

    原因優先取 container 的 waiting reason
    （CrashLoopBackOff、ImagePullBackOff 比 phase=Running 有用）。
    """
    status = pod.status
    phase = getattr(status, "phase", None) or "Unknown"
    reason = getattr(status, "reason", None) or ""
    ready = True
    restarts = 0
    statuses = getattr(status, "container_statuses", None) or []
    if not statuses:
        ready = False
    for cs in statuses:
        restarts += int(getattr(cs, "restart_count", 0) or 0)
        if not getattr(cs, "ready", False):
            ready = False
        state = getattr(cs, "state", None)
        waiting = getattr(state, "waiting", None)
        terminated = getattr(state, "terminated", None)
        if waiting is not None and getattr(waiting, "reason", None):
            reason = waiting.reason
        elif (
            terminated is not None and getattr(terminated, "reason", None) and phase != "Succeeded"
        ):
            reason = terminated.reason
    if phase == "Succeeded":
        ready = True
    return phase, reason, ready, restarts


def _node_metrics(custom_api) -> tuple[dict[str, dict], dict]:
    """metrics.k8s.io 的節點用量；沒裝 metrics-server 或沒權限時回空表＋原因。"""
    if custom_api is None:
        return {}, {"available": False, "reason": "未提供 metrics API client"}
    try:
        payload = custom_api.list_cluster_custom_object(
            "metrics.k8s.io",
            "v1beta1",
            "nodes",
            _request_timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 — 任何失敗都只影響「用量」欄位，不影響整頁
        status_code = getattr(exc, "status", None)
        if status_code == 404:
            reason = "叢集沒有安裝 metrics-server"
        elif status_code == 403:
            reason = "沒有讀取 metrics.k8s.io 的權限"
        else:
            reason = f"讀取失敗：{type(exc).__name__}"
        return {}, {"available": False, "reason": reason}
    usage: dict[str, dict] = {}
    for item in payload.get("items", []) if isinstance(payload, dict) else []:
        name = (item.get("metadata") or {}).get("name")
        used = item.get("usage") or {}
        if name:
            usage[name] = {"cpu": _cpu(used.get("cpu")), "memory": _bytes(used.get("memory"))}
    return usage, {"available": True, "reason": ""}


def summarize(nodes_list, pods_list, metrics_usage: dict[str, dict], metrics_info: dict) -> dict:
    """把 API 物件整理成前端要的結構。拆成純函式是為了讓測試不需要真叢集。"""
    # 先把 pod 依節點彙整：requests、數量、Argus 工作負載
    per_node_cpu: dict[str, float] = {}
    per_node_mem: dict[str, int] = {}
    per_node_pods: dict[str, int] = {}
    workloads: dict[tuple[str, str], dict] = {}
    for pod in pods_list:
        phase, reason, ready, restarts = _pod_status(pod)
        node_name = getattr(pod.spec, "node_name", None) or ""
        # 已結束的 pod（Job 跑完、被驅逐）不佔節點資源
        if phase not in ("Succeeded", "Failed") and node_name:
            cpu, mem = _pod_requests(pod)
            per_node_cpu[node_name] = per_node_cpu.get(node_name, 0.0) + cpu
            per_node_mem[node_name] = per_node_mem.get(node_name, 0) + mem
            per_node_pods[node_name] = per_node_pods.get(node_name, 0) + 1
        namespace = pod.metadata.namespace
        if namespace in ARGUS_NAMESPACES:
            key = (namespace, _pod_app(pod))
            entry = workloads.setdefault(
                key,
                {
                    "app": key[1],
                    "namespace": namespace,
                    "pods": [],
                    "ready": 0,
                    "total": 0,
                },
            )
            entry["pods"].append(
                {
                    "name": pod.metadata.name,
                    "node": node_name or None,
                    "phase": phase,
                    "reason": reason,
                    "ready": ready,
                    "restarts": restarts,
                    "started_at": _iso(getattr(pod.status, "start_time", None)),
                }
            )
            if phase not in ("Succeeded", "Failed"):
                entry["total"] += 1
                entry["ready"] += 1 if ready else 0

    nodes = []
    for node in nodes_list:
        name = node.metadata.name
        labels = getattr(node.metadata, "labels", None) or {}
        status = node.status
        ready_cond = _condition(getattr(status, "conditions", None), "Ready")
        is_ready = getattr(ready_cond, "status", None) == "True"
        pressures = [
            cond_type
            for cond_type in ("MemoryPressure", "DiskPressure", "PIDPressure")
            if getattr(_condition(getattr(status, "conditions", None), cond_type), "status", None)
            == "True"
        ]
        capacity = getattr(status, "capacity", None) or {}
        allocatable = getattr(status, "allocatable", None) or {}
        node_info = getattr(status, "node_info", None)
        cpu_alloc = _cpu(allocatable.get("cpu"))
        mem_alloc = _bytes(allocatable.get("memory"))
        usage = metrics_usage.get(name) or {}
        cpu_req = per_node_cpu.get(name, 0.0)
        mem_req = per_node_mem.get(name, 0)
        internal_ip = next(
            (
                addr.address
                for addr in getattr(status, "addresses", None) or []
                if getattr(addr, "type", None) == "InternalIP"
            ),
            None,
        )
        # 不可排程（cordon）也要讓人看到：節點 Ready 但不收新 pod
        unschedulable = bool(getattr(node.spec, "unschedulable", False))
        nodes.append(
            {
                "name": name,
                "role": _node_role(labels),
                "ready": is_ready,
                "unschedulable": unschedulable,
                "pressures": pressures,
                "kubelet_version": getattr(node_info, "kubelet_version", None),
                "os_image": getattr(node_info, "os_image", None),
                "internal_ip": internal_ip,
                "pods": per_node_pods.get(name, 0),
                "pods_capacity": _cpu(capacity.get("pods")) and int(_cpu(capacity.get("pods"))),
                "cpu": {
                    "capacity": _cpu(capacity.get("cpu")),
                    "allocatable": cpu_alloc,
                    "requests": round(cpu_req, 3),
                    "requests_percent": _percent(cpu_req, cpu_alloc),
                    "usage": usage.get("cpu"),
                    "usage_percent": _percent(usage.get("cpu"), cpu_alloc),
                },
                "memory": {
                    "capacity_bytes": _bytes(capacity.get("memory")),
                    "allocatable_bytes": mem_alloc,
                    "requests_bytes": mem_req,
                    "requests_percent": _percent(mem_req, mem_alloc),
                    "usage_bytes": usage.get("memory"),
                    "usage_percent": _percent(usage.get("memory"), mem_alloc),
                },
            }
        )
    # master 排最前，其餘依名稱
    nodes.sort(key=lambda n: (0 if n["role"] == "master" else 1, n["name"]))

    workload_rows = sorted(
        workloads.values(), key=lambda w: (w["namespace"] != "argus", w["namespace"], w["app"])
    )
    for row in workload_rows:
        row["pods"].sort(key=lambda p: p["name"])

    ready_nodes = sum(1 for n in nodes if n["ready"])
    return {
        "available": True,
        "reason": "",
        "metrics": metrics_info,
        "totals": {
            "nodes": len(nodes),
            "nodes_ready": ready_nodes,
            "pods": sum(per_node_pods.values()),
            "argus_pods": sum(w["total"] for w in workload_rows),
        },
        "nodes": nodes,
        "workloads": workload_rows,
    }


def health_check(cluster: dict) -> dict:
    """給 system_health 的 checks 列一項：節點是否全部 Ready、工作負載是否都就緒。"""
    if not cluster.get("available"):
        return {
            "key": "cluster",
            "label": "Kubernetes 叢集",
            "status": "unknown",
            "detail": cluster.get("reason") or "無法取得叢集狀態",
            "basis": "Kubernetes API：nodes、pods（唯讀）",
        }
    totals = cluster["totals"]
    not_ready = [n["name"] for n in cluster["nodes"] if not n["ready"]]
    pressured = [
        f"{n['name']}（{', '.join(n['pressures'])}）" for n in cluster["nodes"] if n["pressures"]
    ]
    degraded = [
        f"{w['namespace']}/{w['app']} {w['ready']}/{w['total']}"
        for w in cluster["workloads"]
        if w["total"] and w["ready"] < w["total"]
    ]
    if not_ready:
        status, detail = "bad", f"節點 NotReady：{', '.join(not_ready)}"
    elif degraded:
        status, detail = "warn", f"工作負載未全部就緒：{', '.join(degraded)}"
    elif pressured:
        status, detail = "warn", f"節點資源壓力：{', '.join(pressured)}"
    else:
        status = "ok"
        detail = (
            f"{totals['nodes_ready']}/{totals['nodes']} 個節點 Ready，"
            f"Argus {totals['argus_pods']} 個 pod 全部就緒"
        )
    return {
        "key": "cluster",
        "label": "Kubernetes 叢集",
        "status": status,
        "detail": detail,
        "basis": "Kubernetes API：node conditions、pod containerStatuses",
    }


def collect(core_api=None, custom_api=None) -> dict:
    """即時讀取叢集狀態。不在叢集內、沒權限或 API 失敗時回 available=False＋原因。"""
    if core_api is None:
        if not in_cluster():
            return {"available": False, "reason": "未在 Kubernetes 內執行（本機或 CI）"}
        try:
            from kubernetes import client, config

            config.load_incluster_config()
            core_api = client.CoreV1Api()
            custom_api = custom_api or client.CustomObjectsApi()
        except Exception as exc:  # noqa: BLE001 — 設定載入失敗也要誠實回報，不噴 500
            return {"available": False, "reason": f"無法載入 in-cluster 設定：{type(exc).__name__}"}
    try:
        nodes = core_api.list_node(_request_timeout=REQUEST_TIMEOUT_SECONDS).items
        pods = core_api.list_pod_for_all_namespaces(_request_timeout=REQUEST_TIMEOUT_SECONDS).items
    except Exception as exc:  # noqa: BLE001
        status_code = getattr(exc, "status", None)
        if status_code == 403:
            reason = (
                "ServiceAccount 沒有讀取 nodes／pods 的權限（檢查 k8s/13-cluster-status-rbac.yaml）"
            )
        else:
            reason = f"Kubernetes API 讀取失敗：{type(exc).__name__}"
        logger.warning("cluster status unavailable: %s", exc)
        return {"available": False, "reason": reason}
    usage, metrics_info = _node_metrics(custom_api)
    return summarize(nodes, pods, usage, metrics_info)
