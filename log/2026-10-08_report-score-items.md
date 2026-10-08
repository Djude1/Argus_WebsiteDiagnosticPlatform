# PDF 報告附錄加入各分類扣分明細（roadmap 優先序第 4 項）

**日期**：2026-10-08  
**操作者**：Claude

## 變更內容
- **`reports._report_score_items`**：資料來自 `score_explain.score_explanation`，和網頁「分數說明」分頁是同一份。
  - **每個分類的內容**：
    - 分數。
    - 起始分：一般是 100；AEO 是可回答性分數。
    - 逐項扣分：項次、項目、嚴重度、扣分、出現處、只修好這項時的分數。
    - 說明幾筆問答結果已計入起始分、幾筆資訊提示不扣分。
  - **項次**：以 `rule_id` 對回第 4 章的卡片編號。
  - **分數依目前公式加不回保存值時**（舊版公式或事後重新判定）：只寫一行原因，不列表。
  - **匯入方式**：`score_explain` 在函式內匯入，避免 `score_explain → finding_normalization → reports` 循環匯入。
- **`report_render`**：
  - 附錄新增「6.6／6.7 各分類扣分明細」：有 AEO 逐題表時是 6.7，沒有時是 6.6。
  - `schema.json` 新增 `appendix.score_items`。
  - `RENDERER_VERSION` 改為 17，舊報告下載時會重新產生。
- **文件**：scans CLAUDE.md、roadmap、需求書（報告段落）。

## 驗證方式
- `tests_report_score_items.py`，5 項：
  - payload 符合 schema，扣分、出現處、只修好這項時的分數、項次都正確。
  - AEO 起始分的說明。
  - 舊公式的分數只附說明。
  - 未計分的掃描沒有這一節。
  - 實際產生的報告含表格。
- **實際轉成 PDF 看版面**（LibreOffice）：第 8 頁的 SEO、AEO、資安三個分類顯示正常。
  - 欄寬在 LibreOffice 裡平均分配；報告既有的表格也是這樣，不是這次造成的。
- 全套後端測試、`ruff check backend`。
