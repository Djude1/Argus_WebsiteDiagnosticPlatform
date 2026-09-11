# 票01：Open Graph 社交分享標籤偵測 finding rule

**日期**：2026-09-11  
**操作者**：Claude（ZCode）

## 變更內容
- `backend/apps/scans/scanners.py`
  - `HtmlSignalParser` 新增 `og_tags` 收集：`<meta property="og:...">`（`name=` 也認）四個鍵——og:title／og:description／og:image／og:url，content 空白視為缺失。
  - 新增模組常數 `OG_META_KEYS`。
  - `analyze_seo()` 新增規則「缺少 Open Graph 社交分享標籤」：SEO 分類、LOW、priority_score 30，evidence 列出實際缺失的標籤子集。
- `backend/apps/scans/tests_og_detection.py`（新檔）：合成頁面驗證 5 個情境——全缺、全有、部分缺（只列缺的）、空 content 視為缺、`name=` 屬性也認。

## 原因
修正產出功能（spec `docs/specs/0002-fix-output.md`）票 01：既有 scanner 對 Open Graph 完全零覆蓋，管理者不知道社群分享預覽的呈現缺口；後續 OG＋meta 修正產物也以這條 finding 作為報告端的對應偵測。採單一 rule（四標籤併一）而非四條 rule，配合「同 rule_id 只扣一次分」的計分契約，避免一頁被扣四次。

## 影響範圍
- 每個非後台、非二進位的已爬頁面都會多這項 SEO 檢查；缺 OG 的網站 SEO 分類分數會下降（LOW = 4 分懲罰，跨頁同 rule 只扣一次）。
- 報告頁與 Word 報告經既有 finding 呈現機制自動顯示，前端無需改動。
- 不影響其他維度與計分公式。

## 驗證方式
- `uv run python backend/manage.py test apps.scans.tests_og_detection` → 5 tests OK（TDD：先 red 後 green）。
- `uv run ruff check backend` → All checks passed。
- `uv run python backend/manage.py check` → no issues。
- 完整套件 `uv run python backend/manage.py test apps`（903 tests）：除 1 個既有環境錯誤外全綠——`tests_report_verification` 的 `test_missing_file_is_rebuilt...` 在 Windows 因 .docx 檔案 handle 釋放時序 `PermissionError`，已用 git stash 驗證乾淨樹同樣失敗，與本次改動無關；另外本機跑報告類測試需 `ARGUS_REPORT_FONT_REGULAR/BOLD` 指向 Windows CJK 字型（如 `C:\Windows\Fonts\msjh.ttc`），否則 72 個 report 測試因字型路徑只支援 Linux 而錯誤，同為既有環境因素。
