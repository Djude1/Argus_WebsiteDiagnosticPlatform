# Google PageSpeed Insights：Lighthouse＋CrUX（roadmap P1）

**日期**：2026-10-07  
**操作者**：Claude

## 變更內容
- 新增 `backend/apps/scans/pagespeed.py`：呼叫 PSI v5（行動版、四個 category），整理成 `ScanJob.performance_report`：
  - `lab`：Lighthouse 實驗室單次量測，包含四個分數、核心指標與前 5 項改善機會。
  - `field`：CrUX 過去 28 天第 75 百分位。網址本身資料不足時改用整個網站並標示；都沒有資料時記錄原因。
- `ScanJob.performance_report`：新增 migration `scans/0030_scanjob_performance_report`。
- `tasks.stage_pagespeed`：條件成立時只測首頁。
  - 執行條件：勾選 UX，且 `ARGUS_PAGESPEED_ENABLED` 開啟並設有 `ARGUS_PAGESPEED_API_KEY`。
  - 加在 `seo_links` 之後；`planned_scan_steps` 加 `pagespeed`。
  - 覆蓋檢查 `pagespeed`（不屬於任何維度）。
  - 失敗只標 failed，掃描照常完成。
- 設定：`ARGUS_PAGESPEED_API_KEY`、`ARGUS_PAGESPEED_ENABLED`（預設＝有金鑰時開啟）、`ARGUS_PAGESPEED_TIMEOUT_SECONDS`（90）。
- 報告範圍表多兩列：Lighthouse 分數、CrUX 指標。`RENDERER_VERSION` 10 → 11。
- `ScanJobSerializer.performance_report`；openapi／apiTypes 重產。
- 前端：
  - 掃描新增「效能」分頁（`/scans/:scanId/performance`，`PerformancePanel`），Lighthouse 與 CrUX 分開呈現，並註明不計入 Argus 分數。
  - 進度對照加 `pagespeed`。
  - 樣式 `.perf-*`（無彩色左邊條）。
- 文件：
  - scans／backend／frontend CLAUDE.md。
  - `docs/scan-upgrade-roadmap.md` 第 6 項標為已實作。
  - 需求書使用體驗段落。
  - `.env.example`。

## 原因
roadmap P1：Lab（Lighthouse）與 Field（CrUX）是最權威的外部效能訊號。依使用者選擇採用 PSI API（不需在 worker 安裝 Node／Lighthouse），只測首頁以控制配額與掃描時間。外部指標依 roadmap 原則獨立呈現，不校準或併入 Argus 分數。

## 影響範圍
- 部署需套用 migration `scans/0030`。
- 沒設 `ARGUS_PAGESPEED_API_KEY` 時不執行（不會出現在進度與覆蓋紀錄）。正式環境要啟用，需在 K8s Secret 加入金鑰。
- 受測首頁網址會送到 Google 量測；金鑰不寫 log、不進錯誤訊息。
- 報告版本號 +1，下次下載會重新產生。
- 尚未做：
  - 多頁量測、桌面版。
  - GSC 搜尋成效並列。
  - 用真實 PSI 回應做端到端驗證：沙盒沒有金鑰，匿名呼叫回 429。

## 驗證方式
- 新測試 `tests_pagespeed.py`（11 項，PSI 回應 fixture）：
  - 解析。
  - CrUX 網址／網站／無資料三種情況。
  - CLS 換算。
  - 錯誤訊息不含金鑰。
  - 階段成功、失敗與略過。
- 前端 `PerformancePanel.test.tsx`（3 項）。
- 全套 `uv run python backend/manage.py test apps`：1578 項 OK（1 skipped）。
- `ruff check backend`（exit 0）、`makemigrations --check`：通過。
- 前端 lint（exit 0）、typecheck、`npm test` 34 檔 225 項、`vite build`：通過。
