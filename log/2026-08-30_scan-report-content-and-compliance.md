# 掃描報告品質改善 第二階段：對外陳述、授權聲明、掃描範圍與警示

**日期**：2026-08-30
**操作者**：Claude
**依據**：[`docs/scan-report-quality-audit-2026-08-30.md`](../docs/scan-report-quality-audit-2026-08-30.md) 第二階段（F1、E5、F2、F3）
**前一階段**：[`2026-08-30_scan-report-scoring-and-ordering-fix.md`](2026-08-30_scan-report-scoring-and-ordering-fix.md)（commit `bf1f738`）

## 變更內容

### 1. `backend/apps/scans/reports.py` — 附錄不再聲稱 AI 撰寫解釋（F1）
- 舊文：「…再交由 **AI 進行自然語言解釋與改善建議撰寫**。」
- `Finding.ai_explanation` / `ai_remediation` 在整個 backend 只被寫入空字串（`scanners.py`、`agent/findings.py`、`katana_scanner.py` 三處），該功能從未實作，`reports.py` 印出它的分支永遠不執行。
- 改為只描述實際做到的事：證據來自爬蟲與規則引擎、報告產生過程不使用 AI 改寫或推論。
- 同時把附錄改為 `本報告如何產生` 子章節。

### 2. `backend/apps/scans/reports.py` — 新增「掃描授權聲明」（E5）
- `_add_authorization_section()` 讀 `AuthorizationConsent`，輸出授權網域、授權時間、主動測試授權與授權聲明全文。
- **刻意不寫入 `ip_address`、`user_agent` 與授權帳號**。報告會被下載轉寄給第三方，授權人的 IP 與瀏覽器指紋是個資，對收件者零價值只增加外洩面；稽核需求走 DB 與 `AdminAuditLog`。有專屬測試鎖定這條界線。
- 查無授權紀錄時明確寫「查無授權紀錄」，不讓章節消失（否則收件者會以為「有授權只是沒印」）。

### 3. `backend/apps/scans/reports.py` — 新增「掃描範圍」章節（F2）
- 輸出掃描範圍（單頁／全網站）、探測模式、頁數與深度上限、**實際掃描頁數**、是否遵守 robots.txt。
- `scope` 取自 `scan_plan.build_scan_execution_plan()`，不在 `reports.py` 重複「`max_pages==1` 代表單頁」的慣例，避免兩邊漂移。

### 4. `backend/apps/scans/reports.py` — 新增「掃描警示」章節（F3）
- 帶出 `warning_summary` 中對收件者有意義的項目：`scan_effectiveness=no_pages_crawled`（掃描實質失效）、`blocked_urls` 與 `failed_urls` 的頁數、`tech_stack`。
- **`settlement_error`（計費結算）與 `agent` 的 token 用量刻意不輸出**，屬內部運維資訊。有測試鎖定。
- 沒有任何可報告項目時整個章節不出現。

### 5. `backend/apps/scans/scanners.py` — `info` 不進 `top_actions`（第一階段補漏）
- 實際產出一份報告目視檢查時發現：「優先改善建議（依影響程度排序）」列出了「資訊提示 / Nuclei 探針受 WAF 攔截」，而它的建議修補寫的是「無需修復」。
- 第一階段只把 `info` 的 penalty 改成 0（不扣分），漏了 `top_actions` 這一半。已排除，並補測試。

### 6. 新增 `backend/apps/scans/tests_report_content.py`（9 項測試）
涵蓋附錄措辭、授權聲明輸出、**IP／UA／帳號不得外洩**、查無授權要明講、掃描範圍與實際頁數、單頁標籤、爬 0 頁警示、略過／失敗頁數彙總、**內部計費錯誤不得外洩**。

### 7. 文件同步
- `backend/apps/scans/CLAUDE.md`：新增「報告內容契約」章節（必須有／絕對不能寫進報告兩張表），並在分數契約補上「`info` 同樣不進 `top_actions`」。同時記載 `ai_explanation` 等 4 個欄位目前是死欄位。

## 原因

第二階段的共同性質是**對外陳述的正確性與合規**，不是排版美化：

1. **F1 是不實陳述**。報告是對外交付文件，聲稱有一個從未實作的功能，比缺少該功能更嚴重。實作 LLM 解釋是獨立的功能專案（需要 provider、成本與延遲設計），不屬於「修正對外陳述」，因此本階段只修措辭。
2. **E5 是本專案的核心賣點**。Argus 定位是授權式掃描，`AuthorizationConsent` 存了授權網域與聲明，報告卻完全沒讀。
3. **F2 決定報告可不可信**。不知道掃了幾頁、什麼模式，「沒發現問題」就沒有意義。
4. **F3 是誤導防線**。`scan_effectiveness=no_pages_crawled` 代表掃描實質失效，沒帶進報告的話，一次爬 0 頁的掃描會產出看起來正常、只是分數偏高的報告。

## 影響範圍

- **報告新增 3 個章節**（掃描範圍、掃描警示、掃描授權聲明），既有章節與 finding 呈現未變動。
- **`top_actions` 不再含 `info` 項目**。極端情況下（全部發現都是 info）「優先改善建議」會是空的，此時報告只會有一個空標題——這個既有行為第三階段的排版重寫會一併處理。
- **未動**：`security/redaction.py` 的 PII 遮罩規則、狀態機、billing、`security/` 子套件、前端。
- 舊掃描資料照樣可產出報告：`AuthorizationConsent` 不存在時顯示「查無授權紀錄」，`warning_summary` 為空時不出現警示章節。

## 驗證方式

- `uv run ruff check backend` → All checks passed
- `uv run python backend/manage.py test apps` → **Ran 709 tests，OK（skipped=1）**（第一階段後 699，+9 內容測試 +1 top_actions 測試，無回歸）
- **實際產出一份報告並逐段目視檢查**（暫時 SQLite + scratchpad media root，未動 dev DB）。確認：
  - 同一問題跨 3 頁確實合併成一筆並列出 3 個受影響頁面（舊版會列 3 次）
  - 摘要顯示「UX：未評估」，其餘 4 個分類平均 91.25 → 整體分數 91，對得起來
  - 授權聲明有網域／時間／聲明全文，**沒有 IP、沒有 UA、沒有帳號**
  - 掃描警示有失敗頁數與技術棧，**沒有 settlement_error**
  - 優先改善建議依 priority 排序（SPF 中風險 → Meta title 低風險）
- **目視檢查抓到測試沒抓到的問題**（第 5 項的 `info` 進 top_actions），已修並補測試。

## 未處理／待決事項

- **`SCORE_DECAY_CONSTANT = 50.0` 仍待你確認**（第一階段列的同一項）。
- **受影響頁面的排列順序是反的**（`p2、p1、p0`）。成因是 `Finding.Meta.ordering` 最後一個鍵是 `-created_at`，同一問題的多筆 finding 其他鍵完全相同。純呈現問題，留給第三階段排版一併處理。
- **「優先改善建議」全空時只會留下一個空標題**，同上留給第三階段。
- **`ai_explanation` / `ai_remediation` / `llm_model` / `llm_generated_at` 四個死欄位仍在 model 裡**。本階段只停止對外聲稱，沒有移除欄位也沒有實作功能——這是產品決策，需要你決定「實作」或「移除」。
- 第三階段（C 可讀性與術語 + D 排版格式）尚未開始，這是工作量最大的一段（`reports.py` 需重構成有樣式系統的產生器）。
- **compose DB 仍是空的**，兩個階段的驗證都來自單元測試與腳本產出的樣本報告，**沒有跑過一次真實掃描的端到端報告**。
