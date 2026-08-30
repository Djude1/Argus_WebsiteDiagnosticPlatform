# 掃描報告品質稽核：待優化解決清單

**日期**：2026-08-30
**稽核對象**：`backend/apps/scans/reports.py`（Word 報告產生）+ `backend/apps/scans/scanners.py::calculate_scores()`（評分）
**實測樣本**：`argus-scan-25-report.docx`（目標 `https://lqll.clouda.dpdns.org/`，掃描完成於 2026-08-24 11:08:58）

---

## 稽核範圍與盲區

**已檢查**：`reports.py` 全文、`scanners.py::calculate_scores()`、`models.py` 的 `Finding` / `ScanJob`、`views.py` 的 report action、`security/` 全部 scanner 的 `priority_score` 指派情況、`frontend/nginx.conf` 與 `config/urls.py` 的 media 服務規則、樣本 docx 的完整段落與樣式結構。

**盲區**：
- **scan 25 的資料列不在手上**。compose 的 PostgreSQL 目前 `ScanJob=0 / Page=0 / Finding=0`，樣本掃描在正式 K8s。所以下面 SECURITY 分數的重算是**用報告內容反推**的，GEO / SEO 的扣分我無法逐項對帳（報告顯示的是合併後的項目，計分用的是合併前的原始 finding，數量對不上）。
- 沒有實際使用者訪談資料，「使用者看不懂」的判斷來自術語是否為內部識別碼，不是使用者測試結果。
- 沒有檢查 `apps/insights`（AI 洞察）是否有另一套報告呈現。

---

## 摘要：本次共發現 30 項問題

| 分類 | 項次 | 最高嚴重度 |
|---|---|---|
| A. 評分系統邏輯 | 6 | **P0 — 分數本身是錯的** |
| B. 排序與去重 | 5 | **P0 — 已驗證的環境相依 bug** |
| C. 可讀性與術語 | 5 | P1 |
| D. 排版與格式 | 5 | P1 |
| E. 品牌、防偽與法遵 | 5 | P1 |
| F. 內容缺口 | 7 | P1 / 含 1 項**不實陳述** |
| G. 工程面 | 2 | P2 |

**最需要優先處理的三項**：A1（同一問題被重複扣分）、B1（正式站報告排序是反的）、F1（報告聲稱有 AI 解釋，實際永遠是空的）。

---

## A. 評分系統邏輯（P0）

觀察到的分數：

```
整體分數：39
UX：100    AEO：100    GEO：24    SEO：32    SECURITY：0
```

現行演算法（`scanners.py:1000-1024`）：

```python
severity_penalty = {critical: 35, high: 25, medium: 14, low: 6, info: 2}
category_score = max(0, 100 - sum(每個 finding 的 penalty))
overall_score  = round(已測分類分數的算術平均)
```

### A1. 同一個問題出現在 N 個頁面就扣 N 次分（**根因**）

報告的「發現項目」用 `_group_findings_for_report()`（`reports.py:47`）把重複問題**合併成一筆顯示**，但 `calculate_scores()` 吃的是**合併前的原始 finding 陣列**。

**顯示合併、計分不合併** —— 使用者看到報告裡只有一項「頁面外洩個人資料 (PII)」，卻不知道它在背後被扣了 3 次。

用報告內容反推 SECURITY：

| 項目 | 嚴重度 | 扣分 | 次數 | 小計 |
|---|---|---|---|---|
| 網域未啟用 DNSSEC | 低 | 6 | 1 | 6 |
| DMARC 政策過寬 | 低 | 6 | 1 | 6 |
| 網域缺少 SPF | 中 | 14 | 1 | 14 |
| **頁面外洩個人資料 (PII)** | 高 | 25 | **3** | **75** |
| 表單可能缺少 CSRF token | 中 | 14 | 1 | 14 |
| 缺少 CSP | 中 | 14 | 1 | 14 |
| 缺少 HSTS | 中 | 14 | 1 | 14 |
| 缺少 X-Content-Type-Options | 資訊 | 2 | 1 | 2 |
| 缺少 X-Frame-Options | 低 | 6 | 1 | 6 |
| WAF 保護攔截說明 | 資訊 | 2 | 1 | 2 |
| | | | **合計** | **153** |

