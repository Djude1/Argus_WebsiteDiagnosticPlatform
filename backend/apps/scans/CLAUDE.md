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
| `crawler.py` | Playwright BFS 爬蟲、收集頁面 | 修改 ScanJob.status、呼叫 billing |
| `scanners.py` | SEO/AEO/GEO/UX 掃描 + 被動式基本安全檢查（HTTPS/header 存在性/CSRF/PII）、產生 findings | 修改 ScanJob.status、深度資安分析 |
| `cancellation.py` | 合作式取消：`is_cancelled` / `raise_if_cancelled` 直接查 DB `ScanJob.status` 是否為 `CANCELLED`（**非 Redis 旗標**），供 worker 在檢查點輪詢 | 直接終止 worker process |
| `fixgen/` | 修正產出引擎（ADR-0002）：`facts.py` 爬取事實萃取、`policy.py` 事實政策三級驗證、`engine.py` prompt＋單次 JSON 產生＋渲染、`services.py` 計費閘門觸發（先扣後派）＋狀態機冪等、`tasks.py` Celery 任務（不重試）。API 掛在 ScanJobViewSet 的 `fix-output/trigger|status|artifacts` | 修改 `ScanJob.status`、自動重試、繞過事實政策驗證、派工後才計費 |
| `reports.py` | 產生 Word 報告（.docx） | 任何 DB 寫入 |
| `aeo/` | AEO 問答檢測（內容擷取、出題、找答案與判定、標記一致性、整站評估；見下「AEO 問答檢測」） | 修改 `ScanJob.status`、發出任何網路請求（只分析爬蟲已抓到的頁面） |
| `nuclei_scanner.py` | Nuclei binary 封裝；工具預算、JSONL 解析、Finding mapping | 在 passive 或未授權模式執行 |
| `katana_scanner.py` | Katana 全站 JS/端點探索封裝；時間、大小、同主機與 RPS 預算 | 在單頁、passive 或未授權模式執行 |
| `domain_verification.py` | 網域所有權驗證引擎：token 產生、網域正規化、DNS TXT／meta tag／HTML 檔三種驗證、`run_verification()` 更新 `VerifiedDomain` | 修改 `ScanJob.status`、繞過 `assert_public_http_url` SSRF 檢查 |
| `security/` | 深度主動式資安檢查（SSL/TLS、Cookie、CORS、CSP 品質、敏感檔外洩探測、硬編碼秘鑰偵測、OWASP 對映、Kali 工具）| 修改 ScanJob.status、呼叫 billing |

### 掃描範圍與工具矩陣

產品範圍只有兩種：前端以 `max_pages=1` 表示**單頁**，其餘合法值表示**全網站**。`passive/active` 是探測授權層級，不是第三種掃描範圍。所有工具閘門集中由 `scan_plan.py` 決定：| 範圍與授權 | Nuclei | Katana | 敏感路徑探測 | Agent（資安） | Agent（UX） | Kali |
|---|---:|---:|---:|---:|---:|---:|
| 單頁 + passive | 否 | 否 | 否 | 否 | 否 | 否 |
| 全網站 + passive | 否 | 否 | 否 | 否 | 勾 UX 才跑 | 否 |
| 單頁 + active 且已授權 | 僅輸入頁 | 否 | 否 | 否 | 否 | 可執行既有同源候選驗證 |
| 全網站 + active 且已授權 | 已爬 URL | 是 | 是 | 是（另受總開關控制） | 勾 UX 才跑 | 可執行既有同源候選驗證 |

Katana 與 Nuclei 並行時必須共享 `ARGUS_ACTIVE_MAX_RPS`；若總預算只有 1 RPS，必須改為依序執行。單頁不得用 Katana、敏感路徑字典或 Agent 擴張成全站掃描。

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
- 三種驗證方法共用一支 token（`argus-site-verification=<token>`）：DNS TXT（`_argus-verification.<domain>`，重試 3 次×timeout 5 秒）／首頁 meta 標籤（HTML 前 64KB 需同時出現標籤名與 token）／驗證檔（`/.well-known/argus-verification.txt` 內容等於 token）
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
2. **`info` 不扣分**。info 多半是純資訊甚至正向指標（例如「Nuclei 探針被 WAF 攔截，代表防護有效」）。**同理 `info` 不進 `top_actions`**——它對應的建議修補是「無需修復」，列進「優先改善建議」會被當成待辦。
3. **指數衰減 `100 * exp(-penalty / SCORE_DECAY_CONSTANT)`**，不是 `max(0, 100 - penalty)`。舊公式累積 100 分懲罰後永遠是 0，無法分辨「4 個高風險」與「40 個高風險」。`SCORE_DECAY_CONSTANT` 是可調的產品參數，不是演算法細節。
4. **未評估的分類不寫進 `category_scores`，缺鍵即代表未評估**。`category_scores` **不保證含全部 5 個分類，取值一律用 `.get()`**。這同時保證「報告列出的分數」與「`overall_score` 平均的分母」是同一組，使用者算得出總分。
5. **有基準分的分類（`base_scores`，目前只有 AEO）**：`calculate_scores(findings, tested, base_scores={"aeo": N})` 以 N 取代 100 當起點，`BASE_SCORED_RULE_PREFIXES`（`aeo-answer-`）的逐題 finding 不再扣分（已反映在基準分裡），其餘 AEO finding（noindex、標記不一致…）照常衰減扣分。`rerun_scan` 與 `finding_normalization._rescore` 都從 `aeo_report["score"]` 取回基準分（第 5 條由 `tests_aeo_answerability.py` 鎖定）。

