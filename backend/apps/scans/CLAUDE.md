# scans 模組規則

Claude Code 進 `backend/apps/scans/` 工作時，本檔在專案層 `CLAUDE.md` 之後自動載入；**ZCode／Codex 不會自動載入本檔**，動手前必須先讀（見根 `AGENTS.md` 模組規則必讀閘門）。

---

## ScanJob 狀態機

狀態只能按以下順序推進，**禁止跳轉或逆轉**：

```
queued → crawling → scanning → [agent_testing] → completed
    ↘ cancelled（任何階段可轉）
    ↘ failed（任何階段可轉）
```

- 狀態推進只能在 `tasks.py` 中進行
- `scanners.py` 和 `crawler.py` 禁止直接修改 `ScanJob.status`
- 原因：集中在 `tasks.py` 管理讓狀態轉換可追蹤，也讓 signal 可以統一監聽

---

## 各檔案職責

| 檔案 | 職責 | 禁止做的事 |
|---|---|---|
| `tasks.py` | Celery task 入口、狀態機推進、呼叫 billing；掃描流程拆成 `SCAN_PIPELINE` 階段函式（見下「掃描流程階段」）；`request_scan_cancel()` 為網頁與 MCP 共用的取消＋退款入口 | 直接執行爬蟲邏輯 |
| `scan_plan.py` | 將單頁／全網站範圍與主動授權集中轉成各工具的執行閘門 | 寫 DB、執行任何掃描工具 |
| `process_runner.py` | 以 `Popen` 執行 Nuclei/Katana，輪詢 DB 取消並終止 process tree | 吞掉 `ScanCancelled`、記錄 raw stdout/stderr |
| `crawler.py` | Playwright BFS 爬蟲、收集頁面（`har_dir` 有值時每個 context 錄一個只含同 origin 的 HAR，給 ZAP 被動分析）；整站模式以 robots.txt 宣告的 sitemap（或 `/sitemap.xml`）補種子（`discover_sitemap_urls` → `_CrawlState.seed`，同 origin、非 `.gz`、≤2 MB、索引最多展開 3 個子檔；與掃描網址只差 `www.` 前綴的 sitemap 網址由 `to_scan_origin` 改寫成掃描 origin），連結稀疏的網站也能達到頁數上限；預設深度 `ARGUS_DEFAULT_MAX_DEPTH`＝6。**爬取預算（2026-10-08，roadmap「爬取」第 2 項）**：`_CrawlState` 記種子來源（起始網址／sitemap）、頁面連結排入數、超過頁數上限沒排入、超過深度、robots.txt 禁止、擷取失敗、速率限制等待次數與秒數、每頁耗時；`crawl_site` 結束時（含例外）寫 `warnings["crawl_budget"]`＝`budget_summary(stop_reason, 秒數)`（`stop_reason`：max_pages／queue_exhausted／browser_failed），存進 `warning_summary`、`stage_crawl` 以 `tasks.crawl_budget_text` 寫一行 log（不列在「爬取警告」）、後台掃描詳情顯示。**渲染就緒（2026-10-08，roadmap「爬取」第 1 項）**：`goto(domcontentloaded)` 之後、擷取之前 `wait_for_render_ready`：每 250ms 量正文字數與元素數，至少等 0.5 秒（hydration），連續兩次幾乎不變（字數差 ≤ max(20, 0.5%)、元素數差 ≤ 2，容許輪播）就算就緒；上限 `ARGUS_RENDER_READY_MAX_SECONDS`（5）。逾時照樣擷取，記在 `crawl_budget.render_readiness`（ready／timeout／error 數、平均毫秒、逾時網址）、log 與 `crawl` 覆蓋說明（`render_readiness_timeout`，**不改覆蓋狀態**）。不用 networkidle。等待時間從 `load_time_ms` 扣掉（SEO「載入慢」與網站優勢的載入時間依此判斷）。沙箱實測 9 個網站都在約 0.5 秒就緒、就緒後 3 秒正文沒有再增加。同次修正：`enqueue_links` 不再重複排入已在佇列的網址（sitemap 已排入的頁面又被首頁連結排一次，重複項目會佔掉頁數上限、把新頁面擠掉）。測試 `tests_crawl_budget.py`。`/cdn-cgi/` 路徑一律不爬（`is_crawl_trap`：Cloudflare 給機器人的無限陷阱連結）。Cloudflare 攔截頁判定只認 `/cdn-cgi/challenge-platform/h/`、`_cf_chl_opt` 等攔截頁專屬標記——**不可用裸字串 `challenge-platform`**：CF Bot 偵測會在每個正常頁面插入 `/cdn-cgi/challenge-platform/scripts/` 背景腳本，曾讓整站只爬到首頁且被誤標為被阻擋（`waf_scanner.py` 同理） | 修改 ScanJob.status、呼叫 billing |
| `scanners.py` | SEO/AEO/GEO/UX 掃描 + 被動式基本安全檢查（HTTPS/header 存在性/CSRF/PII）、產生 findings | 修改 ScanJob.status、深度資安分析 |
| `score_explain.py` | 分數說明（`GET /api/scans/<id>/score-breakdown/`）：以 `finding_normalization.stored_scoring_inputs` 還原計分輸入，依目前公式 `scanners.score_breakdown` 逐維度列基準分、扣分項目（權重、出現處數、`score_without`）、`in_base`／`info` 筆數、覆蓋狀態與未完整完成的檢查；重算分數與保存分數不同時 `matches=false` | 寫 DB、自己重寫一套計分邏輯 |
| `coverage.py` | 掃描覆蓋契約（見下「掃描覆蓋契約」）：`ScanCoverage` 累積各檢查狀態與產生的問題代號、`category_status`、`incomplete_checks`、`absent_issue_status`（前次有本次沒有的問題狀態）、`issue_key` | 寫 DB、修改 `ScanJob.status` |
| `fingerprint.py`、`fingerprint_gold.py`、`fingerprint_benchmark.py` | 網站特徵（Smart Scan 階段 1，見下「網站特徵」）：`build_fingerprint` 只用爬取已有的訊號、`fingerprint_snapshot` 存 `ScanJob.fingerprint`；準確率資料集與指標 | 發任何請求、改變執行計畫或覆蓋紀錄、把「沒看到」寫成 False |
| `ai_bots.py` | AI 爬蟲的 robots.txt 政策：13 個 AI 爬蟲依用途分訓練／AI 搜尋／使用者觸發，依 RFC 9309 判斷（點名群組優先於 `*`、產品名稱完全比對、Allow／Disallow 取最長路徑）允許／部分限制／封鎖；爬蟲讀 robots.txt 時算好放 `site_signals.ai_bot_policy`，`site_profile.ai_bots`（勾 GEO）。**只封鎖訓練用爬蟲不算問題**；封鎖 AI 搜尋或使用者觸發的爬蟲才產生 `geo-ai-search-bots-blocked`（低） | 另發請求、把封鎖訓練爬蟲當成問題 |
| `geo_entity.py` | GEO 實體與權威訊號（roadmap §3 第 1 項，`stage_geo_site` 呼叫）：讀已保存頁面的 JSON-LD 與 meta，判斷組織實體（Organization／LocalBusiness 等，不含 Person——文章作者就是 Person）、`sameAs`（Wikidata、維基百科、社群）、文章作者。Finding：`geo-entity-organization-missing`（低，有結構化資料但沒有組織；完全沒有 JSON-LD 的網站交給逐頁提醒）、`geo-entity-no-same-as`（資訊）、`geo-article-author-missing`（低）。文章頁＝JSON-LD 標 Article 類，或 `og:type=article`＋`article:published_time` 且 `<article>` 區塊少於 3 個；`CollectionPage`／`ItemList` 不算（WordPress 常把分類頁標成 og:type=article）。**內容新鮮度**（roadmap §3 第 2 項，`freshness_findings(summary, today)`）：文章頁的 JSON-LD `datePublished`／`dateModified` 與 `article:published_time`／`article:modified_time` → `geo-article-date-missing`（低，兩邊都沒有日期）、`geo-article-date-invalid`（低，更新早於發布或未來日期，容許 1 天）、`geo-article-date-inconsistent`（低，JSON-LD 與 meta 相差超過 1 天）；只檢查日期標記，不判斷內容新舊 | 發請求、把列表頁當文章、把作者 Person 當組織、把長青內容判為過時 |
| `geo_structure.py` | GEO 可被 AI 摘要性（roadmap §3 第 3 項，`scanners.analyze_page` 的 GEO 分支逐頁呼叫；函式內匯入避免循環）：`geo-long-content-no-subheadings`（低，成句段落 ≥40 字合計約中文 1500 字／英文 1000 詞以上且原始 HTML 沒有 h2–h6——直接數原始 HTML，因為正文擷取排除 `<header>`、部落格常把文章標題放在裡面）、`geo-enumeration-not-list`（資訊，同一段有 3 個以上編號）。略過非 HTML 文件（RSS）與 `<pre>`／`<code>`；入口網站的短連結文字不算長文 | 判斷「開頭有沒有摘要句」這類寫作品質、看整頁有沒有 `<ul>`（導覽列幾乎都是 `<ul>`） |
| `pagespeed.py` | Google PageSpeed Insights（見下「PageSpeed Insights」）：`fetch` 呼叫 PSI v5、`parse` 整理成 `ScanJob.performance_report`、`summary_lines` 給報告範圍表 | 修改 `ScanJob.status`、把金鑰寫進 log 或錯誤訊息、把外部分數併入 Argus 分數 |
| `evidence/` | 跨模組共用證據（P0-B）：`contacts.py` 的 Email／電話格式、正規化（`normalize_phone`：+886→0、去分機）、`collect_contacts`（每筆帶來源網址、取得方式、位置 content／comment／link、視窗、登入狀態）。資安 `scanners.analyze_data_exposure`、`security/redaction.py` 與 AEO `aeo/answers.py`、`aeo/evaluate.reconcile_contact` 都從這裡取，**不得各自另寫 Email／電話 regex** | 寫 DB、連線目標網站 |
| `cancellation.py` | 合作式取消：`is_cancelled` / `raise_if_cancelled` 直接查 DB `ScanJob.status` 是否為 `CANCELLED`（**非 Redis 旗標**），供 worker 在檢查點輪詢 | 直接終止 worker process |
| `fixgen/` | 修正產出引擎（ADR-0002）：`facts.py` 爬取事實萃取、`policy.py` 事實政策三級驗證、`engine.py` prompt＋單次 JSON 產生＋渲染、`services.py` 計費閘門觸發（先扣後派）＋狀態機冪等、`tasks.py` Celery 任務（不重試）。API 掛在 ScanJobViewSet 的 `fix-output/trigger|status|artifacts` | 修改 `ScanJob.status`、自動重試、繞過事實政策驗證、派工後才計費 |
| `reports.py` | 報告 payload 與排版：`render_report_docx` 產生 .docx（內容測試直接讀它），`build_scan_report` 再交給 `report_pdf.py` 轉成 PDF 並寫 `ReportVerification`；**對外只提供 PDF**（2026-10-03） | 防偽紀錄以外的 DB 寫入 |
| `report_pdf.py` | LibreOffice headless 把 .docx 轉成 PDF：每次用獨立暫存使用者設定檔（web／worker 同時轉檔不互鎖）、逾時 `ARGUS_REPORT_PDF_TIMEOUT_SECONDS`、原子寫入；失敗拋 `ReportConversionError`，**不退回提供 .docx**。Docker image 裝 `libreoffice-writer-nogui` | 退回 .docx、共用 LibreOffice 設定檔 |
| `seo/`、`seo_views.py` | SEO 分析頁與 Google Search Console（見下「SEO 分析與 Search Console」） | 修改 `ScanJob.status`、產生 Finding、回傳 refresh token |
| `projects.py` | 網站專案的彙整資料（只讀 DB）：`project_overview`（含 `latest_scan.site_summary`：`site_summary()` 整理已保存的 PageSpeed 效能分數／CrUX 評等／pagespeed 覆蓋狀態、CDN 邊緣、技術前 6 項與總數、安全標頭等第、`profile_available`，2026-10-08；本次掃描覆蓋 `stats`、各維度問題數、AEO 摘要、最近掃描，以及 `site_description`：最新完成掃描首頁 HTML 的 meta description／og:description，前 100k 字元、最多 `SITE_DESCRIPTION_LIMIT` 字）、`project_issues`／`compare_issues`（新增／持續／本次未出現；每個問題含說明、修法、最多 `ISSUE_URLS_LIMIT` 個網址）、`project_security`（資安分析頁，2026-10-08：沿用 `project_issues` 只取資安問題，加上資安分數與覆蓋、未完成的資安檢查、`site_profile.observatory`、CDN 邊緣、依類型的數量（`finding_kind.KIND_LABELS`／`KIND_DESCRIPTIONS`）、相關根本原因、資安類網站優勢；測試 `tests_project_security.py`）、`project_pages`（逐頁狀態與問題數）、`project_summaries`（清單用：最新分數與變化、`score_history` 走勢、最新完成掃描依嚴重度的 `issue_counts`；兩次查詢） | 寫 DB、連線目標網站 |
| `root_causes.py` | 根本原因關聯（roadmap Root Cause Correlation，2026-10-08）：`ROOT_CAUSES` 以 rule_id 正則把同一處修法的問題歸類（伺服器回應標頭 `SECURITY_CSP_`／`SECURITY_HSTS_`／`SECURITY_X_FRAME_OPTIONS_`／`SECURITY_X_CONTENT_TYPE_OPTIONS_`／`header-`、`cookie-`、`ssl-`、`dns-spf|dmarc-`、`SEO_ALT_`＋axe 圖片替代文字、`geo-article-`）；`annotate_root_causes` 只在同一原因有 2 個以上問題時給問題加 `root_cause` 並回傳摘要（依最高嚴重度、問題數、頁數排序）。`project_issues` 回 `root_causes`；PDF 報告第一章「改一處就能一起解決」（`reports._report_root_causes` → `summary.root_causes`，項次對應第 4 章、資訊提示不列，`RENDERER_VERSION` 18）。新增歸類必須是修法確實在同一處，不可為了湊組放進去。測試 `tests_root_causes.py` | 改嚴重度、合併問題、影響計分或歷史比較 |
| `favicon.py` | 網站專案圖示：**新增／恢復專案時立刻抓**（`refresh_project_favicon_from_url`：先抓首頁 HTML 前 512KB 找 `<link rel=icon>`，整體上限 8 秒），掃描時再用爬到的首頁更新（`stage_favicon`，每 7 天最多一次）；沒宣告就 `/favicon.ico`。每一跳轉址都過 `assert_public_http_url`、圖示上限 200KB、逾時 5 秒、帶 `ARGUS_SCANNER_USER_AGENT`（Wikipedia 等會拒絕沒有 UA 的請求）；任何 `image/*`（含 gov.tw 的 `image/x-png`）交給 Pillow 縮成 64px PNG、SVG 限 20KB；存成 `SiteProject.favicon`（data URL），失敗保留舊圖示。舊專案補抓：`manage.py refresh_project_favicons`（`--all`／`--dry-run`） | 修改 `ScanJob.status`、讓掃描因圖示失敗 |
| `aeo/` | AEO 問答檢測（內容擷取、出題、找答案與判定、標記一致性、整站評估；見下「AEO 問答檢測」） | 修改 `ScanJob.status`、發出任何網路請求（只分析爬蟲已抓到的頁面） |
| `nuclei_scanner.py` | Nuclei binary 封裝；模板治理（固定 KEV 模板集、只掃網站根網址、模板集指紋，見下「Nuclei 模板治理」）、JSONL 解析、Finding mapping | 在 passive 或未授權模式執行 |
| `katana_scanner.py` | Katana 全站 JS/端點探索封裝；時間、大小、同主機與 RPS 預算 | 在單頁、passive 或未授權模式執行 |
| `domain_verification.py` | 網域所有權驗證引擎：Google Search Console 擁有者驗證（主要）、token 產生、網域正規化、DNS TXT／meta tag／HTML 檔三種備用驗證、`run_verification()` 更新 `VerifiedDomain`、`sync_search_console_ownership()` 連接 Search Console 時自動驗證 | 修改 `ScanJob.status`、繞過 `assert_public_http_url` SSRF 檢查 |
| `security/` | 深度主動式資安檢查（SSL/TLS、Cookie、CORS、CSP 品質、敏感檔外洩探測、硬編碼秘鑰偵測、OWASP 對映、Kali 工具）| 修改 ScanJob.status、呼叫 billing |

