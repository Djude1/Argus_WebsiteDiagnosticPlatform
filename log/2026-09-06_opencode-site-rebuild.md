# 網頁複刻與優化（接上 OpenCode agent）

**日期**：2026-09-06
**操作者**：Claude

## 變更內容

新增 `backend/apps/rebuild/`（8 個模組 + 21 個測試）：

- `snapshot.py`：`build_snapshot_html`——從 `Page.rendered_dom` 補 `<base>` 產出複刻，**不呼叫模型**
- `client.py`：`OpenCodeClient`，只實作用得到的四個端點（session / message / file-content / abort）
- `prompts.py`：優化指令，含提示注入的邊界宣告與截斷告知
- `services.py`：`run_rebuild` 兩段式編排；`agent_workspace()` / `output_relpath()`
- `tasks.py` / `views.py` / `serializers.py` / `urls.py` / `models.py`（`SiteRebuild`）

周邊：

- `backend/config/settings.py`：`apps.rebuild` 進 INSTALLED_APPS + 9 個 `ARGUS_OPENCODE_*` 設定（預設關閉）
- `backend/config/urls.py`：掛 `api/`（`/api/rebuilds/`）
- `k8s/07-network-policies.yaml`：`application-egress-boundary` 新增 `172.16.2.126/32:4096`
- `k8s/01-namespace-config.yaml` / `02-secret.example.yaml`：ConfigMap 與 Secret 鍵
- `backend/apps/scans/tests_k8s_network_policy.py`：補上新規則的契約斷言（7 → 8 條）
- 文件：`docs/opencode-site-rebuild.md`（新）、`backend/apps/rebuild/CLAUDE.md`（新）、
  根 `CLAUDE.md` / `AGENTS.md` / `專案導覽.md` 索引

## 原因

使用者要「給連結生成相同的網頁」與「依掃描結果生成優化後的網頁」，並自行在
172.16.2.126 部署了 OpenCode server。

**複刻刻意不走 LLM**：爬蟲階段已經把 `rendered_dom` 存進 `Page`，要重現那一頁
只需要補一個 `<base>`。交給模型「推理出一個長得一樣的頁面」既貴又不可能逐字
一致——模型能加值的是後面的優化階段。這也讓優化失敗時複刻仍可交付。

## 影響範圍

- 新增 migration `rebuild/0001_initial`（建 `SiteRebuild` 表），需要跑 migrate
- `ARGUS_OPENCODE_ENABLED` 預設 `false`：這次推上去**不會**有任何對外呼叫，
  只會產出複刻。啟用是另一次明確動作
- 產出寫進 media PVC（`rebuilds/scan-<id>/page-<id>/`），會佔用 5Gi 配額；
  目前**沒有**對應的清理 CronJob
- **尚未接 billing**：優化會花錢但不扣使用者點數
- 前端尚未有 UI，只有 API

## 過程中發現的環境事實（實測，非推論）

- opencode **允許用不存在的目錄建 session，但之後送 prompt 回 500**。所以
  session 的 cwd 固定指向既有目錄，每個 rebuild 的隔離靠輸出子路徑
- `.126` 上的 agent 執行身分已從 root 換成 `argus`，但 `worktree` 仍是 `/`、
  `build` agent 仍 `*:* allow`、全域 `permission.external_directory` 是 `allow`
  （**放寬**了 opencode 預設的 `ask`）。細節與應有狀態記在 `docs/opencode-site-rebuild.md`
- `.126` 的 hostname 是 `k8s`
- 不是免費的：實測一頁極小 HTML（2 個 finding）→ MiniMax-M3，$0.00178578

## 驗證方式

- `apps.rebuild` 21 tests OK
- `apps.scans.tests_k8s_network_policy` 5 tests OK（含新增的 `.126/32` 斷言）
- root `tests/` 42 tests OK
- `ruff check backend`、`manage.py check`、`makemigrations --check --dry-run` 全過
- `kubectl kustomize k8s` 渲染通過；`scripts/verify_rendered_manifests.sh` 通過
- **對真實 server 端到端實測**（不是 mock）：session → prompt → 讀回檔案，
  agent 正確補上 `<title>` 與 `img alt`，且保留了 `<base>` 與原內容

## 待辦（未做，非漏做）

- 前端 UI
- 接 billing 扣點
- `rebuilds/` 的清理 CronJob
- `.126` 上的權限收斂（worktree、bash 白名單、`external_directory`）
