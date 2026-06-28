# 2026-06-09 被動安全 scanner Docker 端到端驗證與 OWASP 對映修正

## 變更內容

對 2026-06-07 完成的被動安全 scanner 套件進行真實 Docker 端到端驗證（Chrome 操作 `localhost:8080` UI），並修正驗證中發現的問題：

- `owasp_mapper.py` 新增 `_KEYWORD_OWASP_MAP` 子字串比對層，涵蓋既有 `analyze_security` 的 `SECURITY_<token>_<hash>` rule_id（HSTS / CSP / X-Frame-Options / X-Content-Type-Options / CSRF / HTTPS / PII）。保留新 scanner 乾淨 rule_id 的精確比對優先。
- `tests_security_scanners.py` 新增 `TestOwaspMapperExistingFindings`（4 個測試）。

## 原因

真實掃描（靶機 `https://camb.xn--gst.tw/`，自設、已授權）暴露單元測試未涵蓋的問題：
**既有 `analyze_security` findings 的 rule_id 帶 sha1 雜湊後綴，原 `_RULE_OWASP_MAP` 精確比對永遠配不到，導致報告中實際出現的 findings（HSTS/CSP/X-Frame 等）OWASP/CWE 全空。** 這正中「報告加 OWASP/CWE 標籤」目標的要害。此問題在 2026-06-07 log 的備註中已被預示為待辦。

## 影響範圍

- 僅改 `owasp_mapper.py` 的 `_lookup`（加關鍵字 fallback）與測試；`tag()` / `backfill()` 介面不變。
- 既有 finding 的 owasp/cwe 由空字串變為有值，純加法、不影響非 security finding。

## 驗證方式（真實 Docker E2E）

1. `docker compose up -d --build web worker`，migration `0009` 套用成功。
2. Chrome 操作 UI 建立掃描（單一頁面，靶機 camb.xn--gst.tw）：
   - scan 20（修正前）：log 出現「深度被動安全掃描完成：0 項發現」→ 新 scanner 確實執行、Cloudflare 後健康目標 0 誤報；但 6 個既有 security finding 的 OWASP/CWE 全空 → 暴露問題。
   - 修正並重建 worker 後，對 scan 20 跑 `backfill` → 5 個 finding 正確貼標（PII=A02/CWE-359、CSP=A05/CWE-693、HSTS=A05/CWE-319、X-Content=A05/CWE-693、X-Frame=A05/CWE-1021）。
   - 產生 scan 20 Word 報告（`build_scan_report`）→ 確認 5 行「OWASP：.. / CWE：..」實際渲染。
   - scan 21（修正後全新掃描）：正常 Celery 管線 findings **自動**帶 OWASP/CWE 標籤，無需手動 backfill。
3. `uv run python backend/manage.py test apps.scans.tests_security_scanners` → 全綠。
4. `uv run ruff check ...` → All checks passed。

## 已知限制（待後續）

- 新 SSL/Cookie/Header scanner 在「健康且受 Cloudflare 保護」的目標上不會產生 finding（正確、無誤報）。要在 demo 展示新 findings，需挑有實際問題的目標（已用 `expired.badssl.com` / `self-signed.badssl.com` / `apache.org` 離線驗證三個 scanner 皆能命中真實問題）。
- 前端 React finding 卡片尚未顯示 OWASP/CWE（本次只到 serializer 輸出 + Word 報告層；UI 卡片顯示為後續可選項）。