### 掃描範圍與工具矩陣

產品範圍只有兩種：前端以 `max_pages=1` 表示**單頁**，其餘合法值表示**全網站**。`passive/active` 是探測授權層級，不是第三種掃描範圍。所有工具閘門集中由 `scan_plan.py` 決定：| 範圍與授權 | Nuclei | Katana | 敏感路徑探測 | Agent（資安） | Agent（UX） | Kali |
|---|---:|---:|---:|---:|---:|---:|
| 單頁 + passive | 否 | 否 | 否 | 否 | 否 | 否 |
| 全網站 + passive | 否 | 否 | 否 | 否 | 勾 UX 才跑 | 否 |
| 單頁 + active 且已授權 | 網站根網址（KEV 模板） | 否 | 否 | 否 | 否 | 可執行既有同源候選驗證 |
| 全網站 + active 且已授權 | 網站根網址（KEV 模板） | 是 | 是 | 是（另受總開關控制） | 勾 UX 才跑 | 可執行既有同源候選驗證 |

Katana 與 Nuclei 並行時必須共享 `ARGUS_ACTIVE_MAX_RPS`；若總預算只有 1 RPS，必須改為依序執行。單頁不得用 Katana、敏感路徑字典或 Agent 擴張成全站掃描。

### Nuclei 模板治理（2026-10-08，roadmap §6 第 1 項）

- **模板版本鎖在 image**：Dockerfile `NUCLEI_TEMPLATES_VERSION`（目前 v10.4.9）下載到 `/opt/nuclei-templates`（`ARGUS_NUCLEI_TEMPLATES_DIR`），以 sha256 鎖定的 `templates-checksum.txt` 逐一驗證模板內容，並寫 `.argus-templates-version`；任何一步失敗 build 就失敗。原本 `nuclei -update-templates || true` 每次 build 模板不同，下載失敗也照樣 build 成功。升級模板要同時改兩個 ARG 並重新量 KEV 模板集的請求量。
- **固定模板集 `TEMPLATE_POLICY`**：`-tags kev`（CISA 已知被利用漏洞）、`-severity critical,high,medium`、排除 dos／fuzz 等標籤、只用 http。實測（v10.4.9，對單一網址）：原本 deep 模式全部模板 6680 個、9535 個請求，在 1–2 RPS 下要 80 分鐘，正式環境 300 秒逾時後回傳 0 項卻記為完成；KEV 511 個模板、628 個請求。Nuclei 標籤是單數（`cve`、`misconfig`、`exposure`、`default-login`），原本快速模式寫成 `cves`／`misconfigurations` 只選到 3 個模板（該模式已移除）。高噪音模板加進 `EXCLUDED_TEMPLATE_IDS` 並寫原因。
- **只掃網站根網址**（`_root_url`）：模板多半檢查網站層級路徑，每頁重掃只是把同樣的探測乘以頁數；單頁與全網站相同。
- **模板集紀錄**：每次執行用 `nuclei -tl` 列出實際選到的模板，記錄引擎版本、模板版本、模板數與指紋（模板路徑＋內容雜湊的 sha256），存在 `warning_summary.nuclei` 並寫進掃描 log；同一指紋才代表同一組檢查。
- **結果狀態**：逾時（`ARGUS_NUCLEI_TIMEOUT`，預設 660 秒——全網站時 Nuclei 與 Katana 分預算只有 1 RPS）保留逾時前已輸出的結果（`process_runner` 逾時時把已輸出的 stdout 放進 `TimeoutExpired.output`），覆蓋紀錄 `partial`；沒有 binary、模板目錄缺失、選不到模板或異常結束拋 `NucleiUnavailable`，覆蓋紀錄 `failed`（原因是固定代碼）。WAF 之後 0 項發現的說明只在 Nuclei 完整跑完時才加。
- 呼叫 `nuclei -tl`／`-version` 一律帶 `-no-stdin`／`-duc` 與 `stdin=DEVNULL`：沒有時 nuclei 會等 stdin 的目標清單或檢查更新，在 worker 裡卡到逾時。
- Agent 的 `run_nuclei` 工具用同一個模板目錄（`-t ARGUS_NUCLEI_TEMPLATES_DIR`），tags 由 agent 指定。

**Agent 有兩種角色，閘門分離**（都受 `ARGUS_AGENT_ENABLED` 總開關控制）：

- **資安（deep_mode）**＝`run_agent`：只有「全網站 ＋ active 且已授權」才開，執行主動滲透（recon→orchestrator→specialist）。
- **UX（擬真使用者體驗測試）**＝`run_agent_ux`：`scope == "site"` 且 `effective_categories` 含 `ux` 就開，**不需要主動授權**（passive 全網站勾 UX 也跑）。單頁不跑（無流程可走）。
- `tasks.py` 只要 `run_agent or run_agent_ux` 任一成立即呼叫 `run_agent_for_scan`；是否允許 agent 送出表單由 `may_submit_forms` 決定＝`run_agent`（deep_mode）**或**掃描目標 hostname 已通過 `user_owns_domain`。未驗證網域的 passive UX 測試 `may_submit_forms=False`：runner 隱藏 `send_message` 工具、prompt 明示只填欄位不送出，避免在他人網站留下測試資料。

### 掃描維度選擇（ScanJob.categories，2026-09-26）

使用者逐項勾選掃描維度（`ALL_CATEGORIES`＝seo/aeo/geo/ux/security，至少一項、預設全選），**費用＝頁數 × 勾選維度數 × `ARGUS_COIN_PER_CATEGORY`**（預設 2，五維全選＝每頁 10 coin 與舊定價等價）：

- 事實來源：`models.ALL_CATEGORIES`；`ScanJob.effective_categories` 過濾未知值、空集合退回全開（migration 0017 讓既有資料列預設五維全選，行為不變）
- 閘門：serializer（`categories` ListField 至少一項）與 `ScanJob.clean()`（**主動模式必須勾資安**）雙層檢查；`rerun_scan` replay 沿用 `effective_categories`
- 派工：`analyze_page(page_input, categories=...)` 過濾頁面級子分析（管理頁/二進位資源的 security 檢查也受資安維度控制）；tasks.py 對「秘鑰偵測、站台層級資安、站台訊號 GEO」按維度跳過
- 計分最後防線：`tested_categories &= scan_job.effective_categories`——沒勾的維度即使有量測（UX layout_metrics 在爬蟲一律收集）也不得進 `category_scores`，報告顯示「未評估」

### 網域所有權驗證閘門（VerifiedDomain，2026-09）

主動測試（`scan_mode=active`）除了宣告式勾選 `active_testing_authorized`，還必須通過**技術性**網域所有權驗證——兩道閘門並存，缺一不可：

- 閘門位置：`ScanJobCreateSerializer.validate`（API 層）與 `ScanJob.clean()`（model 層）都檢查；判定函式為 `services.user_owns_domain(user, hostname)`
- 有效判定：`VerifiedDomain.is_effectively_verified`＝`admin_override=True`（管理員人工核准）**或**（`status=verified` 且 `expires_at > now`，TTL 預設 90 天，`ARGUS_DOMAIN_VERIFICATION_TTL_DAYS`）
- 子網域涵蓋：對 `example.com` 驗證通過，`www.example.com` 等子網域也可主動掃描；不做 eTLD+1 萃取，以完整 hostname／父網域比對
- **Google Search Console（2026-10-04 起主要方法，`method=search_console`）**：讀使用者所有 `SearchConsoleConnection` 的 `sites.list`，涵蓋該網域的資源 `permissionLevel` 必須是 `siteOwner`（`siteFullUser`／受限使用者不算）。涵蓋規則 `gsc.property_covers_domain`：`sc-domain:X` 涵蓋 X 與其子網域；網址前置字元資源只證明那一個主機（不能拿 `https://www.example.com/` 驗證 `example.com`）。OAuth callback 成功後呼叫 `sync_search_console_ownership(connection, project)`：涵蓋該專案網站且是擁有者的資源，自動建立／更新 VerifiedDomain（`sc-domain` 記網域、前置字元記主機；管理員否決的不動；失敗只 log、不影響連接），導回 `?gsc=connected&verified=<網域>`。TTL 與其他方法相同（90 天），到期後在 `/domains` 按驗證即可重新以 Search Console 確認。
- **帳號層級 Search Console 連線（2026-10-04）**：`SearchConsoleConnection.project` 可為空＝帳號層級（每人最多一筆，`uniq_account_level_search_console`；migration 0024），只用來驗證網域。端點（`seo_views.py`，在 `scans/urls.py` 排在 router 前面，否則 `domains/gsc/` 會被當成 `domains/<pk>/`）：`GET/DELETE /api/domains/gsc/`（狀態／中斷並撤銷帳號層級連線，專案連線不動）、`POST /api/domains/gsc/connect/`（OAuth state 的 `p` 為 null）、`POST /api/domains/gsc/sync/`。OAuth callback 遇到 `p is None` 走 `_account_callback`，導回 `/domains?gsc=…`。`sync_owned_domains(connection)`：Search Console 裡 `siteOwner` 的資源全部匯入為已驗證網域，並驗證清單中被涵蓋、尚未生效的網域（否決的不動）。`GET /api/domains/<id>/` 另附自己的 token 與三種備用方法說明。刪除帳號會撤銷並刪除使用者全部 Search Console 連線（含帳號層級）。
- 備用的三種驗證方法共用一支 token（`argus-site-verification=<token>`）：DNS TXT（`_argus-verification.<domain>`，重試 3 次×timeout 5 秒）／首頁 meta 標籤（HTML 前 64KB 需同時出現標籤名與 token）／驗證檔（`/.well-known/argus-verification.txt` 內容等於 token）
- HTTP 驗證抓取先過 `assert_public_http_url` SSRF 檢查、串流讀取上限 5MB；DNS 查詢走 dnspython
- 使用者 API：`/api/scans/domains/`（list／create＋instructions／`<id>/verify/`／delete；重複建立回 409 帶現況）
- 管理端人工審核：`/api/admin/domains/` 與 `/api/admin/domains/<id>/override/`（approve=人工核准、reject=rejected；寫 `AdminAuditLog` action=`domain_override`）
- **管理員測試旁路（2026-09-26）**：`user_owns_domain` 對 `is_staff`／`is_superuser` 一律放行——能力等同 admin_override 人工核准，省去「先建網域紀錄、再到後台核准」兩步，供管理員直接對受控測試目標（Juice Shop 等）主動掃描；不建立任何 VerifiedDomain 紀錄，掃描與授權紀錄仍歸屬管理員帳號，宣告式授權勾選（`active_testing_authorized`）與其他 SSRF／範圍閘門不受影響；前端對 staff 以「管理員測試模式」徽章取代未驗證警告
- passive 掃描不受此閘門限制

### 資安邊界（重要）

`scanners.py` 的 `analyze_security()` 與 `security/` sub-package 的分工：

