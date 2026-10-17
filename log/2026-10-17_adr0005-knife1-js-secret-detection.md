# ADR-0005 第一刀：外部 JS bundle 秘鑰偵測

**日期**：2026-10-17
**操作者**：Claude
**依據**：[ADR-0005](../docs/adr/0005-scan-pipeline-tool-integration.md) §1、遷移計畫第 1 刀。

## 背景
現況四個重疊之一：Katana 的「JS 秘鑰（-jsl jsluice）」在 CF 後面歸零（主動重抓吃 challenge），
而 Argus 自家 `secret_scanner` 只掃 HTML／inline script、**不掃外部 .js bundle**——等於外部 JS 的
秘鑰是真實漏報，且需要它的 CF 場景沒人補。crawler 是真瀏覽器、已把這些 JS bytes 讀進記憶體
（為了抽 API 路徑），正是補洞的最佳位置（CF-safe）。

## 變更內容

### `backend/apps/scans/crawler.py`
- `_collect_js_secrets(body, url, state)`（新）：對讀到的 JS body 跑 `detect_secrets_in_text`，
  跨檔以 (kind, masked) 去重累積到 `state.js_secrets`（每筆帶來源 .js URL），上限 `_MAX_JS_SECRETS`=40。
- `_collect_js_api_paths` 的 `_read()` 在抽完路徑後呼叫它（同一份 body，不另發請求）。
- `_CrawlState` 加 `js_secrets`／`js_secret_keys`；`crawl_site` 收尾寫 `site_signals["js_secrets"]`。
- JS 讀取上限 `_MAX_JS_BODIES` 40→80（使用者裁定不限重抓，放寬提高涵蓋）。

### `backend/apps/scans/tasks.py`
- `_js_secret_findings(ctx)`（新）：把 `site_signals.js_secrets` 按來源檔分組，用 `build_secret_finding`
  ＋`build_browser_key_finding`（`source="js_bundle"`）轉成 `exposure-hardcoded-secret`／
  `exposure-browser-api-key`。
- `stage_deep_security` 的 findings 併入這批（與逐頁 HTML／inline 秘鑰互補，不同來源檔不交叉去重）。

## 驗證
- `tests_js_secrets.py`（5）：偵測＋標來源、跨檔去重、乾淨 JS 零誤報、finding 分組（critical secret ＋
  browser key 分流、evidence_source=js_bundle）、空輸入零 finding。
- `ruff check backend` 通過；`apps.scans` 全套 1433 通過（skipped 12）。
- **本容器無法實機爬真站驗證**（crawl_site 的真實 Playwright 迴圈無單元測試覆蓋，依 CLAUDE.md 規範
  需在本機測試站實跑）；本刀的改動都在 body 處理與 finding 組裝，已用單元測試覆蓋純邏輯。

## 此刀未完（列為後續增量）
- 主動抓齊頁面沒自然載入的 .js（透過瀏覽器 context 重抓，帶 CF clearance）。
- 強化 JS 端點抽取深度（逼近 jsluice AST）。
- 兩者動到無測試保護的爬行迴圈，刻意不混進這次低風險補洞；被動載入已涵蓋導航會載入的 bundle。

## 備註（安全）
測試用虛構網址（site.example.test）與 canonical 範例金鑰（AKIAIOSFODNN7EXAMPLE），不含真實秘鑰或站名。
