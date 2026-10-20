# 報告審查第三輪：掃描警示、第 3 章文案、證據呈現、語言版佔預算、敏感檔探測覆蓋、Kali 訊息、log 遮罩

**日期**：2026-10-20  
**操作者**：Claude

## 變更內容
- C-9 `reports._scan_warning_lines`：不再列 Katana 技術棧（不是警示；版本已由 service-version-exposed、HSTS 由網站優勢呈現）。
- C-10 `reports._report_why_matters`：分類最嚴重一筆為中風險以上才用規則專屬文案，否則用分類層級後果。
- C-13 `reports._report_evidence`／`_clip`：證據只有 HTML 實體時 `html.unescape`；截斷加「…」。
- D1 `crawler._CrawlState`：只差語系參數的網址進 `language_variants`，新內容爬完才輪到；`budget_summary.language_variants_deferred`、`crawl_budget_text` 新增一項。
- D2 `exposure_scanner.probe_paths(stats=)`＋`tasks._exposure_probe_status`：探針全打不到標 blocked、半數以上 partial、例外 failed；log 附原因。
- D3 `scan_logger.already_logged`＋`kali_tools._log_kali_decision`：同一原因一次掃描只記一次。
- D4 `redaction.redact_url_query_values`：`_SAFE_QUERY_KEYS` 的短規則值保留，其餘照遮。
- 測試：`tests_crawl_budget`（延後順序、計數）、`tests_security_redaction`、`tests_exposure_scanner`（狀態判定、stats 回填）、`tests_kali_tools`（只記一次）、`tests_report_site_metrics`（實體還原、省略號、第 3 章文案、不列技術棧）。
- 文件：`apps/scans/CLAUDE.md`、`apps/scans/security/CLAUDE.md`。

## 原因
2026-10-19 cs.ntust.edu.tw 實掃報告與 log 審查剩餘項目：掃描警示列「技術棧：HSTS、PHP」；第 3 章 SEO 列是 title 長度說明；4.2 證據顯示 `&lt;html&gt;`、4.1 截在半句；50 頁有一半是 zh-tw／en 重複、389 個新頁沒排到；敏感檔探測「探測 0 路徑」卻標完成；Kali 略過訊息連出三次；log 網址全成 `Lang=[REDACTED]`。

## 影響範圍
- 既有 `tests_report_rule_specific` 鎖定「中高風險分類用規則文案」，C-10 改成條件式以同時滿足。
- `RENDERER_VERSION` 未升：C-9／C-10／C-13 都在資料層（payload），重新下載報告時當場重算。
- 探測覆蓋狀態變嚴：被 WAF 擋的掃描資安維度會標部分評估，報告「未完整完成的檢查」會列出。

## 驗證方式
- `uv run ruff check backend` 通過；`manage.py test apps.scans apps.agent`（含真實 Chromium）1633 項通過（skipped 3）。
- 前端未改；`npm run lint`／`typecheck`／`vitest` 仍全綠（304）。
