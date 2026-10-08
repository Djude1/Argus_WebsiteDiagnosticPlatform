# Argus 掃描系統升級強化 Roadmap

> 這是掃描核心（爬取 + 12 個維度/階段）的**全系統升級總表**，對照 2026-10-07 的
> `backend/apps/scans/` 實際程式撰寫。它是「方向與投報比」層級的規劃；**單一項目要動手前，
> 必須先逐行讀該 scanner 內部、把下方標記 `【待驗證】` 的假設確認掉，再開細部規格。**
>
> 智慧動態掃描是本表「跨領域工程化」的旗艦項目，已獨立開出細部實作計劃：
> [`docs/adr/0004-smart-dynamic-scan.md`](adr/0004-smart-dynamic-scan.md)。本表其餘項目尚未開 ADR。

## 總體評估

Argus 掃描架構已達商用雛形：`tasks.py` 以 `ScanRunContext` + 20+ 個 `stage_*` 串成管線，
階段與計費/取消/退款收斂乾淨；安全分「被動（`scanners.py`）／深度主動（`security/`）」兩層；
工具鏈 Nuclei + Katana + Kali(SQLmap) + 自建 scanner 齊備。**主要缺口不在「缺功能」，而在可信度與可驗證性**：
1. Finding 準確度與跨模組一致性不足，同一份 evidence 可能被 Security／SEO／AEO／UX 以不同方式解讀；
2. Finding 缺「可驗證性分級（confidence）」、完整 evidence 與限制條件；
3. 各維度評分偏規則加總，缺業界基準校準、Root Cause 關聯與可解釋性；
4. 外部權威資料源仍不足（目前以 GSC 為主），且缺歷史趨勢 diff 與 coverage 透明度。

**原則：下一階段優先提升 Accuracy → Evidence → Confidence → Consistency → Root Cause，再擴充規則數量。**

---

## 爬取（Crawler）

- **現況**：`crawler.py` Playwright BFS、robots/sitemap 補種子、深度 6、`/cdn-cgi/` 陷阱防護、
  CF 攔截頁精準判定、RPS 節流。紮實。
- **升級**：
  1. **有上限的 Render Readiness**：維持 `domcontentloaded`，再以短暫 hydration grace period、DOM/內容穩定度與可選 site-specific selector 判斷就緒；**不以 networkidle 作為必要條件**。必須有總時間上限，逾時仍保留已取得 DOM/截圖並標示 `LIMITED: render_readiness_timeout`。（**已實作 2026-10-08**：`crawler.wait_for_render_ready`，DOM 穩定度（正文字數＋元素數，每 250ms、至少 0.5 秒、容許輪播的小幅變動），上限 `ARGUS_RENDER_READY_MAX_SECONDS`＝5；逾時照樣擷取，記在爬取預算與 `crawl` 覆蓋說明，不改覆蓋狀態。等待時間不計入頁面載入時間。沙箱實測 9 個網站就緒約 0.5 秒、就緒後 3 秒正文沒有增加，nextjs.org 在等待期間正文由 3880 增為 4197 字。site-specific selector 未做：沒有需要的網站實例）
  2. 爬取預算可觀測（種子來源、每頁耗時、被節流次數、render readiness 結果寫進 coverage/progress）。（**已實作 2026-10-08**：`crawler._CrawlState.budget_summary` → `warning_summary.crawl_budget`：結束原因（達頁數上限／沒有更多頁面／瀏覽器異常）、種子來源、略過原因與數量、速率限制等待、每頁平均與最慢 3 頁；掃描 log 一行說明、後台掃描詳情顯示。render readiness 要等第 1 項實作後才有。同次發現並修正佇列重複排入同一網址佔掉頁數上限的問題）
  3. **Near-duplicate 只做 Analysis Reuse，不做 URL Skip**：SimHash / hreflang 僅可重用文字結構、部分 AEO/GEO 等高成本內容分析；每個 URL 仍必須各自做 headers、canonical/noindex、表單、權限、安全與 URL-specific 檢查。（**評估後暫緩 2026-10-07**：實測逐頁五維規則分析一頁約 70–150 ms（1.1 MB 的大頁約 1.3 s），50 頁合計約 5–10 秒，遠小於爬取本身的數分鐘；重用最多省幾秒，卻有把逐頁問題錯誤複製的風險。等分析改用 LLM 等高成本方法時再做）
  4. 所有重用必須記錄 `analysis_reused_from`、重用規則與未重用檢查，不能讓 dedupe 犧牲 coverage。

## 1. SEO

- **現況**：`scanners.py` 逐頁 title/meta/H1/alt/canonical/OG；`seo/` 有 `link_check`、
  `page_audit`、`site_findings`、`gsc`、`keywords`。GSC 已接。
