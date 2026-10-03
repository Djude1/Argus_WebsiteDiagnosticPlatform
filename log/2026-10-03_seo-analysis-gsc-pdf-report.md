# 報告改 PDF、SEO 分析頁、Search Console 串接、導覽與側邊欄調整

**日期**：2026-10-03  
**操作者**：Claude

## 變更內容
- **報告只提供 PDF**
  - `reports.py` 拆成兩步：
    - `render_report_docx` 只排版產生 .docx。
    - `build_scan_report` 在暫存目錄排版後，交給新的 `report_pdf.convert_docx_to_pdf` 轉成 `scan-<id>-report.pdf`，再寫 `ReportVerification`。
  - 轉檔用 LibreOffice headless：每次用獨立的暫存使用者設定檔，逾時設定 `ARGUS_REPORT_PDF_TIMEOUT_SECONDS`，原子寫入。
  - 轉檔失敗拋 `ReportConversionError`，不寫防偽紀錄，也不退回提供 .docx。
  - 防偽雜湊改為對 PDF 計算。`RENDERER_VERSION` 從 3 改為 4，舊的 .docx 快取會自動重產。
  - 下載回應改成 `application/pdf`。
  - `cleanup_reports` 會同時清除 .pdf 與舊的 .docx。
  - MCP 的 `get_scan_report` 改為 `format: pdf`。
  - 前端改為「下載 PDF 報告」：掃描詳情與歷史報告；公開頁與合作頁的文案一併修改。
  - content migration 0015 把首頁功能卡「Word 報告匯出」改為 PDF，只改仍是種子原文的資料列。
  - Dockerfile 加裝 `libreoffice-writer-nogui`，並在 build 時跑 `soffice --version` 確認安裝成功。
  - CI Quality Gate 加裝同一套件，讓真實轉檔測試在 CI 執行。
- **SEO 分析頁**：側邊欄「掃描」下方新增，路由 `/projects/:id/seo`。後端在 `apps/scans/seo/`，API 在 `seo_views.py`。
  - 逐頁檢查（`page_audit.py`）：Title、Description、H1–H6 清單與跳號、正文、canonical、robots meta／X-Robots-Tag、圖片 alt、連結與錨文字、OG、hreflang。
  - 新掃描階段 `seo_links`（勾 SEO 才跑）：
    - 連結狀態與跳轉鏈：每一跳都檢查是否為公開位址，最多 150 個連結、120 秒。
    - 站台檢查：robots.txt、sitemap、HTTP→HTTPS、www、404、index.html、結尾斜線。
    - 結果寫 `ScanJob.seo_report`。
  - 彙整（`report.py`）：概覽、優先修復事項、全部問題（每處附網址、檢測時間與證據）、依目標合併的連結、錨文字問題、重複的 Title／Description。
  - 目標關鍵字：`SiteProject.target_keywords`，`keywords.py` 做比對。
  - 前端 `ProjectSeoPage.jsx`，樣式 `95-seo.css`。四個分頁：概覽、頁面與內容、連結、搜尋關鍵字。另有單頁證據抽屜，以及網址篩選與掃描批次切換。
- **Google Search Console 完整串接**（`seo/gsc.py`）
  - OAuth web flow，權限只有 webmasters.readonly。state 有簽章，並與只在 callback 路徑送出的 HttpOnly nonce cookie 綁定，防 OAuth CSRF。
  - refresh token 以 Fernet 加密存在新 model `SearchConsoleConnection`（migration 0022）。
  - 功能：選擇資源（以 Google 回傳清單驗證）、搜尋成效（查詢字詞含與前一期比較、頁面、每日趨勢、字詞對應頁面，快取 1 小時）、網址檢查（Google 是否已收錄）、中斷連線時撤銷授權。
  - 新設定：`GOOGLE_OAUTH_CLIENT_SECRET`、`ARGUS_GSC_REDIRECT_URI`、`ARGUS_GSC_TOKEN_KEY`、`THROTTLE_GSC`。`.env.example` 與 `k8s/02-secret.example.yaml` 已補上。
- **導覽與側邊欄**
  - 工作區側邊欄最上方新增「所有專案」入口。
  - 會員導覽列全螢幕時貼齊兩側（取消 1440px 置中上限）。
  - 品牌小字「AI 網站健檢平台」放大到 1.12rem，頭像放大到 42px。
  - 切換器與 ⌘K 搜尋加入 SEO 分析分頁。