- **`scanners.py` 留著**：被動讀取已有 response headers/HTML，不需要額外連線（HTTPS 判斷、header 存在性、CSRF token、PII 偵測）
- **`security/` 新增**：需要額外連線或工具呼叫的深度分析（SSL 憑證讀取、Cookie API、OPTIONS 探測、敏感檔主動探測 content discovery、docker exec kali）
- **例外（被動但放 security/）**：硬編碼秘鑰偵測 `secret_scanner.detect_secrets_in_text` 是純解析，但因屬「深度解析」歸 security/；由 tasks.py 對已抓 HTML 被動呼叫（零額外請求）
- **新的資安功能一律寫進 `security/`**，不要再擴充 `scanners.py` 的資安部分

詳細規則見 [`security/CLAUDE.md`](security/CLAUDE.md)。

---

## 分數計算契約（`scanners.py::calculate_scores`）

2026-08-30 依 [`docs/scan-report-quality-audit-2026-08-30.md`](../../../docs/scan-report-quality-audit-2026-08-30.md) 修正，四條規則都有測試鎖定（`tests_scoring_and_report_grouping.py`）：

1. **同一分類內同一 `rule_id` 只扣一次分**。一個問題出現在幾頁是「廣度」不是「嚴重度」；報告本來就把它們合併成一筆顯示，計分不跟著去重會讓使用者看到一項卻被扣了 N 次。
2. **`info` 不扣分**。info 多半是純資訊或提醒（例如「主動弱點掃描 0 項發現，但目標位於 WAF／CDN 之後」——0 項發現不能當成防護有效的證據，2026-10-06 起措辭改為「結果可能不完整」）。**同理 `info` 不進 `top_actions`**——它對應的建議修補是「無需修復」，列進「優先改善建議」會被當成待辦。
3. **指數衰減 `100 * exp(-penalty / SCORE_DECAY_CONSTANT)`**，不是 `max(0, 100 - penalty)`。舊公式累積 100 分懲罰後永遠是 0，無法分辨「4 個高風險」與「40 個高風險」。`SCORE_DECAY_CONSTANT` 是可調的產品參數，不是演算法細節。
4. **未評估的分類不寫進 `category_scores`，缺鍵即代表未評估**。`category_scores` **不保證含全部 5 個分類，取值一律用 `.get()`**。這同時保證「報告列出的分數」與「`overall_score` 平均的分母」是同一組，使用者算得出總分。
5. **有基準分的分類（`base_scores`，目前只有 AEO）**：`calculate_scores(findings, tested, base_scores={"aeo": N})` 以 N 取代 100 當起點，`BASE_SCORED_RULE_PREFIXES`（`aeo-answer-`）的逐題 finding 不再扣分（已反映在基準分裡），其餘 AEO finding（noindex、標記不一致…）照常衰減扣分。`rerun_scan` 與 `finding_normalization._rescore` 都從 `aeo_report["score"]` 取回基準分（第 5 條由 `tests_aeo_answerability.py` 鎖定）。
6. **分類分數由 `score_breakdown()` 算出**（2026-10-07）：`calculate_scores` 只取它的 `score`，「分數說明」分頁與計分永遠同一套公式；扣分權重在 `SEVERITY_PENALTY`。改公式時兩者一起變，不要在別處另算（`tests_score_explain.py` 鎖定兩者一致）。

`Finding.Meta.ordering` 一併鎖定兩件事：`priority_score` 必須明確 `nulls_last=True`（PostgreSQL 的 `DESC` 預設 NULLS FIRST、SQLite 是 NULLS LAST，不指定的話同一份報告在本機與正式站排序相反），`severity` 必須用 `Case/When` 的風險序（CharField 直接排是字母序 `critical < high < info < low < medium`，info 會插到 low 與 medium 前面）。

`make_finding()` 在呼叫端沒傳 `priority_score` 時，依 severity 給預設值——`security/` 子套件的 scanner 全都不傳，留 `None` 會被 PostgreSQL 頂到報告最前面。

---

## AEO 問答檢測（`aeo/`，2026-09-28 重做）

AEO 不再數 FAQPage／HowTo 標記，改成檢測「問題能否從網站內容中被找到、回答並追溯證據」。四層各一個模組：

| 模組 | 職責 |
|---|---|
| `aeo/content.py` | 第 1 層：主要文字擷取（排除 nav／header／aside／表單／隱藏元素；footer 另標 region）、段落與所屬標題、`robots_directives`（meta robots／googlebot＋`X-Robots-Tag`）、`data-nosnippet` |
| `aeo/questions.py` | 依網站內容出題：固定意圖（電話、Email、地址、營業時間、費用、報名方式／截止、資格、退款、運送、付款方式、預約…，需在正文命中觸發詞才出題）＋網站自己寫的問句標題。付款方式（`PAYMENT`：答案要有付款方式名稱，含英文 credit card 等，可信度「確認」）與預約（`BOOKING`：答案要有預約管道——線上系統、表單、LINE、電話號碼或點選／填寫；可信度「可能」）2026-10-08 加入（roadmap §2 第 5 項）：觸發詞只算小標題與 ≥15 字的段落、判定也只看 ≥15 字的段落（`answers._PROSE_ONLY`），選單連結文字（ntub.edu.tw 的「出納付款查詢」「心理諮商線上預約」）不算；平台名稱（EZTABLE）與英文單字 inline 不算預約管道。不從一般小標題自動造題（該段本身就是答案，只會灌高分數） |
| `aeo/answers.py` | 第 2、3 層：逐題找候選段落並判定 `answered`／`insufficient`（空泛、日期無年度）／`conflict`（不同頁截止日期矛盾；2026-10-08 起另有 `_value_conflict`：同一個標籤（值前面同一句的文字）在兩個以上頁面寫了不同的價格、營業時間或客服專線。價格標籤要含項目名稱、標籤或小標題帶原價／優惠／早鳥／平日／假日／連假等字的不比、網站有多個據點時不比營業時間與電話、電話只比客服／訂購／預約專線與總機）／`missing`，附原文與位置。`evaluate.reconcile_contact` 不覆寫 conflict |
| `aeo/markup.py`、`aeo/page_checks.py` | 第 4 層與逐頁規則：結構化資料語法、標記與可見文字一致性、noindex／nosnippet（`scanners.analyze_aeo` 只委派到這裡） |
| `aeo/evaluate.py` | 整站評估 `evaluate_site(pages)`：正文 < `MIN_MAIN_TEXT_CHARS` 或題目 < `MIN_QUESTIONS` → `status=insufficient`、**不給分**（`tested_categories_for` 移除 aeo，報告顯示「未評估」）；否則依逐題判定加權算分，產生 `aeo-answer-*` finding 與 `aeo-render-dependent`（主要文字需執行 JS 才出現） |

- 結果存在 `ScanJob.aeo_report`（migration 0018）：`status`、`reason`、`questions_total`、`counts`、`answered_ratio`（有答案的問題比例）、`evidence_ratio`（答案附有原文的比例）、`score`、`questions[]`（逐題判定、理由、證據；2026-10-08 起可回答與內容衝突另有 `confidence`／`confidence_label`／`limitation`：確認＝號碼、金額、時間、日期等格式化答案值逐字出現在原文，可能＝步驟／條件規則或網站自己的問題，推測＝只確認段落有具體敘述（介紹類）；`aeo_benchmark` 另輸出各等級的 precision，`tests_aeo_confidence.py` 鎖定確認等級 ≥ 0.95），`method` 目前是 `rules-v1`。可信度只是說明，不影響計分。**引用可得性（2026-10-08，roadmap §2 第 6 項）**：可回答的題目另有 `citation`（`status` citable／limited／not_citable、`label`、`reasons`），看判定依據的第一筆證據：頁面 noindex、禁止摘要（nosnippet、max-snippet:0，meta robots 或 `X-Robots-Tag`——`SitePage.headers` 由 `tasks._aeo_site_pages`／`rerun_scan` 帶入）或段落在 data-nosnippet 區塊內（`Passage.nosnippet`／`Evidence.nosnippet`，`content._MainTextParser` 追蹤 data-nosnippet 深度，行內元素也算）＝無法被引用；答案值（沒有值時用引文前 20 字）不在原始 HTML 的正文裡＝引用受限（多數 AI 爬蟲不執行 JavaScript）。`aeo_report.citation`＝`counts`＋`citable_ratio`。**不改分數、不另產生 Finding**：noindex／nosnippet／data-nosnippet 已由 `page_checks.py` 逐頁列出並扣分，再列會重複扣分。測試 `tests_aeo_citation.py`。
- 呈現：網站專案的「AEO 問答」分頁（`/projects/:id/aeo`，`AeoAnswerPanel`；2026-10-02 前在掃描詳情最下方）、PDF 報告範圍表「AEO 問答檢測」列與附錄 6.6 逐題表（`appendix.aeo_items`，`RENDERER_VERSION` 3）、MCP `get_scan` 的 `aeo` 欄位（證據遮罩）、`ScanJobSerializer.aeo_report`。
- **答案蘊含（2026-10-06，ntubimdbirc.tw 第二輪審查）**：
  - 題庫意圖可設 `anchors`（主題詞）。段落或其小標題沒有主題詞時，答案值不算數；沒有任何段落在談這個主題就判 `missing`，不再拿無關段落當「資訊不足」的證據。實例：學員心得裡的「必須」被當成申請資格。
  - 心得／見證段落（小標題含「見證、心得、評價…」，或第一人稱單數「我」出現兩次以上）不能回答題庫問題（`answers.is_testimonial`）。
  - 超過 `MAX_HEADING_CHARS`（80）或含句中句號的 h1–h6 視為內文段落（`content._is_body_text`）。實例：隱私權政策整段寫在 h3 裡，裡面的 Email 被當成標題略過，造成資安判「公開 Email」、AEO 卻判「找不到 Email」的矛盾。
- **共用聯絡資訊證據（2026-10-07，P0-B）**：`evaluate_site` 以 `evidence.contacts.collect_contacts` 擷取同一份 Email／電話，`reconcile_contact` 核對聯絡題：共用證據的值出現在任何可讀段落（含被當成標題的短段落）就判可回答；只在導覽列、頁首、隱藏區塊或 HTML 註解時判定不變，但理由寫明位置與「與資安檢查情境不同、並不矛盾」。`aeo_report.shared_contacts` 只記筆數不存值。地址（2026-10-08）也走共用證據：`contacts.ADDRESS_PATTERN`（AEO 答案格式同一份）＋JSON-LD `address`（位置 `structured_data`，PostalAddress 只取 streetAddress），頁面文字含該街道即判可回答；只在 JSON-LD 時判定不變、理由寫「搜尋引擎讀得到、訪客看不到」。日期不共用（AEO 與 GEO 的日期是不同的事）。測試 `tests_shared_evidence.py`。
- **回歸資料集與指標（2026-10-07，P0-C）**：`aeo/gold_dataset.py`（`GOLD_CASES` 調整用＋`HOLDOUT_CASES` 保留集，每題人工標註；tag 分 answerable／insufficient／conflict／missing／near_miss／holdout）、`aeo/benchmark.py`（以「可回答」為正類算 precision、recall、false positive rate、accuracy、每站耗時、混淆矩陣）、`manage.py aeo_benchmark [--holdout] [--json]`（低於門檻非零結束）。門檻 `benchmark.THRESHOLDS`（accuracy／precision／recall ≥ 0.95、FPR ≤ 0.05）由 `tests_aeo_benchmark.py` 鎖定，只能往上調；**不可為了讓規則通過而改標註**，保留集不要拿來調規則。同次依資料集修正的規則：小標題就是主題時段落算候選（`_passage_score` 標題命中權重 1）、「如需／若需」不算條件（`_CONDITIONAL`）、感謝詞算空泛（`_VAGUE`）、營業時間關鍵詞加「無休／全天」。
- 人工校驗題集在 `tests_aeo_answerability.py` 的 `GOLD_SITES`：改動規則後判定正確率必須維持 100%。**第一版只做可重現的規則判定**；受控 AI 評估與外部平台觀察尚未實作，報告不得宣稱有。
- 新增意圖或判定規則：先在 `GOLD_SITES`（或 `gold_dataset.GOLD_CASES`）加一個會踩到的案例，再改規則，最後跑 `manage.py aeo_benchmark` 確認門檻。

## 網站專案（`SiteProject`，2026-10-02）

會員區以網站專案為單位（[`docs/adr/0003-site-project-workspace.md`](../../../docs/adr/0003-site-project-workspace.md)）：

