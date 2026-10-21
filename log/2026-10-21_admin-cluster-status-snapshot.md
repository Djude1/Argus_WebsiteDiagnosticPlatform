# 後台系統健康：叢集節點偶發「無法取得叢集狀態」→ 放寬逾時＋失敗時顯示快照

**日期**：2026-10-21
**操作者**：Claude

## 變更內容
- `backend/apps/admin_api/cluster_status.py`：
  - 逾時由單一 3 秒改為 `REQUEST_TIMEOUT = (3, 10)`（連線 3 秒、讀取 10 秒）：全叢集 pod 清單偶爾要幾秒，3 秒讀取逾時是偶發失敗的主因。
  - 成功結果寫入 Django cache（`SNAPSHOT_CACHE_KEY`，10 分鐘）並標 `stale=False`、`snapshot_at`；API 讀取失敗時 `_unavailable_or_snapshot` 回最近快照（`stale=True`、`stale_reason`），沒有快照才 `available=False`。
  - `health_check`：快照仍照內容判定，但 ok 降為 warn，detail 前綴「最近一次讀取失敗（原因），以 N 秒前的快照判定」。
- `backend/apps/admin_api/tests_cluster_status.py`：新增 `ClusterSnapshotTests`（成功寫快取、失敗回快照＋warn、無快照回 unavailable、逾時為連線／讀取對）。
- `frontend/src/features/admin/AdminHealthPage.jsx`：叢集節點面板標題列在 `cluster.stale` 時顯示「最近一次讀取失敗（原因），顯示 <時間> 的快照」，節點與工作負載照常顯示，不再整塊變空。
- `backend/apps/admin_api/CLAUDE.md`：同步。

## 原因
使用者回報後台系統健康頁的「叢集節點」時常顯示「無法取得叢集狀態」。頁面每 15 秒輪詢，每次都即時打 Kubernetes API（nodes＋全叢集 pods＋metrics），讀取逾時只有 3 秒；API Server 偶發慢回應（或 CNI 偶發掉包）就整塊消失，看起來像叢集壞了，其實只是這一次探測失敗。改成：給讀取多一點時間，失敗時用最近成功的快照墊著並明講是快照、失敗原因是什麼，檢查項降 warn 而不是 unknown。

## 影響範圍
- 只動 `health` 端點的 `cluster` 區塊與對應檢查項；RBAC、NetworkPolicy 不變（web pod 對 API Server 的 egress 本來就開著）。
- 快照用 Django cache：正式環境若仍是預設 LocMemCache，每個 gunicorn worker 各自一份快照，第一次失敗前沒快照的 worker 仍會回 unavailable；設 Redis cache 後共用。

## 驗證方式
- `uv run ruff check backend/apps/admin_api`：All checks passed。
- `manage.py test apps.admin_api.tests_cluster_status apps.admin_api.tests`：全過。
- `npm run lint`：0 error；`npx vitest run src/features/admin/`：80 pass。
- 未自動驗證：部署後觀察健康頁一段時間——失敗時應看到「最近一次讀取失敗（ReadTimeoutError／…），顯示 … 的快照」而不是整塊空白；若原因持續是同一種（例如 MaxRetryError），再往 CNI／API Server 追。
