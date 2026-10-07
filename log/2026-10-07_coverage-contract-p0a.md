# 掃描覆蓋契約（roadmap P0-A MVP）

**日期**：2026-10-07  
**操作者**：Claude

## 變更內容
- 新增 `backend/apps/scans/coverage.py`：檢查級狀態（completed／partial／failed／blocked／skipped）、維度級狀態（completed／partial／not_tested）、`absent_issue_status`（resolved／not_observed／not_tested／blocked／inconclusive）。
- `ScanJob.coverage`（migration `scans/0028_scanjob_coverage`，新增欄位）。
- `tasks.py`：各階段記錄檢查結果與產生的問題代號；Nuclei／Katana／敏感檔案探測／SEO 連結檢查／Agent／Kali 失敗時標 failed（`_tool_failed` 取代 `_log_tool_skipped`）；Nuclei 0 項且位於 WAF 後標 partial；`tested_categories_for` 移除所有檢查都失敗的維度；`stage_scoring` 寫入 `coverage`。
- `projects.py`：`compare_issues` 的「本次未出現」每項附 `status`／`status_label`，總覽 `changes.resolved` 與 `latest_scan.coverage`；`issue_key` 改由 `coverage.py` 提供。
- `reports.py`：「已解決 N 項」只算 resolved，另註明無法確認的數量；掃描範圍表列「未完整完成的檢查」「部分評估的面向」；`RENDERER_VERSION` 7 → 8。
- `ScanJobSerializer.coverage`；openapi／apiTypes 重產。
- 前端：專案總覽不完整提示（`CoverageNotice`）、「未出現（已修好 N）」、本次未出現清單狀態標籤。
- 文件：scans／backend／frontend CLAUDE.md、`docs/scan-upgrade-roadmap.md`、需求書報告與網站專案工作區段落。

## 原因
roadmap P0-A：工具失敗被呈現成「0 項問題」會灌高分數；前次問題沒出現就被當成已解決，可能只是這次沒跑到或沒爬到該頁。

## 影響範圍
- 部署需套用 migration `scans/0028`（新增欄位，舊掃描 coverage 為空 dict）。
- 舊掃描沒有覆蓋紀錄：本次未出現一律標「本次未觀察到」，報告不再宣稱「已解決」，改寫無法確認的數量。
- 報告版本號 +1，下次下載會重新產生（舊雜湊保留在 `previous_sha256`）。
- 尚未做：rule／resource 級細分、`scoring_version`、檢查狀態接到計費。

## 驗證方式
- `uv run python backend/manage.py test apps`：1533 項 OK（1 skipped）；之後追加的總覽欄位以 `tests_site_projects`、`tests_coverage`、`tests_report_appendix`、`apps.mcp_access` 重跑 91 項 OK
- 新測試 `tests_coverage.py` 20 項（含完整 pipeline 寫入 coverage、Nuclei 失敗不被隱藏、歷史比較狀態）
- `ruff check backend`、`makemigrations --check`：通過
- 前端 lint（0 error，既有 AdminPages 1 warning）、typecheck、`npm test` 33 檔 222 項、`vite build`：通過
