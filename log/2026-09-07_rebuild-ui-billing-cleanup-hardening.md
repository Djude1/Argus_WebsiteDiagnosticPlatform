# 網頁複刻：前端 UI、點數計費、產出清理、agent 權限收斂

**日期**：2026-09-07
**操作者**：Claude

## 變更內容

依使用者指定的順序做完四項待辦。

### 1. 前端 UI
- 新增 `frontend/src/components/scans/PageRebuildPanel.jsx`：觸發、狀態輪詢、兩種產出下載
- 掛在 `ScanExperience.jsx` 掃描詳情頁右欄，**只在選定單一頁面時出現**（複刻是針對某一頁的產出）
- `styles.css` 新增 `.rebuild-*` 樣式，沿用 `top-actions-box` 的卡片語言；
  進行中狀態沿用既有 `pulse-soft` keyframes，並補 `prefers-reduced-motion`

### 2. 點數計費
- `CoinTransaction.Kind` 新增 `rebuild_hold` / `rebuild_refund`
- `CoinTransaction.site_rebuild` FK：退款冪等判斷必須綁到「哪一次複刻」，
  只記 `scan_job` 會把同掃描其他複刻的預扣一起退掉
- `billing/services.py` 新增 `estimate_rebuild_cost` / `hold_for_rebuild` / `refund_rebuild`
- 建立任務時預扣（餘額不足回 402 並刪掉孤兒紀錄），任何失敗路徑統一走
  `services._fail()` 退款
- 新增 `GET /api/rebuilds/cost/`：讓按鈕先講清楚價格與餘額，而不是按下去才吃 402
- `ARGUS_COIN_PER_REBUILD` 預設 30（**佔位價格**）

### 3. 產出清理
- `manage.py cleanup_rebuilds`（保留 30 天，逐「頁目錄」判斷）
- `cleanup-rebuilds` CronJob，21:00 UTC，掛 media PVC

### 4. agent 端權限收斂
- `ARGUS_OPENCODE_AGENT` 預設改為 `argus-rebuild`（受限專用 agent）
- `docs/opencode-site-rebuild.md` 附上依官方 schema 寫出的 agent 設定
- `output_relpath()` 改用扁平檔名，讓 agent 端可以把 bash 整個關掉

### 途中修掉的一個真實缺陷
實測發現 agent 會**自作主張建子目錄**再把檔案放進去，回覆裡還宣稱已寫好
（`/tmp/opencode/argus/scan-1-page-1/...`）。原本只讀指定路徑，會被判成
「未產出」。改成三層取回：指定路徑 → `/find/file` 全目錄搜同名 → 回覆的
```html 圍欄。同時把輸出檔名從 scan/page 改成 **rebuild 主鍵**——否則同一頁
重跑會撞名，find 可能撈到上一次失敗留下的舊檔當成這次的產出。

## 原因

前三項是既有待辦。第四項是安全前提：worker 是唯一會載入攻擊者可控網站的
元件，讓它打得到一個全權限、有 shell 的 agent 等於把提示注入接到 shell 上。

## 影響範圍

- 新增 migration `billing/0006`，需要跑 migrate
- **`ARGUS_OPENCODE_AGENT` 預設改了**：`.126` 上沒有 `argus-rebuild` 就會回 500、
  功能整個不動。這是刻意 fail closed，不退回全權限的 `build`
- 複刻現在會扣點。`ARGUS_COIN_PER_REBUILD=30` 對應不到任何實測成本，上線前要重定
- 產出 30 天後自動刪除，`SiteRebuild` 紀錄保留

## 驗證方式

- 後端 849 tests OK（224 + 625，分兩批跑避開記憶體不足）
- root `tests/` 42 OK；ruff / check / makemigrations 全過
- `kubectl kustomize` + `verify_rendered_manifests.sh` + `verify_repository_text.py` 通過
- 前端 `vite build` 通過；確認元件字串與 `.rebuild-*` 樣式（含 reduced-motion）
  都進了 production bundle
- **對真實 agent 跑完整鏈路**：
  - 失敗案例：`agent 未產出優化後的 HTML` → 餘額 500→470→**退回 500**
  - 成功案例：`succeeded`、兩份產出都在、餘額 500→**470 未退**
  - 交易紀錄：`rebuild_hold -30` / `rebuild_refund +30` 各自綁對 `site_rebuild`

## 未驗證（需要使用者）

- **UI 外觀沒有親眼看過**：這台沒有瀏覽器工具，只驗到「元件與樣式進了 bundle」
- `argus-rebuild` agent 設定是依官方 schema 寫的，**沒能在 .126 上實測**
  （只有 HTTP API，沒有 shell）。套用後要確認 `GET /agent` 看得到它、且能產出檔案
- `cleanup-rebuilds` CronJob 尚未在正式叢集跑過
