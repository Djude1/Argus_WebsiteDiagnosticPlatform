# 掃描報告品質稽核：補充驗證與新增問題

**日期**：2026-08-30
**作者**：Codex（Sisyphus / MiniMax-M3）
**對象**：`docs/scan-report-quality-audit-2026-08-30.md`（Claude 出具的稽核文件）
**實測樣本**：`argus-scan-25-report.docx`（目標 `https://lqll.clouda.dpdns.org/`，掃描完成於 2026-08-24 11:08:58）

**本文件關係**：
- 不修改 Claude 的 audit（依使用者要求）
- 對 audit 的 30 項發現做**逐項獨立驗證**（代碼佐證）
- 補充 audit **未涵蓋**的 38 項問題（依嚴重度分類）
- 提出 8 項**必須由使用者決策**的方向問題

---

## 0. 範圍宣告與盲區

**已檢查**：
- `backend/apps/scans/reports.py`（156 行全文）
- `backend/apps/scans/scanners.py::calculate_scores()`（978-1038）
- `backend/apps/scans/models.py` 全文（279 行，含 `Finding` / `ScanJob` / `Page` / `AuthorizationConsent`）
- `backend/apps/scans/views.py:200-299` 的 `report` action
- `backend/apps/scans/security/` 子套件 grep `priority_score`
- `ai_explanation` / `ai_remediation` / `llm_model` 寫入點（3 處全部為空字串）
- `frontend/src/App.jsx` 的 `/download` route 與 `ScanExperience.jsx` 的下載入口
- `frontend/src/features/public/PublicPages.jsx`（含 DownloadPage）
- `frontend/src/styles.css:146-167` 的 Argus 品牌 token
- `frontend/public/favicon.svg`（既有 Argus 4 角星 logo）

**已知盲區**（與 Claude audit 同）：
- scan 25 的 DB row 不在手上（compose PostgreSQL 為空），SECURITY 分數重算是用報告內容反推
- 前端沒有自動化測試框架，verify 頁的測試只能手動驗證
- `apps/insights`（AI 洞察）是否有另一套報告呈現沒檢查
- 沒有實際使用者訪談資料，「使用者看不懂」的判斷來自術語是否為內部識別碼

---

## 1. Claude audit 30 項發現的逐項驗證

