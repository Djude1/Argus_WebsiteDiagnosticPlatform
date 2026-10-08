# 優化系統手冊圖 3-1-2 與圖 3-1-3

**日期**：2026-06-01  
**操作者**：Codex

## 變更內容

- 新增兩張統一視覺風格的 PNG 圖：
  - `專題文件生成/argus_3_1_2_scan_data_flow.png`
  - `專題文件生成/argus_3_1_3_scanjob_state_controls.png`
- 以 `專題文件/Argus_系統手冊_第三章優化版_3-1-1架構圖優化.docx` 為基底，輸出：
  - `專題文件/Argus_系統手冊_第三章優化版_3-1圖組優化.docx`
- 替換圖 3-1-2「掃描任務執行資料流圖」：
  - 改為使用者、PWA、Django API、Redis、Celery Worker、Playwright、Scanners、Hermes Agent、PostgreSQL、授權目標網站與報告的左至右資料流。
  - 將合規先行與狀態回寫獨立為輔助區塊，避免主流程線條混亂。
- 替換圖 3-1-3「ScanJob 核心狀態與橫切機制圖」：
  - 改為主狀態線：queued → crawling → scanning → agent_testing → completed。
  - 將取消與失敗改成匯流排形式，減少多條交叉箭頭。
  - 橫切控制獨立呈現授權、爬蟲邊界、帳務、進度與稽核。
- 三張 3-1 圖均使用一致米色背景、灰色虛線邊界與相近色彩語意。

## 原因

使用者指出原本圖 3-1-2 與圖 3-1-3 的架構流程不清晰、不容易理解，希望比照圖 3-1-1 的形式重新優化，並統一背景顏色。

## 影響範圍

- 僅影響系統手冊第三章圖 3-1-2、圖 3-1-3，以及新增圖片素材。
- 未修改前後端程式碼、資料庫或部署設定。

## 驗證方式

- 使用 `python-docx` 檢查新 DOCX：
  - 圖 3-1-1 圖片為 1900×1160。
  - 圖 3-1-2 圖片為 1900×1080。
  - 圖 3-1-3 圖片為 1900×1060。
  - 三張圖 caption 均保留原本圖號與文字。
- 使用 Word COM 將新 DOCX 匯出 PDF 成功，確認 Word 可正常開啟與轉檔。
- `render_docx.py` 因本機缺少 LibreOffice/soffice，無法完成 PNG render QA。
