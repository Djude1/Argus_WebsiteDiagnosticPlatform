# PDF 報告摘要加入「改一處就能一起解決」

**日期**：2026-10-08  
**操作者**：Claude

## 變更內容
- **`reports._report_root_causes`**：用和問題分析頁「依根本原因」同一套歸類（`root_causes.py`），放進 `summary.root_causes`。
  - 每組內容：原因、在哪裡修、對應的第 4 章項次。
  - 資訊提示不列。
- **`report_render`**：第一章「建議先處理這 3 件事」之後新增「改一處就能一起解決」小節。
  - `schema.json` 新增 `summary.root_causes`。
  - `RENDERER_VERSION` 改為 18，舊報告下載時會重新產生。
- **文件**：roadmap、scans CLAUDE.md、需求書。

## 驗證方式
- **`tests_root_causes.py` 新增 2 項**：
  - payload 的項次對應第 4 章，資訊提示不列。
  - 產生的報告含這一節。
- **報告相關測試**：`tests_report_payload`、`tests_report_score_items` 一起重跑通過。
- **用示範專案最新一次掃描（本機沙箱資料庫）轉 PDF 檢視第 2 頁**：
  - 列出兩組：回應標頭（4.4、4.5）、SPF／DMARC（4.7、4.8）。
  - 版面正常，沒有把分數圖擠到下一頁。
- 全套後端測試、`ruff check backend`。