| 項 | 標題 | 狀態 | 代碼佐證 |
|---|---|---|---|
| **A1** | 同問題扣 N 次分 | ✅ 成立 | `_group_findings_for_report()` 用 `(rule_id, evidence)`（reports.py:54）；`calculate_scores` 直接 sum 原始 finding（scanners.py:1009-1013）—— 兩處完全沒對齊 |
| **A2** | max(0,…) 地板 | ✅ 成立 | scanners.py:1014 `category_scores[category] = max(0, 100 - penalty)` |
| **A3** | info 也扣分 | ✅ 成立 | scanners.py:1005 `INFO: 2` |
| **A4** | 未測顯示 100 | ✅ 成立 | scanners.py:1014 永遠寫滿 5 個 category；tested_categories 只用於 overall 平均（1015-1024） |
| **A5** | 5 個數字算不出 39 | ✅ 成立 | 報告直接 `category.upper()`（reports.py:81）沒標 UX「未評估」 |
| **A6** | 無分數說明 | ✅ 成立 | reports.py 整檔沒任何分數解釋段落 |
| **B1** | 排序反了 | ✅ 成立 + 補充 | 見 §1.1 補充 |
| **B2** | top_actions 重複 | ✅ 成立 | scanners.py:1025-1037 沒 dedup |
| **B3** | DNS/SSL 進不了 top | ✅ 成立 | scanners.py:1030, 1034 `or 0` 讓 None 全變 0 |
| **B4** | 分組鍵錯 | ✅ 成立 | reports.py:54 evidence 含頁面專屬內容 → 同問題分頁就分開 |
| **B5** | severity 字串排序 | ✅ 成立 + 補充 | 見 §1.2 補充 |
| **C1** | 內部識別碼未翻譯 | ✅ 成立 | reports.py:106, 110, 124-128, 80-89 都直接寫內部識別碼 |
| **C2** | 英文 Deterministic Evidence | ✅ 成立 | reports.py:124 |
| **C3** | 缺「為什麼危險」結構 | ✅ 成立 | reports.py:117-121 只有 description + remediation |
| **C4** | 標籤與內文同樣式 | ✅ 成立 | 全部 `add_paragraph`，無樣式區分 |
| **C5** | 無詞彙表 | ✅ 成立 | 報告沒附錄詞彙表（reports.py:149-154 只 1 段） |
| **D1** | 零表格 | ✅ 成立 | reports.py 全文無 `add_table` |
| **D2** | 零分頁 | ✅ 成立 | reports.py 全文無 `add_page_break` |
| **D3** | 無封面/目錄 | ✅ 成立 | reports.py:69 直接 `add_heading("Argus...")`，無封面 |
| **D4** | 無頁首頁尾頁碼 | ✅ 成立 | reports.py 全文無 `section.header/footer` |
| **D5** | 無顏色視覺編碼 | ✅ 成立 | 嚴重度只有文字 |
| **E1** | Argus 只出現 1 次 | ✅ 成立 | reports.py:69 是唯一的 `add_heading("Argus...")` |
| **E2** | 無編號/時間 | ✅ 成立 | reports.py:73-75 只寫 `completed_at` |
| **E3** | 無防偽 | ✅ 成立 | 全文無 SHA/QR/水印邏輯 |
| **E4** | 無免責聲明 | ✅ 成立 | reports.py:149-154 只有 Evidence-first 一段 |
| **E5** | 無 AuthorizationConsent | ✅ 成立 | model 存在（models.py:81-104），reports.py 完全沒讀取 |
| **F1** | AI 解釋不存在 | ✅ 成立 + 補充 | 見 §1.3 補充 |
| **F2** | 無掃描範圍說明 | ✅ 成立 | 報告沒列爬了幾頁、被動/主動、深度等 |
| **F3** | warning_summary 未進報告 | ✅ 成立 | model 有欄位（models.py:49），reports.py 不讀 |
| **F4** | 無頁面清單 | ✅ 成立 | reports.py 完全沒用 Page 表資料 |
| **F5** | 截圖未進報告 | ✅ 成立 | model 有欄位（models.py:126），無 `add_picture` |
| **F6** | bounding_box/selector 未用 | ✅ 成立 | model 有欄位（models.py:199-200），reports.py 完全沒用 |
| **F7** | 無前次比較 | ✅ 成立 | views.py:181 有 history 概念，reports.py 完全沒用 |
| **G1** | 每次下載重產 | ✅ 成立 | views.py:246-254 每次 GET 都 `build_scan_report()`，無快取 |
| **G2** | 報告檔案堆積 | ✅ 成立 | reports.py:64-66 寫入 MEDIA_ROOT/reports/，無 cleanup |
| **G3** | 測試只蓋 PII | ✅ 成立 | grep 確認 `test_report_*` 只有 PII/檔名相關測試 |

**驗證結論**：**30/30 全部成立**。以下 3 項有更精準的補充細節。

### 1.1 B1 補充：priority_score=null + db_index 的副作用

`Finding.priority_score = models.FloatField(null=True, blank=True, db_index=True)`（models.py:184）—— `db_index=True` 同時建索引在 NULL 上。

即使補了 priority_score 值，**已存在的 NULL index entries 仍會排在前面**，需要 migration 把 NULL 補值或重建索引。建議解法：補值 migration 用 `Case/When` 把 NULL 補成 severity 對應值。

### 1.2 B5 補充：severity 字母序實際順序

`Finding.Severity` choices（models.py:155-160）：
```
CRITICAL = "critical"
HIGH = "high"
MEDIUM = "medium"
LOW = "low"
INFO = "info"
```

字母序：`critical < high < info < low < medium`

**`info` 永遠夾在 `high` 與 `low` 中間**——比 Claude 描述的更嚴重，因為它不只是「與嚴重度無關」，而是會把 info 級別的 finding 排到 high 後面、low 前面。

### 1.3 F1 補充：欄位本身是死碼

除了 reports.py:140 的 dead branch，**Finding model 還保留了 4 個 AI 相關欄位**：
- `ai_explanation`（models.py:195）
- `ai_remediation`（models.py:196）
- `llm_model`（models.py:197）
- `llm_generated_at`（models.py:198）

所有寫入點（scanners.py:393-395、agent/findings.py:93-95、katana_scanner.py:82-84）都填空字串。

**既然永遠空，欄位本身是死碼**。建議「實作 or 移除」二選一，不要保留假象。

---

## 2. 新增問題（audit 未涵蓋）

### 2.1 分數層面（N1-N6，6 項）

