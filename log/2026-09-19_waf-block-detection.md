# WAF／防護機制封鎖偵測（評審問題 4 回應）

- **日期**：2026-09-19
- **操作者**：ZCode（subagent 實作，main 驗收）

## 變更內容

- 新檔 `backend/apps/scans/security/waf_scanner.py`（128 行）：
  - `detect_waf_block(scan_job)`：統計該掃描已落地 Page 的 HTTP 403/429 與 challenge 特徵（title 5 個固定文案特徵＋body 3 個技術標記，刻意排除純 "captcha" 防誤判）
  - 閾值（任一觸發）：403+429 佔嘗試頁面 ≥ 30%，或 challenge 特徵頁 ≥ 2；未達閾值不產出
  - 達閾值回傳**單一** info finding（rule_id=`waf_block_detected`，category=security）：description 帶實際統計、remediation 給三點建議（降頻/離峰重掃、白名單、結果可能不完整提醒）、evidence_json 放統計
  - 冪等（同掃描已存在同 rule_id finding 則跳過）、純讀取不發網路請求、例外 silent-fail
- `backend/apps/scans/tasks.py`：深度被動安全掃描區（`analyze_services` 之後、OWASP 標注之前）接入 `detect_waf_block`，產出時 append `deep_security_findings` 並寫執行日誌
- 新檔 `backend/apps/scans/tests_waf_scanner.py`（185 行，9 個測試）

## 原因

- 複賽評審問題 4（防火牆質問）：「雲端網站服務本身有防火牆機制，你探得進去嗎？會不會被擋掉？」——既有節流（RPS 2/5、robots.txt、頁數/深度上限）降低觸發機率，但被擋時系統需**如實告知使用者**結果可能不完整，並給可行建議。本功能讓掃描報告在觸發 WAF/速率限制時產生明確 finding，demo 時可直接展示。

## 影響範圍

- 掃描結果新增一種 finding 類型；不影響掃描狀態機（未動 ScanJob.status）、不影響計費、不發新增網路請求（純統計既有 Page 資料）。
- 前端無需修改（Finding 既有渲染管線自動顯示）。
- 競賽文件同步：`需求書_複賽版完整內容.md` 新增 F-033 條目（32→33 條）、目錄/自我檢查同步；`設計文件_圖表與成本模組.md` §8.1 被動層清單加 waf_scanner 列；差異對照已標記完成（依 專題文件生成/Word文件同步規則.md）。

## 驗證方式

- `uv run python backend/manage.py check` 通過；`uv run ruff check backend/apps/scans` 全過
- `uv run python backend/manage.py test apps.scans`＝676 tests：674 通過、2 skipped、1 error——該 error（`tests_report_verification` 的 docx unlink 撞 Windows 檔案鎖 WinError 32）已用乾淨 HEAD worktree 對照證明為既有環境問題，與本變更無關
- 新測試 9/9 通過：低於閾值不產出、≥30% 403 產出含統計、challenge ≥2 產出、403＋challenge 同時觸發僅單一 finding 且落地後冪等、正常 captcha 頁不誤判、大小寫、純函式統計
