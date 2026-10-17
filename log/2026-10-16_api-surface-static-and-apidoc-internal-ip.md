# API 端點清單併入靜態發現 + API 規格內網 IP 升級嚴重度

**日期**：2026-10-16
**操作者**：Claude

## 變更內容

### (A) API 端點清單不再誤報「沒有可檢查的端點」
- `tasks._passive_api_check`：原本只有「爬取期間觀察到的 API 呼叫」才會產生 `api_surface`，沒有觀察到就標 `skipped`、附錄與資安分析頁顯示「這次掃描的頁面沒有呼叫同網站的 API」。公開頁本來就不會呼叫登入後的後端 API，所以即使 JS 裡明明寫了 `/api_proxy` 等端點，附錄仍是空的、與 4.1「API 文件外洩」互相矛盾。
- 現在把 `site_signals.js_api_paths`（前端 JS bundle 靜態抽出、執行期未呼叫的端點）併入 `api_surface`：標 `source="js_static"`、`method="靜態"`、`status=None`，與觀察到的路徑去重（已觀察到的不重複列），並記 `static_discovered` 計數。觀察與靜態兩者皆空才標 `skipped`。
- `analyze_api` 本身不變（仍只分析觀察到的回應）；靜態併入只在 `tasks` 這層做。
- 呈現：
  - PDF 報告附錄「API 端點清單」（`reports._report_api_surface` + `report_render/report.py`）：靜態列「發現」欄寫「前端 JS 靜態發現，執行期未呼叫」，說明段加「另有 N 個端點由前端 JS 靜態發現、執行期未實際呼叫」。`RENDERER_VERSION` 31 → 32。
  - 資安分析頁（`ProjectSecurityPage.jsx` 的 `ApiSurface`）：標題數量＝執行期＋靜態，靜態列「發現」欄顯示來源說明。

### (B) API 規格暴露內網 IP → 嚴重度中升高
- `exposure_scanner.analyze_probe_results`：命中的敏感檔案（如 OpenAPI／Swagger 規格）內容若夾帶私有／內部網段 IP（`servers` 常寫 `http://10.x.x.x:8080` 這類內網位址），等同內部網路拓樸外洩，比「只是文件公開」更實質 → 在秘鑰／PII 升級之後，至少提升為 `high`；描述與證據附內網位址判讀。公網 IP 不升級。
- 新增 `ip_context.private_ips(text)` 純函式（只做位址種類判斷、不解析 DNS）；證據用既有 `describe_ips` 產生判讀句。
- **嚴重度定為「高」而非「嚴重」**：確定性探測只能證明「規格可公開存取且內含內網位址」，尚未驗證 API 本身可未授權存取或可利用；嚴重保留給已驗證可利用／秘鑰外洩。之前 AI Agent 把同一份規格判成「嚴重」，是 Agent 以推論綜合判斷，確定性規則採較保守的「高」。若要對齊 Agent 的嚴重，可再討論。

## 原因
使用者對 ntubimdbirc.tw 最新一次正式掃描報告（ARGUS-20261016-124E）回饋兩點：
1. 報告附錄「API 端點」寫「沒有可檢查的端點」，與 4.1「`/api_proxy/v2/api-docs` API 文件外洩」互相矛盾——發現層確定性找到了端點，但附錄的呈現只看執行期呼叫。
2. 該份 API 規格暴露現在只判「中」，但規格的 `servers` 洩漏內部 IP；之前 Agent 因此判「嚴重」。確定性探測找到了規格卻沒有因內網 IP 升級。

## 影響範圍
- 只動 `api_surface` 的組成與敏感檔案嚴重度判定；不新增 model／migration／計費。
- 靜態端點只是「併入清單呈現」，不送請求、不改分數計算的輸入（原本也只有觀察到的 API findings 進分數，靜態列不產生 finding）。
- 內網 IP 升級只在命中 2xx 的敏感檔案 body 內偵測，公網 IP 不受影響。

## 驗證方式
- 後端：`uv run ruff check backend` 全過；`manage.py check` 無問題；`makemigrations --check` 無變更；`apps.scans` 全套 1385 項通過（skipped 12）。
- 新增測試：
  - `tests_api_passive.py`：無觀察但有靜態路徑時仍產生 surface（`static_discovered`、`source="js_static"`、`method="靜態"`）、靜態不與觀察到的重複、報告列標示文字。
  - `tests_exposure_scanner.py`：API 規格內含內網 IP（虛構 `10.1.2.3`）升為 high、公網 IP（`8.8.8.8`）維持 medium。
- 前端：`npm run lint`（0 error）、`npm run typecheck`、`npm test`（297 項）全過。
- 無法在本容器執行的：對 ntubimdbirc.tw 重新掃描實測（雲端容器出口 TLS 由代理重簽、無 LLM 金鑰、不應主動對第三方站台發流量）。待正式環境重掃確認：附錄列出靜態端點、API 規格暴露因內網 IP 判「高」。

## 備註（安全）
目標站的 OpenAPI/Swagger 暴露（含內部 IP）在撰稿時仍未修補。本次所有程式、測試 fixture 與文件一律使用虛構端點（`/gateway`）與虛構內網 IP（`10.1.2.3`），不含真實端點路徑或真實內網位址；修補建議（關閉對外 api-docs／swagger-ui、邊界擋 API 規格路徑、移除回應中的內網位址）由網站方執行。執行期掃描報告會把實際偵測到的內網 IP 回報給已授權的網站擁有者，這是該 finding 的用途。

## 文件同步
- `backend/apps/scans/security/CLAUDE.md`：exposure_scanner（內網 IP 升級）、api_scanner（靜態併入在 tasks 層）。
- `backend/apps/scans/CLAUDE.md`：`_passive_api_check` 說明、`RENDERER_VERSION` 32 條目。
- `backend/apps/scans/report_render/__init__.py`：`RENDERER_VERSION` 32。
- `docs/scan-stage-checks.md`、`專題文件生成/系統手冊_附錄三_掃描階段與檢測項目.md`：API 端點清單併入靜態、敏感檔案內網 IP 升級。