- 修正掃描時間卡在 390px 寬被長選項撐出 29px 水平捲動（既有問題，SEO 頁也會用到）。
- 新增依賴 `cryptography>=44`。之前只是間接相依，現在直接使用 Fernet，改為明確宣告。

## 原因
使用者要求：
- 下載的報告從 Word 改為 PDF，回答確認只提供 PDF。
- 側邊欄加上所有專案入口。
- 頂部列全螢幕時左右留白要貼齊，品牌字與頭像放大。
- 參考 Sitechecker 對 https://ntubimdbirc.tw 的分析與需求說明，新增「SEO 分析」頁，並完整串接 GSC。

需求中的判定原則全部有測試鎖定：
- H1 不必與 Title 相同。
- 302 → 200 不算失效。
- 繁中不套用英文字符門檻。
- 每項結論附網址、時間與證據。
- 「可索引」與「Google 已收錄」分開顯示。
- GSC 平均排名標示為期間統計值。

## 影響範圍
- **部署**：
  - backend image 多了 LibreOffice Writer（約數百 MB）。
  - web 第一次下載報告時會同步轉檔，實測約 2 秒。
  - migration 0022（scans）與 0015（content）由 Argo PreSync Job 套用。
- **GSC 啟用前需要人工設定**：
  1. Google Cloud 啟用 Search Console API。
  2. OAuth 同意畫面加入 scope `webmasters.readonly`。
  3. OAuth 用戶端為每個對外網域登記 `https://<網域>/api/gsc/callback/`。
  4. 把 `GOOGLE_OAUTH_CLIENT_SECRET` 放進 `.env`／`argus-secret`。
  - 未設定時，頁面顯示「管理員尚未設定」，其他功能照常。
- **舊掃描**：沒有 `seo_report`，連結區只顯示爬蟲已造訪的站內頁，站台檢查顯示「這次掃描沒有」。示範專案同樣如此（示範資料沒有重產）。
- **掃描變慢**：勾 SEO 的掃描多一個連結檢查步驟，最多約 2 分鐘。失敗只記 log，不影響完成與計分。

## 驗證方式
- **後端測試**：
  - `tests_seo_analysis.py`（29 項）涵蓋：
    - 中文寬度門檻、H1 與 Title 不比較。
    - X-Robots-Tag noindex 與 canonical 影響可索引。
    - 302→200、HEAD 520 以 GET 確認、403 判為無法確認、轉址迴圈、非公開位址略過。
    - 證據帶網址與時間、robots.txt Disallow、重複 Title。
    - 跨使用者 404、關鍵字驗證、掃描階段失敗不拋。
    - GSC：完整 OAuth 流程與加密、nonce 不符拒絕、scope 不足拒絕、資源驗證、前後期比較、網址檢查限本站、撤銷、授權失效提示、未設定與示範專案的限制。
  - `tests_report_pdf.py`：PDF 流程、下載標頭、轉檔失敗不寫紀錄、找不到 LibreOffice、逾時、真實 LibreOffice 轉檔。
  - 既有報告測試改為讀 `render_report_docx` 產生的 .docx；需要完整流程的以 `fake_pdf_conversion` 替身。
- **全部檢查**：後端全部測試、ruff、`makemigrations --check`、`manage.py check` 通過；前端 lint（只剩 AdminPages 既有 1 個 warning）、typecheck、vitest 25 檔 187 項、vite build 通過。
- **實機**（本機 runserver＋真實掃描 https://ntubimdbirc.tw ，15 頁上限、只勾 SEO）：
  - 12 頁、23 個連結。
  - 實測發現該站 HEAD 一律回 Cloudflare 520，因此改成 HEAD 錯誤時一律以 GET 確認，並排除 Cloudflare 注入的 `/cdn-cgi/` 連結。
  - 修正後結果與 curl GET 一致：`/service/0–3` 為 404；子網域 200；Instagram 302 → 429 判為「對方限制檢查」；www 與非 www 都回 200（警告）；HTTP 301 → HTTPS 正確。
- **PDF 實機下載**：`Content-Type: application/pdf`、14 頁。拿下載檔的 SHA-256 到 `/api/verify/<編號>/?content_sha256=` 查詢，結果 `matches: true`。
- **Playwright 截圖**（1440／390px、日／夜）：
  - 概覽、問題展開、頁面與內容、單頁證據抽屜、連結、搜尋關鍵字、總覽側邊欄。
  - 無水平捲動、無 JS 錯誤。
- **尚未實測**：真實 Google OAuth（需上述 Google Cloud 設定與 client secret），目前只有以 mock 驗證的完整流程。