- **每筆掃描都要有專案**：`ScanJob.save()` 新建時沒指定就依 `(user, origin)` 歸入（`SiteProject.objects.ensure_for`），所以 MCP、後台重排、`rerun_scan` 與測試不用改。指定了已封存的專案會恢復它。
- **建立掃描可帶 `project`**：`ScanJobCreateSerializer` 檢查專案屬於本人，且網址的 origin 與專案相同（換網站＝換專案，回 400 `url`）。
- **`/api/scans/?project=<id>`** 回該專案全部掃描；沒帶時維持「每個 origin 只回最新一筆」。
- **問題只收本次有勾的維度**（`issue_groups` 以 `effective_categories` 過濾，總覽的 `top_actions` 同理）：部分站台層級檢查不論勾選都會寫 finding，問題分析必須與計分一致。
- **連續次數**：`issue_streaks` 往回數同專案連續幾次完成的掃描都出現該問題（最多 `STREAK_LOOKBACK` 次，遇到沒出現或那次沒勾該維度就停），回傳 `streak`／`since`。
- **`domain_verified`**：`SiteProjectSerializer` 的唯讀欄位，等於 `user_owns_domain(user, hostname)`，前端頁首顯示已驗證勾勾；權限判斷仍以 view 內的檢查為準。
- **預設掃描設定**：`SiteProject.default_scope`／`default_categories`／`default_scan_mode`（passive/active，2026-10-03）只是前端表單初始值，建立掃描時仍以實際送出的參數為準；新增專案時可一併設定（`SiteProjectCreateSerializer`），預設主動測試時預設維度必須含資安（`_check_active_needs_security`）。`description`（選填 300 字）在網站沒有 meta description 時顯示在總覽頁首。
- **示範專案（`is_demo`，2026-10-03，`demo/`）**：Email 註冊與第一次 Google 登入時由 `demo.seed.create_demo_project_safely` 建立（`ARGUS_DEMO_PROJECT_ENABLED`，預設開；失敗只記 log、不影響註冊）。資料是虛構網站 `scripts/demo_site/server.py` 三個版本的**真實掃描**匯出（`manage.py export_demo_dataset`），截圖放在 `demo/screenshots/`、所有示範專案共用；重產步驟見 `demo/README.md`。示範專案唯讀：建立掃描（`_resolve_project`）、PATCH（`SiteProjectUpdateSerializer.validate`）、修正產出觸發、網頁複刻（`apps/rebuild`）都回 400，可以封存。後台統計與清單（`admin_api.views.real_scans()`）與評論資格（`reviews._latest_completed_experience`）都排除示範掃描。`ScanJobSerializer.is_demo` 給前端隱藏複刻。既有帳號補建：`manage.py seed_demo_project --without-projects`（封存過的不補）。測試：`tests_demo_project.py`。
- **問題的追蹤單位**＝一次掃描中同一條 `rule_id`（沒有就「分類:標題」），與報告合併規則一致；比較對象是同專案前一次「完成」的掃描。「本次未出現」只列本次仍有勾的維度，每項附覆蓋契約判定的狀態（見「掃描覆蓋契約」），只有 `resolved` 能稱為已修好。
- **migration 0019 會先清掉殘留**（`drop_orphaned_site_project_schema`）：0019 未套用時若資料庫已有 `scans_siteproject` 表或 `scans_scanjob.project_id` 欄位，只可能是同功能較早版本跑過後被回退（程式與 migration 紀錄退回但表沒刪），會先移除再建立並回填。2026-10-02 Docker migrate 因此報 `relation "scans_siteproject" already exists`；由 `SiteProjectMigrationRecoveryTests` 鎖定（SQLite／PostgreSQL 皆驗證）。**回退含 migration 的功能時要用 `migrate <app> <前一版>` 反向套用，不要只退程式碼或刪 `django_migrations` 紀錄。**
- **不提供硬刪除**：DELETE＝封存（`archived_at`），單筆讀取仍可讀封存專案（舊掃描詳情要顯示所屬專案），清單只列未封存。
- **頁面分頁**：`/api/projects/<id>/pages/?scan=` 回一次掃描的每一頁與其問題數（只算有勾的維度），沒有對應頁面的站台層級發現另計 `site_level_findings`。
- 測試：`tests_site_projects.py`（儀表板資料、頁面清單、歸入、回填、API、跨使用者 404、總覽與比較、預設掃描設定、已封存清單、連續次數、維度過濾）。

## SEO 分析與 Search Console（2026-10-03，`seo/`）

會員區「SEO 分析」分頁（`/projects/:id/seo`）的資料層，是給網站主逐頁查證與修正的工作清單。**例外（2026-10-06）**：`seo/site_findings.py` 把站台層級的結論轉成 Finding（計入 SEO 分數、出現在問題清單與報告）——站內失效連結 `seo-broken-internal-links`（中）、主網址設定不一致 `seo-primary-url-inconsistent`（低；同一個根本原因的症狀合併成一項：www／非 www 都直接回應、og:url／canonical／robots Sitemap 指向另一個主機、沒有 canonical 的頁數，列在 `evidence_json.symptoms`；2026-10-06 前拆成 `seo-www-duplicate`／`seo-declared-host-mismatch` 兩項）、多頁同一個 title `seo-duplicate-titles`（中，≥3 頁且過半）、索引指示互相矛盾 `seo-index-signals-conflict`（低，2026-10-07：sitemap 列出 noindex／canonical 指他頁／錯誤／轉址／robots.txt 禁止 Googlebot 的網址，noindex 頁被 robots.txt 擋住；資料來自 crawler 的 `site_signals.sitemap_urls`／`robots_text`，robots 判斷用 `ai_bots.robots_allows`）；ntubimdbirc.tw 實測這些只出現在 SEO 頁明細、報告完全沒有。其餘逐頁明細仍不產生 Finding。

| 模組 | 職責 |
|---|---|
| `seo/page_audit.py` | 逐頁解析已保存的 HTML（`rendered_dom` 優先）：Title、Description、H1–H6 清單與跳號、正文（沿用 `aeo/content.extract_page_content`）、canonical、robots meta＋`X-Robots-Tag`、圖片 alt、連結（錨文字含圖片 alt）、OG、hreflang、載入時間。**只讀 DB，不連線** |
| `seo/structured_data.py` | Google 複合式搜尋結果必填欄位（依 Search Central 2026-09 版；`scanners._seo_structured_data` 逐頁呼叫，Finding `seo-structured-data-required`（低）與自評星等 `seo-structured-data-self-serving-reviews`（資訊））：只套頂層節點（區塊根、陣列、`@graph`、`mainEntity`）的類型規則，Review／AggregateRating 任何層都檢查，Offer／活動地點只在 Product／Event 底下檢查；`@type` 接受 schema.org 網址形式；純 `@id` 參照不檢查；語法錯誤略過（由 AEO 回報）。**不檢查** FAQPage／HowTo（Google 已不支援）、建議欄位、值是否正確 |
| `seo/link_check.py` | 連結狀態：每一跳都過 `assert_public_http_url`、手動跟隨轉址最多 5 跳並記錄跳轉鏈；HEAD 回 4xx／5xx 或連線層錯誤（`RemoteProtocolError` 等，2026-10-06 domjudge 子網域實測）時改 GET（不讀內容）。站台檢查：robots.txt（`User-agent: *` 的 Disallow）、sitemap、HTTP→HTTPS、www／非 www、隨機路徑 404、`/index.html`、結尾斜線。逾時是獨立判定 `timeout`（2026-10-08 前併在 `error`）；`check_links` 的未檢查數分成 `over_limit`（超過數量上限）與 `budget_exhausted`（時間用完），存 `seo_report.unchecked_reasons` |
| `seo/link_trend.py` | 連結覆蓋與趨勢（2026-10-08，roadmap §11 第 2、3 項）：`link_coverage` 把每個連結歸到已確認／對方限制／逾時／無法連線／非公開位址／超過數量上限／時間用完，存 `seo_report.coverage`，`seo_links` 覆蓋紀錄的說明列出沒有明確結果的狀態；`link_trend` 和同專案上一次有 `seo_report` 的完成掃描比較，失效連結標 `new`／`persisting`／`recovered`／`unconfirmed`，存 `seo_report.trend`（`items` 逐網址、`counts`、`previous_scan_id`）。只有這次真的檢查過且正常（含轉址後正常）才算恢復；沒檢查、逾時、被拒或頁面上找不到都是無法確認。爬蟲已造訪的頁面不做連結檢查，兩次都用 `crawled_verdicts` 併入爬蟲 HTTP 狀態（上一次由 `Page` 表取）。`seo/report.py` 的連結列帶 `trend`、links 區塊帶 `coverage`／`trend`（不含 items；`CACHE_VERSION` 2），`seo-broken-internal-links` 的描述與證據註明新壞掉／持續失效 |
| `seo/collect.py` | `stage_seo_links` 主體：收集所有頁面的不重複連結（爬蟲已直接造訪且沒轉址的頁面不重查；爬蟲已取得的 robots.txt／llms.txt／sitemap（`site_signals.fetched`，不跟隨轉址的狀態）也不重查，robots.txt 以爬蟲原文解析，站台檢查先沿用已有結果；轉址的照常檢查；沿用數在 `seo_report.reused`，2026-10-08 roadmap §11 第 1 項，測試 `tests_seo_reuse.py`），依站內→子網域→站外排序，前 `ARGUS_SEO_LINK_CHECK_LIMIT`（150）個、總時間 `ARGUS_SEO_LINK_CHECK_SECONDS`（120） |
| `seo/report.py` | API 資料：概覽（掃描頁數、受影響頁數、重大／警告／提示、可索引頁數、失效連結、優先修復事項）、頁面、問題（每處附網址、檢測時間、證據）、連結（依目標合併、來源頁與錨文字）、站台檢查、關鍵字報告；以「掃描 id＋連結檢查時間」快取 1 小時 |
| `seo/keywords.py` | 目標關鍵字（`SiteProject.target_keywords`，最多 20 個、每個 60 字）字面比對 Title／H1／Description／H2–H6／網址／正文 |
| `seo/gsc.py`、`seo_views.py` | Google Search Console（下表） |

**判定原則（使用者需求，測試鎖定在 `tests_seo_analysis.py`）**：
- H1 不必與 Title 相同，不做相同／不同的判定。
- 302 → 200（轉址後正常）不算失效連結；401／403／429／999 是「對方限制檢查、無法確認」，不是失效；只有站內轉址列為提示。
- 中文不套用英文字符門檻：Title／Description 以顯示寬度計算（全形字＝2，Title 20–60、Description 70–160），正文以「英文詞＋中文字÷1.5」換算（< 150 為正文偏少，只是提示）。
- 每項結論附受影響網址、檢測時間（頁面類＝`Page.created_at`，連結與站台類＝`seo_report.checked_at`）與證據（原始值或跳轉鏈）。
- 「可索引」（HTTP 200、無 noindex、canonical 指向自己、robots.txt 未擋）是 Argus 的判斷；「Google 已收錄」只由 Search Console 回答（期間內有曝光，或網址檢查 API），兩者分開顯示。GSC 平均排名一律標示為期間統計值。

**API**（`SiteProjectViewSet` 繼承 `seo_views.ProjectSeoActions`）：`GET /api/projects/<id>/seo/?scan=`、`GET seo/pages/<頁面 id>/`（單頁證據）、`POST seo/keywords/`（示範專案也可設定）、`GET|PATCH|DELETE gsc/`、`POST gsc/connect/`、`GET gsc/properties/`、`GET gsc/performance/?days=7|28|90`、`POST gsc/inspect/`（只接受本專案網站的網址）；callback 是 `GET /api/gsc/callback/`（`AllowAny`）。GSC 相關端點有 `gsc` throttle（`THROTTLE_GSC`，預設 120/hour）。

**Search Console 串接**：
| 規則 | 為什麼 |
|---|---|
| scope 只有 `webmasters.readonly`，`access_type=offline`＋`prompt=consent` 取得 refresh token；callback 確認 Google 回傳的 scope 確實含 Search Console | 使用者在同意畫面可以取消勾選 |
| state 以 `signing.dumps`（salt `argus-gsc-oauth`，10 分鐘）簽章並含 nonce，nonce 另寫進只在 `/api/gsc/callback/` 送出的 HttpOnly cookie，兩者必須相符 | callback 時瀏覽器沒有記憶體中的 JWT；只靠 state 會讓攻擊者把受害者的 Google 帳號接到攻擊者的專案（OAuth CSRF） |
| refresh token 以 Fernet 加密存 `SearchConsoleConnection.refresh_token_encrypted`（金鑰 `ARGUS_GSC_TOKEN_KEY`，空值由 `SECRET_KEY` 推導）；不保存 access token、不回傳、不寫 log | 機密外洩面最小化；輪替 `SECRET_KEY` 的代價是使用者要重新連接 |
| 選擇資源時以 Google 回傳的清單驗證；`property_matches` 只用來提示，不擋 | 使用者可能用網域資源涵蓋多個子網域 |
| 授權失效（`invalid_grant`／401）寫 `last_error`，前端顯示重新連接 | 使用者可能在 Google 帳號頁撤銷授權 |
| 中斷連線時呼叫 Google revoke，失敗不影響本地刪除；**同一個授權還被其他連線共用時只刪本地**（`seo_views._disconnect`） | 專案沿用帳號層級授權後兩筆連線是同一個 refresh token，撤銷會讓另一邊一起失效 |
| **只連一次、不必選資源**（`seo_views._ensure_project_connection`，2026-10-06）：網域驗證頁連接 Google 後，callback 立刻讓使用者所有網站專案沿用同一個授權（`link_user_projects`），重新授權也會修復授權已失效的專案連線；SEO 分析頁（`GET seo/` 與 `GET gsc/`）若專案仍沒有連線或沒選資源，當場沿用並自動選資源（`pick_property`：網域資源 `sc-domain:` 優先、多個取最具體，否則用協定＋主機相同的網址前置字元資源）。選不到時 10 分鐘內不重試；使用者按「更換資源」後 24 小時內不自動選回 | 使用者回報同一個 Google 帳號要連兩次、連好後還要在清單裡再按「選擇」；**SEO 頁讀的是 `GET seo/` 的 `gsc` 狀態**，只掛在 `GET gsc/` 不會生效 |
| 示範專案不能連接 | 虛構網站 |

設定：`GOOGLE_OAUTH_CLIENT_ID`（與登入共用）＋`GOOGLE_OAUTH_CLIENT_SECRET` 都有值才啟用；`ARGUS_GSC_REDIRECT_URI` 選填（空值＝目前網域的 `/api/gsc/callback/`，`DEBUG=False` 時一律組成 `https://`——正式環境 cloudflared → Gateway 走 http，`X-Forwarded-Proto` 是 http，2026-10-04 曾因此 `redirect_uri_mismatch`；nonce cookie 綁網域，固定成別的網域會讓 callback 讀不到 cookie，多網域時保持空值）。Google Cloud 端：啟用 Search Console API、同意畫面加 scope、OAuth 用戶端登記每個對外網域的 callback。

## 報告內容契約（`reports.py`）

報告（PDF）會被下載、轉寄、存檔給第三方，內容邊界是硬規則：