- **升級**：
  1. 接 **PageSpeed Insights API（CrUX 真實場域資料）**：LCP/INP/CLS 實驗室 vs 真實使用者並列——目前最缺的權威外部訊號。（**已實作 2026-10-07**，見優先序第 6 項：`pagespeed.py`）
  2. 結構化資料驗證（JSON-LD 語法 + Google Rich Results 必填欄位，可離線）。（**已實作 2026-10-07**：語法由 AEO `aeo-markup-syntax` 回報；必填欄位 `seo/structured_data.py`，依 Google Search Central 2026-09 版，涵蓋產品（含 Offer／AggregateOffer）、軟體、職缺、食譜、影片、導覽路徑（含 ListItem）、活動（含地點）、在地商家、評論與評分彙總，缺必填 → `seo-structured-data-required`（低）；商家／組織自評星等 → `seo-structured-data-self-serving-reviews`（資訊）。FAQPage／HowTo 已不在 Google 支援清單、Article／Organization 無必填，不檢查；不檢查建議欄位與值的正確性）
  3. robots/sitemap 一致性交叉檢查（sitemap 列出卻 noindex、canonical 指他頁等矛盾）。（**已實作 2026-10-07**：原本 `site_checks` 只檢查 robots.txt／sitemap 是否存在、`seo-primary-url-inconsistent` 只比主機，沒有交叉檢查。`seo/site_findings.index_signal_conflicts` → `seo-index-signals-conflict`（低）：sitemap 列出 noindex／canonical 指他頁／回應錯誤／轉址／robots.txt 禁止 Googlebot 的網址，以及 noindex 頁被 robots.txt 擋住；只比對本次爬到的頁面與讀到的 sitemap 網址（最多頁數上限個）。實測 wordpress.org、docs.djangoproject.com、smashingmagazine.com 都抓到真實矛盾並逐筆核對屬實）
  4. 目標關鍵字 vs GSC 實際曝光關鍵字的落差分析。（**已實作 2026-10-07**：前端 `features/projects/seoKeywordGap.ts`，用 SEO 分頁已有的 `keyword_report` 與 `gsc/performance` 查詢字詞（前 200 個）計算，不新增 API：每個目標關鍵字彙總包含它的搜尋詞曝光／點擊、最佳平均排名分段（第 1 頁／第 2 頁／更後面／沒有曝光）、Google 帶到的頁面與內容最相關頁面不同時提示；另列有曝光但不是目標的搜尋詞，可一鍵設為目標。字面包含比對、不斷詞；尚未用真實 Search Console 帳號驗證）

## 2. AEO（問答檢測）

- **現況**：`aeo/evaluate.py` 四層判定（可回答/資訊不足/內容衝突/無答案），框架完整，已有答案蘊含判定（`aeo/answers.py` 的 `entails()`）與日期衝突判定（2026-10-06 第二輪準確度修正）；實測曾出現「語意相關段落被誤判為真正答案」與跨模組 evidence 不一致，已知案例已修正，但**缺少量測基準**，無法知道整體誤判率。
- **升級**：
  1. **Answer Entailment 量測與強化（P0）**：`entails()` 初版已上線，候選段落須通過蘊含判定才算答案。下一步不是重做，而是用 gold dataset（見優先序 P0-C）量測誤判率，再依誤判類型強化。（**已實作 2026-10-07**，見優先序 P0-C：`aeo/gold_dataset.py`、`manage.py aeo_benchmark`）
  2. **Specificity / Conflict Check（P0）**：衝突判定目前**只判日期**；擴充到價格、資格、聯絡方式等需具體可核對的欄位，多頁內容互斥時標記 conflict。（**已實作 2026-10-08**：`aeo/answers._value_conflict` 涵蓋價格、營業時間、客服專線，同一標籤在兩個以上頁面的值不同才算；先在回歸資料集加 6 個調整案例（3 衝突＋3 不是衝突）與 4 個保留集案例再寫規則。量測：全體 accuracy 0.971、precision 1.0、recall 0.974、FPR 0；保留集 19／21（兩題是沒出題，衝突 3／3 全對，不是衝突的案例沒有判成衝突）。資格條件不做：條件文字差異多半是不同方案，字面比對無法可靠判斷）
  3. **Cross-module evidence reuse（P0）**：Email、電話、地址、日期等與 Security／SEO 共用 evidence，避免一個模組「找到」、另一個模組「找不到」。（**Email／電話已實作 2026-10-07**，見優先序 P0-B：`evidence/contacts.py`。**地址已實作 2026-10-08**：AEO 地址題與結構化資料（JSON-LD `address`）共用同一份擷取，位置多一種「結構化資料」；頁面文字寫出結構化資料的街道就判可回答，地址只在 JSON-LD 時判定不變、理由說明搜尋引擎讀得到但訪客看不到。真實網站 yamatoya.com.tw 首頁就是只有 JSON-LD 地址。**日期不共用**：AEO 的日期是正文中的截止日、活動日，GEO 的日期是文章發布／更新標記，描述的是不同的事，不會互相矛盾）
  4. **Answer confidence（P1）**：輸出 Confirmed／Likely／Possible，並保留引用來源與限制。（**已實作 2026-10-08**：`aeo/answers.QuestionResult.confidence`，確認＝格式化答案值逐字出現在原文、可能＝步驟／條件或網站自己的問題、推測＝介紹類只確認有具體敘述；附 `limitation` 說明判定限制，顯示在 AEO 分頁與報告附錄，不影響計分。`aeo_benchmark` 輸出各等級 precision：目前資料集三個等級都是 100%（全體 precision 已是 1.0），還無法量出等級之間的差異，需要更多「看起來像答案」的案例）
  5. 問題生成多樣化（標題/H2 + 同業常見問句模板）。（**已實作 2026-10-08**：同業常見問句新增付款方式與預約／訂位兩個意圖（`aeo/questions.py`），先在回歸資料集加 5 個調整案例與 4 個保留集案例並標註再寫規則：保留集 4／4 一次判對，全體 accuracy 0.971→0.975、precision 1.0、recall 0.974→0.977。真實網站核對後修正：選單連結文字不觸發也不當答案（ntub.edu.tw）、英文付款方式（inline.app）、平台名稱 EZTABLE 不算預約管道。不做「標題／H2 自動造題」：該小標題下的段落本身就是答案，幾乎必判可回答，只會灌高分數；網站自己以問號結尾的小標題原本就會出題）
  6. 引用可得性評分。（**已實作 2026-10-08**：`aeo/evaluate._citation`，可回答的題目逐題標示能否被搜尋引擎與 AI 引用——頁面 noindex、禁止摘要（nosnippet、max-snippet:0，含 `X-Robots-Tag`）或答案段落在 data-nosnippet 區塊內＝無法被引用；答案只在執行 JavaScript 後才出現＝引用受限；另算可被引用比例 `aeo_report.citation.citable_ratio`。只是指標，不改 AEO 分數、不另列問題（這些頁面設定本身已由 `page_checks.py` 逐頁列出並扣分）。真實網站核對見 log）
  7. `llms.txt`／`llms-full.txt` 僅列為 **Emerging / Experimental** 訊號，不與成熟 SEO 規則等價扣分。（**已驗證 2026-10-08**：`scanners.analyze_site_signals` 的「網站未提供 llms.txt」是 info，計分權重 0、不進優先改善建議，描述與報告依據都寫明是新興做法；由 `tests_accuracy_review.py` 鎖定嚴重度與不扣分。`llms-full.txt` 不檢查）


