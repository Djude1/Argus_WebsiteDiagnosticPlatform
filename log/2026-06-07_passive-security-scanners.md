# 2026-06-07 Phase 4 被動安全 scanner 套件

## 變更內容

在 `backend/apps/scans/security/` 新增三個被動安全 scanner 與一個 OWASP/CWE 對映器，並整合進掃描流程與報告層：

- `ssl_scanner.py` — SSL/TLS 深度分析（憑證到期、過期協議 TLS 1.0/1.1、弱 cipher、自簽憑證）
- `cookie_scanner.py` — Cookie 安全旗標（Secure / HttpOnly / SameSite=None）
- `header_scanner.py` — 資訊洩露標頭（Server/X-Powered-By）、CORS 萬用字元、CSP unsafe-inline/eval
- `owasp_mapper.py` — `tag()`（寫入前貼標）+ `backfill()`（回填既有 security finding）
- `Finding` model 新增 `owasp_category` / `cwe_id` 兩個 nullable 欄位（migration `0009`）
- `tasks.py` 在 Nuclei 區塊後新增「深度被動安全掃描」段落（純加法）
- `serializers.py` FindingSerializer 輸出兩欄；`reports.py` Word 報告顯示 OWASP/CWE
- `tests_security_scanners.py` 新增 35 個單元測試

## 原因

補齊 Argus 與 Nessus 在 Web 應用層的偵測廣度差距（見 `docs/nessus-gap-analysis.md` 第一優先項目），讓現場 demo 掃描能列出更多漏洞、報告帶 OWASP/CWE 標籤更專業。硬約束是純加法、不破壞現有可 demo 的掃描流程。

## 影響範圍

- 新增檔案集中在 `backend/apps/scans/security/`，舊掃描邏輯一行未改。
- `tasks.py` 僅新增 28 行（0 刪除），插入點在 Nuclei extend 之後。
- 每個 scanner 例外 silent-fail 回 `[]`，掃描失敗不影響主流程。
- OWASP/CWE 只對 `category=security` 的 finding 生效，其他類別不受影響。

## 驗證方式

- `uv run python backend/manage.py test apps.scans` → 152 測試全通過（含 35 個新測試）。
- `uv run ruff check backend/apps/scans/security backend/apps/scans/tests_security_scanners.py` → All checks passed。
- `uv run python backend/manage.py check` → 0 issues。
- rule_id 一致性已比對：owasp_mapper 的 13 個 key 與三個 scanner 產生的 rule_id 完全對應。
- **待人工驗證（Docker 整合）**：`docker compose up -d --build web worker` 後於 `localhost:8080` 對真實 HTTPS 目標掃描，確認報告多出 SSL/Cookie/Header findings 且帶 OWASP/CWE 標籤、舊功能正常。

## 備註

- ~~`owasp_mapper._RULE_OWASP_MAP` 目前只涵蓋本套件新 scanner 的 rule_id~~ → 已於 2026-06-09 修正：新增 `_KEYWORD_OWASP_MAP` 子字串比對涵蓋既有 `analyze_security` findings，詳見 [`log/2026-06-09_passive-security-e2e-verification.md`](2026-06-09_passive-security-e2e-verification.md)。
- 既有 `tests_nuclei_scanner.py` 有 2 個 pre-existing 的 ruff F841 警告，非本次引入，依精準修改原則未動。