`max(0, 100 - 153) = 0`。**單一個 PII 問題就佔掉 153 分裡的 75 分**，只因為它出現在 3 個頁面。

同樣的機制也在 GEO（「核心內容高度依賴 JavaScript 渲染」列了 3 次）與 SEO（「Meta title 長度不理想」列了 4 次）身上發生。

**建議**：計分前先做和報告一樣的去重，或改為「同一 rule_id 首次全額扣分、後續每頁遞減（例如 ×0.3）」，讓「問題廣度」有影響但不主導。

### A2. 線性累加 + 歸零地板，讓分數失去解讀能力

`max(0, ...)` 表示 SECURITY 只要累積 4 個高風險（4 × 25 = 100）就到 0。**0 分無法區分「有 4 個問題」和「有 100 個問題」**，而且對一個只是缺 SPF / DNSSEC / CSP 的網站宣告「資安 0 分」是嚴重誤導 —— 它沒有已知可利用漏洞。

**建議**：改用有下界的衰減（例如 `100 × exp(-Σpenalty / k)`）或分級制（A/B/C/D/E），讓分數永遠落在有意義的區間，並且邊際問題不會把分數壓到失真。

### A3. `info` 等級也扣分 —— 好消息倒扣

`info: 2`。報告最後一項是：

> 「偵測到 Cloudflare … 等 WAF / CDN 保護機制 … **這表示您的網站已部署有效的入侵防護，屬正向安全指標。**」

這筆是 `severity="info"`（`tasks.py:449`），於是**「你有 WAF 保護」這個好消息扣了 2 分**。這是明確的邏輯錯誤。

**建議**：`info` penalty 歸 0，並為「正向指標」新增獨立的 severity（例如 `positive`），在報告中放到獨立的「已做對的事」章節。

### A4. 沒測的分類照樣顯示 100 分

`ARGUS_AGENT_ENABLED` 預設 `False`（`settings.py:295`），UX 根本沒有任何檢查來源。`calculate_scores()` 的 `tested_categories` 機制**只用來把 UX 排除在 overall 平均外**，`category_scores` 仍然回傳 `ux: 100` 並被報告原樣印出。

報告上寫「UX：100」，使用者的解讀是「UX 完美」，實際是「**完全沒測**」。這是整份報告誤導性最強的一項。

**建議**：未測分類顯示「未評估」而非分數，並在摘要說明原因。

### A5. 摘要的 5 個數字算不出整體分數

`(100 + 24 + 32 + 0) / 4 = 39` —— UX 的 100 被排除了，但報告完全沒說。使用者拿 5 個數字怎麼平均都算不出 39，只會得到「這分數是亂給的」的結論。**這正是「看起來很不合理」的直接來源之一。**

### A6. 完全沒有分數說明

報告沒有任何一句話說明分數怎麼算、範圍是多少、幾分算合格、各分類代表什麼。

**建議**：摘要區加「分數如何計算」小節 + 分級對照表（例如 80-100 良好 / 60-79 需改善 / <60 需優先處理）。

---

## B. 排序與去重（P0）

### B1. 正式站的報告排序是反的（**已實測驗證**）

樣本報告的「發現項目」順序：

```
1. 網域未啟用 DNSSEC        低風險    ← 最不重要的排第一
2. DMARC 政策過寬            低風險
3. 網域缺少 SPF              中風險
4. 頁面外洩個人資料 (PII)     高風險    ← 最嚴重的排第四
```

**根因**：`security/` 子套件的 scanner —— `dns_scanner`、`header_scanner`、`cookie_scanner`、`ssl_scanner`、`sri_scanner`、`js_library_scanner`、`service_cve_scanner` —— **全部沒有指派 `priority_score`**（grep 全數 0 命中），欄位是 `null=True`，所以留 `NULL`。

`Finding.Meta.ordering = ["-priority_score", ...]`（`models.py:207`），而 **PostgreSQL 的 `ORDER BY x DESC` 預設是 NULLS FIRST**。

已實測兩種資料庫：

```
PostgreSQL（compose，與正式同款）：NULL, 90.0, 10.0   ← NULL 排最前
SQLite（本機 dev 預設）：            90.0, 10.0, NULL   ← NULL 排最後
```