`Finding.Meta.ordering` 一併鎖定兩件事：`priority_score` 必須明確 `nulls_last=True`（PostgreSQL 的 `DESC` 預設 NULLS FIRST、SQLite 是 NULLS LAST，不指定的話同一份報告在本機與正式站排序相反），`severity` 必須用 `Case/When` 的風險序（CharField 直接排是字母序 `critical < high < info < low < medium`，info 會插到 low 與 medium 前面）。

`make_finding()` 在呼叫端沒傳 `priority_score` 時，依 severity 給預設值——`security/` 子套件的 scanner 全都不傳，留 `None` 會被 PostgreSQL 頂到報告最前面。

---

## AEO 問答檢測（`aeo/`，2026-09-28 重做）

AEO 不再數 FAQPage／HowTo 標記，改成檢測「問題能否從網站內容中被找到、回答並追溯證據」。四層各一個模組：

| 模組 | 職責 |
|---|---|
| `aeo/content.py` | 第 1 層：主要文字擷取（排除 nav／header／aside／表單／隱藏元素；footer 另標 region）、段落與所屬標題、`robots_directives`（meta robots／googlebot＋`X-Robots-Tag`）、`data-nosnippet` |
| `aeo/questions.py` | 依網站內容出題：固定意圖（電話、Email、地址、營業時間、費用、報名方式／截止、資格、退款、運送…，需在正文命中觸發詞才出題）＋網站自己寫的問句標題 |
| `aeo/answers.py` | 第 2、3 層：逐題找候選段落並判定 `answered`／`insufficient`（空泛、日期無年度）／`conflict`（不同頁日期矛盾）／`missing`，附原文與位置 |
| `aeo/markup.py`、`aeo/page_checks.py` | 第 4 層與逐頁規則：結構化資料語法、標記與可見文字一致性、noindex／nosnippet（`scanners.analyze_aeo` 只委派到這裡） |
| `aeo/evaluate.py` | 整站評估 `evaluate_site(pages)`：正文 < `MIN_MAIN_TEXT_CHARS` 或題目 < `MIN_QUESTIONS` → `status=insufficient`、**不給分**（`tested_categories_for` 移除 aeo，報告顯示「未評估」）；否則依逐題判定加權算分，產生 `aeo-answer-*` finding 與 `aeo-render-dependent`（主要文字需執行 JS 才出現） |

- 結果存在 `ScanJob.aeo_report`（migration 0018）：`status`、`reason`、`questions_total`、`counts`、`answered_ratio`（有答案的問題比例）、`evidence_ratio`（答案附有原文的比例）、`score`、`questions[]`（逐題判定、理由、證據），`method` 目前是 `rules-v1`。
- 呈現：掃描詳情頁 `AeoAnswerPanel`、Word 報告範圍表「AEO 問答檢測」列與附錄 6.6 逐題表（`appendix.aeo_items`，`RENDERER_VERSION` 3）、MCP `get_scan` 的 `aeo` 欄位（證據遮罩）、`ScanJobSerializer.aeo_report`。
- 人工校驗題集在 `tests_aeo_answerability.py` 的 `GOLD_SITES`：改動規則後判定正確率必須維持 100%。**第一版只做可重現的規則判定**；受控 AI 評估與外部平台觀察尚未實作，報告不得宣稱有。
- 新增意圖或判定規則：先在 `GOLD_SITES` 加一個會踩到的案例，再改規則。

## 報告內容契約（`reports.py`）

`.docx` 會被下載、轉寄、存檔給第三方，內容邊界是硬規則：

