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
  1. **有上限的 Render Readiness**：維持 `domcontentloaded`，再以短暫 hydration grace period、DOM/內容穩定度與可選 site-specific selector 判斷就緒；**不以 networkidle 作為必要條件**。必須有總時間上限，逾時仍保留已取得 DOM/截圖並標示 `LIMITED: render_readiness_timeout`。
  2. 爬取預算可觀測（種子來源、每頁耗時、被節流次數、render readiness 結果寫進 coverage/progress）。
  3. **Near-duplicate 只做 Analysis Reuse，不做 URL Skip**：SimHash / hreflang 僅可重用文字結構、部分 AEO/GEO 等高成本內容分析；每個 URL 仍必須各自做 headers、canonical/noindex、表單、權限、安全與 URL-specific 檢查。（**評估後暫緩 2026-10-07**：實測逐頁五維規則分析一頁約 70–150 ms（1.1 MB 的大頁約 1.3 s），50 頁合計約 5–10 秒，遠小於爬取本身的數分鐘；重用最多省幾秒，卻有把逐頁問題錯誤複製的風險。等分析改用 LLM 等高成本方法時再做）
  4. 所有重用必須記錄 `analysis_reused_from`、重用規則與未重用檢查，不能讓 dedupe 犧牲 coverage。

## 1. SEO

- **現況**：`scanners.py` 逐頁 title/meta/H1/alt/canonical/OG；`seo/` 有 `link_check`、
  `page_audit`、`site_findings`、`gsc`、`keywords`。GSC 已接。
- **升級**：
  1. 接 **PageSpeed Insights API（CrUX 真實場域資料）**：LCP/INP/CLS 實驗室 vs 真實使用者並列——目前最缺的權威外部訊號。
  2. 結構化資料驗證（JSON-LD 語法 + Google Rich Results 必填欄位，可離線）。
  3. robots/sitemap 一致性交叉檢查（sitemap 列出卻 noindex、canonical 指他頁等矛盾）【待驗證：`site_checks` 現況是否已含】。
  4. 目標關鍵字 vs GSC 實際曝光關鍵字的落差分析。

## 2. AEO（問答檢測）

- **現況**：`aeo/evaluate.py` 四層判定（可回答/資訊不足/內容衝突/無答案），框架完整，已有答案蘊含判定（`aeo/answers.py` 的 `entails()`）與日期衝突判定（2026-10-06 第二輪準確度修正）；實測曾出現「語意相關段落被誤判為真正答案」與跨模組 evidence 不一致，已知案例已修正，但**缺少量測基準**，無法知道整體誤判率。
- **升級**：
  1. **Answer Entailment 量測與強化（P0）**：`entails()` 初版已上線，候選段落須通過蘊含判定才算答案。下一步不是重做，而是用 gold dataset（見優先序 P0-C）量測誤判率，再依誤判類型強化。
  2. **Specificity / Conflict Check（P0）**：衝突判定目前**只判日期**；擴充到價格、資格、聯絡方式等需具體可核對的欄位，多頁內容互斥時標記 conflict。
  3. **Cross-module evidence reuse（P0）**：Email、電話、地址、日期等與 Security／SEO 共用 evidence，避免一個模組「找到」、另一個模組「找不到」。
  4. **Answer confidence（P1）**：輸出 Confirmed／Likely／Possible，並保留引用來源與限制。
  5. 問題生成多樣化（標題/H2 + 同業常見問句模板）。
  6. 引用可得性評分。
  7. `llms.txt`／`llms-full.txt` 僅列為 **Emerging / Experimental** 訊號，不與成熟 SEO 規則等價扣分。【部分完成：`reports.py` 已對 llms.txt 標示「依據／限制」並說明是新興慣例；評分權重是否已降級【待驗證】】


## 3. GEO（生成式引擎優化）