## 3. GEO（生成式引擎優化）

- **現況**：`analyze_geo` / `analyze_geo_fast`（文字區塊數、可見文字長度）。偏輕量。
- **升級**：
  1. 實體與權威訊號（作者、組織、`sameAs` → Wikidata/社群）——E-E-A-T。（**已實作 2026-10-08**：`apps/scans/geo_entity.py`，組織實體缺少（低）、組織沒有 sameAs（資訊）、文章頁沒有作者（低）。真實網站核對：blog.cloudflare.com 只有 WebSite 標記（缺組織）、wordpress.org 與 css-tricks 的組織 sameAs 正確辨識；WordPress 分類頁與 Smashing Magazine 列表頁標了 og:type=article，改以 CollectionPage／`<article>` 區塊數排除，避免誤判成缺作者的文章）
  2. 內容新鮮度（`dateModified`/`datePublished` 與實際更新落差）。（**已實作 2026-10-08**：`geo_entity.freshness_findings`，文章頁缺日期、日期不合理（更新早於發布、未來日期）、JSON-LD 與 article:*_time meta 不一致，各為低風險。只檢查日期標記本身，不判斷內容「舊不舊」（長青內容不需常更新）；也不比對 HTTP Last-Modified——動態網站每次回應都是當下時間，比對沒有意義。真實網站核對 css-tricks、blog.gslin.org 的兩邊日期一致，沒有誤報）
  3. 可被 AI 摘要性（段落結構、清單化、摘要句位置）——與 AEO 共用訊號但角度不同。（**已實作 2026-10-08**：`apps/scans/geo_structure.py`，段落過長／可引用區塊偏少／缺 main 原本已有；新增長篇內容沒有小標題（低）、列舉寫成一整段（資訊）。「摘要句位置」屬寫作品質，規則無法可靠判定，不做。真實網站核對：ntubimdbirc.tw/about 的「1.技術研究…2.辦理…3.業務…」與 ntub.edu.tw 無障礙說明頁「1) 上方導覽…4) 主要內容區」正確列出；修正四種誤判：RSS 被當網頁、部落格標題在 `<header>` 裡被漏數、入口網站短連結被當長文、CSS 程式碼被當編號）

## 4. UX

- **現況**：`crawler.py` 的 `collect_ux_signals`/`collect_mobile_layout`/`collect_element_boxes`，
  `scanners.py` 行動版溢出/觸控目標/未標籤欄位/JS 錯誤，截圖已精準框選。
- **升級**：
  1. **接 axe-core（Playwright 注入）**：目前 a11y 是自建規則，接開源業界標準可一舉覆蓋 WCAG 2.2 數十條。**UX 維度投報率最高**。（**已實作 2026-10-07**，見優先序第 5 項：`accessibility.py`）
  2. **接 Lighthouse（programmatic）**：Performance/Accessibility/Best-Practices/SEO 四分數與自建並列。（**已實作 2026-10-07，經由 PageSpeed Insights 取得**，見優先序第 6 項；未在 worker 內另跑 Lighthouse）
  3. CLS 元素級歸因（哪個元素造成位移）。（**已實作 2026-10-08**：爬蟲逐頁讀瀏覽器 layout-shift 紀錄（`crawler.collect_layout_shift`），依 Google CLS 定義計算並列出位移的元素與移動距離，CLS >0.1 → `ux-layout-shift`（低，>0.25 中）；不需要 PSI 金鑰、每頁都量。排除爬蟲捲到底後跳回頂端造成的位移。列出的是「被推動」的元素，真正原因通常在它上方較晚載入的內容；另提示沒有標寬高的圖片／影片／iframe 數量。限制：桌面視窗單次量測，沙箱實測 udn 首頁兩次 0.851 與 0.025，網路慢時樣式表晚到也會量到；Lighthouse 的 layout-shifts 稽核（根因）需 PSI 金鑰，未接）