| 必須有 | 為什麼 |
|---|---|
| 掃描範圍（範圍／模式／頁數上限／實際頁數／robots） | 收件者要能判斷涵蓋範圍，「沒發現問題」才有意義 |
| 掃描授權聲明（`AuthorizationConsent`） | Argus 是授權式掃描平台，報告沒有授權依據等於放棄核心合規主張；查無紀錄要明講，不能讓章節消失 |
| 掃描警示（`scan_effectiveness` / 略過與失敗頁數） | 爬 0 頁的掃描會產出看起來正常的報告，分數只反映站台層級檢查 |

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
| **不要改 `report_render/` 的程式碼** | 它是 vendored 第三方 module，已在 ruff `extend-exclude`。唯一的在地修改是 `theme.py` 的字型解析，有註解說明 |

**字型是硬需求**：圖表由 matplotlib 繪製，缺 CJK 字型時 `theme.py` 直接 `RuntimeError`（刻意大聲失敗——退回預設字型的話中文會變成一整排 □，報告照樣寄給客戶）。Dockerfile 已裝 `fonts-noto-cjk`，另可用 `ARGUS_REPORT_FONT_REGULAR` / `_BOLD` 覆寫。

**報告用的圖檔放 `backend/apps/scans/report_assets/`**，不可放 `frontend/public/`——backend image 只有 `COPY backend ./backend`。

schema 沒有的東西（掃描頁面清單、已解決項目清單）不要硬塞：頁面清單已移除（與範本一致，掃描範圍表仍有頁數）；已解決數量收進 `summary.headline`。

---

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

- **PII 分級**（`scanners.analyze_data_exposure`）：高風險 `SECURITY_PII_8B24BB8B28` 只給身分證號／信用卡號；手機、非本站網域 Email、藏在 HTML 註解的資料、開發殘留 → 中風險 `security-pii-personal-contact`；本站網域（同 registrable domain）或 `mailto:`／`tel:` 的聯絡方式 → info `security-pii-public-contact`（多半是刻意公開）。舊版一看到任何 Email 就判高風險。
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
- **觸控目標過小 ＋ 表單欄位缺可及名稱**（`collect_ux_signals()` → `page["ux_signals"]`）：
  可點元素在手機寬或高 < `_MIN_TAP_TARGET_PX`（40px）列為 tap-target 問題（≥5 個升
  MEDIUM）；`<input>`/`<select>`/`<textarea>` 無 label/aria/title/placeholder 列為
  accessibility 問題（MEDIUM）。每類上限 `_MAX_UX_OFFENDERS`（8）。
- **未捕捉的 JS 例外**（`pageerror` 監聽 → `page["js_errors"]`）：頁面 console 未攔截的
  例外列為 MEDIUM，證據上限 `_MAX_JS_ERROR_EVIDENCE_CHARS`（800）。

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

每次 `build_scan_report()` 完成時寫入一列 `ReportVerification`：報告編號、檔案內容 SHA-256、產生時間。

| 規則 | 為什麼 |
|---|---|
| **報告編號跨重新產生保持不變** | 由 `HMAC(SECRET_KEY, scan_id)` 推導，不含時間戳。報告一旦交付就可能被轉寄存檔，換編號會讓已流出的副本失效 |
| **報告本身只印編號、不印雜湊** | 雜湊要涵蓋整份檔案，檔案裡又要有雜湊＝循環相依。雜湊由查驗端點提供，收件者自行 `sha256sum` 比對 |
| **`views.py` 的 report action 必須用快取** | 省下每次下載的 IO 與 CPU。三個條件都成立才可重用：有防偽紀錄、檔案存在、`renderer_version` 等於目前的 `report_render.RENDERER_VERSION` |
| **改動 `.docx` 版面就要把 `RENDERER_VERSION` +1** | 否則掃描一旦產過報告就永遠鎖在舊版面。實際踩過：圖表修好後重新下載舊掃描的報告，拿到沒有圖表的快取檔，看起來像修復失敗 |
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
`active_probe`（`run_nuclei`）、`deep_security`、`exposure_probe`（`run_exposure`）、`geo_site`（勾 GEO）、`agent`（Agent 啟用且可執行）、`scoring`。
頁面分析改為**逐維度、逐頁**執行（`analyze_page(categories={單一維度})`），結果與一次跑全部維度相同；新增子步驟時要同步前端 `ScanExperience.jsx` 的 `SCAN_STEP_META`。

`step_done`／`step_total` 是**本階段**內的進度（爬取＝頁、逐維度分析＝該維度已分析頁數、Agent＝步數；其他子步驟 0/0＝不定進度），`step_started_at` 在同一步內保留不變（供前端估算本階段剩餘時間）。前端整體百分比由階段序號加上本階段比例算出，進度條才會和階段一起走（2026-09-28 前整體進度只看頁數，爬完就 100%、後面十個階段進度條不動）。

