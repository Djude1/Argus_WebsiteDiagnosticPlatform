# 後台系統健康頁改版：Kubernetes 叢集視角（2026-10-19）

## 背景
正式環境是 1 master + 3 worker 的 K8s。原本「系統資源」四張卡量的是「回應這個請求的那一個 web pod 容器」的
CPU／記憶體／磁碟／網路，看不出叢集整體：某台 worker NotReady、worker pod 一直 CrashLoopBackOff，舊頁面照樣全綠。
使用者決策：RBAC 全叢集 pods 唯讀（才算得出每節點 requests 佔比與 pod 數）；舊資源卡縮成一行附註。

## 後端
- `apps/admin_api/cluster_status.py`：`collect()` 在叢集內（`KUBERNETES_SERVICE_HOST`）用 in-cluster config 讀
  nodes、全叢集 pods、metrics.k8s.io（404＝沒裝 metrics-server、403＝沒權限，只影響用量欄位）；`summarize()` 純函式整理成
  節點（角色、Ready、MemoryPressure／DiskPressure／PIDPressure、cordon、容量／可分配、排在其上的 pod requests 合計與佔比、
  用量與佔比、pod 數、kubelet、內部 IP；master 排第一）與 Argus 工作負載（argus／argus-zap／argus-kali 的 pod 依 app 分組：
  就緒／總數、節點、phase 或 waiting reason、重啟、啟動時間；Succeeded 的 Job pod 列出不計入）。
  `health_check()`：NotReady → bad；工作負載未全部就緒或節點壓力 → warn；不在叢集內 → unknown（不影響整體）。
  API 逾時 3 秒；失敗回 `available=false`＋可讀原因，不噴 500。
- `views.system_health`：回應加 `cluster`，checks 加「Kubernetes 叢集」一項（既有測試改為 6 項）。
- 測試 `tests_cluster_status.py`：SimpleNamespace 假 API 物件（requests 合計、master 排序、metrics 用量、工作負載分組、
  health_check 優先序、403 提示 RBAC、404 判沒裝 metrics-server、本機 unknown）。

## k8s
- `13-cluster-status-rbac.yaml`：SA `argus-web`、ClusterRole `argus-cluster-status-reader`（nodes／pods get,list、metrics.k8s.io get,list）、
  ClusterRoleBinding；加入 `kustomization.yaml`；`04-backend.yaml` web Deployment `serviceAccountName: argus-web`。
- egress：web 已在 `application-egress-boundary`（web、worker 共用）對 API Server 10.96.0.1:443／172.16.2.122:6443 放行，不需改 NetworkPolicy。
- 只有 `k8s/**` 與 backend 改動；Argo 自動同步 RBAC，backend image 由 CI build。

## 前端
- `AdminHealthPage.jsx`：整體狀態 → 掃描鏈路 → **叢集節點** → **Argus 工作負載** → 檢查明細 → 頁尾一行「回應這次請求的 web pod：記憶體、程序運行（剛重啟提醒）」。
  本機不在叢集內時叢集區塊顯示原因。
- 新元件 `components/admin/AdminClusterNodes.jsx`（節點卡：角色徽章、Ready 徽章、壓力／cordon 籤、CPU／記憶體條——標明是「用量」還是「requests」、pod 數、kubelet、內部 IP；沿用 `.admin-sys-card` 卡片與進度條樣式）、
  `AdminWorkloads.jsx`（分組表：元件＋就緒數列，底下各 pod；狀態用 `.admin-order-status` 徽章）。
- 刪除 `AdminSystemStats.jsx`（只剩健康頁用；網路速率差分一併移除）。`72-admin-health.css` 加節點卡與工作負載表樣式。
- 文件：`frontend/CLAUDE.md`、`backend/apps/admin_api/CLAUDE.md`、`k8s/README.md`。

## 驗證
- `uv run python backend/manage.py test apps.admin_api`（含新測試與既有 SystemHealthTests）OK；`ruff check backend` 全過。
- 前端 `npm run lint`、`npm run typecheck`、`npx vitest run` 303 全過。
- 根 `tests/`：35 過、1 error 是本機沒有 `kubectl`（`test_kali_k8s_contract` 渲染 kustomize 用），與本次無關。
- YAML 三個檔 `yaml.safe_load_all` 可解析。

## 待實機確認（雲端無法）
1. Argo 同步後 `kubectl -n argus get sa argus-web`、`kubectl auth can-i list nodes --as=system:serviceaccount:argus:argus-web`。
2. web pod 滾動更新後後台 `/admin/health`：四個節點卡、Argus 工作負載表、metrics 是「用量」還是「requests」（看叢集有沒有 metrics-server）。
3. 若叢集區塊顯示「ServiceAccount 沒有讀取 nodes／pods 的權限」→ 檢查 ClusterRoleBinding 是否套用。
