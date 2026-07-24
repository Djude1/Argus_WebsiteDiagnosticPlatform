# 修 score 誤導 bug：爬蟲 0 頁不該給滿分（scan 有效性）

**日期**：2026-07-24
**操作者**：Claude（commit 待使用者同意）

## 變更內容

- **`backend/apps/scans/tasks.py`**（`run_scan_job` scoring 段）
  - `tested_categories` 決定邏輯：原硬編碼 `{"seo","aeo","geo","security"}`，改為
    `{"security","geo"}` + `if crawled_pages: update({"seo","aeo"})`。
  - 原因：seo/aeo 的 finding 只來自 `analyze_page`（頁面層級）；爬蟲 0 頁（目標不可達/
    全 timeout）時根本沒頁面可分析，若仍計入 `overall_score` 平均，等於把「沒測」誤當
    「零問題」灌高總分。security（DNS/SSL 站台層級）與 geo（`analyze_site_signals`：
    llms.txt/robots）即使 0 頁仍有站台層級檢查，故保留。與既有的 UX `tested_categories`
    把關模式（agent 拋例外時排除 ux）同理。
  - 新增 0 頁有效性警示：`warning_summary["scan_effectiveness"] = "no_pages_crawled"` +
    `scan_log` warn，避免 `overall_score`（此時只反映站台層級）被誤讀為「網站安全」。
  - 正常掃描（有頁）行為與修復前完全一致（seo/aeo 恢復計入）。

- **`backend/apps/scans/tests_kali_pipeline.py`**（新增 2 個測試，沿用 setUp 的 0 頁 mock）
  - `test_zero_pages_excludes_seo_aeo_from_tested_categories`：0 頁時 `tested_categories`
    不含 seo/aeo，但含 security/geo/ux。
  - `test_with_pages_includes_seo_aeo_in_tested_categories`：有頁時 seo/aeo 恢復計入
    （防回退保護）。

## 原因

覆蓋度實測（scan 19 掃 `testphp.vulnweb.com`）揭露：爬蟲入口 URL timeout、**0 頁**，
幾乎所有 scanner 沒跑，Argus 卻給 **score 96 / security 88**——無效掃描卻誤導性高分。
根因：scoring 的 `tested_categories` 硬編碼含 seo/aeo，0 頁時這些根本沒測卻以 100 分
計入 overall 平均。開發者原先已用 `tested_categories` 機制處理 UX 的同類問題（agent
例外時 ux 沒測卻滿分），但**未覆蓋「爬蟲 0 頁」情境**——本修復補上這塊。

## 影響範圍

- 只動 scoring 的 `tested_categories` 決定 + 新增 `warning_summary` 欄位，**不變更
  `calculate_scores` 本身**（`category_scores` 仍回傳全部 5 個供前端/報告顯示，只有
  `overall_score` 平均排除未測分類）。
- 0 頁時 `overall_score` 會下降（只反映 security/geo 站台層級），並在 `warning_summary`
  標記 `scan_effectiveness=no_pages_crawled` 供前端辨識「掃描不完整」。
- 正常掃描（`crawled_pages ≥ 1`）`overall_score` 與舊版完全一致。

## 驗證方式

本機已驗證（全綠）：

- `apps.scans.tests_kali_pipeline`：7 tests OK（含 2 個新測試 + 既有 5 個）。
- `apps.scans.tests`（含 `calculate_scores`）+ `apps.scans.tests_progress`：110 tests OK。
- `ruff check backend/apps/scans/tasks.py backend/apps/scans/tests_kali_pipeline.py`：
  All checks passed。

**未驗證**（待後續）：

- 前端是否讀取 `warning_summary["scan_effectiveness"]` 並顯示「掃描不完整」提示
  （本次只改後端資料，前端呈現待後續）。
- 正式環境實際 0 頁掃描的 overall 變化（scan 19 因 testphp 不可達無法重跑；可改用
  `aiglasses.qzz.io` 或構造 0 頁情境驗證）。

## 附帶發現

- 覆蓋度實測同時確認：`testphp.vulnweb.com`（Acunetix 刻意脆弱站）**當下不可達**
  （TCP 80/443 timeout，本機 + 正式 worker 都連不到），不適合作覆蓋度測試目標。
  公開 purposely vulnerable 站普遍不穩（juice-shop demo 503、testhtml5 掛、dvwa 403）。
- 本機 `.env` 缺 `PASSWORD_RESET_TOKEN_PEPPER`（preflight §1 要求的 key；
  `DJANGO_SECRET_KEY` 與 `JWT_SECRET_KEY` 皆有）。測試用環境變數注入繞過；正式 .env
  完整性需使用者確認。
