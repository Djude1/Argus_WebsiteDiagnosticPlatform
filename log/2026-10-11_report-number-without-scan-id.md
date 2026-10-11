# 報告編號與下載檔名不再含掃描編號

**日期**：2026-10-11  
**操作者**：Claude

## 變更內容
- **報告編號**：`ARGUS-164-20261011-E03E` → `ARGUS-20261011-E03E`（`reports.build_report_number`）。
  - 驗證碼沿用原本的 HMAC，同一份報告的後四碼不變。
  - 少了掃描編號後，同一天可能撞號；遇到時加長到 6、8 碼。
- **舊編號仍可查驗**：查驗端點（`verify_views._find`）認得 `ARGUS-{掃描編號}-{日期}-{驗證碼}`。必須重新算出完全相同的驗證碼才算數，不能靠猜流水號查到別人的報告。輸入會先去除空白並轉大寫。
- **下載檔名**：`argus-scan-164-report.pdf` → `argus-report-20261011-E03E.pdf`。
  - 後端以 Content-Disposition 提供（網頁下載與 MCP 報告連結都用 `report_download_name`）。
  - 前端改讀標頭的檔名（新增 `shared/download.js`，掃描報告頁與掃描與報告列表共用）。
- **其他**：報告查驗頁的輸入範例改成新格式。
- **版本**：`RENDERER_VERSION` 28 → 29，舊報告下載時重產，印上新編號。

## 原因
使用者要求報告與檔名不要出現 164 這類內部掃描流水號，改用日期加驗證碼。

## 影響範圍
- 已寄出、印著舊編號的報告：照樣能在查驗頁查到；雜湊比對仍包含歷史版本。
- 伺服器內部的檔案路徑（`media/reports/scan-<id>-report.pdf`）不對外，不變。

## 驗證方式
- **新增測試**：
  - 後端 `tests_report_verification` 3 項：新格式不含掃描編號且下載檔名對應、舊編號可查而竄改驗證碼的不行、撞號時加長。
  - 前端 `download.test.ts` 3 項。
- **全套測試**：
  - 後端 `apps.scans`＋`apps.agent`＋`apps.mcp_access` 1449 項通過（10 項略過）；`ruff` 通過。
  - 前端 lint、typecheck 結束碼 0，vitest 278 項通過。

## 文件同步
- `backend/apps/scans/CLAUDE.md`：報告防偽表、RENDERER_VERSION。