## 5. 被動資安（Passive Security）

- **現況**：HTTPS/header/CSRF/PII、SSL/Cookie/CORS/CSP/SRI/DNS、JS 套件 CVE、服務 CVE 等規則已具備，OWASP/CWE 對映齊全，NVD 離線庫已接。
- **升級**：
  1. **校準既有 `Finding.confidence` 的語義與使用方式**：欄位、`make_finding()` 與 serializer 已存在；缺口是規則如何產生 confidence、如何影響 score/report，以及如何區分「配置建議」「曝露面」「疑似弱點」「已驗證弱點」。既有資料的預設 `1.0` 一律視為 **legacy / uncalibrated**，不得回溯解讀為 Confirmed。（**第一階段已實作 2026-10-08：只標示**。`security/finding_kind.py` 依規則與來源（不看 confidence）把資安發現分成設定建議／曝露面／疑似弱點／已驗證弱點：安全標頭、Cookie、DNS、TLS、SRI、ZAP 被動告警＝設定建議；版本號、技術標頭、管理入口、公開聯絡資料、低風險探測檔案＝曝露面；依版本比對的 CVE、秘鑰樣式、Nuclei 樣板命中、AI 觀察、可能缺 CSRF token、CORS 帶憑證＝疑似弱點；sqlmap 確認注入、真的下載到高風險檔案＝已驗證弱點；掃描說明（例如 WAF 之後 0 項發現）不分類。顯示時推得、不寫 DB、舊掃描也有；呈現在問題分析表、掃描詳情的判定證據與報告每項的追蹤列。**不影響分數與排序**；confidence 的產生方式與影響扣分仍待後續）
  2. Security headers 評分接 **Mozilla Observatory 規則**（可離線實作，給 A~F 等第）。（**已實作 2026-10-07**：`security/observatory.py`，獨立呈現在網站架構與報告，不併入 Argus 分數）
  3. CVE 資料源補 **OSV.dev + EPSS**，讓漏洞優先序不只看 CVSS。（**已實作 2026-10-07**：`security/vuln_intel.py`，EPSS 影響排序與說明、OSV 提供前端函式庫修補版本，不改嚴重度）

## 6. 主動探測（Active Probing）

- **現況**：Nuclei + Katana + Kali(SQLmap) + 敏感檔案探測（`security/exposure_scanner.py`；`scan_plan.py` 的 `run_exposure` 只在主動模式＋已授權＋整站時開啟）+ 自建 probe，可在授權閘門後做主動檢測。
- **升級**：
  1. **Nuclei 模板治理**：鎖版本與模板雜湊、記錄實際使用模板集、排除高噪音模板，結果可重現。（**已實作 2026-10-08**：模板 v10.4.9 鎖在 image 並以 templates-checksum.txt 逐一驗證；固定只跑 KEV 模板集（511 個、628 個請求）且只掃網站根網址——實測原本的全部模板對單一網址 9535 個請求，1–2 RPS 下要 80 分鐘，正式 300 秒逾時後回傳 0 項卻記為完成；原快速模式標籤寫錯只選到 3 個模板。每次記錄引擎／模板版本與模板集指紋（`warning_summary.nuclei`）；逾時保留部分結果並標 partial，缺模板或異常結束標 failed。高噪音模板清單 `EXCLUDED_TEMPLATE_IDS` 目前為空，尚無真實誤報資料。見 scans CLAUDE.md「Nuclei 模板治理」）
  2. **SQLMap 專項化**：保留為 SQL Injection 深查工具，不把它當通用 Web DAST。
  3. 主動探測補「掃描來源 IP 宣告」供目標端白名單，並維持 `AuthorizationConsent` + 網域驗證雙閘門。（**已實作 2026-10-08**：公開頁 `/scanner`「掃描來源說明」＋`GET /api/content/scanner-info/`，User-Agent、robots 比對名稱、出口 IP（`ARGUS_SCANNER_EGRESS_IPS`，逗號分隔 IP／CIDR，格式錯誤由 `scans.E003` 擋下；未設定時請對方以 User-Agent 辨識）與被動／主動速率都取自實際設定。說明 robots.txt 只影響網頁走訪、如何以 WAF 封鎖或放行；網域驗證頁與主動測試設定處連到這頁。同次修正 Docker 版 sqlmap 沒帶統一 User-Agent（K8s runner 原本就有）。正式環境出口 IP 尚未設定；User-Agent 仍是舊名稱 `SiteSense-AI-Scanner`，使用者決定不改。雙閘門不變）
  4. 所有主動 stage 必須有 request budget、timeout、RPS 上限與 BLOCKED/LIMITED 狀態，避免 WAF 攔截被誤解為 0 findings。
  5. 敏感檔案探測字典對齊 **SecLists**，每個命中做內容型別確認；`exposure_scanner` 已有 soft-404 基準比對，擴字典時要一併驗證誤報率。

## 7. 深度 Web Security / DAST

- **新增 OWASP ZAP（P1）**：作為 Argus 深度 Web Application DAST 引擎，補足 Nuclei/SQLMap 無法完整覆蓋的
  session-aware、parameter-based、browser-oriented 掃描能力。
