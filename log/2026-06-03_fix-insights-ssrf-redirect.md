# 修復 insights speed-test 的 redirect SSRF 繞過

**日期**：2026-06-03
**操作者**：Claude

## 變更內容
- **`backend/apps/insights/analyzers.py`**：新增 `_safe_get`（`allow_redirects=False` + 逐跳 `assert_public_url`），`analyze_speed` 改呼叫它取代原本 `allow_redirects=True` 的單次 `requests.get`；新增 `urljoin` import 與 `REDIRECT_STATUSES` / `MAX_SPEED_REDIRECTS`。
- **`backend/apps/insights/tests.py`**：新增回歸測試 `test_speed_test_blocks_redirect_to_internal_host`（公開 URL 302 轉址到 link-local `169.254.169.254` 必須被擋、且只發出 1 個請求）。
- **`backend/apps/insights/CLAUDE.md`**：安全段由「待修」更新為「✅ 已修復」並補「DNS rebinding 已知殘留限制」；禁止事項改為「嚴禁改回 `allow_redirects=True`」（文件同步強制規則，同次 commit）。

## 原因
使用者核准修復 `analyze_speed` 的 SSRF 殘留（先前 QA 子代理發現）：原本 `allow_redirects=True` 只檢查初始 URL，公開 URL 若 302 轉址到內網仍會被抓 → SSRF 繞過。要求「修前詳細確認」，已先讀懂 `assert_public_url`/`normalize_url`/測試 mock 後再改。

## 影響範圍
- 只影響 `/api/insights/speed-test/` 的外部抓取路徑；其餘 insights 功能不變。
- 後續若有人把 `_safe_get` 改回 `allow_redirects=True` 會重新引入漏洞（已於 CLAUDE.md 標明嚴禁）。
- 純此 app；不影響其他 app。

## 待辦（已回報使用者，本次未動）
- 🔴 `backend/apps/scans/views.py` 的 `estimate_scan` 是**同類、仍存在**的 SSRF：`_is_safe_url`（:446）的 regex blocklist **放行 `169.254.169.254` 雲端 metadata**，且 `:483`/`:530` 用 `allow_redirects=True`。建議改用 insights 同一套 `assert_public_url` + `_safe_get`。待使用者決定。

## 驗證方式
- `uv run python backend/manage.py test apps.insights -v 2` → **7 tests OK**（含新回歸測試；既有 `test_speed_test_returns_lightweight_metrics` 未被改壞）。
- QA 子代理實測多種繞過（protocol-relative、相對 redirect、redirect 迴圈、大小寫 Location、IPv6、十進位/十六進位 IP、非 http scheme）皆被擋下。
