# 新增 OWASP ZAP 主動掃描階段（gated、預設關閉）

**日期**：2026-10-17
**操作者**：Claude

## 背景
使用者希望 ZAP 從只做被動分析升級成「主動」。主動 ZAP（spider＋active scan）會對目標送攻擊 payload，依平台授權模型只能打「主動模式＋網域已驗證」的目標，因此實作為：授權掃描跑主動 ZAP，未授權／被動掃描仍只有被動（被動是所有資安掃描的地板）。

## 變更內容

### 新增 `backend/apps/scans/security/zap_active.py`
- `run_active(har_paths, origin, scan_id, *, cancel_check, client)`：
  1. 用爬蟲 HAR（`build_har`）匯進 ZAP 建站台樹——Playwright 已繞過 Cloudflare 抓到真實 URL，不依賴 ZAP spider（CF 後面 spider 幾乎無效）。
  2. spider（有限時間）→ active scan（對 origin 底下 recurse 節點送攻擊 payload）。
  3. 輪詢進度到 100 或逾時；逾時／取消就 stop。
  4. finally 一律清理：stop 掃描、清 origin 告警與節點、把上傳的 HAR 覆寫成 `{}`、釋放 per-origin cache 鎖（與被動共用 `argus-zap:<origin>`，不會同時兩個掃描打同一 ZAP）。
- 無可掃描節點（HAR 空＋spider 被擋，ascan 起不來）→ `scanned=False`、覆蓋標 skipped，不算失敗。
- `active_enabled()`：`ARGUS_ZAP_ACTIVE_ENABLED and zap_passive.enabled()`。

### `zap_passive.py`
- `ZapClient` 加 spider／ascan 方法（`spider_scan/status/stop`、`ascan_scan/status/stop`），只給 active 用。
- `alerts_to_findings(..., active=False)` 加 `active` 參數：來源標「主動掃描」、`evidence_json.source=zap_active`；其餘（嚴重度映射、重複規則不列、低信心降一級）不變。ZAP risk 最高只到 high，不會有 critical。

### 接線
- `settings.py`：`ARGUS_ZAP_ACTIVE_ENABLED`（預設 False）、`ARGUS_ZAP_ACTIVE_TIMEOUT_SECONDS`（600）、`ARGUS_ZAP_ACTIVE_SPIDER_SECONDS`（120）。
- `scan_plan.py`：`ScanExecutionPlan.run_zap_active = site_active`（全站＋主動＋已授權，與 Nuclei／Kali 同閘）。
- `tasks.py`：`_runs_zap_active`（勾資安＋`active_enabled`＋`run_zap_active`）、`stage_zap_active`、`SCAN_PIPELINE` 於 `zap_passive` 後插入、`planned_scan_steps` 加 `zap_active`；爬蟲在「被動或主動 ZAP 任一要跑」時錄 HAR；被動階段的 HAR 留到主動階段跑完才刪。
- `coverage.py`：`zap_active` 歸 security、標籤「OWASP ZAP 主動掃描」。
- 前端 `ScanExperience.jsx`：`SCAN_STEP_META.zap_active` 進度步驟。

## 授權邊界（不可放寬）
主動流量只對「主動模式＋網域已驗證」目標送。被動模式、單頁、未驗證網域一律不送（`run_zap_active=site_active`，而 active 模式本身就要網域驗證才設得起來）。這是平台授權前提，不是可調偏好。

## 影響範圍
- 預設關閉：不設 `ARGUS_ZAP_ACTIVE_ENABLED=true` 時完全不跑，現有行為不變。
- 開啟後，授權掃描會多一個主動掃描階段（被動仍跑）；多耗 ZAP 時間與一次 per-origin 鎖（序列，不衝突）。
- 不新增 model／migration／計費。

## 驗證方式
- 後端：`ruff check backend` 通過；`apps`（含 scans）全套 1980 項通過（skipped 12）；根目錄 `tests/` 通過；修正 `tests_pipeline_stages` 的階段順序期望。
- 新增 `tests_zap_active.py`（假 client，不需真 ZAP）：HAR 建樹→spider→ascan→清理順序、HAR 覆寫成 `{}`、無可掃節點標未掃、per-origin 鎖忙碌擲 ZapBusy、授權閘（只在 site_active）、`ARGUS_ZAP_ACTIVE_ENABLED` 關閉時即使已授權也不跑、`alerts_to_findings(active=True)` 來源標示。
- 前端 `npm run lint` 0 error。
- **無法在本容器實測**：沒有 ZAP 實例，且不該從開發 session 對外部網站送主動流量。真正驗證要在正式環境接 K8s 的 ZAP、對已授權目標重掃；需確認 worker→ZAP 的 NetworkPolicy 與 ZAP→目標的連線。

## 啟用（正式環境，操作者執行）
1. 確認 ZAP daemon 已部署、worker 連得到、ZAP 連得到目標。
2. K8s env／secret 設 `ARGUS_ZAP_ACTIVE_ENABLED=true`（與 `ARGUS_ZAP_ENABLED=true` 並存）。
3. 對已授權的測試網站跑一次「全站＋主動」掃描，確認掃描紀錄出現「ZAP x.y.z 主動掃描：…」且覆蓋為 completed／partial。

## 備註（安全）
程式、測試 fixture、文件一律用虛構網址（`site.example.test`）與虛構告警；不含真實站名、未修補漏洞路徑或內網 IP。