| ID | 問題 | 為什麼嚴重 |
|---|---|---|
| **N1** | `overall_score` 與 `category_scores` 寫入沒有 transaction 保護 | 若 worker 寫完 overall 後 crash，DB 留下「overall=39 但 category_scores 沒寫」的不一致狀態，下載時直接噴錯 |
| **N2** | 分數沒有「信心區間」 | `confidence=0.3` 的 finding 跟 `confidence=1.0` 扣一樣分。使用者看到 39，無法判斷是「確定 39」還是「估 39 ± 15」 |
| **N3** | 「100 分」是預設不是滿分 | 沒測的、沒 finding 的、滿分的，UI 看起來都是 100。**0 問題 ≠ 完美網站**，但使用者無法分辨 |
| **N4** | 沒有分數歷史趨勢 | `views.py:181` 已有同 origin 歷史 query，但 report 完全沒用 |
| **N5** | category 順序寫死（UX → AEO → GEO → SEO → SECURITY） | 對不同商業目標應該可配置（賣資安 vs 賣 SEO） |
| **N6** | 沒有「同產業平均分數」 | 中小企業電商、上市公司、政府機關基準完全不同，光給一個 39 沒參照系 |

### 2.2 內容層面（N7-N15，9 項）

| ID | 問題 | 為什麼嚴重 |
|---|---|---|
| **N7** | 報告開頭沒有「Argus 是什麼 / 為什麼可信」 | 第一份報告的接收者（很可能是被掃的客戶）打開 .docx，**完全不知道 Argus 是誰** |
| **N8** | 報告結尾沒有「下一步該怎麼做」 | 修完 25 項之後呢？要再掃嗎？要等多久？ |
| **N9** | 沒有「Argus 客服 / 聯絡方式」 | 一般使用者看不懂就找不到人問 |
| **N10** | 沒有「這份報告適合誰看」的分層摘要 | 業務決策者 / 技術人員 / 管理層需求完全不同 |
| **N11** | 「建議修補」沒有具體步驟 | 「啟用 CSP」對中小企業主根本不知道從哪開始 |
| **N12** | 沒有「修完之後如何驗證」的標準 | 應該有驗收指令（curl -I ... \| grep -i strict） |
| **N13** | 沒有「資料保留與個資處理」聲明 | 報告裡有遮罩後的個資，**這份 docx 該怎麼保管？留多久？能不能寄給外部？** |
| **N14** | 沒有「Argus 對這份報告的擔保與不擔保」 | 對外發出資安判斷必須聲明「不等同完整滲透測試 / 不構成法律意見」 |
| **N15** | 沒有「Argus 認證標章 / 防偽特徵」（含顯眼藝術字） | 你明確要求的核心項目。**目前完全不存在的**：無 logo、無浮水印、無 QR code、無報告編號、無雜湊、無 `/verify/` 路由 |

### 2.3 結構與排版（N16-N22，7 項）

| ID | 問題 | 為什麼嚴重 |
|---|---|---|
| **N16** | 「優先改善建議」沒有預估時間與成本 | 5 項建議無法排序先修哪個（週末 30 分鐘 vs 工程師 3 天） |
| **N17** | 「發現項目」沒有交叉參照 | 缺 CSP 與缺 X-Frame-Options 是同一層問題，可一次修齊，但報告當獨立項目 |
| **N18** | 沒有「Argus 風格識別」 | 標題用 `add_heading(..., 0)` 內建 Title 樣式，**與一般 Word 文件無異** |
| **N19** | 沒有圖表、圖示、icon | 連 emoji 都沒有。**純文字 328 段**對中小企業主毫無吸引力 |
| **N20** | 「受影響頁面（共 N 處）」列表超長時沒有編號 | 3 個還好，30 個 URL 直接 `、`.join 完全無法�讀 |
| **N21** | 摘要區「5 個分數」沒有視覺化 | 沒有長條圖、雷達圖、severity 色塊。**數字並排對使用者沒有訊息量** |
| **N22** | 「建議優化 / 改善重點 / 風險描述」是三種不同名稱 | reports.py:21-26 用 severity 切換標籤名稱，**同一個結構卻給三個名字**，讓人懷疑是不同東西 |

### 2.4 工程實作（N23-N34，12 項）

