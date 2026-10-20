# Swagger UI 與預設錯誤頁版本號補成確定性規則

**日期**：2026-10-20
**操作者**：Claude

## 變更內容
- `security/exposure_scanner.py`：
  - `_probe_tech_disclosure(requester, origin, api_path_prefixes)`：主敏感檔探測後，對根目錄與 API 前綴（上限 `MAX_TECH_PREFIXES`＝4）探 `SWAGGER_UI_SUFFIXES`（`swagger-ui/index.html` 等）與 `ERROR_PAGE_SUFFIXES`（`WEB-INF/web.xml`，觸發預設錯誤頁、無論狀態碼都讀 body），結果帶 `kind` 併進 `probe_paths` 回傳。
  - `analyze_swagger_ui(results)`：body 帶 Swagger UI 專屬標記（`_SWAGGER_UI_MARKERS`，排除 SPA catch-all）→ `exposure-swagger-ui`（低）。
  - `analyze_server_banner(results)`：只看 `kind=error_page` body，比對 `_SERVER_BANNER_RE`（`Apache Tomcat/9.0.102` 等精確版本橫幅）→ `exposure-server-error-banner`（低）。
  - `_endpoint_path()` 輔助（跨層去重用的端點正規化）。
- `tasks.stage_exposure`：`exposure_findings` 併入上述兩個分析器的結果（覆蓋檢查同 `exposure_probe`）。
- `security/owasp_mapper.py`：`exposure-swagger-ui`、`exposure-server-error-banner` → A05／CWE-200。
- 測試：`tests_exposure_scanner.py` 新增 `AnalyzeSwaggerUiTests`、`AnalyzeServerBannerTests`；既有 `test_baselines_and_probe_share_one_rate_limiter` 的 GET／sleep 次數因多了技術棧探測而更新（3→7、2→6）。

## 原因
使用者要求把 Swagger UI 公開、Tomcat 預設錯誤頁版本號補成確定性規則。這兩項原本只有 AI Agent 偶然發現，代號是「弱點類＋描述雜湊」，措辭一變就漂——導致同一問題同時出現在「新增」與「本次未出現」、不進計分與優先處理。沉澱成確定性後代號固定，不再漂、會進計分與優先處理、跨掃描比較穩定。

第二組內網 IP（v2 api-docs 的 `host: 172.17.202.181:3000`）不需新規則：根目錄字典與 API 前綴都已探 `v2/api-docs`，`analyze_probe_results` 既有的「回應夾帶內網 IP 就升級嚴重度」會涵蓋。

## 影響範圍
- 只在「全站＋主動＋網域已驗證」的授權掃描執行（沿用 exposure 閘門）。
- 新增兩個低風險確定性資安發現，進計分、問題清單與報告；`finding_kind` 依 `exposure-` 歸「曝露面」。
- Swagger UI 的規格本身外洩仍由 `exposure-file-apidoc`（高）另計，此項是互動式 UI；避免與 apidoc 重複：Swagger UI 的 URL 含 `swagger` 會被 apidoc 分類器當 HTML soft-404 跳過，不會雙報。
- 外部請求量：每次掃描多出根目錄＋最多 4 個前綴 ×（3 Swagger UI＋1 錯誤頁）的探測，受既有 active RPS 與同一個 pacer 控制。

## 驗證方式
- `uv run ruff check`（exposure_scanner、tasks、owasp_mapper、tests）：All checks passed。
- `uv run python backend/manage.py check`：no issues。
- `manage.py test apps.scans.tests_exposure_scanner apps.scans.tests_authz_probe apps.scans.tests_pipeline_stages`：85 pass。
- 未自動驗證：正式叢集對真實目標的實際命中（Swagger UI 標記、Tomcat 版本橫幅）——需部署後實機確認；不影響本機與 CI。
