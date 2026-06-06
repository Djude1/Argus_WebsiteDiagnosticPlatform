# 2026-05-31 PlantUML.md 專業化優化紀錄

## 本次調整

- 重建 `PlantUML.md`，移除先前可能殘留的衝突標記與亂碼內容。
- 保留 13 張系統手冊所需 UML 圖，並重新整理為一致的 Markdown 標題與 PlantUML 區塊格式。
- 因 PlantUML 1.2026.4beta4 對 `title` 指令出現相容性錯誤，本版不在圖內使用 `title`，改由 Markdown `## 圖...` 作為圖名。
- 統一圖面樣式：
  - 指定 `Microsoft JhengHei` 字型。
  - 關閉陰影、使用一致圓角與配色。
  - 依架構層級區分用戶端、API、領域服務、掃描執行、資料層與外部服務。
- 強化圖面內容，使 UML 更貼近 Argus 專案實際架構：
  - React/Vite/Tailwind/Zustand 前端。
  - Django 5/DRF 後端與各 app 邊界。
  - Celery/Redis/Playwright 非同步掃描流程。
  - 點數 reserve/settle/refund 計費流程。
  - 授權聲明、same-origin、robots.txt、Active 掃描額外授權與 RPS 限制。
  - AI Provider 與 Agent 分析流程。

## 驗證

- 使用本機 PlantUML jar 進行渲染驗證：
  - `C:\Users\Jie\.vscode\extensions\jebbs.plantuml-2.18.1\plantuml.jar`
- 已抽出全部 13 個 `plantuml` 區塊並以 `-failfast2 -tpng` 渲染。
- 驗證結果：13 張 PNG 全部成功產生。