**所以這是環境相依 bug**：本機用 SQLite 開發時報告排序看起來正常，正式站用 PostgreSQL 才會把所有 DNS / header / SSL / cookie 類問題頂到最前面。開發環境永遠複現不出來。

**建議**：兩件事都要做 —— (1) 補齊 `security/` 各 scanner 的 `priority_score`；(2) `ordering` 改用 `F("priority_score").desc(nulls_last=True)` 讓兩種 DB 行為一致。

### B2. 「優先改善建議」5 個名額只講了 2 件事

```
高風險 / SECURITY：頁面外洩個人資料 (PII)
高風險 / SECURITY：頁面外洩個人資料 (PII)     ← 重複
高風險 / SECURITY：頁面外洩個人資料 (PII)     ← 重複
中風險 / GEO：核心內容高度依賴 JavaScript 渲染
中風險 / GEO：核心內容高度依賴 JavaScript 渲染 ← 重複
```

`calculate_scores()` 的 `top_actions`（`scanners.py:1025`）直接對原始 finding 陣列排序取前 5，**沒有去重**。整份報告最重要的一塊區域被浪費掉了。

### B3. DNS / SSL / header 類問題永遠進不了「優先改善建議」

`top_actions` 排序用 `finding.get("priority_score") or 0` —— 承 B1，這些 scanner 的 `priority_score` 是 `None`，`or 0` 讓它們一律變成 0 分，**排在所有頁面層級問題後面**。即使出現高風險的 SSL 憑證即將過期或 CVE，也不會進優先建議。

### B4. 發現項目的分組鍵選錯

`_group_findings_for_report()` 用 `(rule_id, evidence)` 當合併鍵（`reports.py:54`）。但 `evidence` 含**頁面專屬內容**（例如該頁實際的 title 文字），所以同一種問題在不同頁面的 evidence 不同 → 合併失敗。

實測結果：25 個「發現項目」裡，「Meta title 長度不理想」出現 4 次、「核心內容高度依賴 JavaScript 渲染」3 次、「Meta description」2 次 —— **實際只有約 17 個不同問題**。

**建議**：改用 `rule_id` 當主鍵合併，每個受影響頁面的 evidence 收進子清單。

### B5. `severity` 是字串，排序等於字母序

`ordering` 的第二鍵是 `severity`（CharField）。字母序是 `critical < high < info < low < medium` —— **`info` 排在 `low` 和 `medium` 前面**。這與嚴重度完全無關。

**建議**：加 `severity_rank` 整數欄位，或用 `Case/When` 明確排序。

---

## C. 可讀性與術語（P1）

目標使用者是中小企業網站主，不是資安工程師。目前報告裡直接裸露的內部識別碼：

### C1. 未經翻譯的內部識別碼

| 報告原文 | 問題 |
|---|---|
| `規則 ID：SECURITY_PII_8B24BB8B28` | 內部雜湊，對使用者零意義 |
| `OWASP：A05 / CWE：CWE-345` | 專業標準代碼，未附解釋 |
| `證據來源：rule_engine` | 內部模組名稱 |
| `證據型態：text` | 內部欄位值 |

**建議**：`rule_id` 移到附錄的技術索引；OWASP / CWE 保留但加中文說明與說明連結；`evidence_source` / `evidence_type` 翻成人話（「由規則引擎自動比對」）或直接移除。

### C2. 「Deterministic Evidence」是全篇唯一的英文區塊標題

中文報告裡突然出現英文術語，且「決定性證據」這個概念一般使用者不熟。

**建議**：改為「檢測依據」或「我們看到了什麼」。

### C3. 沒有「這是什麼 / 為什麼危險 / 不修會怎樣」的固定結構

目前每項只有 `description` + `remediation` 兩段，而且 `description` 把「現象描述」和「危害」混在一起。以缺 SPF 為例：

> 網域 clouda.dpdns.org 未設定 SPF（v=spf1）TXT 記錄，攻擊者可偽冒此網域寄送釣魚郵件。

現象和危害擠在同一句，而且「攻擊者可偽冒此網域」對非技術使用者仍然抽象 —— 缺少「會怎樣」（客戶收到假冒你公司的釣魚信、你的正常信件被判垃圾郵件、品牌信任受損）。