| 必須有 | 為什麼 |
|---|---|
| 掃描範圍（範圍／模式／頁數上限／實際頁數／robots） | 收件者要能判斷涵蓋範圍，「沒發現問題」才有意義 |
| 掃描授權聲明（`AuthorizationConsent`） | Argus 是授權式掃描平台，報告沒有授權依據等於放棄核心合規主張；查無紀錄要明講，不能讓章節消失 |
| 掃描警示（`scan_effectiveness` / 略過與失敗頁數／部分掃描：`1 < max_pages < ARGUS_DEFAULT_MAX_PAGES`） | 爬 0 頁的掃描會產出看起來正常的報告，分數只反映站台層級檢查；部分掃描不能被當成整站結論 |

| 絕對不能寫進報告 | 為什麼 |
|---|---|
| `AuthorizationConsent.ip_address`、`user_agent`、授權帳號 | 個資與瀏覽器指紋，對收件者零價值只增加外洩面；稽核走 DB 與 `AdminAuditLog` |
| `warning_summary["settlement_error"]`、`agent` 的 token 用量 | 內部運維／計費資訊，不是客戶要看的東西 |
| 未實作功能的描述 | 附錄曾聲稱「交由 AI 進行自然語言解釋」，但 `ai_explanation` / `ai_remediation` 全 backend 只被寫入空字串——對外文件的不實陳述 |

## 報告的資料層與排版層分離（2026-09-01）

排版由 vendored 的 `report_render/` 負責（使用者提供的 module，原樣搬入 `backend/apps/scans/`）。`reports.py` 的職責變成**只產生 payload**：

```
reports.build_report_payload(scan_job) -> dict   # 資料層：去重、評分、比較、遮罩、per-rule 文案
report_render.generate_report(payload, path)     # 排版層：版面、配色、圖表、浮水印
```

| 規則 | 為什麼 |
|---|---|
| payload 必須通過 `report_render/schema.json` | 不符合時錯誤會在排版階段以難懂的 KeyError 爆出來。`tests_report_payload.py` 直接對 schema 驗證 |
| 嚴重度一律走 `_render_severity()` | `report_render` 會拿它查色塊與排序，**值不在 theme.SEVERITY 表裡就 KeyError、整份報告產不出來**。未知等級退回「資訊提示」 |
| finding 先依嚴重度排序才編號 | `report_render` 依嚴重度分組顯示，不先排好編號就不連續 |
| 未評估分類送 `null` 而非 `0` | 送 0 會被畫成一條紅色滿分條，把「沒測」說成「很糟」 |
| `report_render/` 由 Argus 自行維護（2026-10-06 依使用者要求重新設計版面） | 原本是 vendored module、已在 ruff `extend-exclude`；改版面時同步改 `schema.json`、`RENDERER_VERSION` 與版面測試 |

**字型是硬需求**：圖表由 matplotlib 繪製，缺 CJK 字型時 `theme.py` 直接 `RuntimeError`（刻意大聲失敗——退回預設字型的話中文會變成一整排 □，報告照樣寄給客戶）。Dockerfile 已裝 `fonts-noto-cjk`，另可用 `ARGUS_REPORT_FONT_REGULAR` / `_BOLD` 覆寫。

**報告用的圖檔放 `backend/apps/scans/report_assets/`**，不可放 `frontend/public/`——backend image 只有 `COPY backend ./backend`。

schema 沒有的東西（掃描頁面清單、已解決項目清單）不要硬塞：頁面清單已移除（與範本一致，掃描範圍表仍有頁數）；已解決數量收進 `summary.headline`。

---

### 報告版面（2026-10-06 重新設計）

| 規則 | 為什麼 |
|---|---|
| 字級層級固定在 `theme.TYPE`：章節 20、小節 13.5、問題名稱 12、內文 10.5、標籤 9、中繼資料與證據 8.5（pt） | 使用者回饋舊版標題、章節、問題名稱、說明字重太接近，讀不出層次 |
| **不用任何彩色左邊條**（卡片標題、怎麼修、檢測依據、嚴重度分組、h2 都拿掉）；層次靠字級、字重、留白與細底線 | 全站規則（frontend/CLAUDE.md），報告也一樣 |
| 中風險以上用完整卡片；低風險與資訊提示是精簡條目（標題＋一句問題＋一句建議，不列逐頁證據與追溯資訊） | 讀者注意力要放在該處理的項目；舊版 25 頁中低風險卡片佔一半 |
| 第一章摘要先列「建議先處理這 3 件事」（優先清單前三項）、「網站優勢」（每項附依據；由間接訊號推論的標「推論」，例如單次實驗室量測的載入時間）與「網站架構」（`payload.site_profile`：事實表＋CDN／反向代理提醒），之後才是分數圖 | 報告不能只有負面問題；網站在 Cloudflare 等邊緣之後時，必須提醒 Port／主機層級資訊反映的是邊緣節點 |
| 附錄「修補後如何驗證」只逐項列中風險以上，其餘一行帶過（payload 仍保留全部 `verify_items`） | 舊版這張表單獨佔 5 頁 |
| 第一章「建議先處理這 3 件事」之後是「改一處就能一起解決」（`summary.root_causes`，2026-10-08）：修法在同一處的問題列一行原因、項次與在哪裡修 | 讀者看到 5 個標頭問題容易以為要改 5 次 |
| 附錄「各分類扣分明細」（`appendix.score_items`，2026-10-08，`RENDERER_VERSION` 17）由 `reports._report_score_items` 取 `score_explain.score_explanation`，與網頁分數說明同一份；項次對應第 4 章卡片（以 `rule_id` 對）；`matches=false`（舊公式或事後重新判定）只放 `note` 不列表 | 分數要能被讀者自行核對；加不回保存分數的表比不列更讓人困惑 |

ntubimdbirc.tw（26 項）由 25 頁降到 19 頁。2026-10-06 第二輪：第 3 章「這些分類為什麼重要」與第 5 章「掃描資訊與範圍」不再強制換頁（章節標題 `keep_with_next`），浮水印縮小、透明度降低；分數說明註明是 Argus 自訂模型、不是產業標準（`SCORE_NOTE`）。

### 報告要短：樣板只講一次（scan 38 事後修正）

scan 38 是 34 頁，使用者回饋「結構跟之前差不多、優化不明顯」。實測分布：發現項目佔全文 78.9%，其中

- 逐項的 AI 提示詞佔發現項目 **43%**，內容是把上方「問題是什麼／檢測依據／怎麼修」原封不動再抄一遍
- 「為什麼要在意」出現 14 次卻只有 **6 種**內容；「修好了怎麼確認」14 次只有 **3 種**

所以規則是：**只跟分類有關的講一次、只跟流程有關的講一次，每項發現只留屬於它自己的內容。**

| 內容 | 放哪裡 |
|---|---|
| 分類的「沒處理會怎樣」 | 摘要的「這些分類為什麼重要」表，**且只列有非 info 發現的分類**——某分類若只有正向資訊提示，寫「會被攻擊者利用」就是把好消息說成威脅 |
| 修補後怎麼驗證 | 附錄，一次 |
| 怎麼用 AI 深入了解 | 附錄，一次（叫讀者複製該項的三段文字，不逐項重印提示詞）|
| 問題是什麼／怎麼修／檢測依據 | 逐項 |

### 證據品質（2026-09-28 報告審查）

- **嚴重度反映實際風險（2026-10-06 第二輪審查，`tests_accuracy_review.py`）**：缺少 CSP 是縱深防禦，列低風險（原中風險）；CSP 有 `frame-ancestors` 就不報缺少 X-Frame-Options（看的是有沒有防點擊劫持）；沒有 H1 是低風險、多個 H1 只是 info；登入／註冊／忘記密碼等帳號功能頁（路徑段 `login`、`register`、`signup`… 與 `/management`）比照後台跳過 SEO／AEO／GEO（`is_admin_path`）；觸控目標的描述區分 Argus 易用性建議（40px）與 WCAG 2.2（AA 2.5.8＝24×24 且間距足夠可豁免、AAA 2.5.5＝44×44）；llms.txt 標明是新興做法。
- **PII 分級**（`scanners.analyze_data_exposure`）：高風險 `SECURITY_PII_8B24BB8B28` 只給身分證號／信用卡號；手機、非本站網域 Email、藏在 HTML 註解的資料、開發殘留 → 中風險 `security-pii-personal-contact`；本站網域（同 registrable domain）或 `mailto:`／`tel:` 的聯絡方式 → info `security-pii-public-contact`（多半是刻意公開）。舊版一看到任何 Email 就判高風險。信箱名稱含網站名稱（`ntubimdbirc@ntub.edu.tw` 之於 ntubimdbirc.tw）或角色信箱（info、service、contact…）也視為組織窗口；`placeholder` 屬性的填寫範例（`e.g.0911-222-333`）不掃描（2026-10-06 實測誤報）。
- **判定依據**：高風險、PII 與 AI 觀察項目在 `evidence_json.assessment`（或 `reports._assessment_for` 的預設）寫「成立條件／實際觀察／尚缺證據／驗證方法」，報告卡片逐項印出。
- **AI 觀察封頂中風險**（`reports._report_severity`，對 `agent-` 規則；舊資料亦同）並標示來源；每張卡片一行追溯資訊：規則、觀測時間、來源（規則引擎／工具／AI Agent）。
- **合併多頁保留逐頁證據**（`locations`），Cookie 值遮蔽（`cookie_scanner.mask_cookie_line`，頭 4 尾 2）。
- **掃描範圍**：寫清楚已檢查幾頁、是否達頁數上限、完整分析頁數、被阻擋／錯誤頁數、本次沒跑的檢查；不把「全網站模式」說成檢查了整個網站。
- **資安與內容分開**：發現清單分「資訊安全」與「網站內容與體驗」兩節；內容類建議附 `RULE_BASIS`／`CATEGORY_BASIS`（依據與限制），不得推論「缺 llms.txt／JSON-LD／字數少 ⇒ 不會被搜尋或引用」；摘要附分數算法（`SCORE_NOTE`）。
- **修補驗證**：附錄逐項列「如何確認已修好」（`verify_items`），並提醒重掃沒出現不等於已修好；CSP 要檢查指令內容而非只看標頭存在；JS 渲染比對要用同一種文字擷取方式。
- **既有掃描**：`manage.py renormalize_findings --scan-id N`（或 `--all`）以資料庫保存的頁面 HTML 重跑 PII 分級、AI 觀察降級＋IP 核對、Cookie 遮蔽，重算分數並刪除快取報告（`finding_normalization.py`，不對目標發請求，可重複執行）。

其他硬性上限：每項發現的中繼資料壓成**一行**不用表格（19 項就是 19 張表，在 Word 裡非常吃垂直空間）；受影響頁面最多列 `_MAX_LISTED_PAGES` 個、其餘收成「…另 N 處」；證據顯示上限 `_MAX_EVIDENCE_CHARS`。

成效：總字元 15848 → 6669（−58%），表格 30 → 10，發現項目數不變。由 `tests_report_compactness.py` 鎖定。

### 報告的讀者是網站主，不是資安工程師

| 規則 | 為什麼 |
|---|---|
| 內部識別碼（`rule_id`、`evidence_source`、`evidence_type`）不進正文 | 對讀者零意義。`rule_id` / OWASP / CWE 收進附錄「技術索引」供工程師與稽核查用 |
| 每筆發現固定四段：問題是什麼 / 為什麼要在意 / 怎麼修 / 修好了怎麼確認 | 舊版依 severity 給同一個結構三種標題（風險描述／改善重點／建議優化），讀者會以為是三種不同的東西 |
| **`info` 走不同結構**（這代表什麼，且沒有「怎麼修」） | info 常是正向指標。實際產出報告時發現「Nuclei 探針受 WAF 攔截」（代表防護有效）底下寫著「這類問題會被攻擊者利用」——與該項意義完全相反，還叫讀者去修一個沒壞的東西 |
| 「修好了怎麼確認」不得假設問題型態 | 舊文字寫「用 curl -I 檢查回應標頭」，但頁面外洩個資這類問題根本不是標頭問題 |
| 名詞解釋只列這份報告真的出現過的術語 | 貼固定清單會塞進一堆與本次無關的名詞 |

排版下限：**必須有**封面、目錄、章節分頁、表格、頁首頁尾與頁碼 field、嚴重度顏色。舊版是 328 段純文字流（其中 293 段 Normal、0 表格、0 分頁），有 `tests_report_layout.py` 鎖定。

中文字型要同時設 `run.font.name` 與 `w:eastAsia`（`_styled_run()` 已封裝），只設前者 Word 會對中文退回預設字型。

前端 `styles/03-tokens.css` 的 `--argus-cyan (#38bdf8)` 是為深色背景設計的，**印在白紙上對比不足**；報告標題用 `--argus-cyan-deep (#0c4a6e)`，cyan 只當強調線。

**`Finding.ai_explanation` / `ai_remediation` / `llm_model` / `llm_generated_at` 目前無任何寫入點**，報告不得聲稱有 AI 解釋。

報告改為輸出 **`ai_handoff_prompt`**（`scanners.build_ai_handoff_prompt()` 產生，每筆 finding 都有值）——使用者可直接貼進 ChatGPT / Claude 取得深入說明。**這段必須跟 `evidence` 一樣套 `mask_pii_evidence()`**：提示詞內嵌了原始 evidence，不遮罩等於從後門把個資漏回這份會被轉寄的報告。

---

## 大函式的內部結構（2026-09-28 拆解，行為不變）

| 函式 | 拆成 |
|---|---|
| `crawler.crawl_site` | `_CrawlState`（佇列、造訪、重試、速率時鐘；`next_target`／`enqueue_links`／`progress`）→ 每頁 `_throttle` → `_visit_page`（`_attach_page_listeners`、`_capture_same_origin_page` 內含 framenavigated 跨網域保護 → `_capture_content`、`_page_record`）→ 失敗 `_record_page_failure`（Playwright 錯誤重試）→ `_recycle_context`、`_report_progress`。清空內容一律走 `_empty_capture`，錯誤原因的階段名由 `_PageStage` 追蹤 |
| `scanners.analyze_seo` | `SEO_PAGE_CHECKS` 逐項檢查函式（`_seo_title_length` …），順序即 finding 順序 |
| `scanners.analyze_data_exposure` | `_collect_pii`（正文＋HTML 註解＋開發者字串）→ `_classify_pii`（高風險／個人聯絡／刻意公開）→ 三種 finding |
| `security.exposure_scanner.probe_paths` | `_PacedRequester`（取消檢查＋共用 RPS 時鐘）→ `_fetch_robots_disallow` → `_soft_404_baselines` → `_probe_one` |
| `reports.build_report_payload` | `_sorted_report_groups`、`_report_finding_entry`、`_report_summary`、`_report_priorities`、`_report_why_matters`、`_report_scan_info`、`_report_appendix` |

