# 報告快取版本、清單分頁、滿分口徑、清理排程、佔比標註

**日期**：2026-09-05
**操作者**：Claude

## 變更內容

### 1. 報告快取沒有排版版本概念
- `report_render/__init__.py` 新增 `RENDERER_VERSION`（目前 2），改版面就要 +1。
- `models.ReportVerification` 新增 `renderer_version`、`previous_sha256`（migration `0012`）。
- `views.report` 快取判斷從「有紀錄 + 檔案在」改為再加「排版版本相符」。
- `reports.build_scan_report` 重產時把舊 `content_sha256` 收進 `previous_sha256`。
- `verify_views.verify_report` 支援 `?content_sha256=`，比對範圍含歷史雜湊，
  回傳 `matches` 與 `is_latest_version`；歷史雜湊本身不列進回應。

### 2. finding / page 清單只拿第一頁
- `ScanExperience.jsx` 新增 `fetchAllResults()`，以 `page_size=500` 逐頁取完
  （上限 20 頁）。findings 與 pages 都改用它。
- 不使用回應的 `next` 絕對網址：經反向代理時 scheme/host 可能與前端不一致。

### 3. 「0 個 finding = 100 分」
- `report_render/report.py` 在各分類分數圖下方，對「滿分且零發現」的分類加註
  「本次檢查的項目全部通過，而不是該面向已無任何風險」。
- **分數本身不動**：把 100 改成 95 或 98 都是憑空取的數字，沒有依據。

### 4. 清理作業從未排程
- `k8s/04-backend.yaml` 新增 `CronJob/cleanup-reports`（每日 20:00 UTC，保留 180 天）
  與 `CronJob/cleanup-screenshots`（20:30 UTC，保留 90 天）。
- 兩者都掛 `media` PVC 到 `/app/backend/media`。

### 5. 分類佔比的計數口徑沒有標註
- 報告（合併重複後）與前端（原始筆數）各自標註在數什麼。

## 原因

前四項是 2026-08-30 稽核後一直掛著的待辦，第五項是先前兩次詢問使用者未獲回覆的
取捨，本次由 Claude 定案。使用者指示「都幫我解決」。

第 1 項有實際事故：使用者在圖表修好後重新下載舊掃描的報告，拿到的是沒有圖表的
快取檔，誤以為修復失敗。

## 影響範圍

- **既有掃描的報告會在下次下載時重產一次**（renderer_version 由 default=1 起算，
  現行版本為 2）。重產會換掉內容雜湊，但舊雜湊進入 `previous_sha256`，先前交付
  出去的副本在查驗頁仍驗得過。
- 前端首次載入的請求數不變（多數掃描 findings < 500，一次取完）；超過 500 筆才
  會有第二次往返。
- 兩個新 CronJob 會**實際刪檔**。首次執行前若要確認範圍，可手動跑
  `manage.py cleanup_reports --dry-run`。

## 驗證方式

- `ruff check backend` → All checks passed
- `manage.py check` → no issues
- `manage.py test apps` → **813 tests OK (skipped=1)**（前次 805，+8）
- `unittest discover -s tests` → **39 tests OK**（前次 38，+1）
- 前端 `vite build` 通過（本機 Node v22；`build-node22.ps1` 為 Windows 腳本，
  該禁令針對 Windows 的 Node v24 + Rollup crash，本機不適用）
- `kubectl kustomize k8s` 確認兩個新 CronJob 的 image 會被改寫成 `sha-92900c0`
  且掛到 media PVC
- 新增測試以「還原 report.py 到 HEAD 再跑」確認會失敗，不是僥倖通過

## 過程中發現並修正的問題

- 用 `cat >>` 追加測試時，`tests/test_k8s_runtime_commands.py` 結尾有
  `if __name__ == "__main__":` 區塊，新測試被接在 `unittest.main()` 之後、
  **落在 if 區塊內**，成為永遠不會被收集的死碼——但 `discover` 仍顯示 OK。
  靠比對測試總數（38 → 38）才發現。已把方法移回 class 內（38 → 39）。
- 既有 `test_stale_scan_reaper_cronjob_exists` 用「第一個 CronJob」定位，
  manifest 有多個 CronJob 後會靜默驗到別支作業，改為按名稱選取。

## 尚未處理

- 報告的視覺與頁數仍需人工用 Word 開啟確認（本機無 LibreOffice/pandoc）。
- 兩個 CronJob 的實機執行結果需在正式叢集確認（K8s 在另一台機器）。