- 建議接入能力與邊界：
  1. **ZAP Passive Analysis**：只分析 Argus 已取得或代理流經的 HTTP message，不主動產生新的目標請求。
  2. **Traditional Spider / AJAX Spider 屬 Discovery Traffic，不是純被動**：只可在 Authorized Scope 內執行，需限制 exact-origin/已授權 host、redirect boundary、排除路徑、request budget、RPS、timeout；預設禁止提交表單、logout、delete、purchase、password reset、upload submit 等狀態改變操作。
  3. **ZAP Active Scan**：只在已驗證網域 + 明確主動授權下執行，且只啟用 Argus 核准 policy。
  4. **取消契約**：使用者取消或 scan 中止時，必須停止 ZAP spider / active scanner / subprocess 或 container，並確認不再產生新的網路流量；coverage 記為 CANCELLED/PARTIAL。
  5. Authenticated Context：後續支援測試帳號 / session context 時再開啟，不把登入失敗當成「已測」。
  6. ZAP alert 先正規化進 Shared Evidence Store，再由 Argus 做 confidence、severity、去重與 Root Cause；**不要直接照搬 ZAP risk 等級到最終報告**。
  - 進度（2026-10-07）：第 1 項 Passive Analysis 已實作（HAR 匯入，見 [`zap-passive.md`](zap-passive.md)）；第 2–5 項尚未開始。
- 工具定位：
  - Nuclei = template / known-pattern detection
  - SQLMap = SQL Injection 專項驗證
  - ZAP = Web Application DAST / session-aware deep scan
  - Argus = orchestration + evidence normalization + confidence + root cause + report

## 8. API / CMS / Auth 專項安全

- **方向**：與 Smart Dynamic Scan 共用 fingerprint / risk surface，只有高信心命中時才追加深查。
- API：OpenAPI/Swagger、CORS、錯誤堆疊、未登入資料曝露；公開 API 本身不等於漏洞。
- Auth/Session：Cookie、CSRF、登入流程、session 保護與可驗證帳號列舉跡象。
- CMS：WordPress/Drupal/Joomla 的版本、外掛/佈景、已知 CVE 與 attack surface；「存在」不等於 vulnerability。

## 9. Vulnerability Validation / VAPT Workflow

- **VAPT 不作為單一 scanner 或 stage 名稱**。它是 Argus 資安層的工作流與產品方法論：
  ```
  Discovery
    ↓
  Vulnerability Assessment
    ↓
  Authorized Active Validation
    ↓
  Evidence + Confidence
    ↓
  Exploitability / Risk Prioritization
    ↓
  Remediation
    ↓
  Retest / Verification
  ```
- Argus 現階段對外定位應採：
  **VAPT-oriented automated security assessment** /
  **Automated Vulnerability Assessment with authorized active testing**。
- **暫不宣稱完整 Penetration Testing**：完整 PT 通常還包含人工商業邏輯測試、多步漏洞鏈、權限提升、
  authenticated attack paths 與人工驗證；這些不是目前自動掃描可完整覆蓋的能力。
- 報告需清楚區分：Detected / Suspected / Confirmed / Not Tested / Blocked，並附 evidence 與 coverage。


## 10. AI 爬蟲（可供 AI 抓取性）

- **現況**：llms.txt 成熟度檢查、FAQ 結構偵測。
- **升級**：
  1. AI bot robots 政策分析（`GPTBot`/`ClaudeBot`/`Google-Extended`/`PerplexityBot` 允許或封鎖，說明商業取捨）。（**已實作 2026-10-07**：`apps/scans/ai_bots.py`，13 個 bot 依訓練／AI 搜尋／使用者觸發分類；只封鎖訓練用爬蟲不再列為問題）
  2. 內容可機讀性（語意 HTML 比例、主內容可否與導覽/頁尾分離 `<main>`/`article`）。（**已驗證 2026-10-08，不新增規則**：既有檢查已涵蓋——缺 `<main>`（`scanners.analyze_geo` 的「缺少語意化主內容區塊」）、正文擷取排除 nav／header／aside／footer（`aeo/content.py`）、核心內容依賴 JavaScript、段落與小標題結構（`geo_structure.py`）。曾評估新增「多個可見 `<main>`」與「`<main>` 只包含少部分正文（<30%）」：實測 8 個網站約 40 頁（ntubimdbirc、ntub、wordpress.org、blog.gslin、cna、setn、law.moj、docs.djangoproject）沒有任何頁面有多個 `<main>`；`<main>` 正文占比除 wordpress.org/showcase（0.31，正文僅約 67 詞）外都在 0.68 以上，沒有 `<main>` 的頁面（cna 首頁、law.moj）已由既有規則列出。新規則不會觸發，不做。「語意 HTML 比例」沒有公認門檻，不做）

## 11. 連結檢查