`crawl_site` 沒有單元測試能驅動真實 Playwright 迴圈；改動它時用本機測試站實際爬一次，前後比對回傳的頁面、警告與進度序列。

## 截圖失敗不得讓整頁分析作廢（2026-08-31 事故）

`page.screenshot()` 在 `crawler.py` 裡是在 **`pages.append()` 之前**執行的。
舊版讓它的例外直接冒出去，會被外層的 `except Exception` 接住，**整頁被丟進 `failed_urls`**——連帶該頁的 `Page` 紀錄與 SEO/AEO finding 一起消失。

**UX 有三個來源**：規則式檢查（`analyze_ux()`，每頁都跑、不需 LLM）與擬真使用者
Agent UX 測試（`run_agent_ux`，全網站＋勾 UX 才跑，預設總開關關）。規則式檢查含
三類量測，全部由爬蟲逐頁收集、`analyze_ux()` 逐頁產生 finding：

- **行動版版面**（`collect_mobile_layout()` → `Page.layout_metrics`）：水平溢出等。
- **版面位移 CLS 與元素歸因（2026-10-08，roadmap §4 第 3 項）**（`collect_layout_shift()` →
  `layout_metrics["layout_shift"]`，不需 migration）：每頁在 `scroll_to_bottom` 與 `page.content()` 之後、
  **截圖之前**量（整頁截圖會改視窗大小），被阻擋的頁不量。讀瀏覽器 buffered `layout-shift` 紀錄，依 Google
  CLS 定義取最大工作階段視窗，`hadRecentInput` 不計；`scroll_to_bottom` 最後瞬間跳回頂端前會設
  `window.__argusScrollTopAt`，之後的位移（捲動後縮小的標頭又展開）是量測動作造成的、不計。每個元素分數＝它有移動
  的位移分數合計（同一次位移同名元素只記一次，不會大於整頁 CLS），附最大移動距離；另數沒有同時標
  width／height 的 img／video／iframe 當可能原因。`scanners._ux_layout_shift` → `ux-layout-shift`：CLS >0.1 低、
  >0.25 中。PSI（`pagespeed.py`）只測首頁且需金鑰，這裡是每頁、桌面視窗、單次量測，數值會浮動（沙箱實測
  udn 首頁兩次分別 0.851 與 0.025：網路慢時樣式表晚到也會量到）。測試 `tests_layout_shift.py`（真實瀏覽器部分
  要用 `goto`：`set_content` 之後的位移會被 Chromium 標成使用者操作後而不計）。
- **觸控目標過小 ＋ 表單欄位缺可及名稱**（`collect_ux_signals()` → `page["ux_signals"]`）：
  可點元素在手機寬或高 < `_MIN_TAP_TARGET_PX`（40px）列為 tap-target 問題（≥5 個升
  MEDIUM）；`<input>`/`<select>`/`<textarea>` 無 label/aria/title/placeholder 列為
  accessibility 問題（MEDIUM）。每類上限 `_MAX_UX_OFFENDERS`（8）。
- **精準標註（2026-10-06）**：觸控目標、缺標籤欄位、破版元素都記錄行動版文件座標 `box`（`rect + scroll`）；只要有這類問題，爬蟲另拍一張行動版整頁截圖（`page-N-mobile.png`，路徑存 `layout_metrics["mobile_screenshot"]`，API `pages/<id>/screenshot/?variant=mobile`、`PageSerializer.has_mobile_screenshot`）。Finding 的 `evidence_json.annotations = {"viewport": "mobile", "boxes": [...]}`，前端在行動版截圖上逐一框住實際元素，不再框整個區塊。移出視窗左右兩側的抽屜選單不算觸控目標（`isVisible` 排除 `rect.right <= 0 || rect.left >= innerWidth`）。
- **未捕捉的 JS 例外**（`pageerror` 監聽 → `page["js_errors"]`）：頁面 console 未攔截的
  例外列為 MEDIUM，證據上限 `_MAX_JS_ERROR_EVIDENCE_CHARS`（800）。
- **axe-core WCAG 自動化檢查（2026-10-07，roadmap P1，`accessibility.py`）**：勾 UX 且
  `ARGUS_AXE_ENABLED` 時，爬蟲在桌面版視窗、內容／截圖／連結／元素座標都擷取完之後、行動版量測
  **之前**跑（會注入腳本，不可影響已保存的 HTML；行動版量測會改 viewport）。以 `page.evaluate(原始碼)`
  注入（DevTools 協定，不受目標網站 CSP 影響；`add_script_tag` 會被擋），只跑 WCAG 2.0／2.1／2.2 A／AA、
  只回違規；關掉與自建檢查重疊的 `target-size`、`label`、`select-name`。結果在 `page["a11y"]`（不落 DB，
  與 `ux_signals` 相同），每項違規最多 5 個元素的選擇器、HTML 片段、桌面文件座標。`scanners._ux_axe`
  轉成 finding：`rule_id=axe-<規則>`、impact critical、serious→中／moderate、minor→低（2026-10-09 起上限是中：axe 的 critical 是對使用輔助科技者的影響，不等於網站整體風險；button-name／link-name 的說明補上「一般訪客看圖示就懂、螢幕閱讀器使用者聽不到用途」，`_AXE_NOTES`）、
  `bounding_box`＝第一個元素、`evidence_source=axe-core <版本>`、常見規則有中文標題與修法（`_AXE_ZH`）。
  每頁逾時 `ARGUS_AXE_TIMEOUT_SECONDS`（15）、最多 `ARGUS_AXE_MAX_PAGES`（50）頁；覆蓋檢查 `axe`
  （全部可分析頁跑完＝completed、部分＝partial、全失敗＝failed）。報告來源標「外部工具（axe-core）」、
  依據 `reports.AXE_BASIS`（自動化檢查不等於符合 WCAG）。axe 檔案固定版本放 `vendor/axe/`（含 LICENSE），
  升級時換檔並更新 `tests_accessibility_axe.py` 的版本斷言。測試的真實瀏覽器案例需 `ARGUS_TEST_CHROMIUM_PATH`。
- **PageSpeed Insights（2026-10-07，roadmap P1，`pagespeed.py`）**：勾 UX、`ARGUS_PAGESPEED_ENABLED` 且有
  `ARGUS_PAGESPEED_API_KEY` 時，`stage_pagespeed` 以 PSI v5（`strategy=mobile`，四個 category）**只測首頁**，結果寫
  `ScanJob.performance_report`（migration 0030）：`lab`＝Lighthouse 實驗室單次量測（四個分數、LCP／CLS／TBT／FCP／
  Speed Index、前 5 項改善機會，`runtimeError` 記在 `lab.error`），`field`＝CrUX 過去 28 天第 75 百分位（優先
  網址本身，`origin_fallback` 時改用整個網站並標 `scope=origin`；都沒有則 `scope=none`＋`reason`，不硬湊數字；
  CrUX 的 CLS 以 ×100 整數回傳，要除以 100）。**外部指標不併入 Argus 分數、不產生 Finding**，只在掃描「效能」
  分頁與報告範圍表兩列（`summary_lines`）並列呈現。覆蓋檢查 `pagespeed`（維度 None，不影響維度覆蓋）：成功＝
  completed、Lighthouse 有 runtimeError＝partial、呼叫失敗＝failed（掃描照常完成）。錯誤訊息只寫原因（逾時、配額
  用完、HTTP 狀態碼），不含金鑰與回應內文。受測網址會送到 Google。逾時 `ARGUS_PAGESPEED_TIMEOUT_SECONDS`（90）。
  測試以 PSI 回應 fixture 驗證（`tests_pagespeed.py`），不連線 Google。

`Page.layout_metrics` 為空代表**沒量到**（量測失敗或舊資料），
不可當成「沒問題」——`tasks.py` 的 `tested_categories` 也依此判斷，否則報告會
把「未評估」顯示成滿分。量測本身在 `crawler.collect_mobile_layout()`，**必須
留在所有其他擷取之後**：它會改 viewport，跑在截圖或內容擷取之前會讓那些結果
變成行動版的。`collect_ux_signals()` 緊接在 mobile layout 之後、同樣在其他擷取
之後；失敗一律吞掉回傳 `{}`，比照截圖的失敗隔離。跨源／過大／離站等重置分支
必須同步把 `ux_signals`／`js_errors` 清空，避免把上一頁的訊號帶到被重置的頁。

**SEO 與 AEO finding 只由 `analyze_page()` 逐頁產生**，所以「爬到 0 頁」＝這兩類完全沒有結果。正式站的實際症狀是：掃描顯示完成，但畫面截圖空白、SEO 分析整個不見，只剩站台層級的 DNS/SSL/header 檢查。

| 規則 | 為什麼 |
|---|---|
| 截圖一律走 `_capture_screenshot()`，**不得直接 `await page.screenshot()`** | 截圖是輔助資料，不該有讓整頁作廢的殺傷力 |
| 建目錄一律走 `_prepare_screenshot_dir()` | 磁碟寫滿／唯讀掛載時，`mkdir` 的例外會讓整次掃描在爬第一頁前就失敗 |
| 失敗記進 `warning_summary["screenshot_failures"]`，**不是 `failed_urls`** | 那一頁其實抓到也分析過了，記進 `failed_urls` 會讓報告誤報成「頁面擷取失敗」 |

截圖有保留期限：`manage.py cleanup_screenshots --older-than-days N`（預設 90，支援 `--dry-run`）。`media/scans/<掃描id>/page-N.png` 是全頁擷取、體積遠大於報告，**是 media volume 上真正無限成長的那一塊**；磁碟寫滿正是上述事故最可能的觸發原因。

---

## 報告防偽與快取（`ReportVerification`）

每次 `build_scan_report()` 完成時寫入一列 `ReportVerification`：報告編號、**PDF** 檔案內容 SHA-256、產生時間（.docx 只是暫存目錄裡的中間產物，轉檔失敗不寫紀錄）。

| 規則 | 為什麼 |
|---|---|
| **報告編號跨重新產生保持不變** | 由 `HMAC(SECRET_KEY, scan_id)` 推導，不含時間戳。報告一旦交付就可能被轉寄存檔，換編號會讓已流出的副本失效 |
| **報告本身只印編號、不印雜湊** | 雜湊要涵蓋整份檔案，檔案裡又要有雜湊＝循環相依。雜湊由查驗端點提供，收件者自行 `sha256sum` 比對 |
| **`views.py` 的 report action 必須用快取** | 省下每次下載的 IO 與 CPU。三個條件都成立才可重用：有防偽紀錄、檔案存在、`renderer_version` 等於目前的 `report_render.RENDERER_VERSION` |
| **改動報告版面（含轉檔方式）就要把 `RENDERER_VERSION` +1**（目前 18：摘要「改一處就能一起解決」；17：附錄各分類扣分明細；16：資安發現類型；15：AEO 逐題可信度；14：AI 爬蟲政策；13：安全標頭等第；12：OWASP ZAP 被動分析的來源標示；11：PageSpeed Insights 兩列；10：axe-core 依據與來源；9：評分版本；8：覆蓋契約；7：部分掃描警示；6：網站優勢附依據、短章節不換頁；5：重新設計版面；4：改為 PDF） | 否則掃描一旦產過報告就永遠鎖在舊版面。實際踩過：圖表修好後重新下載舊掃描的報告，拿到沒有圖表的快取檔，看起來像修復失敗 |
| **重產時舊雜湊要進 `previous_sha256`** | 重產會換掉 `content_sha256`，若直接覆蓋，先前已寄出的正本在查驗頁會被判成「對不上」——等於自己把交付過的報告變成偽造品 |
| **`/api/verify/<編號>/` 是公開端點，絕不回傳掃描發起人** | 否則用報告編號就能反查使用者身分。回應只有：編號、目標網址、掃描與產生時間、整體分數、內容雜湊。帶 `?content_sha256=` 時另回 `matches` / `is_latest_version`，比對範圍含 `previous_sha256`；歷史雜湊本身不列進回應 |

報告檔案有保留期限：`manage.py cleanup_reports --older-than-days N`（預設 180，支援 `--dry-run`）。**只刪檔案、不刪 `ReportVerification`**——收件者手上的報告不會因為伺服器清檔就失效，編號必須繼續查得到。清掉後若重新下載會產生新的一版、指紋隨之更新，但舊指紋會留在 `previous_sha256`，舊副本仍驗得過。排程見 `k8s/04-backend.yaml` 的 `CronJob/cleanup-reports`（每日 20:00 UTC）與 `CronJob/cleanup-screenshots`（20:30 UTC）——**兩者都必須掛 media PVC**，沒掛就是在容器的空目錄裡掃，每天回報「刪除 0 個」卻什麼也沒清。

附錄小節用 `_SectionNumber` 動態編號：名詞解釋、技術索引、頁面清單都會在沒資料時整段消失，寫死號碼會跳號。

入口頁截圖**刻意只放一張**：全頁截圖體積大，50 頁的掃描全塞進去會讓 `.docx` 失控，而 header / DNS / meta 這類發現本來就沒有視覺佐證價值。

與前次掃描比較**只比對同一位使用者的掃描**：同一個網址可能被不同人掃過，拿別人的當「前次」既不合理也會洩漏他人掃描的存在。

