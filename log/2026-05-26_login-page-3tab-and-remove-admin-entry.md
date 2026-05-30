# LoginPage 改為 3-tab 並移除前台後台入口

**日期**：2026-05-26
**操作者**：Claude（implement subagent）

## 變更內容

### `frontend/src/App.jsx`
- 重寫 `LoginPage` 元件（原本 12 行的 wrapper 改為 ~200 行的 3-tab 完整登入頁）：
  - 三個 tab：Google 登入 / Email 登入 / 新帳號
  - Email 登入呼叫 `/auth/email-login/`
  - 新帳號呼叫 `/auth/register/`（前端先檢查兩次密碼一致）
  - Dev 跳過登入按鈕僅在 `import.meta.env.DEV` 顯示
  - 登入成功後跳轉：若 `?next=` 為空、為 `/login`、或不是以 `/` 開頭，預設導 `/dashboard`，否則導 `next`
  - 已登入時直接 `<Navigate to={redirect} replace />`，避免回到 login 頁閃白
- 刪除 `AccountBar` 中的 `admin-entry-chip`（前台右上角「🛡️ 後台」按鈕），staff 進後台改由直接打字 URL 或從 Dashboard 入口
- 刪除舊的 `LoginForm` 元件（變成孤兒）

### `frontend/src/styles.css`
- 末尾新增 `.login-page` / `.login-card` / `.login-tabs` / `.login-tab` / `.login-form` / `.login-submit` / `.login-google-wrap` / `.login-dev-btn` / `.login-error` / `.login-notice` 等樣式

## 原因
Phase 1 Task 1.4：
1. 統一登入入口，讓使用者一頁能完成 Google、Email 登入與註冊三種流程
2. 前台不再露出 admin 入口（資安考量 + UI 簡化）

## 影響範圍
- `/login` 頁面外觀與行為完全更新
- 前台右上角 staff 不再有「後台」chip；要進管理後台需手動輸入 `/admin/overview`
- `LoginForm` 元件移除，但沒有其他地方引用，無破壞
- styles.css 末尾新增區塊，不影響既有樣式

## 驗證方式
- `cd frontend; .\build-node22.ps1` → vite build 成功（266 modules，無 error）
- grep 確認沒有殘留 `LoginForm` 引用
- grep 確認沒有殘留 `admin-entry-chip` JSX 使用（CSS 規則保留無妨）
