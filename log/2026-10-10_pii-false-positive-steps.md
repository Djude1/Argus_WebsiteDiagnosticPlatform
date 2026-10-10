# 信用卡號誤報、瀏覽器金鑰降級、恢復五個分析階段

**日期**：2026-10-10  
**操作者**：Claude

## 變更內容
- `scanners.py`（PII）
  - 身分證號與信用卡號只看頁面上看得到的文字（`_visible_text`：去掉 script／style／template、註解與標籤屬性）。HTML 註解仍另外掃描。
  - 信用卡新增 `_card_issuer_ok`：開頭（IIN）與位數要符合 Visa／Master／Amex／JCB／銀聯／Discover／Diners。
  - `_is_formatted_card` 改為要照卡片分組（4-4-4-4、4-6-5、4-6-4、4-4-4-4-3），且只用同一種分隔符號。
- `security/secret_scanner.py`
  - Google `AIza` 金鑰改為低風險，另由 `build_browser_key_finding` 產生 `exposure-browser-api-key`（提醒確認參照網址與 API 限制）；`build_secret_finding` 不再算它。
  - 泛用賦值（`apiKey: "AIza…"`）在值已被特定格式抓到時不重複列。
- `katana_scanner.py`：jsluice 抓到的 `AIza` 值降為低（原本嚴重）。
- `security/finding_kind.py`、`security/owasp_mapper.py`：登記新規則。
- `tasks.py`：逐頁秘鑰偵測同時產生兩種 finding。
- 恢復五個逐維度分析階段（`analyze_seo`／`aeo`／`geo`／`ux`／`security`），撤回同日合併成 `analyze_pages` 的改動；PageSpeed 背景量測保留。前端 `ScanExperience.jsx`、`tests_progress.py` 還原。
- `versions.py`：`RULESET_VERSION` 改為 `2026.10.10.2`。
- 文件：新增 `docs/scan-stage-checks.md`（六個階段的檢查項目、速度說明、AI Agent 執行條件）；`backend/apps/scans/CLAUDE.md`、`security/CLAUDE.md`、需求書同步。

## 原因
- 使用者實掃網站時，Next.js 圖片網址 `/_next/static/media/20221027 0069652-ISO 9001-…jpg` 裡的「20221027 0069652」（日期＋流水號）巧合通過 Luhn，又因含空白且 15 位被當成「格式化卡號」，判成高風險 PII。
- Google 地圖／Firebase 金鑰設計上就放在前端，判高風險是常見誤報。
- 使用者不要合併的頁面分析階段，要求恢復五個階段。

## 影響範圍
- 新掃描的 PII 高風險、秘鑰問題會減少；舊掃描可用 `manage.py renormalize_findings --scan-id N` 重跑 PII 分級（不重跑秘鑰偵測）。
- 規則版本變更，與先前掃描的分數差會標「評分規則已更新」。

## 驗證方式
- 新增測試：分組與卡組織規則、屬性值與 script 內的號碼不算、看得到的卡號照樣抓到；瀏覽器金鑰為低風險且不進秘鑰 finding。
- `uv run python backend/manage.py test apps`（全部，序列執行）、`uv run ruff check backend`。
