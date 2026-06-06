# 修正 PlantUML title 相容性

**日期**：2026-05-31  
**操作者**：Codex

## 變更內容
- 修改 `PlantUML.md`，移除 13 個 PlantUML code block 內的 `title ...` 指令。
- 保留 Markdown 小節標題作為圖名，避免不同 PlantUML 版本在 code block 內解析 `title` 時出現語法錯誤。

## 原因
使用者回報 PlantUML 1.2026.4 beta 在多個圖碼的第 2 行 `title ...` 顯示 Syntax Error。

## 影響範圍
- 僅影響 `PlantUML.md` 圖碼相容性。
- 未修改 DOCX 文件與程式碼。

## 驗證方式
- 重新抽出 `PlantUML.md` 中 13 個 ```plantuml code block。
- 使用本機 PlantUML jar 執行 `-failfast2 -tpng`，13 張圖均成功產生 PNG。