- **現況**：`analyze_geo` / `analyze_geo_fast`（文字區塊數、可見文字長度）。偏輕量。
- **升級**：
  1. 實體與權威訊號（作者、組織、`sameAs` → Wikidata/社群）——E-E-A-T。
  2. 內容新鮮度（`dateModified`/`datePublished` 與實際更新落差）。
  3. 可被 AI 摘要性（段落結構、清單化、摘要句位置）——與 AEO 共用訊號但角度不同。

## 4. UX

- **現況**：`crawler.py` 的 `collect_ux_signals`/`collect_mobile_layout`/`collect_element_boxes`，
  `scanners.py` 行動版溢出/觸控目標/未標籤欄位/JS 錯誤，截圖已精準框選。
- **升級**：
  1. **接 axe-core（Playwright 注入）**：目前 a11y 是自建規則，接開源業界標準可一舉覆蓋 WCAG 2.2 數十條。**UX 維度投報率最高**。
  2. **接 Lighthouse（programmatic）**：Performance/Accessibility/Best-Practices/SEO 四分數與自建並列。
  3. CLS 元素級歸因（哪個元素造成位移）。

## 5. 被動資安（Passive Security）

- **現況**：HTTPS/header/CSRF/PII、SSL/Cookie/CORS/CSP/SRI/DNS、JS 套件 CVE、服務 CVE 等規則已具備，OWASP/CWE 對映齊全，NVD 離線庫已接。
- **升級**：
  1. **校準既有 `Finding.confidence` 的語義與使用方式**：欄位、`make_finding()` 與 serializer 已存在；缺口是規則如何產生 confidence、如何影響 score/report，以及如何區分「配置建議」「曝露面」「疑似弱點」「已驗證弱點」。既有資料的預設 `1.0` 一律視為 **legacy / uncalibrated**，不得回溯解讀為 Confirmed。
  2. Security headers 評分接 **Mozilla Observatory 規則**（可離線實作，給 A~F 等第）。（**已實作 2026-10-07**：`security/observatory.py`，獨立呈現在網站架構與報告，不併入 Argus 分數）
  3. CVE 資料源補 **OSV.dev + EPSS**，讓漏洞優先序不只看 CVSS。（**已實作 2026-10-07**：`security/vuln_intel.py`，EPSS 影響排序與說明、OSV 提供前端函式庫修補版本，不改嚴重度）

## 6. 主動探測（Active Probing）

- **現況**：Nuclei + Katana + Kali(SQLmap) + 敏感檔案探測（`security/exposure_scanner.py`；`scan_plan.py` 的 `run_exposure` 只在主動模式＋已授權＋整站時開啟）+ 自建 probe，可在授權閘門後做主動檢測。
- **升級**：
  1. **Nuclei 模板治理**：鎖版本與模板雜湊、記錄實際使用模板集、排除高噪音模板，結果可重現。
  2. **SQLMap 專項化**：保留為 SQL Injection 深查工具，不把它當通用 Web DAST。
  3. 主動探測補「掃描來源 IP 宣告」供目標端白名單，並維持 `AuthorizationConsent` + 網域驗證雙閘門。
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
  2. 內容可機讀性（語意 HTML 比例、主內容可否與導覽/頁尾分離 `<main>`/`article`）。

## 11. 連結檢查

- **現況**：`seo/collect.py` 已以 URL 去重跨頁重複連結，`check_links()` 已用 `ThreadPoolExecutor` 並發，並具備站內/子網域/站外分類、跳轉鏈、狀態、robots、難懂錨文字與時間/數量上限。
- **升級**：
  1. 不重做既有 scan-level 去重與並發；改補 **freshness / cache reuse**，避免同一掃描流程內其他 stage 重複查相同外部 URL。
  2. 連結 coverage 明確區分 checked / restricted / timeout / skipped / budget_exhausted，歷史比較只能在 coverage 足夠時判定 resolved。
  3. 連結健康度趨勢標記「新壞掉／持續失效／已確認恢復／本次無法確認」。
  4. 錨文字品質延伸（「點這裡」「更多」等無意義文字，SEO + 無障礙雙重影響）。

