# PDF 報告標示部分掃描

**日期**：2026-10-07  
**操作者**：Claude

## 變更內容
- `apps/scans/reports.py::_scan_warning_lines`：全網站掃描且 `max_pages` 小於 `ARGUS_DEFAULT_MAX_PAGES`（50）時，掃描警示加一行「部分掃描：本次只檢查最多 N 頁（標準完整掃描為 50 頁）…」。
- `report_render.RENDERER_VERSION` 6 → 7，讓已快取的報告重新產生。
- 測試：`tests_report_content.py` 新增部分掃描有標示、單頁與 50 頁不標示。
- 文件：`apps/scans/CLAUDE.md`（報告必備內容、RENDERER_VERSION）、`docs/business-model-plan.md` 實作狀態、需求書 F-006。

## 原因
商業計劃短期項要求 Partial Scan 在報告明確標示 coverage；上一輪只在掃描詳情頁標示，PDF 尚未處理。

## 影響範圍
- 只影響報告內容；版本號 +1 會讓所有掃描下次下載報告時重新產生一次（舊雜湊保留在 `previous_sha256`，舊副本仍可查驗）。

## 驗證方式
- `apps.scans` 報告相關測試（content／payload／compactness／layout）49 項 OK；`apps.scans` 全套 964 項 OK（1 skipped）。
- `uv run ruff check backend`：通過
