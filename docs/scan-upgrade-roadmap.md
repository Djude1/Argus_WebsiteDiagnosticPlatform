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
  1. SPA 渲染等待分級（`networkidle` + 關鍵選擇器才算完成），避免抓到骨架屏。
  2. 爬取預算可觀測（種子來源、每頁耗時、被節流次數寫進 `progress`）。
  3. 近重複頁 SimHash 去重（分頁/篩選參數頁只深掃一次）——參考 Screaming Frog near-duplicate。
  4. hreflang 多語分群，避免重複掃等價頁。

## 1. SEO

- **現況**：`scanners.py` 逐頁 title/meta/H1/alt/canonical/OG；`seo/` 有 `link_check`、
  `page_audit`、`site_findings`、`gsc`、`keywords`。GSC 已接。
- **升級**：
  1. 接 **PageSpeed Insights API（CrUX 真實場域資料）**：LCP/INP/CLS 實驗室 vs 真實使用者並列——目前最缺的權威外部訊號。
  2. 結構化資料驗證（JSON-LD 語法 + Google Rich Results 必填欄位，可離線）。
  3. robots/sitemap 一致性交叉檢查（sitemap 列出卻 noindex、canonical 指他頁等矛盾）【待驗證：`site_checks` 現況是否已含】。
  4. 目標關鍵字 vs GSC 實際曝光關鍵字的落差分析。

## 2. AEO（問答檢測）

- **現況**：`aeo/evaluate.py` 四層判定（可回答/資訊不足/內容衝突/無答案），框架完整，但實測已出現「語意相關段落被誤判為真正答案」與跨模組 evidence 不一致。
- **升級**：
  1. **Answer Entailment Validation（P0）**：候選段落命中後，再判斷是否真的回答問題，不能把 retrieval hit 直接等同 answer。
  2. **Specificity / Conflict Check（P0）**：日期、價格、資格、聯絡方式等需具體可核對；多頁內容互斥時標記 conflict。
  3. **Cross-module evidence reuse（P0）**：Email、電話、地址、日期等與 Security／SEO 共用 evidence，避免一個模組「找到」、另一個模組「找不到」。
  4. **Answer confidence（P1）**：輸出 Confirmed／Likely／Possible，並保留引用來源與限制。
  5. 問題生成多樣化（標題/H2 + 同業常見問句模板）。
  6. 引用可得性評分。
  7. `llms.txt`／`llms-full.txt` 僅列為 **Emerging / Experimental** 訊號，不與成熟 SEO 規則等價扣分。


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

- **現況**：HTTPS/header/CSRF/PII、SSL/Cookie/CORS/CSP/SRI/DNS、JS 套件 CVE、服務 CVE、
  exposure 等規則已具備，OWASP/CWE 對映齊全，NVD 離線庫已接。
- **升級**：
  1. Finding 加 `confidence` 與 evidence 強度，將「配置建議」「曝露面」「疑似弱點」「已驗證弱點」分開。
  2. Security headers 評分接 **Mozilla Observatory 規則**（可離線實作，給 A~F 等第）。
  3. CVE 資料源補 **OSV.dev + EPSS**，讓漏洞優先序不只看 CVSS。
  4. 敏感檔案字典對齊 **SecLists**，每個命中做內容型別與 soft-404 確認。

## 6. 主動探測（Active Probing）

- **現況**：Nuclei + Katana + Kali(SQLmap) + 自建 probe，可在授權閘門後做主動檢測。
- **升級**：
  1. **Nuclei 模板治理**：鎖版本與模板雜湊、記錄實際使用模板集、排除高噪音模板，結果可重現。
  2. **SQLMap 專項化**：保留為 SQL Injection 深查工具，不把它當通用 Web DAST。
  3. 主動探測補「掃描來源 IP 宣告」供目標端白名單，並維持 `AuthorizationConsent` + 網域驗證雙閘門。
  4. 所有主動 stage 必須有 request budget、timeout、RPS 上限與 BLOCKED/LIMITED 狀態，避免 WAF 攔截被誤解為 0 findings。

## 7. 深度 Web Security / DAST

- **新增 OWASP ZAP（P1）**：作為 Argus 深度 Web Application DAST 引擎，補足 Nuclei/SQLMap 無法完整覆蓋的
  session-aware、parameter-based、browser-oriented 掃描能力。
- 建議接入能力：
  1. ZAP Passive Scan：可在較低風險情境下分析 response / header / DOM 訊號。
  2. ZAP Traditional Spider / AJAX Spider：補 SPA、動態路由與表單探索。
  3. ZAP Active Scan：**只在已驗證網域 + 明確主動授權下執行**，並限制 policy、request budget、RPS、timeout。
  4. Authenticated Context：後續支援測試帳號 / session context 時再開啟，不把登入失敗當成「已測」。
  5. ZAP alert 先正規化進 Shared Evidence Store，再由 Argus 做 confidence、severity、去重與 Root Cause；**不要直接照搬 ZAP risk 等級到最終報告**。
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
  1. AI bot robots 政策分析（`GPTBot`/`ClaudeBot`/`Google-Extended`/`PerplexityBot` 允許或封鎖，說明商業取捨）。
  2. 內容可機讀性（語意 HTML 比例、主內容可否與導覽/頁尾分離 `<main>`/`article`）。

## 11. 連結檢查

