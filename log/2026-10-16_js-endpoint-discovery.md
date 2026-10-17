# API 端點發現層：JS bundle 靜態抽取、靜態資源過濾、Katana 過濾放寬

**日期**：2026-10-16  
**操作者**：Claude

## 變更內容
- **靜態資源不再被當成 API**（`crawler._on_response`）：新增 `is_static_asset_path()`，攔截 same-origin 回應時先擋掉 `/_next/static/`、`/static/`、`/assets/`、`.css/.js/.map/字型/圖片` 等；這些不進 `api_endpoints`／`api_observations`。原本 Next.js 用 `fetch` 預取 CSS，resource_type 是 fetch，被收進來，「API 端點清單」整排是 `/_next/static/css/*.css`。
- **JS bundle 靜態端點發現**（`crawler`）：爬蟲載入頁面時瀏覽器已抓下同源 JS chunk（含 `_buildManifest.js`），`_on_response` 對 script 回應呼叫 `_collect_js_api_paths` → `extract_api_paths_from_js()` 用 regex 抽出看起來像 API 的絕對路徑與 rewrite base，存 `_CrawlState.js_api_paths`（最多讀 40 個 JS、每個 2 MB、抽 60 條），回在 `site_signals.js_api_paths`。body 讀完即丟，只留抽出的路徑。
- **接回探測**（`tasks._observed_api_paths`）：把 `site_signals.js_api_paths` 併入推前綴的來源，`exposure_scanner.api_prefixes` 推出前綴後，API 文件探測就會打到 `<前綴>/v3/api-docs` 等。
- **`api_prefixes` 支援單段 API 基底**（`exposure_scanner`）：JS 裡 rewrite base 常是裸字串（例如 `/gateway`、`/graphql`），拼接後的完整路徑在別處；原本要求兩段以上會把裸字串前綴丟掉。改成單段時只有該段本身是 API 基底（`_API_BASE_SEGMENT`：api／api_proxy／backend／rest／graphql／gateway／rpc／v\d／api-docs…）才當前綴，一般頁面路徑（`/about`）不當前綴。
- **Katana 隱藏端點過濾放寬**（`katana_scanner._extract_endpoint_finding`）：原本寫死 `"/api/" not in path` 才算 API，會漏掉 `/api_proxy`、`/backend`、`/rest`、`/graphql`、`/v3/api-docs`。改用 `_API_ENDPOINT_HINT`。
- 文件：`backend/apps/scans/CLAUDE.md`（crawler 列、exposure 階段、katana 列）、`backend/apps/scans/security/CLAUDE.md`（exposure_scanner 列）、`docs/scan-stage-checks.md`（第 8、11 節）、`專題文件生成/需求書_複賽版完整內容.md`。

## 原因
使用者在正式 K8s 對 實測站台 重掃仍找不到先前 AI Agent 偶然發現的「OpenAPI/Swagger 規格公開暴露」，並指出兩件事：
1. **Katana 不是在做 API 發現嗎，為什麼沒掃到？** 查出三層原因：(a) Katana 的隱藏端點判定寫死 `/api/`，把反向代理前綴形式的路徑濾掉；(b) Katana 解析到的端點只轉成資訊性 finding，沒有接回敏感檔案探測／`api_surface`／前綴推導；(c) Katana 是主動重抓，目標在 Cloudflare 後面會被 challenge 歸零。我上次（task 82）加的 API 前綴探測依賴被動攔截到的 API 回應，但該站公開頁不會呼叫登入後的後端 API，所以前綴來源是空的。真正能確定性發現、又繞得過 Cloudflare 的，是靜態讀「瀏覽器載入頁面時已經抓下來的 JS」——目標端點明文寫在網站自己的 `_buildManifest.js` 裡。
2. **PDF 報告的「API 端點清單」是垃圾**：列的全是 `/_next/static/css/*.css`。根因是 `api_scanner` 沒過濾靜態資源，而靜態資源本來就不該進 API 觀察。

## 影響範圍
- 整站＋主動＋已授權的掃描：敏感檔案探測多打幾個 API 文件路徑（每個前綴 5 個、最多 5 個前綴，仍受總上限 220 與主動速率限制）。
- 「API 端點清單」只列真正的 API 呼叫，不再混靜態資源；前綴推導也不再拿 `/_next/static/` 去推。
- JS 讀取是重用瀏覽器已載入的回應，不另外對目標發請求。
- 不新增 model／migration／計費改動。

## 驗證方式
- 功能驗證（本機）：以模擬 `_buildManifest.js` 風格的 JS 字串，`extract_api_paths_from_js` 正確抽出 rewrite base 與 API 路徑、排除頁面與靜態路徑；`api_prefixes` 把單段基底轉成前綴、`/about` 不當前綴；`build_probe_targets` 生出 `<前綴>/v3/api-docs` 探測目標並被 `classify_exposure` 判為 `exposure-file-apidoc`。
- 新增測試：`tests_js_discovery.py`（靜態資源判定、JS 抽取）、`tests_exposure_scanner.py`（單段 API 基底成前綴）、`tests_katana_scanner.py`（`/api_proxy` 等現在會回報、頁面與靜態仍略過）。
- CI 順序：ruff 通過；`tests/` 36 項通過；`manage.py check` 通過；`makemigrations --check` 無變更；後端全套 1951 項通過（skipped 12）。沒有改 `k8s/`，未跑渲染腳本。
- 尚未完成（需正式環境＋能連到目標的 worker）：對 實測站台 重新掃描，確認 OpenAPI/Swagger 規格由敏感檔案探測確定性找到、API 端點清單不再是 CSS。

## 備註（安全）
目標站的 OpenAPI/Swagger 暴露在撰稿時仍未修補（含內部 IP）。本次所有程式、測試 fixture 與文件一律使用虛構端點（`/gateway`、`/backend/report` 等）與不含真實內網 IP；修補建議（正式環境關閉 springdoc api-docs／swagger-ui、邊界擋 `/<代理前綴>/v3/api-docs`、移除回應中的內網位址）由網站方執行。