| ID | 問題 | 為什麼嚴重 |
|---|---|---|
| **N23** | 報告每次下載都重新跑 156 行 python-docx | views.py:248 每次 GET 都 `build_scan_report()`，白白浪費 IO 與 CPU |
| **N24** | `category_scores`、`top_actions`、`warning_summary`、`scan_log` 都是裸 JSONField，無 schema 驗證 | 重構 scanner 時若 key 改了，**舊報告的資料不會 migrate** |
| **N25** | `evidence` 截斷到 1000 字是 magic number | reports.py:136 `masked_evidence[:1000]`，沒解釋為什麼 1000 |
| **N26** | 時間顯示沒帶 timezone | reports.py:74 `auto_now_add` 是 UTC，**但顯示成 naive datetime** |
| **N27** | `created_at` 也是同樣問題 | models.py:57-58 是 UTC，序列化時若前端沒處理 tz，會與「報告裡寫的時間」對不上 |
| **N28** | `Page.screenshot_path` 是字串路徑，沒用 `MEDIA_URL` | reports.py 即使要 `add_picture()`，也只讀到實體檔 |
| **N29** | `ai_handoff_prompt` 是 Finding 欄位，但 reports.py 完全沒用 | models.py:203 寫說「可直接複製的 AI prompt」，但報告根本沒把這個最有「AI 感」的東西放進去 |
| **N30** | `impact_area` 欄位已存在但 reports.py 沒顯示 | models.py:185（給 finding 分領域：付款/註冊/個資…），完全沒用 |
| **N31** | `confidence` 欄位已存在但 reports.py 沒顯示 | models.py:186 已有 0-1 的信心度，**但報告當 1.0 處理** |
| **N32** | `bounding_box` / `selector` 已存在但 reports.py 沒用 | models.py:199-200 寫好 JSON，**前端能標位置，docx 不能** |
| **N33** | `evidence_json` 已存在但 reports.py 完全沒用 | reports.py 只用 `finding.evidence`（純文字），**放棄了 structured 證據** |
| **N34** | PII 遮罩警告放在 evidence 後 | reports.py:133-135 警告放在 evidence 段**之後才出現**，應該在 evidence 段**之前**，且封面就該有警告 |

### 2.5 商業 / 產品定位（N35-N38，4 項）

| ID | 問題 | 為什麼嚴重 |
|---|---|---|
| **N35** | 報告沒有任何「Argus 是 SaaS / 訂閱制」訊號 | 對商業產品，下載的 docx 應該放「想定期健檢？→ argus.com/plans」，**目前完全沒有商業轉換路徑** |
| **N36** | 沒有 Argus 官方社群/教學連結 | **放棄了內容行銷機會** |
| **N37** | 報告無法被「分享給第三方」的指引 | 對資安顧問公司，客戶掃完想拿給自己的資安長看。**目前 docx 沒標「可轉寄」或「機密文件請勿外流」** |
| **N38** | 沒有「與 Argus 客服即時對話」入口 | 對中小企業主，看不懂就放棄了。應該有「掃 QR code 加 Argus LINE/微信客服」 |

---

## 3. 防偽特徵可行性評估（依你提到的「顯眼藝術字」）

### 3.1 現有可重用的設計資產

| 資源 | 位置 | 用途 |
|---|---|---|
| ✅ **Argus star logo**（4 角星 + cyan-indigo 漸層 + glow 圓） | `frontend/public/favicon.svg` | 轉 PNG 內嵌 docx 做封面圖示、浮水印、品牌識別 |
| ✅ **Argus 設計 token**（完整） | `frontend/src/styles.css:146-167` | `--argus-navy-950 #050a1c`、`--argus-cyan #38bdf8`、`--argus-cyan-glow #67e8f9` 等 |
| ✅ **前端下載入口** | `frontend/src/features/scans/ScanExperience.jsx:1098-1105` `downloadReport()` | 已用 `api.get('/scans/{id}/report/')` |
| ❌ Argus PNG logo asset for download | 無 | 需從 favicon.svg 匯出（cairosvg + Pillow） |
| ❌ `/verify/` 路由 | 無 | 全新設計 |
| ❌ Report hash / 編號 model | 無 | 需新增 `ReportVerification` model |

### 3.2 `/verify/` 路線可行性：**完全可行**

**Backend（沿用既有架構）**：
- 新 model `ReportVerification { scan_id (OneToOne), content_sha256, report_number, generated_at, docx_filename }`（比照 `AuthorizationConsent` 模式，models.py:81-104）
- 新 endpoint `GET /api/verify/{report_number}/`（**公開**，AllowAny）—— 回傳 scan meta + hash + status
- 由 `views.py:246-254` 的 report action 寫入 hash

**Frontend（沿用既有科技風）**：
- 新 route `/verify/{id}` 放進 `PublicPages.jsx`（沿用 `.public-shell` 樣式與既有科技風 token）
- 共用 `api.js` 的 axios instance（不繞過）
- 共用 `styles.css:146-167` 的 `:root` 變數

