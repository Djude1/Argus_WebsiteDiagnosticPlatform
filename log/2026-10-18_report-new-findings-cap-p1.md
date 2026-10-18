# P1：報告「與前次比較」新出現項目收斂

**日期**：2026-10-18
**操作者**：Claude
**來源**：三站報告審查。juice-shop 第 3 頁「與前次比較」把 ~30 個「新出現」項目全擠在一段，變成一大坨難讀的文字。

## 根因
`reports._report_summary` 的 `summary["new_findings"]` 是**無上限**的完整標題清單；renderer（`report_render/report.py`）直接 `、`.join 全部印出。前次掃描規則集不同（或久未掃）時，本次幾乎每一條都算「新出現」，數十項一次傾倒。

## 修法（沿用 locations 的 `_MAX_LISTED_PAGES` 模式）
- 資料層 `reports.py`：`_MAX_NEW_FINDINGS=8`，`new_findings` 只留前 8 項，另存 `new_findings_total`（總數）。
- renderer `report_render/report.py`：標籤顯示總數、列出前 8 項，超出時加「…等，另 N 項」。
- `schema.json` 加 `new_findings_total`（選填整數）；`RENDERER_VERSION` 33 → 34。

## 驗證
- `tests_report_payload.test_new_findings_list_is_capped_with_total`（前次掃描無相同 rule、本次 20 條 →
  列出剛好 8、total ≥ 20）。`apps.scans.tests_report_payload`＋`tests_report_compactness`＋`tests_report_layout`
  共 37 項通過；`ruff check backend`（CI 樣式，report_render 在 extend-exclude）乾淨。
- 文件同步 `scans/CLAUDE.md` 的 RENDERER_VERSION 說明。

## 備註
純報告版面/資料層收斂，不影響發現數、計分或比較邏輯；不含機密值。