---

## 掃描流程階段（`tasks.py`，2026-09-28 工程化）

`run_scan_job` 只做三件事：`start_scan_run()` CAS 取件並建立 `ScanRunContext` → 依序執行 `SCAN_PIPELINE` → 取消／超時／失敗三種收尾（`finish_cancelled`／`finish_timeout`／`finish_failed`，退款失敗會讓 task 失敗）。完成時由 `stage_settlement()` 結算與贈與修正產出額度。

| 階段名（失敗 log 會寫 `[階段名:例外類別]`） | 函式 | 做什麼 |
|---|---|---|
| `target_validation` | `stage_validate_target` | 再次確認目標是公開 HTTP(S) |
| `crawl` | `stage_crawl` | Playwright BFS；每頁回報進度並當取消檢查點 |
| `enter_scanning` | `stage_enter_scanning` | 記錄警告、狀態推進到 scanning、落地 `Page` |
| `page_analysis` | `stage_analyze_pages`（單頁單維度：`_analyze_one_page`） | 逐維度、逐頁規則分析＋inline 秘鑰偵測 |
| `aeo_answers` | `stage_aeo_answerability`（`_aeo_site_pages`） | AEO 問答檢測（見下「AEO 問答檢測」），結果寫 `ScanJob.aeo_report` |
| `site_security` | `stage_site_security` | 站台層級 HTTPS/HSTS/CSP 等（只評估一次） |
| `active_probe` | `stage_active_probe`（`_collect_probe_targets`、`_run_site_active_tools`、`_run_single_page_nuclei`、`_waf_blocked_nuclei_note`） | Nuclei／Katana，遵守範圍與授權矩陣 |
| `deep_security` | `stage_deep_security` | security/ 子套件被動深度檢查＋WAF 封鎖偵測 |
| `exposure` | `stage_exposure` | robots 敏感路徑（被動）＋敏感檔案主動探測（全網站 active） |
| `geo_site` | `stage_geo_site` | llms.txt、AI 爬蟲可存取性 |
| `agent` | `stage_agent` | Hermes-Agent（資安／UX），失敗不讓掃描失敗 |
| `kali` | `stage_kali` | Kali 主動驗證 fallback |
| `scoring` | `stage_scoring`（`tested_categories_for`、`base_scores_for`） | 計分並 CAS 推進到 completed |

階段之間只透過 `ScanRunContext` 傳遞中間產物；`ctx.record(findings, page=...)` 同時寫 `Finding` 與納入計分清單。**新增階段**：寫 `stage_xxx(ctx)`、加進 `SCAN_PIPELINE`；要在進度條顯示時同步 `planned_scan_steps()` 與前端 `SCAN_STEP_META`。測試 patch 目標仍是 `apps.scans.tasks.<名稱>`，所以外部依賴一律以模組層級名稱呼叫。結構由 `tests_pipeline_stages.py` 鎖定。

網頁 API 與 MCP 共用的掃描入口：`views.enqueue_created_scan()`（派工，失敗全額退款）、`views.ensure_report_file()`（報告快取）、`tasks.request_scan_cancel()`（取消＋退款）。

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
`tasks.py` 併入：sqlmap 候選＝全部端點；Nuclei extra_urls＝頁面＋帶
query 端點前 3 個（`_NUCLEI_MAX_ENDPOINT_URLS`，全塞會炸時間預算）。
Agent 端同能力＝`get_network_requests` 工具（見架構文件 §3）。

---

## Coin 扣點流程（與 billing 整合）

```
建立掃描 → hold_for_scan(max_pages × 勾選維度數 × 每維單價 ＋ agent_ux_fee)
  ↓ worker 完成
settle_scan_actual(actual_pages × 同組維度數 × 每維單價 ＋ agent_ux_fee)  ← 退差額
  ↓ 若失敗/取消
refund_full_for_scan(scan)  ← 全退（冪等）
```

`tasks.py` 負責在適當時機呼叫這三個 `billing/services.py` 函式。

**Agent UX 附加費**：`estimate_scan_cost` 已把 `agent_ux_fee(max_pages, categories)`
折進頁面費，hold／settle 都自動含這筆固定點數（`ARGUS_COIN_AGENT_UX`，預設 20），
不新增 `CoinTransaction.kind`、不需 migration。收費條件與 `run_agent_ux` 對齊：
`ARGUS_AGENT_ENABLED` 開、`max_pages > 1`（全網站）、且勾了 `ux` 才收；否則回 0。
若實際只爬到 1 頁，settle 以 `actual_pages=1` 重算 → 這筆費用自動退回（fee 也回 0）。

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