- **現況**：`seo/collect.py` 已以 URL 去重跨頁重複連結，`check_links()` 已用 `ThreadPoolExecutor` 並發，並具備站內/子網域/站外分類、跳轉鏈、狀態、robots、難懂錨文字與時間/數量上限。
- **升級**：
  1. 不重做既有 scan-level 去重與並發；改補 **freshness / cache reuse**，避免同一掃描流程內其他 stage 重複查相同外部 URL。（**已實作 2026-10-08**：同一次掃描內重複請求集中在 SEO 連結檢查——robots.txt 爬蟲讀過又重抓、頁面連到的 sitemap／llms.txt 與站台檢查的 sitemap 等網址重查。爬蟲在 `site_signals.fetched` 記下已取得檔案的 HTTP 狀態（robots.txt、llms.txt、sitemap；兩邊都不跟隨轉址，語意相同），`seo/collect.build_link_report` 沿用：robots.txt 以爬蟲原文解析、連結檢查不再送出、站台檢查先查已有結果（含連結檢查查過的網址）；轉址的不沿用（要跟跳轉鏈）。沿用數記在 `seo_report.reused` 並寫進掃描 log。其他外部查詢原本就有快取或不重複：EPSS／OSV 快取 1 天、PageSpeed 每次掃描只呼叫一次。跨掃描不沿用：每次掃描要反映網站當下狀態）
  2. 連結 coverage 明確區分 checked / restricted / timeout / skipped / budget_exhausted，歷史比較只能在 coverage 足夠時判定 resolved。（**已實作 2026-10-08**：`seo/link_trend.link_coverage`；逾時從「無法連線」分出成 `timeout`，未檢查分成超過數量上限與時間用完，存 `seo_report.coverage`，`seo_links` 覆蓋紀錄說明列出沒有明確結果的連結數，SEO 分析頁連結分頁顯示）
  3. 連結健康度趨勢標記「新壞掉／持續失效／已確認恢復／本次無法確認」。（**已實作 2026-10-08**：`seo/link_trend.link_trend`，和同專案上一次有連結檢查的完成掃描比較；只有這次真的檢查過且正常才算恢復，沒檢查、逾時、被拒或這次頁面上找不到一律「本次無法確認」；併入爬蟲已造訪頁面的 HTTP 狀態。標記顯示在 SEO 分析頁連結列與「站內連結失效」問題的描述與證據。只比對上一次掃描，不追溯更早的歷史）
  4. 錨文字品質延伸（「點這裡」「更多」等無意義文字，SEO + 無障礙雙重影響）。（**已具備，2026-10-08 核對**：`seo/page_audit.GENERIC_ANCHORS`（點此、這裡、更多、了解更多、read more、click here 等）與空錨文字由 `seo/report.py` 列在 SEO 分析頁的連結問題（空錨文字為警告、無意義文字為提示）；沒有可讀名稱的連結另由 axe-core `link-name`（WCAG）列為無障礙問題。「連結目的是否清楚」屬 WCAG 2.4.4，需看上下文，不再以字面規則擴充）

## 12. 評分

- **現況**：`calculate_scores` + `base_scores_for` + `_dedupe_findings_for_scoring` 依 finding 嚴重度加權；專案層已有前次分數、new/persisting/本次未出現與趨勢資料，但目前比較主要依「本次有勾該 category」，尚未感知 rule/URL coverage。
- **升級（整體最關鍵）**：
  1. **Coverage-aware scoring**：FAILED / BLOCKED / LIMITED / NOT_TESTED 的規則或資源不得被視為「0 問題」而拉高分數。分數需附有效 coverage，coverage 低於門檻時顯示「資料不足／部分評估」，而非假精準高分。（**已實作 2026-10-07**，見優先序 P0-A：`coverage.py`）
  2. **歷史狀態語義重做**：`finding absent` 先標 `NOT_OBSERVED`；只有同 rule、相容 resource/context、偵測能力已完整執行且 coverage 足夠時，才能升級成 `RESOLVED`。建議生命週期：`NEW / PERSISTING / RESOLVED / NOT_OBSERVED / NOT_TESTED / BLOCKED / INCONCLUSIVE`。（**已實作 2026-10-07**，見優先序 P0-A：`coverage.absent_issue_status`）
  3. **評分可解釋化**：每個維度列出扣分來源、coverage、confidence 與未測範圍。（**已實作 2026-10-07**：扣分來源、coverage、未完整完成的檢查；confidence 目前不影響扣分，待第 6 項校準後再列）
  4. **外部指標保持獨立，不做錯誤「對齊總分」**：Lighthouse、CrUX、axe、Observatory 各自呈現；只在同 URL/裝置/期間/構面可直接對應的子指標做 validation。（**現況已符合**：PageSpeed、axe、Observatory 各自呈現、不併入 Argus 分數）
  5. **保存 `scoring_version` / `ruleset_version`**：規則或權重版本變更時，歷史圖必須標示模型版本；跨版本不得直接把 score delta 解讀成網站改善。（**已實作 2026-10-07**，見優先序第 4 項：`versions.py`）
  6. **confidence 使用既有欄位但需重新校準**：低 confidence 可影響排序/扣分，但 legacy `confidence=1.0` 不得等同 Confirmed。（**第一階段已實作 2026-10-08**：資安發現類型標示，見 §5 第 1 項；尚未影響排序或扣分）

---

## 跨領域工程化