- **現況**：`seo/link_check.py` 分類（站內/子網域/站外）、跳轉鏈、狀態、robots、難懂錨文字。
- **升級**：
  1. 跨頁重複外部連結只查一次（scan 層級快取）+ 並發，大站省大量請求。
  2. 連結健康度趨勢（接下方歷史趨勢後，標「本次新壞的連結」）。
  3. 錨文字品質延伸（「點這裡」「更多」等無意義文字，SEO + 無障礙雙重影響）。

## 12. 評分

- **現況**：`calculate_scores` + `base_scores_for` + `_dedupe_findings_for_scoring`，依 finding 嚴重度加權。
- **升級（整體最關鍵）**：
  1. **評分可解釋化**：每個維度分數附「扣了幾分、因為哪幾條 finding」，前端可展開。目前是黑盒加總。
  2. **基準校準**：接外部權威分數（Lighthouse/Observatory/CrUX）後校準自建刻度，避免「Argus 給 90 但 Lighthouse 給 60」的信任落差。
  3. **信心加權**：低 confidence 的 finding 扣分打折，與「可利用性分級」連動。
  4. **歷史趨勢 diff**：`ScanJob` 已按專案歸集，新增「分數隨時間」與「本次新增/已修復/仍存在」的 finding diff——留存使用者的核心（Ahrefs/SEMrush Site Audit 都有）。

---

## 跨領域工程化

| 項目 | 現況 | 升級 |
|---|---|---|
| **Shared Evidence Store（P0）** | 各 scanner 各自產 finding | DNS／Headers／DOM／Network／Nuclei／axe／Lighthouse／GSC／CrUX 先正規化成 evidence，再由各維度判定；報告前跑 cross-module consistency check |
| **Root Cause Correlation（P1）** | finding 去重為主 | 聚合成 Root Cause → Related Findings → Evidence → Fix |
| **Stage Result / Coverage（P0）** | scanner 失敗可被隱藏 | 記錄 COMPLETED／FAILED／SKIPPED／BLOCKED／LIMITED，禁止把工具失敗呈現成「0 findings」 |
| **智慧動態掃描（旗艦）** | 固定管線 | 指紋→模組選擇決策層；見 [ADR-0004](adr/0004-smart-dynamic-scan.md) |
| 外部工具統一介面 | Nuclei/Katana 走 `process_runner`，各自 parse | 抽象 `ExternalTool` protocol（執行/逾時/取消/版本鎖/結果正規化），axe/Lighthouse/**ZAP** 都照契約接；ZAP alert 必須先 normalize，不直通最終 Finding |
| Finding schema | `make_finding` 統一格式 | 加 `confidence`、`maturity`、`evidence[]`、`limitations[]`、`source_tool`、`tool_version`、`root_cause_id`、`first_seen_scan_id`、`verification_status` |
| 結果可重現 | — | 記錄每次掃描用的工具版本與模板雜湊，寫進報告附錄 |
| 掃描設定檔化 | 五維 + 主動/被動 | 進階使用者可選單項模組，計費按實跑項目（與 ADR-0004 的結算模型共用） |
| 效能 | 階段循序 | 無相依的 scanner（SSL/DNS/連結/CVE）可並發 |

---

## 建議導入優先序（投報比）

1. **Shared Evidence Store + Cross-module consistency（P0）** — 先解決不同模組對同一事實互相矛盾。
2. **Finding confidence + Stage Result（P0）** — 區分 Confirmed／Likely／Possible，並明示 FAILED／BLOCKED／LIMITED。
3. **AEO Answer Entailment Validation（P0）** — 先解決「語意相關 ≠ 真正回答」的誤判。
4. **axe-core（UX/無障礙）** — 快速提升 WCAG 2.2 覆蓋與權威性。
5. **Lighthouse + CrUX（SEO/UX/效能）** — Lighthouse 做 Lab、CrUX 做 Field、GSC 做 Search impact。
6. **Root Cause correlation + 評分可解釋化 + 歷史趨勢 diff** — 從 finding list 升級為診斷平台。
7. **智慧動態掃描階段 1（指紋收斂層）** — 先只記錄、不改行為，建立 fingerprint accuracy benchmark。
8. **OWASP ZAP（Deep Web Security / DAST，P1）** — 先以受控 policy 接入 Passive/Spider，再於已授權 Smart/Deep Security Scan 啟用 Active Scan；結果先正規化再進 Argus。
9. **OSV.dev + EPSS（資安）** — 補漏洞優先序的外部實證。
10. 其餘（Observatory 規則、SimHash 去重、AI bot 政策、連結快取）為第二梯次。

---

## 落地共通紀律（每一項都適用）

- 遵守 Migration 鐵律（欄位一律新增）、`scans/CLAUDE.md` 的 scanner 回傳契約與狀態機規則、
  `docs/environment-preflight.md` 的掃描驗證閘門。
- 新 scanner：回傳 `list[dict]`（`make_finding` 格式）、不寫 `ScanJob.status`、不呼叫 billing。
  單一模組例外不得中斷整場掃描，但 orchestrator 必須記錄 stage status / error / coverage；
  **禁止 silent-fail 被呈現成「0 findings」**。被動偵測 severity 原則封頂 HIGH，並受 confidence 與 page type/context 調整。
- 每項動手前先寫可驗證測試 → `uv run python backend/manage.py test apps.scans` 全綠 + `ruff` →
  必要時 Docker 整合實掃。對外可見功能異動要同步競賽 Word 內容 md。
