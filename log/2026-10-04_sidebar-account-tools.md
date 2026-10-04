# 網域驗證與 MCP 接入移到側邊欄

**日期**：2026-10-04  
**操作者**：Claude

## 變更內容
- `ProjectWorkspace.jsx`：側邊欄新增「帳號工具」分組（`ACCOUNT_TOOLS`：網域驗證、MCP 接入，圖示＋一行說明）；`ProjectSidebar` 支援沒有專案（只顯示所有專案與帳號工具）與 `activeTool`；新增 `WorkspaceShell`；`/projects` 沒有專案時也顯示側邊欄。
- `App.jsx`：`/domains` 包 `WorkspaceShell activeTool="domains"`，左側同一個側邊欄。`/mcp` 是新版樣式、不在 `MemberLegacy` 內，維持獨立頁。
- `NavActions.jsx`：頭像選單移除網域驗證與 MCP 接入中心（只剩帳號設定、購點與訂閱、管理後台、登出）。
- 樣式：`legacy-member/93-projects.css` 新增 `.project-sidebar-group`（窄螢幕隱藏分組標題，連結接在橫向分頁列後面）。
- 測試：`WorkspaceShell.test.tsx`。文件：`frontend/CLAUDE.md`（順手修正評論入口的過時描述）。

## 原因
使用者要求網域驗證與 MCP 接入工具不要藏在頭像選單，要讓使用者容易看到。

## 驗證方式
- 前端 lint、typecheck、`npm test`、build。
- 本機瀏覽器：有／沒有網站專案時的側邊欄（日／夜）、從側邊欄進入 `/domains` 並標示目前頁、頭像選單項目、390px 無水平捲動、無 JS 錯誤。
