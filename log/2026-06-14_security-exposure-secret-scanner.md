# 2026-06-14 資安掃描補強：敏感檔案外洩 + 硬編碼秘鑰偵測 + PII 誤報收斂

## 變更內容

針對「Argus 掃不到靶機 `htb.xn--gst.tw`（CEKB 弱點靶機）漏洞、也掃不到市面常見『敏感檔案/秘鑰外洩』」的核心缺口，新增主動內容探測層：

**新增檔案**
- `backend/apps/scans/security/secret_scanner.py` — 硬編碼/外洩秘鑰偵測（AWS/Google/GitHub/Stripe/SendGrid/Slack/私鑰/連線字串/JWT/明文賦值），含 `detect_secrets_in_text`、`redact_secrets_in_text`（遮罩）、`build_secret_finding`。
- `backend/apps/scans/security/exposure_scanner.py` — 敏感檔案主動探測（content discovery）：`parse_robots_disallow` / `parse_sitemap_urls` / `build_probe_targets`（內建 ~80 條高訊號路徑字典，含 dotted/非 dotted/.txt 變體）/ `classify_exposure`（16 類檔案型態）/ `analyze_probe_results`（秘鑰+PII 解析、動態提升嚴重度、新手易讀證據）/ `analyze_robots_disclosure` / `async probe_paths`（重用 Playwright 繞 CF、same-origin、max_redirects=0、速率限制、cancel 檢查點）。
- 測試：`tests_secret_scanner.py`（13）、`tests_exposure_scanner.py`（16），輸入皆取自靶機真實檔案內容。

**修改檔案**
- `tasks.py` — 整合三條：①per-page inline HTML 秘鑰偵測（被動）；②robots.txt 敏感路徑洩露 finding（被動）；③敏感檔案主動探測（**僅 deep_mode = active+authorized**）。findings 經 `owasp_mapper.tag` 寫 DB（沿用既有流程，未改狀態機）。
- `crawler.py` — `probe_site_signals` 多回傳 `robots_disallow`（供被動 robots 洩露判斷）。
- `scanners.py` — `detect_pii_in_text` 信用卡加「上下文門檻」（格式化 15/16 位 或 附近有 card/卡/付款 等關鍵字才採計），收斂隨機數字湊巧過 Luhn 的誤報。
- `security/owasp_mapper.py` — 新增 18 條 `exposure-*` / `exposure-hardcoded-secret` rule_id → OWASP/CWE 對映。
- `security/CLAUDE.md` — 檔案規劃表 + 設計原則。

## 原因

- 證據：`靶機/argus-scan-26-report.txt`（前次實掃輸出）只抓到每頁 PII（信用卡大量誤報）+ header/CSRF/GEO，**零外洩檔案命中**，SECURITY 0 分。
- 根因：`crawler.py` 純 BFS 連結跟隨，掃不到未被連結的隱藏檔；靶機 `robots.txt` 列了 ~60 條敏感路徑當地圖，Argus 完全沒利用。PII 偵測也不認 API key/連線字串/私鑰/明文密碼。

## 影響範圍

- 掃描引擎（scans app）。被動掃描新增：inline 秘鑰偵測、robots 洩露、信用卡誤報收斂。付費（active+authorized）新增：敏感檔案主動探測。
- 零 DB migration（全沿用既有 `Finding` 欄位 + `make_finding` + `owasp_mapper`）。
- 既有掃描流程不受影響（所有新邏輯 silent-fail）。

## 設計決策（使用者裁定）

1. 主動探測僅付費（active+authorized）啟用；被動只做「分析已抓到資料」（零額外請求）。
2. 注入測試（XSS/open redirect）本次不做（Phase C，後續）。
3. 一併收斂信用卡誤報。

## 子代理審查與修正（反覆修正）

`security-reviewer` 審查後修正：
- **C-2（必修，真 bug）**：`redact_secrets_in_text` 對含 placeholder 子字串的真密碼會豁免遮罩 → 改為一律遮罩（加回歸測試）。
- **H-2**：`probe_paths` 逐路徑 GET 加 `max_redirects=0`，防 open-redirect 把探針導向 metadata。
- **M-1**：連線字串 regex 加長度上限防 ReDoS。
- **M-2**：sitemap 解析前截 512KB 防 XML 炸彈。
- **C-1（SSRF，未在本模組修）**：判定為 Argus「可掃任意 host」的**既有產品設計**（crawler 已無限制抓目標、scans serializer 不擋 private IP），片面在單一 scanner 封鎖會破壞合法內網自掃且不一致 → 列產品層級決策（見 security/CLAUDE.md 待辦）。

## 整合測試（Docker 對 live 靶機，已完成）✅

`docker compose -p argusnew run`（掛載 backend、起 db/redis）在 worker 容器內對 `https://htb.xn--gst.tw/` 跑 `probe_paths` + `analyze_probe_results`：

- 探測 110 路徑，**108 個回 HTTP 200**（靶機是 SPA → catch-all 對任意路徑回同一頁；**CF 未擋** `context.request.get`，免 fallback）。
- **發現關鍵問題**：SPA soft-404 會讓 108 個 200 全變誤報。→ **修正（反覆修正）**：`exposure_scanner` 加 soft-404 偵測：探測前抓兩個隨機不存在路徑當 baseline；對每個 200 比對（normalized body 相同 / SPA 樣板前綴相同且長度極近）標記 `soft_404` 略過；另加「非 HTML 型態卻回 HTML body → 略過」內容啟發式保險。新增 5 項單元測試。
- 修正後：過濾 ~82 個 SPA 假命中，產出 **26 個全真實 findings**，完整命中靶機：`.env`/`env`/`.env.backup`/`.git/config`/`git/config`(非 dotted 鏡像也中)/`backup.sql`/`phpinfo.txt`(CRITICAL)、`wrangler.toml`/`package.json`/`server-status`(洩內網 10.0.7.13)/`api/debug/users.json`/`assets/staff.csv`/`assets/transactions.json`/`.well-known/security.txt`(HIGH)、`.DS_Store`/`admin/*`(MEDIUM)。證據皆為真實外洩片段 + flag、中文新手易讀。

## 驗證方式

- `uv run python backend/manage.py test apps.scans` → **191 passed**（含新增 34 項與既有回歸）。
- `uv run ruff check`（新增/修改檔案）→ All checks passed（既有 3 處技術債在未動檔案，未處理）。
- `uv run python backend/manage.py check` → no issues。
- Docker 整合實掃 live 靶機 → 見上，26 真實 findings、CF 不擋、soft-404 已濾。

## 尚待處理（後續精準度微調，非 blocker）

1. 報告（.docx）對新 finding 證據呈現的新手友善度可再人工看一眼。
2. 內容去重：`.env`/`.env.production`、`/admin/`·`/admin/login` 等「同內容多 URL」會產生重複 finding，可加 body hash 去重。
3. M-3（package.json 等公開檔 severity）、M-4（inline Google Maps key 誤報）。
4. C-1 SSRF（產品層級政策）、Phase C 注入測試。

## 部署/commit 狀態

**尚未 commit/push。** push→GitHub→公網部署機自動 PULL 生效（= 動 production），需先取得使用者同意。