**建議**：每項固定四段結構 —— **問題是什麼 → 為什麼要在意（具體後果）→ 怎麼修（分步驟）→ 修好的判斷標準**。

### C4. 標籤與內文用同一個樣式，看不出層次

`風險描述`、`修補方向`、`Deterministic Evidence` 都是 `Normal` 段落，與內文外觀完全相同。實測：**328 段裡有 293 段是 `Normal`**。

### C5. 沒有詞彙表

DNSSEC、DMARC、SPF、CSP、HSTS、CSRF、JSON-LD、canonical URL、X-Frame-Options —— 報告裡出現了 9 個以上未解釋的縮寫。

---

## D. 排版與格式（P1）

實測 `argus-scan-25-report.docx` 的結構：

```
段落總數：328
表格數：  0        ← 全部靠段落堆疊
圖片數：  0
sections：1        ← 沒有任何分頁
樣式分布：Normal 293 / Heading2 25 / List Bullet 5 / Heading1 4 / Title 1
```

### D1. 零表格、零圖片 —— 整份是一條 328 段的純文字流
### D2. 零分頁 —— 章節之間沒有 page break，摘要和發現項目擠在一起
### D3. 沒有封面頁、沒有目錄
25 個發現項目沒有目錄，使用者無法跳讀。
### D4. 沒有頁首、頁尾、頁碼
`python-docx` 的 `section.header` / `section.footer` 完全沒使用。
### D5. 沒有任何顏色或視覺編碼
嚴重度只有文字（「高風險」/「低風險」），沒有紅黃綠色塊；分數只有數字，沒有任何視覺化。

**建議**：封面（目標 / 分數 / 日期 / 報告編號）→ 目錄 → 摘要（分數表格 + 嚴重度統計）→ 優先改善（表格）→ 發現項目（每項一個表格，嚴重度用色塊）→ 附錄（詞彙表 + 技術索引 + 掃描範圍）。章節間加 page break，頁尾放頁碼與報告編號。

---

## E. 品牌、防偽與法遵（P1）

### E1. 全文只出現 1 次「Argus」

只有標題那一次。沒有 logo、沒有頁尾品牌、沒有配色識別。這份文件會被下載、轉寄、存檔給第三方看，目前完全沒有品牌承載。

### E2. 沒有報告編號、產生時間、版本號

只有「掃描完成時間」，沒有「**報告產生時間**」—— 而 `views.py:248` 每次下載都重新產生一份，同一個掃描可以產出內容不同的多份報告（例如 finding 被後續流程補寫），卻無從分辨版本。

### E3. 沒有任何防偽或驗證機制

沒有浮水印、沒有內容雜湊、沒有查驗連結或 QR code。任何人都能用 Word 改掉分數再轉寄，宣稱是 Argus 出具的報告。

**建議**：報告編號（`ARGUS-{scan_id}-{yyyymmdd}-{短雜湊}`）+ 頁尾固定顯示 + 封面放內容 SHA-256 前 16 碼 + 線上查驗頁 `/verify/{報告編號}` 比對雜湊。

### E4. 沒有免責聲明

報告給出資安判斷卻沒有任何範圍限制或免責條款（「本報告基於掃描當下的外部可見資訊，不等同完整滲透測試」）。

### E5. 沒有記載授權來源 —— 對「授權式掃描平台」是關鍵缺漏

專案定位是**授權式**掃描（`AuthorizationConsent` 模型記錄了授權網域、聲明、IP、時間），但 `reports.py` **完全沒有讀取這個模型**。一份對外交付的資安報告，沒有記載「這次掃描是誰在什麼時候基於什麼聲明授權的」，等於放棄了本專案最核心的合規賣點。

**建議**：報告加「掃描授權聲明」章節，帶出 `AuthorizationConsent` 的授權網域、聲明內容、授權時間；主動測試的話額外標註 `active_testing_authorized`。

---

## F. 內容缺口（P1）

### F1. 報告聲稱有 AI 解釋，但該功能從未實作（**不實陳述**）

報告附錄寫著：

> 「…再交由 **AI 進行自然語言解釋與改善建議撰寫**。」

