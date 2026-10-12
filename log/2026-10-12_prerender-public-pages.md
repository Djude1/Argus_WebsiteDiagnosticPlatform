# 公開頁建置時預先渲染（修正「核心內容高度依賴 JavaScript 渲染」）

**日期**：2026-10-12  
**操作者**：Claude

## 變更內容
- `frontend/package.json` build 改成三步：`vite build` → SSR build（`src/entry-server.jsx`）→ `scripts/prerender.mjs`，
  把 12 個公開網址（`App.jsx` 的 `PRERENDERED_ROUTES`）寫成 `dist/<路徑>.html`（`/` 是 `root.html`），並換上各頁標題與摘要
- `main.jsx`：root 有預先渲染內容時先 `preloadRoute()` 再 `hydrateRoot`
- `App.jsx`：
  - `lazyNamed()` 加 `.preload()`，已載入就不經 Suspense
  - 開場動畫改成掛載後才顯示，`restoreSession` 等 hydrate 完成（`startTransition`）才呼叫
  - `/` 與 `/project` 共用 `ProjectEntry`：`/` 先顯示產品介紹，確認登入狀態後才轉址
- Node 端不能用的寫法加判斷：`CsrfField`（document）、`useInstallPrompt`（window）
- `ScannerInfoPage`：說明文字直接渲染，只有 API 的設定值顯示「讀取中…」
- 提供方式：`frontend/nginx.conf`、`k8s/05-frontend.yaml` 改成 `try_files $uri $uri.html …`，並加上 `/` → `root.html`（`nginx-conf-revision` 改為 "4"）；
  Django `config/urls.py` 的 `spa_page` 本機做同樣的事（直接讀檔，不經模板引擎）
- 測試：`apps/content/tests_spa_fallback.py`、root `tests/test_frontend_prerender_contract.py`
- 文件：根 `CLAUDE.md`／`AGENTS.md`、`backend/CLAUDE.md`、`frontend/CLAUDE.md`（Build 規則新增預先渲染規則）

## 原因
使用者要求修 Argus 自掃報告「核心內容高度依賴 JavaScript 渲染」（9 頁）。SPA 的 index.html 只有空的 root，
不執行 JavaScript 的爬蟲與 AI 讀不到內容（規則：原始 HTML 文字量 < 渲染後的 50%）。

過程中處理的問題：
- React 串流輸出逐段轉字串會拆壞中文字，改用 `renderToString`
- hydrate 途中收到 store 更新會出 React #421
- `/` 原本立即轉址，與預先渲染的內容不一致（#418）
- `/` → `/project` 換元件造成整頁重掛，CLS 0.79

## 影響範圍
- 首次載入公開頁時，瀏覽器先顯示預先渲染的 HTML，再由 React 接手
- 已登入使用者開公開頁時，導覽列會從未登入狀態切成已登入。React 會重畫該區塊，沒有錯誤
- 要部署：前端 image 重建後，`frontend` Deployment 才會因 ConfigMap 註解變更而重啟
- 資料靠 API 的內容（方案價格、評論列表）仍在瀏覽器端載入

## 驗證方式
- 本機 production build＋Django，用 Argus 爬蟲＋`analyze_page` 實爬 15 頁：
  - 「核心內容高度依賴 JavaScript 渲染」0 頁（原本 /scanner 以外都已消失，/scanner 改版後也消失）
  - JavaScript 執行期錯誤 0；/scanner 的 CLS 項也不再出現
- Playwright 開 12 個公開頁（React development build）：無 hydration 錯誤或警告
- CLS：`/` 0.032、`/project` 0.032（首次進站含開場動畫）
- 測試帳號登入後 `/` 仍轉到會員區，公開頁無 pageerror。該帳號已刪除（連帶刪除本機 DB 中這個帳號的錢包與首次贈點交易）
- 後端 `manage.py test apps` 1924 項 OK（skipped=3）；ruff 通過
- 前端 lint（0 error，1 個既有 warning）、typecheck 通過，vitest 289 項全過
- root `tests/`：新契約測試通過；`test_kali_k8s_contract` 因本機沒有 kubectl 報錯，與本次無關