| 項目 | 現況 | 升級 |
|---|---|---|
| **Coverage Contract（P0-A）** | category 是否有勾是主要比較條件 | 定義 stage/rule/resource coverage：COMPLETED／PARTIAL／FAILED／BLOCKED／SKIPPED／NOT_APPLICABLE；直接約束 scoring、history diff 與「resolved」判定 |
| **Shared Evidence MVP（P0-B）** | 各 scanner 各自產 finding | 先只接 AEO + Security 共用的 email/phone evidence；驗證跨模組矛盾改善後再擴大，不先做 Universal Evidence Platform |
| **Evidence Context Contract** | evidence 缺統一情境 | 最小欄位：source_url、observed_at、acquisition_method、viewport、auth/session context、initial_html/rendered_dom/network、source/tool version、artifact ref、limitations、missing_reason、redaction_state；不同 context 不強制一致 |
| **Evidence Governance** | — | 敏感資料遮罩、cookie/token 永不落 evidence、raw artifact 大小上限、保留期限與刪除策略 |
| **Root Cause Correlation（P1）** | finding 去重為主 | 聚合成 Root Cause → Related Findings → Evidence → Fix（**第一階段已實作 2026-10-08**：`apps/scans/root_causes.py`，只收修法確實在同一處的規則——伺服器回應標頭、Cookie 屬性、TLS、SPF／DMARC、圖片替代文字（SEO 與 axe-core）、文章作者與日期標記；同一原因有 2 個以上問題才成組。問題分析 API 回 `root_causes` 並在問題標 `root_cause`，前端「依根本原因」顯示模式寫明在哪裡修。只是呈現，不改嚴重度、計分與歷史比較；PDF 報告摘要「改一處就能一起解決」同一套歸類（2026-10-08，資訊提示不列）。示範專案三次掃描分別歸出回應標頭 5／4／2 項與 SPF／DMARC 2 項） |
| **Stage Result（P0-A）** | scanner 失敗可被隱藏 | 狀態必須流入 coverage/scoring/history/billing；禁止把工具失敗呈現成「0 findings」 |
| **智慧動態掃描（旗艦）** | 固定管線 | Signal Collection → Fingerprint → Dynamic Planner；見 [ADR-0004](adr/0004-smart-dynamic-scan.md) |
| 外部工具統一介面 | Nuclei/Katana 走 `process_runner`，各自 parse | 抽象 `ExternalTool` protocol（執行/逾時/取消/版本鎖/結果正規化），axe/Lighthouse/ZAP 照契約接 |
| Finding schema | `make_finding` 與既有 `confidence` 已存在 | 標準化 confidence semantics，新增/整理 `maturity`、`evidence[]`、`limitations[]`、`source_tool`、`tool_version`、`root_cause_id`、`verification_status`；legacy confidence 不回溯解讀 |
| 結果可重現 | — | 記錄工具版本、模板雜湊、`scoring_version`、`ruleset_version`，寫進報告/掃描 metadata |
| 掃描設定檔化 | 五維 + 主動/被動 | 依 ADR-0004 新增 `scan_strategy`（standard／smart），與既有 `scan_mode`（testing level）分開；計費按實跑項目並與 ADR-0004 共用 Billing Matrix |
| 效能 | 階段循序 | 無相依 scanner 可並發，但 coverage、cancel 與 shared request budget 必須一致 |

---

## 建議導入優先序（可直接拆實作）

1. **P0-A Coverage Contract + 既有能力盤點**（**MVP 已實作 2026-10-07**：`apps/scans/coverage.py`、`ScanJob.coverage`（migration 0028）；
   檢查級狀態 completed／partial／failed／blocked／skipped、維度級 completed／partial／not_tested，約束計分、
   專案問題比較（resolved／not_observed／not_tested／blocked／inconclusive）與報告「已解決」。尚未做：rule／resource 級
   覆蓋細分、`scoring_version`、stage status 流入 billing）
   - 先定義 stage/rule/resource coverage 與 finding lifecycle。
   - 修正現況盤點：confidence、history diff、link 去重/並發皆是「已有但語義/coverage 不足」，不是全新功能。
   - 驗收：工具 BLOCKED/FAILED 時不加分；前次 finding 只有在相同偵測能力完整重跑時才可標 RESOLVED。

2. **P0-B 小範圍 Shared Evidence MVP（AEO + Security）**（**MVP 已實作 2026-10-07**：`apps/scans/evidence/contacts.py`；資安個資檢查與 AEO 聯絡題共用格式與擷取，AEO 以共用證據核對並說明情境差異；`tests_shared_evidence.py`）
   - 只先共享 email / phone，帶完整 context contract。
   - 驗收：已知「Security 找到 Email、AEO 說找不到」案例（第二輪已以 `aeo/content.py` 的 `_is_body_text` 修正）納入回歸測試並保持通過；Email／電話改由同一份 evidence 產生、不再各模組各自解析；不同 viewport/auth/DOM context 不被誤判成矛盾。

3. **P0-C AEO Answer Validation + Gold Dataset**（**已實作 2026-10-07**：`aeo/gold_dataset.py` 38 個網站、60 題人工標註
   （含 17 題保留集、13 題「語意相近但不是答案」），`manage.py aeo_benchmark` 輸出指標；門檻 accuracy／precision／recall ≥ 0.95、
   false positive rate ≤ 0.05，由 `tests_aeo_benchmark.py` 鎖定。首次量測：全體 accuracy 0.983、precision 1.0、recall 1.0、
   FPR 0；保留集 16／17（唯一不一致是內容太少時 AEO 不評估，屬設計行為）。平均每站 < 1 ms。尚未做：semantic／LLM 判定的成本比較）
   - 建立 50–100 組 answerable / insufficient / conflict / missing / semantic-near-but-not-answer regression case。
   - 驗收至少追蹤 precision、recall、false-positive rate、平均判定成本與耗時；門檻先在實作票/ADR 明定後再上線。