封面 logo 走「有就用、沒有就用字標」：偵測 `backend/apps/scans/report_assets/`，存在才 `add_picture`。**必須放在 `backend/` 之內**——backend image 只 `COPY backend ./backend`，放 `frontend/public/` 時 `exists()` 一律 False，封面會靜默退回純文字，本機與測試都看不出來。**刻意不引入 SVG 轉檔套件**（`cairosvg` 有系統函式庫相依，會拖累 CI 與 Docker build）。

前端查驗頁在 `frontend/src/features/public/PublicPages.jsx::VerifyReportPage`，路由 `/verify` 與 `/verify/:reportNumber`。

---

## ScanJob.progress 格式

Worker 每完成一頁需更新此 JSON 欄位，前端輪詢後顯示進度條：

```json
{
  "pages_done": 12,
  "pages_total": 50,
  "phase": "crawling",
  "phase_started_at": "2026-05-26T10:30:00Z",
  "step": "analyze_seo",
  "steps": ["crawl", "analyze_seo", "analyze_geo", "deep_security", "geo_site", "scoring"],
  "step_done": 12,
  "step_total": 50,
  "step_started_at": "2026-05-26T10:31:00Z"
}
```

`phase` 值必須是 `"crawling"` / `"scanning"` / `"agent_testing"` 其中之一。

`step`／`steps` 是 phase 之下的細分階段（前端掃描進度條據此顯示「正在分析 GEO／UX／資安…」）：
`steps` 由 `tasks.planned_scan_steps()` 依勾選維度與範圍／授權算出本次實際會跑的子步驟，`step` 是目前這一步。
可能值：`crawl`、`analyze_seo`／`analyze_aeo`／`analyze_geo`／`analyze_ux`／`analyze_security`（只列勾選維度）、`aeo_answers`（勾 AEO，接在逐維度分析之後）、
`active_probe`（`run_nuclei`）、`deep_security`、`zap_passive`（勾資安且已啟用 ZAP）、`exposure_probe`（`run_exposure`）、`geo_site`（勾 GEO）、`seo_links`（勾 SEO）、`pagespeed`（勾 UX 且已設定 PSI 金鑰）、`agent`（Agent 啟用且可執行）、`scoring`。
頁面分析改為**逐維度、逐頁**執行（`analyze_page(categories={單一維度})`），結果與一次跑全部維度相同；新增子步驟時要同步前端 `ScanExperience.jsx` 的 `SCAN_STEP_META`。

`step_done`／`step_total` 是**本階段**內的進度（爬取＝頁、逐維度分析＝該維度已分析頁數、Agent＝步數；其他子步驟 0/0＝不定進度），`step_started_at` 在同一步內保留不變（供前端估算本階段剩餘時間）。前端整體百分比由階段序號加上本階段比例算出，進度條才會和階段一起走（2026-09-28 前整體進度只看頁數，爬完就 100%、後面十個階段進度條不動）。

---

## 掃描流程階段（`tasks.py`，2026-09-28 工程化）

`run_scan_job` 只做三件事：`start_scan_run()` CAS 取件並建立 `ScanRunContext` → 依序執行 `SCAN_PIPELINE` → 取消／超時／失敗三種收尾（`finish_cancelled`／`finish_timeout`／`finish_failed`，退款失敗會讓 task 失敗）。完成時由 `stage_settlement()` 結算與贈與修正產出額度。

| 階段名（失敗 log 會寫 `[階段名:例外類別]`） | 函式 | 做什麼 |
|---|---|---|
| `target_validation` | `stage_validate_target` | 再次確認目標是公開 HTTP(S) |
| `crawl` | `stage_crawl` | Playwright BFS；每頁回報進度並當取消檢查點。**沒有任何可分析的頁面（2xx／3xx 且未被阻擋）就丟 `ScanTargetUnreachable`**，由 `finish_unreachable` 標失敗、寫可讀原因並全額退款（2026-10-06：0 頁曾標完成並給 73 分） |
| `enter_scanning` | `stage_enter_scanning` | 記錄警告、狀態推進到 scanning、落地 `Page` |
| `fingerprint` | `stage_fingerprint` | 網站特徵（只記錄、不影響掃描）：寫 `ScanJob.fingerprint`；失敗只記 log（`fingerprint.py`） |
| `page_analysis` | `stage_analyze_pages`（單頁單維度：`_analyze_one_page`） | 逐維度、逐頁規則分析＋inline 秘鑰偵測 |
| `aeo_answers` | `stage_aeo_answerability`（`_aeo_site_pages`） | AEO 問答檢測（見下「AEO 問答檢測」），結果寫 `ScanJob.aeo_report` |
| `site_security` | `stage_site_security` | 站台層級 HTTPS/HSTS/CSP 等（只評估一次） |
| `active_probe` | `stage_active_probe`（`_collect_probe_targets`、`_run_site_active_tools`、`_run_single_page_nuclei`、`_waf_blocked_nuclei_note`） | Nuclei／Katana，遵守範圍與授權矩陣 |
| `deep_security` | `stage_deep_security` | security/ 子套件被動深度檢查＋WAF 封鎖偵測；已知 CVE 由 `security/vuln_intel.py` 補 EPSS 被利用機率與 OSV 修補版本（只影響排序與說明，不改嚴重度） |
| `zap_passive` | `stage_zap_passive` | 勾資安且 `ARGUS_ZAP_ENABLED` 才跑：爬取時錄的同網站 HAR 交給 OWASP ZAP 只跑被動規則（零新增請求），重複既有檢查的告警不列；ZAP 不可用只標覆蓋 failed，HAR 用完即刪（`security/zap_passive.py`，見 `docs/zap-passive.md`） |
| `exposure` | `stage_exposure` | robots 敏感路徑（被動）＋敏感檔案主動探測（全網站 active） |
| `geo_site` | `stage_geo_site` | llms.txt、AI 爬蟲政策（`ai_bots.py`：只有封鎖 AI 搜尋／使用者觸發的爬蟲才列問題）、組織實體、文章作者與日期（`geo_entity.py`） |
| `seo_links` | `stage_seo_links` | 勾 SEO 才跑：連結狀態與跳轉鏈、robots.txt／sitemap／HTTPS／www／404／結尾斜線檢查，寫 `ScanJob.seo_report`，並由 `seo/site_findings.py` 轉出站台層級 SEO Finding；失敗只記 log（`seo/collect.py`） |
| `pagespeed` | `stage_pagespeed` | 勾 UX 且已設定 PSI 金鑰才跑：首頁 Lighthouse＋CrUX，寫 `ScanJob.performance_report`；失敗只標覆蓋 failed（`pagespeed.py`）。勾了 UX 但平台沒設定金鑰時標覆蓋 skipped（原因「平台尚未設定…」），效能分頁據此說明是平台設定（2026-10-08）；正式環境要在 Secret 設 `ARGUS_PAGESPEED_API_KEY`，後台系統資訊頁 `providers.PAGESPEED_API_KEY_SET` 可確認 |
| `favicon` | `stage_favicon` | 更新所屬專案的網站圖示（`favicon.py`；失敗只記 log，不影響掃描） |
| `agent` | `stage_agent` | Hermes-Agent（資安／UX），失敗不讓掃描失敗 |
| `kali` | `stage_kali` | Kali 主動驗證 fallback |
| `site_profile` | `stage_site_profile` | 網站概況寫 `ScanJob.site_profile`（`site_profile.py`，version 2）：基礎架構（`security/infra_scanner.py`：A／AAAA／CNAME／NS、IP 反解、Cloudflare 網段、標頭／CNAME 指紋 → 掃到的是 CDN 邊緣還是主機）、「網站優勢」`strengths`（HTTPS、HSTS、nosniff、CSP、DNSSEC、SPF -all、DMARC、robots＋sitemap、正確 404、行動版無破版、載入時間；只列本次有勾的維度、不可與同次問題矛盾；每項附 `evidence` 與 `confidence`＝confirmed／likely。**偵測到 CDN 不等於 WAF 有在擋**：只有本次掃描出現 `waf_block_detected`（403／challenge）才寫「確認防護規則已生效」，否則寫「無法從外部確認」）與「使用的技術」`technologies`（`tech_stack.py`：只看首頁 HTML 與回應標頭的特有路徑／屬性，加上 Katana 已辨識的技術，每項附依據；不回報版本號），勾資安時另有 `observatory`（安全標頭參考等第，`security/observatory.py`，非官方、不計入分數），勾 GEO 時另有 `ai_bots`（AI 爬蟲政策，`ai_bots.py`）；失敗只記 log |
| `scoring` | `stage_scoring`（`tested_categories_for`、`base_scores_for`） | 計分並 CAS 推進到 completed |

階段之間只透過 `ScanRunContext` 傳遞中間產物；`ctx.record(findings, page=...)` 同時寫 `Finding` 與納入計分清單。**新增階段**：寫 `stage_xxx(ctx)`、加進 `SCAN_PIPELINE`；要在進度條顯示時同步 `planned_scan_steps()` 與前端 `SCAN_STEP_META`。測試 patch 目標仍是 `apps.scans.tasks.<名稱>`，所以外部依賴一律以模組層級名稱呼叫。結構由 `tests_pipeline_stages.py` 鎖定。

網頁 API 與 MCP 共用的掃描入口：`views.enqueue_created_scan()`（派工，失敗全額退款）、`views.ensure_report_file()`（報告快取）、`tasks.request_scan_cancel()`（取消＋退款）。

---

## 掃描覆蓋契約（`coverage.py`，2026-10-07，roadmap P0-A）

工具失敗或沒跑完不能被呈現成「0 項問題」，前次問題沒出現也不等於已修好。

- **記錄**：各 `stage_*` 以 `ctx.coverage.mark(check, status, reason)` 記錄檢查結果（completed／partial／failed／blocked／skipped），`ctx.record(findings, check=...)` 同時記下該檢查產生的問題代號（`issue_key`）。檢查名稱與所屬維度在 `CHECK_CATEGORIES`；外部工具例外一律走 `tasks._tool_failed`（記 log＋標 failed）。agent 的 finding 由 runner 直接落 DB，以規則前綴（`AGENT_UX_`／`agent-`／`kali-`）對回檢查。
- **保存**：`stage_scoring` 把 `coverage_for(ctx, tested)` 寫入 `ScanJob.coverage`（migration 0028）：`checks`（狀態、原因、問題代號）＋`categories`（completed／partial／not_tested；沒進計分的勾選維度一律 not_tested）。
- **計分**：某維度有記錄的檢查全部失敗／被阻擋時，從 `tested_categories_for` 移除（顯示未評估）；部分失敗照常評分，但標部分評估。爬取有頁面擷取失敗（`failed_urls`）時 `crawl=partial`，逐頁分析的維度都是部分評估；robots／範圍略過不算。
- **歷史比較**（`projects.compare_issues`）：前次有、本次沒有的問題，以前次覆蓋紀錄找出是哪項檢查產生的，看該檢查本次狀態——completed 且受影響頁面本次有完整分析（沒被阻擋、HTTP < 400）才是 `resolved`；partial→`not_observed`、failed→`inconclusive`、blocked→`blocked`、沒跑→`not_tested`。前次沒有覆蓋紀錄時退回以維度狀態判斷；本次沒有覆蓋紀錄（舊掃描）一律 `not_observed`。回應附 `status_label`，總覽 `changes.resolved` 只算 resolved。
- **報告**：摘要「已解決 N 項」只算 resolved，其餘寫「另有 N 項本次未出現，但檢查不完整、無法確認已修好」；掃描範圍表列「未完整完成的檢查」（只有 partial 附原因，failed 的例外類別屬內部資訊不印）與「部分評估的面向」。
- **API**：`ScanJobSerializer.coverage`；`ScanJobSerializer.coins_charged`（2026-10-08：該掃描 `scan_hold`＋`scan_refund` 交易加總取負＝實際扣點，列表以 subquery annotate `coin_net` 一次算完）；專案總覽 `latest_scan.coverage`（`categories`＋`incomplete`），前端顯示不完整提示。
- **新增檢查**：在 `CHECK_CATEGORIES`／`CHECK_LABELS` 登記，成功、失敗、沒執行三種情況都要 mark。測試：`tests_coverage.py`。
- 尚未做：rule／resource 級細分、把檢查狀態接到計費。

## 評分與規則版本（`versions.py`，2026-10-07，roadmap P1）

- `ScanJob.scoring_version`（計分公式，`SCORING_VERSION`）與 `ruleset_version`（判定規則集，`RULESET_VERSION`）由 `stage_scoring` 寫入（migration 0029）；`rerun_scan` 兩個都更新，`finding_normalization._rescore` 只更新計分版本（只重跑部分規則）。舊掃描為空字串＝版本不明。
- **改了 `calculate_scores` 的公式就把 `SCORING_VERSION` +1；改了會影響找出哪些問題、算多嚴重的規則（含 AEO 判定與覆蓋契約）就把 `RULESET_VERSION` 改成當天日期。**
- `versions.comparable(a, b)`：兩次掃描兩個版本都已知且相同，分數差才可直接解讀。專案總覽 `score_comparable`、走勢每點 `model_changed`／`version_label`、`project_summaries` 的 `score_comparable`；前端版本不同時不顯示 ±分，改寫「評分規則已更新，無法直接比較」，歷史報告列標「規則已更新」。
- 報告：導讀句版本不同時寫「評分規則與前次不同，分數不宜直接比較」而不是進步／退步；掃描範圍表列「評分版本」（`RENDERER_VERSION` 9）。測試：`tests_scoring_versions.py`。

## 網站特徵（`fingerprint.py`，2026-10-07，ADR-0004 階段 1）

Smart Scan 的第一步：先記錄「這是什麼樣的網站」，**不改任何掃描決策或計費**（[ADR-0004](../../../docs/adr/0004-smart-dynamic-scan.md)）。

