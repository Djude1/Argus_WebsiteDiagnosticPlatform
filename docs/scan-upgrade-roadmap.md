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
工具鏈 Nuclei + Katana + Kali(SQLmap) + 自建 scanner 齊備。**主要缺口不在「缺功能」，在三處**：
1. 外部權威資料源接得不夠多（目前只有 GSC）；
2. 各維度評分偏規則加總、缺業界基準校準與可解釋性；
3. 偵測結果缺「可驗證性分級（confidence）」與歷史趨勢 diff。

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

- **現況**：`aeo/evaluate.py` 四層判定（可回答/資訊不足/內容衝突/無答案），有 `questions`/`answers`/`content`/`markup`/`page_checks`。設計優秀。
- **升級**：
  1. 問題生成多樣化（從標題/H2 反推使用者問句 + 同業常見問句模板）【待驗證：`questions.py` 現有生成來源】。
  2. 引用可得性評分（能逐字引用作答的段落字數比例）。
  3. 對照新興 `llms-full.txt` 慣例。

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

## 5~9. 資安 / 主動探測 / 深度資安 / 敏感檔案 / AI 爬蟲相關

- **現況**：被動（HTTPS/header/CSRF/PII）+ Nuclei + Katana + SSL/Cookie/CORS/CSP/SRI/DNS/
  JS 庫 CVE/服務 CVE/exposure/Kali SQLmap，OWASP/CWE 對映齊全，NVD 離線庫。覆蓋面達商用水準。
- **升級**：
  1. **可利用性分級（最重要）**：finding 加 `confidence` 三級（已驗證可利用/疑似/僅資訊），報告明確區分；被動偵測封頂 HIGH 的原則推廣到所有被動項。
  2. Nuclei 模板治理（鎖版本雜湊、記錄用了哪些模板、可排除噪音模板集，結果可重現）。
  3. Security headers 評分接 **Mozilla Observatory 規則**（可離線實作，給 A~F 等第）。
  4. CVE 資料源升級：NVD 已接，補 **OSV.dev**（開源套件漏洞，免費 JSON API）+ **EPSS**（實際被利用機率），讓「先修哪個」有依據。
  5. 敏感檔案字典對齊 **SecLists**，每個命中做內容型別確認【部分已做：`exposure_scanner` 有 soft-404】。
  6. 主動探測補「掃描來源 IP 宣告」供對方加白名單【現有 `AuthorizationConsent` + 網域驗證閘門】。

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
| **智慧動態掃描（旗艦）** | 固定管線 | 指紋→模組選擇決策層；見 [ADR-0004](adr/0004-smart-dynamic-scan.md) |
| 外部工具統一介面 | Nuclei/Katana 走 `process_runner`，各自 parse | 抽象 `ExternalTool` protocol（執行/逾時/取消/版本鎖/結果正規化），axe/Lighthouse 照契約接 |
| Finding schema | `make_finding` 統一格式 | 加 `confidence`、`source_tool`、`tool_version`、`first_seen_scan_id` |
| 結果可重現 | — | 記錄每次掃描用的工具版本與模板雜湊，寫進報告附錄 |
| 掃描設定檔化 | 五維 + 主動/被動 | 進階使用者可選單項模組，計費按實跑項目（與 ADR-0004 的結算模型共用） |
| 效能 | 階段循序 | 無相依的 scanner（SSL/DNS/連結/CVE）可並發 |

---

## 建議導入優先序（投報比）

1. **axe-core（UX/無障礙）** — 開源、Playwright 直接注入、立刻提升權威性與覆蓋面。
2. **Lighthouse + PageSpeed/CrUX（SEO/UX/效能）** — 業界共通語言，解決評分信任問題。
3. **評分可解釋化 + 歷史趨勢 diff（評分）** — 留存與說服力核心，純自建、不依賴外部。
4. **智慧動態掃描階段 1（指紋收斂層）** — 見 ADR-0004，風險最低、差異化最大。
5. **OSV.dev + EPSS（資安）** — 免費 API，讓漏洞優先序有實證依據。
6. **Finding confidence 分級（全資安）** — 純 schema + 規則調整，風險低、影響大。
7. 其餘（Observatory 規則、SimHash 去重、AI bot 政策、連結快取）為第二梯次。

---

## 落地共通紀律（每一項都適用）

- 遵守 Migration 鐵律（欄位一律新增）、`scans/CLAUDE.md` 的 scanner 回傳契約與狀態機規則、
  `docs/environment-preflight.md` 的掃描驗證閘門。
- 新 scanner：回傳 `list[dict]`（`make_finding` 格式）、不寫 `ScanJob.status`、不呼叫 billing、
  例外 silent-fail 回 `[]`、被動偵測 severity 封頂 HIGH。
- 每項動手前先寫可驗證測試 → `uv run python backend/manage.py test apps.scans` 全綠 + `ruff` →
  必要時 Docker 整合實掃。對外可見功能異動要同步競賽 Word 內容 md。
