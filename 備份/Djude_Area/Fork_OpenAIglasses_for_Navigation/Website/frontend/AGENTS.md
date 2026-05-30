<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-19 | Updated: 2026-05-19 -->

# Website/frontend（React + Vite 前端）

## 用途

展示網站前端與管理後台。Vite + React + TailwindCSS，含公開站台（首頁、產品、團隊、公告、購買）與獨立管理後台 SPA。

## 關鍵檔案 / 目錄

| 路徑 | 用途 |
|------|------|
| `package.json` | 相依與 scripts |
| `vite.config.js` | Vite 設定（含 `/api` 代理） |
| `tailwind.config.js` / `postcss.config.js` | 樣式設定 |
| `Dockerfile` / `nginx.conf` | 生產建置與靜態服務 |
| `index.html` | HTML 進入點 |
| `src/main.jsx` / `src/App.jsx` | React 進入點與根路由 |
| `src/api/client.js` | 後端 API 客戶端 |

## 子目錄（src/）

| 目錄 | 用途 |
|------|------|
| `pages/` | 路由頁：`Home` `Product` `Team` `Project` `Announcements` `Download` `Purchase`(+`PurchaseResult`) `NotFound` |
| `components/` | 共用元件：`Navbar` `Footer` `FloatingCart` `ModelViewer`（3D）`Toast` `Skeleton` `ScrollReveal` `ScrollToTop` `CountUp` `ErrorBoundary` |
| `context/` | 全域 Context：`CartContext` `ContentContext` `ThemeContext` |
| `admin/` | 管理後台 SPA：`AdminApp` `AdminLogin` `api.js`、`components/`（`Modal` `Sidebar`）、`sections/`（Dashboard、Accounts、Products、Orders、Announcements、PageContent、TeamMembers、DeviceMonitor、VoiceDetection、ServerConfig、AppDevice、ActivityLogs） |

## For AI Agents

### 在本目錄工作

- 註釋繁體中文；遵守 `Website/CLAUDE.md`
- 維持公開站台與 `admin/` 分離；API 呼叫統一走 `src/api/client.js` / `admin/api.js`
- 不硬編碼後端網址，走相對 `/api` 與 Vite/nginx 代理

### 測試要求

- 改動後 `npm run build` 須成功；參考 `web-test` skill 前端章節
- 涉及 API 的頁面需配合後端起服務做整合驗證

### 常見模式

- 頁面置於 `pages/<Name>/<Name>.jsx`；跨頁狀態用 `context/`

## 相依

### 內部
- `Website/backend` REST API

### 外部
- React、Vite、TailwindCSS、3D 模型檢視（ModelViewer 使用 `../aiglass.glb`）

<!-- MANUAL: 此線以下手動註記在重新產生時會保留 -->
