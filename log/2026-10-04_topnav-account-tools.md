# 網域驗證與 MCP 接入改放頂部導覽列、搜尋框縮短

**日期**：2026-10-04  
**操作者**：Claude

## 變更內容
- `TopNav.jsx`：搜尋框右側新增工具連結（`NAV_TOOLS`：網域驗證 `/domains`、MCP 接入 `/mcp`，線條圖示＋文字，目前頁淺藍底、`aria-current`）；搜尋框與工具包在 `.nav-search-row`（寬螢幕 `display: contents`）。
- `64-project-switcher.css`：搜尋框縮短（`flex: 0 1 300px; max-width: 320px`，原 `1 1 420px / 560px`）；新增 `.nav-tools`／`.nav-tool-link`；≤1080px 工具只留圖示（文字改為視覺隱藏，仍是可及名稱）；≤920px 第二列是搜尋＋工具；≤560px 圖示鈕縮為 2.3rem。
- 撤回 `cc928cb` 的側邊欄「帳號工具」：`ProjectWorkspace.jsx`、`App.jsx`（`/domains` 不再包 `WorkspaceShell`）、`legacy-member/93-projects.css` 回到該 commit 之前；刪除 `WorkspaceShell.test.tsx`。頭像選單維持不放這兩項。
- 測試：新增 `features/account/TopNav.test.tsx`。文件：`frontend/CLAUDE.md`。

## 原因
使用者回饋側邊欄加了帳號工具後太長、需要捲動；要求把網域驗證與 MCP 接入放到頂部導覽列，並縮短搜尋框騰出空間。

## 驗證方式
- 前端 `npm run lint`、`npm run typecheck`、`npm test`、`npx vite build` 全部通過。
- 本機瀏覽器（Playwright）在 1440／1180／1080／920／390px、日／夜主題截圖檢查 `/domains` 頂部列：無水平捲動，目前頁淺藍底，窄螢幕工具與搜尋同列。