實際上：`ai_explanation` 與 `ai_remediation` 在整個 backend 只被寫入 `""`（`scanners.py:393-394`、`agent/findings.py:93-94`、`katana_scanner.py:82-83`），**沒有任何一處會填入內容**。`reports.py:140` 的 `if finding.ai_explanation or finding.ai_remediation:` 區塊永遠不執行 —— 樣本報告裡「AI 解釋與改善建議」出現 **0 次**。

這不只是功能缺口，而是**一份對外交付的文件裡的不實陳述**。二選一：實作它，或立刻修正附錄措辭。

### F2. 沒有掃描範圍說明

爬了幾頁？哪些頁？被動還是主動模式？深度多少？有沒有頁面被 robots 擋掉？—— 全部沒有。使用者不知道這份報告的涵蓋範圍，也就無法判斷「沒發現問題」代表什麼。

### F3. `warning_summary` 完全沒進報告

`ScanJob.warning_summary` 存了爬取警告、`tech_stack`、`scan_effectiveness`、`agent` 執行結果、`settlement_error`。報告一個字都沒帶。特別是 **`scan_effectiveness = "no_pages_crawled"`** 這個「掃描實質失效」的警示旗標沒進報告，代表一次爬 0 頁的失敗掃描，仍會產出一份看起來正常、只是分數偏高的報告。

### F4. 沒有頁面清單

`Page` 表存了每頁的 URL、標題、HTTP 狀態、載入時間、深度、阻擋原因，`/topology/` API 也已經算好了拓撲。報告完全沒用。

### F5. 截圖存了卻沒放進報告

`Page.screenshot_path` 有資料，`reports.py` 沒有任何 `add_picture()`。資安 / UX 報告缺少視覺佐證，說服力大打折扣。

### F6. `bounding_box` / `selector` 有資料但沒用

前端能標示問題位置，報告不能。

### F7. 沒有與前次掃描的比較

`get_queryset()` 已經有「同 origin 歷史掃描」的概念（`views.py:181`），報告卻沒有「上次 39 分 → 這次 52 分，修好了 3 項」這種最能展現價值的內容。

---

## G. 工程面（P2）

### G1. 每次下載都重新產生報告

`views.py:248` 每次 GET 都呼叫 `build_scan_report()`。對已完成的掃描，報告內容是確定的，應該產生一次後快取。順帶：這也是 E2「版本無從分辨」的成因。

### G2. 報告檔案永久堆積

寫入 `MEDIA_ROOT/reports/scan-N-report.docx`，沒有任何清理機制或保留期限。

> **已確認不是問題**：報告檔案**沒有**對外洩漏風險。`config/urls.py:120` 只顯式路由 `media/review_images/`，`/media/reports/` 沒有對應 route，SPA fallback 又排除了 `media/`，所以直接猜路徑會得到 404。下載一律走 `/api/scans/{id}/report/`，且 `get_object()` 已依 `user` 過濾。

### G3（附帶）測試覆蓋只涵蓋 PII 遮罩

`tests.py` 對 `build_scan_report` 的 3 個測試集中在 PII 遮罩與副檔名，沒有任何測試鎖定排序、去重、分數合理性或報告結構。上述 A / B 類 bug 全部沒有測試防護。

---

## 建議執行順序

| 階段 | 內容 | 理由 |
|---|---|---|
| **第一階段** | A1、A3、A4、A5、B1、B2、B4 | 這些讓**分數和排序本身是錯的**，任何排版美化在數字錯誤的前提下都沒有意義。改動集中在 `calculate_scores()` 與 `_group_findings_for_report()`，可以用測試鎖住。 |
| **第二階段** | F1（先修措辭）、E5、F2、F3 | 涉及**對外陳述的正確性與合規**，改動小、風險低。 |
| **第三階段** | C 全部 + D 全部 | 可讀性與排版重寫。`reports.py` 目前 160 行的線性堆疊需要重構成有樣式系統的產生器，工作量最大。 |
| **第四階段** | E1-E4、F4-F7、G1-G3 | 品牌、防偽、內容擴充與工程優化。 |

**先決條件**：第一階段動手前，需要能重現一份有代表性的掃描資料。compose DB 目前是空的，建議先在 compose 跑一次對授權目標的完整掃描，作為改動前後的對照基準。
