# 建立 PlantUML 圖碼並優化手冊 UML 圖

**日期**：2026-05-31  
**操作者**：Codex

## 變更內容
- 新增根目錄 `PlantUML.md`，集中保存系統手冊中主要 UML / 架構圖的 PlantUML 原始碼。
- 產出 `專題文件/Argus_系統手冊_第三章與UML圖優化版.docx`。
- 重新渲染並替換手冊中的主要系統圖：第三章架構圖、第五章需求模型圖、第六章設計模型圖、第七章實作模型圖與第八章 ER 圖。
- 同步更新部分圖前說明文字，使其符合目前 Argus 實際架構與執行流程。

## 原因
使用者要求建立 `PlantUML.md` 收納 DOCX 中所有 UML 圖碼，並優化 DOCX 內 UML 圖，使其更符合 Argus 系統架構與運行流程。

## 影響範圍
- 僅新增 Markdown 圖碼與新版 DOCX 文件。
- 未修改程式碼、設定檔、資料庫或原始 DOCX。

## 驗證方式
- 使用本機 PlantUML jar 將 `PlantUML.md` 中 13 個圖碼區塊渲染為 PNG。
- 使用 `python-docx` 確認 13 個目標圖題前皆存在替換後圖片。
- 使用 Microsoft Word COM 開啟新版 DOCX 並匯出 PDF 成功，總頁數 53。