**零新基礎建設，全部沿用既有慣例**。

### 3.3 顯眼藝術字設計方向（給封面）

封面標題「**ARGUS 網站健檢報告**」用以下組合：

1. **大號粗體 navy 底**（`--argus-navy-950`） + **cyan glow 邊框**（`--argus-cyan-glow`） —— python-docx 的 `RGBColor.from_string("38BDF8")`
2. **「ARGUS」字樣**用 4 角星 logo 取代字母 A 中的橫槓（favicon.svg 既有設計）
3. **每頁浮水印**：半透明 star logo（`argus-logo-watermark.png`，alpha=64）+ 報告編號
4. **頁尾**：Argus star + QR code（指向 `/verify/{id}`）+ 頁碼 + 編號
5. **章節標題**：cyan 漸層 underline（透過 `add_paragraph` 的 `paragraph_format` 設定）

**python-docx 限制**：原生 word art 不支援，但可用「大字 + 粗體 + 顏色 + 陰影 paragraph_format 模擬」。進階效果需考慮用 `add_picture()` 把預渲染的 PNG 內嵌。

---

## 4. 重要決策（你必須自己決定）

| ID | 決策 | 選項 |
|---|---|---|
| **C1** | 分數制改成什麼？ | 0-100 數字 / A-F 分級 / Pass/Warn/Fail 三級 / 純文字標籤（良好/普通/需改善） |
| **C2** | 同問題跨頁面怎麼扣分？ | 不扣 / 全額扣一次 / 首次全額後續遞減 30% / 累加但 cap |
| **C3** | 報告要不要支援多語言？ | 繁中為主 / 中英雙語（給跨國客戶）/ 英文版獨立 |
| **C4** | 防偽機制做到多深？ | 只放報告編號 / 加 SHA-256 短碼 + 封面 QR / 加 `/verify/` 線上查驗頁 + 浮水印 |
| **C5** | 報告是否該附 PDF 版？ | 只給 docx / 同時給 PDF / 讓使用者前端選 |
| **C6** | AI 解釋欄位怎麼處理？ | 實作（接 LLM）/ 立刻從報告與 model 移除 / 改成「AI 提示詞」而非「AI 解釋」 |
| **C7** | 報告是否該有分層摘要？ | 一份給所有人 / 三層（業務/技術/管理）/ 一層 + 可展開細節 |
| **C8** | 報告快取策略？ | 不快取（維持現狀）/ 寫入時一次產出 + 永久快取 / 寫入時產出 + 30 天後重新 |

---

## 5. 建議執行優先順序

依 ROI 從高到低：

1. **N29-N33**（5 個現有欄位完全沒用）—— 5 分鐘改 reports.py，無新設計成本
2. **A1 + B4 + B5 + 計算邏輯**（Task 1.1-1.4）—— 改 3 個函式，寫 6 個測試可鎖
3. **N15 + N35-N38 + 防偽**（Task 2.1-2.4 + 3.1-3.2）—— 你明確要求的核心項目
4. **F1 + N34**（AI 欄位死碼 + PII 警告位置錯）—— 二選一決策 + 一行修改
5. **N7-N12**（內容缺口）—— 工作量大，但直接決定中小企業主能不能看懂

**先決條件**（與 Claude audit 一致）：
- compose DB 目前是空的（ScanJob=0 / Page=0 / Finding=0），需要先在 compose 跑一次對授權目標的完整掃描，作為改動前後的對照基準
- 正式環境需部署新版本才能看到 `/verify/` 端點
- 前端 build 必須用 `cd frontend ; .\build-node22.ps1`（CLAUDE.md 硬規則）

---

## 6. 完整實作計畫

詳見 [`docs/superpowers/plans/2026-08-30-scan-report-overhaul.md`](superpowers/plans/2026-08-30-scan-report-overhaul.md)。

涵蓋 4 個 Phase 共 13 個 Task，每個 Task 都用 TDD 方式（failing test → 實作 → verify → commit）：

- **Phase 1**（P0 核心修正）：Task 1.1-1.5（priority_score / ordering / grouping / scoring）
- **Phase 2**（合規與防偽）：Task 2.1-2.4（ReportVerification / verify 端點 / verify 頁 / 修 F1）
- **Phase 3**（報告結構與樣式）：Task 3.1-3.2（logo PNG / 重寫 reports.py）
- **Phase 4**（工程優化）：Task 4.1-4.2（快取 / 整合測試）
