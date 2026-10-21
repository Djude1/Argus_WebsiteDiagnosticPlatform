# 側邊欄「頁面」改名「頁面分析」

**日期**：2026-10-21
**操作者**：Claude

## 變更內容
- 使用者可見文字一律由「頁面」改「頁面分析」（網址 `/projects/:id/pages` 與程式內 key `pages` 不變）：
  - `frontend/src/features/projects/ProjectWorkspace.jsx`：側邊欄項目 label。
  - `frontend/src/shared/documentTitle.ts`：該頁 `<title>`。
  - `frontend/src/components/navigation/CommandSearch.jsx`：⌘K 搜尋的分頁名稱。
  - `frontend/src/features/projects/ProjectPages.jsx`：`ProjectHeader section`（麵包屑與頁首）。
  - 提及「頁面」分頁的說明文字：`ScanExperience.jsx`（掃描詳情導流）、`OptimizationResultPage.jsx`（優化進行中提示）、`PageRebuildPanel.jsx`／`App.jsx` 註解。
- 文件同步：`frontend/CLAUDE.md` 路由表與檔案表、`專題文件生成/需求書_複賽版完整內容.md`。

## 原因
使用者覺得側邊欄「頁面」這個名字怪；同欄其他項目是「SEO 分析／資安分析／問題分析」，依使用者選擇改成同句型的「頁面分析」。

## 驗證方式
- `npm run lint`：0 error；`npm run typecheck`：clean；`npx vitest run`：50 檔 305 個測試全過。
