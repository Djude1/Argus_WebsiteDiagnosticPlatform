# 掃描階段合併與 PageSpeed 背景量測

**日期**：2026-10-10  
**操作者**：Claude

## 變更內容
- `backend/apps/scans/tasks.py`
  - `planned_scan_steps()`：五個逐維度分析步驟（`analyze_seo`／`aeo`／`geo`／`ux`／`security`）合併成一步 `analyze_pages`。
  - `_write_progress()` 新增 `detail` 參數，寫入 `progress.step_detail`；`stage_analyze_pages` 以 `step="analyze_pages"`、`step_detail=<目前維度>` 回報，`step_done`／`step_total` 改為「維度×頁」計數。
  - 新增階段 `pagespeed_start`（`stage_pagespeed_start`，接在 `enter_scanning` 之後）：勾 UX 且已設定 PSI 金鑰時，用模組層級 `_PAGESPEED_EXECUTOR` 在背景送出 PageSpeed Insights 量測，future 存在 `ScanRunContext.pagespeed_future`。
  - `stage_pagespeed` 有 future 就取結果，沒有才當場量測；資料庫寫入與覆蓋紀錄仍在主流程。
- 前端 `ScanExperience.jsx`：`SCAN_STEP_META` 新增 `analyze_pages`「頁面分析」，標題與說明依 `step_detail` 顯示目前維度；舊任務的 `analyze_*` 鍵保留。計數單位為「項」。
- 測試：`tests_progress.py`、`tests_pipeline_stages.py` 更新；`tests_pagespeed.py` 新增背景量測三項；新增前端 `scanProgress.test.ts`。
- 文件：`backend/apps/scans/CLAUDE.md`（progress JSON、可能值、階段表）、`frontend/CLAUDE.md`、`專題文件生成/需求書_複賽版完整內容.md`。

## 原因
使用者要求「掃描階段合併跟平行跑也一起做」：
- 逐維度分析每項只要幾秒，分成五個步驟會讓階段看起來很多、進度一閃而過。
- PageSpeed Insights 要等 Google 量測 20～90 秒，原本排在連結檢查之後空等，現在與頁面分析、資安、連結檢查同時進行。

## 影響範圍
- 進度顯示：新掃描少四個階段；進行中的舊任務仍以舊步驟鍵顯示。
- 分析結果與分數不變（分析順序與內容沒有改）。
- PageSpeed 背景執行緒只做網路請求，掃描取消或失敗時它會在 PSI 逾時內自行結束，結果被丟棄。

## 驗證方式
- `uv run python backend/manage.py test apps`（全部，序列執行）
- `uv run ruff check backend`
- 前端 `npm run lint`、`npm run typecheck`、`npx vitest run`
