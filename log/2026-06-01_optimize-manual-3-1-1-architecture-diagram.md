# 優化系統手冊圖 3-1-1 系統架構圖

**日期**：2026-06-01  
**操作者**：Codex

## 變更內容

- 新增 `專題文件生成/argus_3_1_1_system_flow.png`。
- 依使用者提供的參考圖片形式，重繪 Argus 圖 3-1-1：
  - 保留前端/後端虛線邊界。
  - 使用圖示化方式呈現 User、Argus PWA、Django REST API、PostgreSQL、Redis Queue、Celery Worker、Playwright Crawler、四維掃描、Hermes Agent、AI Provider、授權目標網站與互動報告。
  - 將主流程整理為由左至右：User → PWA → Django API → Redis/Celery → Playwright → 掃描器/Agent → 報告回前端。
  - 將合規邊界、進度/取消/結算、same-origin/robots/depth/page limits 放在輔助路徑，避免主流程混亂。
- 因 `Argus_系統手冊_第三章優化版.docx` 當下被 Word 鎖定，已輸出新檔：
  - `專題文件/Argus_系統手冊_第三章優化版_3-1-1架構圖優化.docx`

## 原因

使用者希望將 `3-1-1` 系統架構圖改成參考圖片那種清楚的系統流程圖形式，避免原先分層架構圖資訊過多、視覺上較雜。

## 影響範圍

- 僅影響系統手冊第三章圖 3-1-1 與新增圖片素材。
- 未修改前後端程式碼、資料庫或部署設定。

## 驗證方式

- 使用 `python-docx` 檢查新 DOCX：
  - 圖 3-1-1 對應圖片已更新為 1900×1160 PNG。
  - caption 保持 `圖 3-1-1　Argus SaaS 分層系統架構圖`。
  - inline shape 尺寸維持原本版面大小。
- 使用 Word COM 將新 DOCX 匯出為 PDF，確認 Word 可正常開啟與轉檔。
- `render_docx.py` 因本機缺少 LibreOffice/soffice，無法完成 PNG render QA。