- **只用爬取已有的訊號**：頁面 HTML（`rendered_dom` 優先）、回應標頭、狀態碼、爬蟲被動攔截的 XHR／fetch 端點；**不發任何請求**（benchmark 以 socket patch 驗證連線數＝0）。只看 2xx／3xx 且沒被阻擋的頁面；401 頁面只用來讀 `WWW-Authenticate`。
- **特徵**：`cms`（WordPress／Drupal／Joomla／Shopify／Wix／Squarespace，標記必須在 `src`／`href` 屬性或 meta generator 裡，正文提到路徑不算）、`frameworks`（特有標記或 `X-Powered-By`）、`server`、`edge`（只看標頭，用 `infra_scanner.detect_edge`）、`has_login`／`login_urls`（實際顯示的密碼欄位，`<template>` 裡的不算）、`has_api`／`api_urls`（端點路徑像 API：`/api/`、`/graphql`、`/wp-json/`、`/rest/`、`/v1/`、`.json`；XHR 載入 HTML 片段不算）、`has_upload`、`auth_scheme`。
- **沒看到＝`None`，不是 `False`**，並在 `completeness` 註明：`complete`（有證據）、`not_observed`（爬取完整但沒看到）、`partial`（爬取不完整——有擷取失敗或達頁數上限；API 與邊緣服務沒看到時一律 partial）、`unavailable`（沒有可分析的頁面）。
- **信心值**：一頁的證據 0.7、兩頁以上 0.9、meta generator＋路徑 0.95。階段 2 的動態加掃只會用 ≥ 0.8 或兩個獨立證據的特徵。
- **保存**：`ScanJob.fingerprint`（migration 0031）＝特徵＋`version`、`phase=pre_scan`、`pages_considered`、`endpoints_considered`、`crawl_complete`、`elapsed_ms`；失敗時只有 `error`（例外類別）。目前不進 API、報告與前端。
- **準確率**：`fingerprint_gold.py`（人工標註；tag `decoy`＝容易誤判、`holdout`＝保留集，不拿來調規則）、`manage.py fingerprint_benchmark [--holdout] [--json]`，門檻 precision／recall ≥ 0.95 且連線數 0，由 `tests_fingerprint.py` 鎖定，只能往上調。**新增特徵或規則：先在資料集加案例並標註，再改規則；不可為了讓規則通過而改標註。**

---

## 合作式取消機制（Cancellation）

實作在 `cancellation.py`，**完全 DB-status-based**（沒有 Redis 旗標）：

1. 使用者呼叫 Cancel API（或 MCP 的 `cancel_scan`）→ `tasks.request_scan_cancel()` 把 `ScanJob.status` 設為 `CANCELLED` 並立即退款後回應。
2. `is_cancelled(scan_job_id)` 用 `ScanJob.objects.filter(id=..., status=CANCELLED).exists()` 即時查 DB（**不**用 ORM 物件快取、**不**經 Redis）；`raise_if_cancelled(scan_job_id)` 在檢查點呼叫它，命中就 raise `ScanCancelled`。
3. Worker 各階段（爬蟲每頁、scanners、agent、Kali fallback、Kubernetes executor 的 watch / Pod list / log I/O 前後）透過 `raise_if_cancelled` 主動輪詢；偵測到取消 → 停止當前工作 → `tasks.py` 主迴圈的 try/except 收到 `ScanCancelled` 後走 cancelled/refund 分支。

選擇 DB-status 而非 Celery `revoke(terminate=True)` 或 Redis 旗標的理由見 `cancellation.py` 模組 docstring：terminate 會送 SIGTERM 給 worker process 可能波及同 worker 其他 task；DB-status 讓 worker 在「安全點」停下，DB 不會留下半完成狀態。

重要：Cancel API 也會呼叫 `refund_full_for_scan`，兩邊都呼叫是安全的（冪等）。

---

## Playwright 規則

**Chromium 必須安裝在專案 `.ms-playwright`，禁止安裝到全域路徑。**

```powershell
# 正確安裝方式
$env:PLAYWRIGHT_BROWSERS_PATH=".ms-playwright"
uv run playwright install chromium

# 禁止（會污染全域）
uv run playwright install chromium
playwright install chromium
```

原因：全域 Playwright 路徑（`%USERPROFILE%\AppData\Local\ms-playwright`）若被覆蓋，會影響其他使用相同機器的開發者。

所有掃描入口、redirect、子資源與 WebSocket 都必須經 `services.py` 的公開 HTTP 目標政策；禁止 localhost、非 global IP、userinfo 與非 80/443 port。應用層驗證仍不能消除 DNS rebinding 的解析/連線競態，production 必須另以受控 egress proxy / firewall 阻擋 private、loopback、link-local 與 metadata 網段。

主 frame navigation 與 WebSocket 在送出前還必須符合 `ScanJob.origin`；公開 CDN 子資源可通過 public HTTP policy，但不可把主頁或 WebSocket 擴張到其他 origin。Nuclei 必須啟用 `-ni`、`-pt http` 並使用授權 User-Agent；`-lna`（= `-restrict-local-network-access`，封鎖私網連線的 SSRF 防護）**預設必須開**，僅在 `ARGUS_ALLOW_PRIVATE_TARGETS`（DEBUG only，掃 Docker 網路內受控目標如 Juice Shop）時由 `nuclei_scanner.py` 自動移除。Katana 必須使用 exact-origin `-cs`，不可只用僅限制 hostname 的 `fqdn`。

### 私網目標旁路（ARGUS_ALLOW_PRIVATE_TARGETS，2026-09-25）

本機／隔離 demo 掃 Docker 網路內受控測試目標（OWASP Juice Shop 等）用：

- **runtime 雙條件**：`services.allow_private_targets()` ＝ 開關開啟 **且** `settings.DEBUG`——正式環境誤設 env 也不生效；`scans.E002`（`checks.py`）另在部署檢查提早報錯。
- 放行範圍：私網 IP、localhost、單標籤 hostname（如 `juice-shop`）、非標準 port；**userinfo、無法解析的 hostname 仍拒絕**。
- 套用點全部集中走 `services.assert_public_http_url`（crawler、agent runner、掃描／網域驗證 serializer）；`domain_verification.normalize_domain` 同步放行單標籤／IP／localhost；`nuclei_scanner` 於旁路時移除 `-lna`。
- 環境：疊加 `docker-compose.juice.yml`（web/worker 設 DEBUG＋旁路＋Agent 開啟，與 K8s 正式環境功能面一致；demo 調幅見 `docs/hermes-agent-architecture.md` §6）。

### Authenticated scan（test_auth_*，2026-09-26）

無公開註冊（或註冊需 email 驗證/CAPTCHA）的網站，agent 無法自建帳號——
建立掃描可選填 `test_auth_email/password`（serializer write_only；
`ScanJob.test_auth_*_encrypted` 以 Django Signer 加密），agent runtime
解密後僅注入 auth 類 specialist 的 prompt 用於登入；**不進** API 回應、
log、findings、報告。migration 0016。

### SPA 攻擊面管道（2026-09-25）

`crawl_site` 被動攔截 same-origin XHR/fetch 端點（第 4 回傳值）→
`tasks.py` 併入：sqlmap 候選＝全部端點。Nuclei 2026-10-08 起只掃網站根網址
（見「Nuclei 模板治理」），不再使用頁面與端點清單。
Agent 端同能力＝`get_network_requests` 工具（見架構文件 §3）。

---

## Coin 扣點流程（與 billing 整合）

```
建立掃描 → hold_for_scan(max_pages × 勾選維度數 × 每維單價 ＋ agent_ux_fee ＋ agent_deep_fee；is_trial＝0)
  ↓ worker 完成
settle_scan_actual(actual_pages × 同組維度數 × 每維單價 ＋ agent_ux_fee
                   ＋ agent_deep_fee（只在 deep_agent_ran）)  ← 退差額
  ↓ 若失敗/取消
refund_full_for_scan(scan)  ← 全退（冪等）
```

`tasks.py` 負責在適當時機呼叫這三個 `billing/services.py` 函式。

**Agent UX 附加費**：`estimate_scan_cost` 已把 `agent_ux_fee(max_pages, categories)`
折進頁面費，hold／settle 都自動含這筆固定點數（`ARGUS_COIN_AGENT_UX`，預設 20），
不新增 `CoinTransaction.kind`、不需 migration。收費條件與 `run_agent_ux` 對齊：
`ARGUS_AGENT_ENABLED` 開、`max_pages > 1`（全網站）、且勾了 `ux` 才收；否則回 0。
若實際只爬到 1 頁，settle 以 `actual_pages=1` 重算 → 這筆費用自動退回（fee 也回 0）。

**深度資安附加費與首次免費掃描（2026-10-07）**：主動＋已授權＋全網站預扣
`ARGUS_COIN_AGENT_DEEP`（50）；`stage_settlement` 以
`deep_agent_ran = execution_plan.run_agent and agent_result is not None` 傳給
`settle_scan_actual`——agent 有跑就收（與實際頁數無關，只爬到 1 頁 agent 一樣花了 token），
沒跑就退。`ScanJob.is_trial`（migration 0027）由 `ScanJobCreateSerializer` 依
`free_trial_available` 設定，試用掃描預扣與結算都是 0。餘額不足時 serializer 回
`affordable_pages`，由前端讓使用者確認 Partial Scan，**不得自動縮小範圍**。詳見
`apps/billing/CLAUDE.md`「2026-10-07 定價調整」。

`settle_scan_actual` 在 `ScanJob` 已寫成 `completed` 之後才執行，因此它的例外
**不得往上拋**：拋出去會落到 `run_scan_job` 的通用 `except`，把已完成的掃描改成
`failed` 並執行**全額**退款（頁面與 findings 仍在 DB，狀態卻是失敗，退的也不是
差額）。結算失敗必須保留 `completed`，在 `warning_summary["settlement_error"]`
與 `scan_log` 留下記錄供後續補結算。

若 `run_scan_job.delay()` 在 worker 取件前失敗，`views.py` 必須呼叫
`tasks.fail_scan_job_before_start()`，以同一筆資料庫交易把 `queued` 改為
`failed` 並執行冪等全額退款；API 回 503，不得留下孤兒工作或回傳 broker 例外細節。

建立掃描的 HTTP request 不得同步執行完整掃描。正式／Docker 模式只負責將任務
publish 到 broker；本機 `CELERY_TASK_ALWAYS_EAGER=true` 時，`views.py` 必須改由
單一背景 executor 啟動獨立 Python 子程序，先回 `201 + queued + ScanJob.id` 讓前端
立即進入詳情頁。Playwright 不得直接跑在 web thread；子程序才可呼叫
`run_scan_job.apply(..., throw=True)`。父程序前後必須清理 DB connection，以容量 1
的 semaphore 限制 outstanding 工作，並設定硬逾時與 process-tree 終止。子程序異常
結束時必須把所有非終態工作收斂為 `failed` 並冪等全額退款；忙碌或提交 executor
失敗仍走 `fail_scan_job_before_start()`。這條路徑只供 `DEBUG=true` 的本機 smoke
test，不是正式 worker；部署檢查 `scans.E001` 會拒絕非 DEBUG 的 eager 設定。

---

## 整合測試規則（必讀）

**完整掃描整合測試一律使用 Docker 環境（`localhost:8080`）。本機 runserver 僅能用 eager 模式做 smoke test。**

原因：本機 eager 可快速驗證單一程序的排程與掃描結果，但不包含 Redis、Celery worker 與 PostgreSQL，不能代表完整背景任務鏈路。環境選擇與前置檢查以 [`../../../docs/environment-preflight.md`](../../../docs/environment-preflight.md) 為準。

本機 eager 的建立 API 會先回傳 queued 任務，再由 web process 內的單一背景
executor 管理獨立 Python 掃描程序；同時只接受一筆 outstanding 工作，忙碌時新任務
會失敗並全額退款。因此可驗證前端立即導頁與掃描狀態輪詢，但關閉／重啟 runserver
可能中斷工作，不能當成具持久性的正式佇列。

```powershell
# 標準整合測試流程
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build web worker   # 含最新程式碼重建

# 給測試帳號補充 coin
docker exec argus-web-1 uv run python manage.py shell -c "
from django.contrib.auth import get_user_model
from apps.billing.services import get_or_create_wallet, admin_adjust
User = get_user_model()
user = User.objects.filter(email='YOUR_EMAIL').first()
admin = User.objects.filter(is_superuser=True).first()
admin_adjust(target_user=user, delta=999999, admin_actor=admin, note='test')
"

# 開啟 localhost:8080，用 UI 建立掃描並觀察 log
```

確認 Docker worker 有安裝 nuclei/katana：
```powershell
docker exec argus-worker-1 nuclei -version
docker exec argus-worker-1 katana -version
```

---

## 禁止事項

| 禁止 | 原因 |
|---|---|
| `scanners.py` / `crawler.py` 修改 `ScanJob.status` | 狀態機只在 tasks.py 管理 |
| `crawler.py` 呼叫任何 billing 函式 | 職責分離 |
| `playwright install` 不加 `PLAYWRIGHT_BROWSERS_PATH` | 污染全域路徑 |
| Nuclei/Katana 主動工具需 `scan_mode=active AND active_testing_authorized`，並遵守單頁／全網站矩陣 | 未授權或超出使用者選擇範圍的主動測試 |
| 主動掃描（`scan_mode=active`）目標 hostname 未通過網域所有權驗證（`user_owns_domain`；staff／superuser 的測試旁路除外，見上） | 宣告式授權不足以證明所有權；必須先完成 VerifiedDomain 驗證或 admin 人工核准 |
| 直接 `ScanJob.objects.filter(...).update(status=...)` | 繞過 signal，狀態不一致 |
| 把本機 eager smoke test 當成完整掃描整合 | 未涵蓋 Redis／worker／PostgreSQL，驗證不完整 |
