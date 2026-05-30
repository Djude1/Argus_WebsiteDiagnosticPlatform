# Technology Adoption Matrix

本文件把使用者提供的外部專案轉成 Argus 可落地的技術採納清單。原則是「採納架構與產品能力，不替換固定技術棧」。Argus 仍固定使用 React 18、Django 5、DRF、Celery、Redis、Playwright Python async、PostgreSQL/SQLite、python-docx 與 Docker Compose。

## 採納總則

- 採納可提升 Argus 核心目標的技術：授權式爬蟲、SEO/AEO/GEO/資安掃描、互動報告、Word 匯出、LLM Agent tool calling、可觀測性。
- 不採納會破壞合規邊界的能力：未授權反爬繞過、隱匿身份、代理池攻擊、批量污染內容、產生修復程式碼。
- 不替換既定語言與框架；外部專案的 PHP/Laravel、Express、Drizzle、Scrapling runtime 只作設計參考。
- 所有外部程式碼若日後要引用，必須先檢查 license；目前只採納概念、任務與驗收條件。

## 立即加入 MVP 的技術

| 來源 | 可採納技術 | Argus 落地位置 | 驗收方式 |
|---|---|---|---|
| Scrapling | 併發爬取、每網域節流、timeout/retry、blocked request detection、pause/resume checkpoint、streaming results、development cache replay | T3 Playwright 爬蟲、Celery 任務、ScanJob 狀態欄位 | 可限制 same-origin/depth/pages/RPS；失敗可重試；任務可從 checkpoint 恢復；測試可用快取重放 |
| GEOFlow | 任務佇列化、失敗記錄、任務篩選、模型 provider fallback、後台快速開始/狀態儀表板 | T1/T7/T9/T13 | Celery 任務狀態可追蹤；Admin 看得到 queued/running/failed/completed；provider 失敗可 fallback |
| aeo-site / Optimeyes | 0-100 AEO/GEO 分數、分類 breakdown、優先級建議、即時分析感、可視化儀表 | T4/T6/T8/T10 | 每次掃描產出總分、分類分數、severity 統計與前 5 個優先處理項 |
| awesome-geo | FAST framework、`llms.txt` 檢查、AI crawler robots 規則、Schema/semantic HTML/SSR 可讀性 | T4 GEO/AEO 掃描 | Finding 包含 fetchable/accessible/structured/trim 維度；檢查 `llms.txt`、robots AI crawler、Schema |
| RTK | 大型命令輸出壓縮、agent 工作規則整合 | 開發流程、AGENTS.md | 預期輸出超過 50 行的 test/build/git/log 命令使用 RTK |

## 延後到 Phase 2 的技術

| 來源 | 可採納技術 | Argus 落地位置 | 延後理由 |
|---|---|---|---|
| GEOFlow | RAG/知識庫切片、embedding、素材庫與提示詞庫 | Phase 2 Agent 分析與報告生成輔助 | MVP 不需要生成大量內容；可先只保存掃描證據與 prompt template |
| Optimeyes | keyword tracking、competitor analysis、API integration、multi-language support | Phase 2/Phase 3 | 需要先有穩定掃描與歷史資料 |
| awesome-geo | AI citation/brand mention monitoring、AI search platform tracking | Phase 2/Phase 3 | 需要外部搜尋或第三方平台整合，先不進 MVP |
| GEOFlow | 多站點/多欄目內容分發、審核發布流程 | Phase 3 | Argus 是健檢平台，不是內容發布 CMS |

## 明確不採納

| 來源 | 不採納項目 | 原因 |
|---|---|---|
| Scrapling | 指紋偽裝、瀏覽器指紋操控、反封鎖繞過、代理池規避 | 與 Argus 授權式、robots-respecting、合規健檢定位衝突 |
| GEOFlow | PHP/Laravel/Blade 技術棧 | Argus 已固定 Django/React |
| aeo-site | Express/Drizzle 技術棧 | Argus 已固定 Django/DRF/PostgreSQL |
| Optimeyes | 行銷式「SEO 已死」文案 | Argus 需要技術中立、可信、可驗證的專業報告語氣 |
| 任何來源 | 自動產生修復後程式碼 | Argus 只輸出問題描述、證據、修補方向與 AI handoff prompt |

## 掃描引擎新增設計

### Crawler Reliability Layer

採納 Scrapling 的可靠性概念，但用 Playwright + Celery 實作：

- per-origin rate limiter：預設 same-origin、RPS 依模式限制，Active ≤ 2。
- bounded concurrency：每個 ScanJob 與每個 origin 都有上限，避免壓垮目標站。
- retry policy：只重試 timeout、5xx、暫時性網路錯誤；4xx 不盲目重試。
- checkpoint：儲存 queue frontier、visited URLs、depth、page count，worker 中斷後可恢復。
- blocked detection：標記 403/429/CAPTCHA/login wall，不繞過，只回報 finding 或 scan warning。
- cache replay：開發與測試時可用已保存 HTML/DOM/screenshot 重放，避免反覆打目標站。

### AEO/GEO Scoring Layer

採納 aeo-site、Optimeyes、awesome-geo 的分數與 checklist 概念：

- `overall_score`：0-100。
- `category_scores`：SEO、AEO、GEO、Security、UX。
- `priority_score`：依 severity、影響範圍、頁面重要性、修復難度排序。
- `top_actions`：最多 5 個優先處理方向，不提供修復程式碼。
- `geo_fast_scores`：Fetchable、Accessible、Structured、Trim。

### GEO Technical Checks

新增 GEO/AEO 檢查項：

- `llms.txt` 是否存在、可讀、內容是否描述站點與重要頁面。
- `robots.txt` 是否允許或阻擋主要 AI crawler；只做診斷，不建議使用者違反自身策略。
- HTML-only 可讀性：核心內容是否在初始 HTML 可取得。
- Schema coverage：Organization、Article、FAQPage、HowTo、Product、BreadcrumbList 視頁型判定。
- chunkability：段落是否短、可獨立引用、標題層級是否清楚。
- entity clarity：品牌、產品、作者、日期、來源是否明確。
- evidence quality：是否有可驗證事實、數據、引用來源。

## 報告與 UX 新增設計

- 報告摘要加入 AEO/GEO score gauge、分類 breakdown、severity histogram。
- Finding 詳情加入「為什麼影響 AI answer visibility」。
- 互動工作區側欄新增「優先處理」排序。
- Word 報告加入「Top Actions」與「GEO FAST 檢查摘要」。
- 後台加入掃描 health：平均耗時、失敗率、blocked rate、重試次數、Celery queue 長度。

## 資料模型增補建議

日後實作 Django models 時，除既有表外可加入：

- `ScanJob.overall_score`
- `ScanJob.category_scores`
- `ScanJob.top_actions`
- `ScanJob.crawl_checkpoint`
- `ScanJob.warning_summary`
- `Page.fetch_mode`
- `Page.blocked_reason`
- `Page.html_only_text`
- `Finding.priority_score`
- `Finding.impact_area`
- `Finding.confidence`

實際欄位型別在 T2 實作時依 Django model 設計決定。