4. **P1 Coverage-aware scoring + comparable history**（**已實作 2026-10-07**：`scoring_version`／`ruleset_version`（`apps/scans/versions.py`、migration 0029），跨版本不顯示分數增減；coverage-aware 計分與 RESOLVED／NOT_OBSERVED／BLOCKED／INCONCLUSIVE 已於 P0-A 完成。評分可解釋化 **已實作 2026-10-07**：`scanners.score_breakdown()`（`calculate_scores` 的分類分數由它算出）＋`score_explain.py`＋`GET /api/scans/<id>/score-breakdown/`，掃描「分數說明」分頁逐維度列基準分、逐項扣分權重、出現處數、只修好該項時的分數、不扣分項目與未完整完成的檢查；舊公式算的分數標示不一致。PDF 報告內的逐項扣分 **已實作 2026-10-08**：附錄「各分類扣分明細」（`reports._report_score_items`，與分數說明分頁同一份 `score_explanation`，項次對應第 4 章，分數依目前公式加不回來時只說明原因）。尚未做：外部 benchmark、confidence 影響扣分）
   - 加 `scoring_version` / `ruleset_version`；歷史 diff 升級成 RESOLVED / NOT_OBSERVED / BLOCKED / INCONCLUSIVE。
   - 外部 benchmark 只驗證可對應子指標，不把 Argus 總分校準成 Lighthouse/CrUX。

5. **P1 axe-core（UX/無障礙）** — 接成熟規則，但同樣走 coverage/evidence 契約。（**已實作 2026-10-07**：`apps/scans/accessibility.py`＋`vendor/axe/`（axe-core 4.14.0，MPL-2.0），勾 UX 時爬蟲每頁注入；覆蓋檢查 `axe`；規則 `axe-<id>`）

6. **P1 Lighthouse + CrUX** — Lighthouse=Lab、CrUX=Field、GSC=Search impact，保留樣本/裝置/期間/URL-or-origin 範圍與缺資料原因。（**已實作 2026-10-07**：`apps/scans/pagespeed.py` 走 PageSpeed Insights API（行動版、只測首頁、需 `ARGUS_PAGESPEED_API_KEY`），結果存 `ScanJob.performance_report`，掃描「效能」分頁與報告並列呈現、不計入 Argus 分數；覆蓋檢查 `pagespeed`）

7. **P1 Smart Scan Phase 1（只記錄 signal/fingerprint）** — 先修正 stage dependency 與 strategy/testing matrix，再做真實站準確率 benchmark。（**已實作 2026-10-07**：`apps/scans/fingerprint.py`＋`stage_fingerprint`（緊接 `enter_scanning`，只吃爬取當下已有的訊號，沒有反向依賴後續 stage）、`ScanJob.fingerprint`（migration 0031）；資料集 28 站（含誤判誘餌與保留集）precision／recall 1.0、0 次連線。strategy／testing 二維語義已在 ADR-0004 定案，`scan_strategy` 欄位留待階段 2。尚未做：以真實掃描結果人工核對的準確率評估）

8. **P1/P2 OWASP ZAP controlled integration** — 先 Passive Analysis；Spider/AJAX Spider 視為 discovery traffic；最後才開受控 Active Scan。（**Passive Analysis 已實作 2026-10-07**：爬蟲錄同網站 HAR → 獨立 ZAP daemon 只跑被動規則，對目標零新增請求；告警正規化後才成為 Finding，與既有檢查重複者不列、ZAP risk 不直接照搬；預設關閉，compose profile `zap`／`k8s/optional/zap-passive.yaml`（未列入 kustomization），見 [`zap-passive.md`](zap-passive.md)。尚未做：正式叢集部署與資源量測、Spider／AJAX Spider、Active Scan）

9. **P2 OSV.dev + EPSS、Observatory、Analysis Reuse、AI bot 政策等**。（OSV.dev＋EPSS、Observatory 等第、AI bot 政策 **已實作 2026-10-07**，見 §5 第 2、3 項與 §10 第 1 項；Analysis Reuse 經量測後暫緩，見「爬取」第 3 項）

### 每一階段的共通驗收指標

- Accuracy：誤報/漏報或對應 regression dataset 指標。
- Coverage：rule/resource/stage 實際覆蓋率與 blocked/limited 比例。
- Cost：新增 request 數、耗時、CPU/記憶體與外部 API/LLM 成本。
- Safety：是否越過 Authorized Scope、是否可能產生狀態改變操作。
- Rollback：功能旗標或 schema 向後相容策略；未達門檻即可關閉而不影響基礎掃描。

---

## 落地共通紀律（每一項都適用）

- 遵守 Migration 鐵律（欄位一律新增）、`scans/CLAUDE.md` 的 scanner 回傳契約與狀態機規則、
  `docs/environment-preflight.md` 的掃描驗證閘門。
- 新 scanner：回傳 `list[dict]`（`make_finding` 格式）、不寫 `ScanJob.status`、不呼叫 billing。
  單一模組例外不得中斷整場掃描，但 orchestrator 必須記錄 stage status / error / coverage；
  **禁止 silent-fail 被呈現成「0 findings」**。被動偵測 severity 原則封頂 HIGH，並受 confidence 與 page type/context 調整。
- 每項動手前先寫可驗證測試 → `uv run python backend/manage.py test apps.scans` 全綠 + `ruff` →
  必要時 Docker 整合實掃。對外可見功能異動要同步競賽 Word 內容 md。
