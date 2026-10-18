# 修敏感檔案外洩誤報：SPA 首頁以註解開頭時 soft-404 保險失效

**日期**：2026-10-18
**操作者**：Claude
**來源**：審查掃描報告 8AC2（juice-shop，新鏡像）。4.1–4.8 共 8 筆「敏感檔案外洩」
（2 嚴重＋6 高）的「檔案內容片段」全是同一份 juice-shop Angular 首頁 `index.html`，
且全部「偵測到 mobile×1」——是 SPA catch-all soft-404 假命中，不是真檔案。資安分數被打到 1 分。

## 根因
exposure_scanner 有兩道 soft-404 防線：(1) `_is_soft_404` 比對「保證不存在路徑」的 baseline；
(2) baseline 沒攔到時的內容啟發式保險——非 HTML 型態（env／actuator／sourcemap／log／apidoc…）
卻回 HTML body 就視為 SPA fallback。

第二道原本只看 `body.lstrip()` 是不是 `<!doctype html>`／`<html` 開頭。juice-shop 的 index.html
**以授權條款註解 `<!-- Copyright… OWASP Juice Shop… -->` 開頭，`<!doctype html>` 在註解之後**，
所以 `startswith` 判不到 → 8 筆全漏過保險被報出來（`/actuator/env.json` 應回 JSON、
`/bundle.js.map` 應回 JSON、`/wp-content/debug.log` 應回文字、`/wp-login.php` juice-shop 根本不是
WordPress——全回同一份 HTML 首頁）。

## 修法（最小、精準）
`security/exposure_scanner.py`：
- 新增 `_starts_html_document(body)`：先 `lstrip`、再去掉開頭連續的 HTML 註解（`<!-- … -->`，
  可能多段；註解沒收尾就停手，不把註解內容當文件開頭），然後才判斷是不是 `<!doctype html`／`<html`。
- `analyze_probe_results` 第二道保險改用此 helper。

政策不變（原本就會把非 HTML 型態回的 HTML 文件當 soft-404 濾掉，含 GraphiQL 這種 trade-off），
只是把「註解開頭的 HTML 文件」也納入判斷，對齊原本註解寫的意圖。`_HTML_EXPECTED_TYPES`
（phpinfo／server_status／admin／dir_listing）照舊豁免，真的後台登入頁回 HTML 不受影響。

## 驗證
- `tests_exposure_scanner`（29，+3）：`test_commented_spa_shell_skipped`（actuator/env.json、
  bundle.js.map、wp-content/debug.log、plans.json、.claude/launch.json 回註解開頭 SPA 首頁都被濾掉）、
  `test_starts_html_document_helper`（含「註解沒收尾不誤判」）；原 `test_admin_html_still_reported`
  仍綠（HTML-expected 型態不被誤殺）。`ruff check backend` 乾淨。
- 文件同步 `backend/apps/scans/security/CLAUDE.md` exposure_scanner 條目。

## 影響
修正後 juice-shop 這類 SPA 的敏感檔探測不再把 catch-all 首頁當成數筆嚴重／高風險外洩，
資安分數回到反映實際風險。待 rebuild backend image 後生效。不影響真實外洩檔案的偵測
（真 JSON／map／log 不會以 HTML 文件開頭）。

## 本次審查同時確認已生效（8AC2 新鏡像）
- security.txt 只含公開聯絡 email → 維持「資訊」等級（4.21），正確；夾帶其他個資才升級。
- ZAP 卡片中文化（4.9／4.14，無 "NO" 截斷）、Agent 一律繁中（4.13）、0.0.0.0 不誤報、
  「與前次比較」新出現項目收斂（列 8 項）——全部驗證生效。

## 待辦（本輪未做，延續統一規劃）
- #4 跨端點同義去重（juice-shop 4.5 中文 = 4.11 英文，同 `/rest/admin/application-configuration`）。
- Agent 4.13 把 `127.0.0.1`（loopback）寫成「內部網路資訊外洩」略為過度；核心發現
  （未授權 `/rest/admin/application-configuration` 洩 Google OAuth client_id）正確。
- SPA 路由發現（P1）。