## 12. 評分

- **現況**：`calculate_scores` + `base_scores_for` + `_dedupe_findings_for_scoring` 依 finding 嚴重度加權；專案層已有前次分數、new/persisting/本次未出現與趨勢資料，但目前比較主要依「本次有勾該 category」，尚未感知 rule/URL coverage。
- **升級（整體最關鍵）**：
  1. **Coverage-aware scoring**：FAILED / BLOCKED / LIMITED / NOT_TESTED 的規則或資源不得被視為「0 問題」而拉高分數。分數需附有效 coverage，coverage 低於門檻時顯示「資料不足／部分評估」，而非假精準高分。
  2. **歷史狀態語義重做**：`finding absent` 先標 `NOT_OBSERVED`；只有同 rule、相容 resource/context、偵測能力已完整執行且 coverage 足夠時，才能升級成 `RESOLVED`。建議生命週期：`NEW / PERSISTING / RESOLVED / NOT_OBSERVED / NOT_TESTED / BLOCKED / INCONCLUSIVE`。
  3. **評分可解釋化**：每個維度列出扣分來源、coverage、confidence 與未測範圍。（**已實作 2026-10-07**：扣分來源、coverage、未完整完成的檢查；confidence 目前不影響扣分，待第 6 項校準後再列）
  4. **外部指標保持獨立，不做錯誤「對齊總分」**：Lighthouse、CrUX、axe、Observatory 各自呈現；只在同 URL/裝置/期間/構面可直接對應的子指標做 validation。
  5. **保存 `scoring_version` / `ruleset_version`**：規則或權重版本變更時，歷史圖必須標示模型版本；跨版本不得直接把 score delta 解讀成網站改善。
  6. **confidence 使用既有欄位但需重新校準**：低 confidence 可影響排序/扣分，但 legacy `confidence=1.0` 不得等同 Confirmed。

---

## 跨領域工程化

| 項目 | 現況 | 升級 |
|---|---|---|
| **Coverage Contract（P0-A）** | category 是否有勾是主要比較條件 | 定義 stage/rule/resource coverage：COMPLETED／PARTIAL／FAILED／BLOCKED／SKIPPED／NOT_APPLICABLE；直接約束 scoring、history diff 與「resolved」判定 |
| **Shared Evidence MVP（P0-B）** | 各 scanner 各自產 finding | 先只接 AEO + Security 共用的 email/phone evidence；驗證跨模組矛盾改善後再擴大，不先做 Universal Evidence Platform |
| **Evidence Context Contract** | evidence 缺統一情境 | 最小欄位：source_url、observed_at、acquisition_method、viewport、auth/session context、initial_html/rendered_dom/network、source/tool version、artifact ref、limitations、missing_reason、redaction_state；不同 context 不強制一致 |
| **Evidence Governance** | — | 敏感資料遮罩、cookie/token 永不落 evidence、raw artifact 大小上限、保留期限與刪除策略 |
| **Root Cause Correlation（P1）** | finding 去重為主 | 聚合成 Root Cause → Related Findings → Evidence → Fix |
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

4. **P1 Coverage-aware scoring + comparable history**（**已實作 2026-10-07**：`scoring_version`／`ruleset_version`（`apps/scans/versions.py`、migration 0029），跨版本不顯示分數增減；coverage-aware 計分與 RESOLVED／NOT_OBSERVED／BLOCKED／INCONCLUSIVE 已於 P0-A 完成。評分可解釋化 **已實作 2026-10-07**：`scanners.score_breakdown()`（`calculate_scores` 的分類分數由它算出）＋`score_explain.py`＋`GET /api/scans/<id>/score-breakdown/`，掃描「分數說明」分頁逐維度列基準分、逐項扣分權重、出現處數、只修好該項時的分數、不扣分項目與未完整完成的檢查；舊公式算的分數標示不一致。尚未做：外部 benchmark、PDF 報告內的逐項扣分、confidence 影響扣分）
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
