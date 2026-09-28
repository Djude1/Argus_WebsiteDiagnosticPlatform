# 會員區 Dashboard／掃描／網域驗證／歷史／購點恢復為 462848b 版本

**日期**：2026-09-28  
**操作者**：Claude

## 變更內容
- **JSX 恢復為 `462848b`**（Night Watch 改版前）：
  - `features/account/DashboardPage.jsx`、`HistoryPage.jsx`、`BillingPage.jsx`、`SubscriptionPanel.jsx`：由當時 `AuthenticatedPages.jsx` 的對應段落拆回（維持現行「一頁一檔、`AuthenticatedPages.jsx` 只 re-export」的結構）。
  - `features/scans/ScanExperience.jsx`（列表／建立表單、互動報告、拓樸）、`RebuildWorkspace.jsx`、`features/domains/DomainVerifyPage.jsx`、`components/scans/FixOutputSection.jsx`、`PageRebuildPanel.jsx` 整檔恢復。
  - 保留改版後才加入的功能：建立掃描表單的估價補回 AI Agent UX 測試附加費（`wallet.agent_ux_fee`，全網站且勾 UX 時計收），維度說明列顯示這筆。
  - 刪除改版時拆出、恢復後不再使用的檔案：`ScanLayout.jsx`、`ScanDetailPage.jsx`、`TopologyPage.jsx`、`components/scans/{FindingDetail,FindingsGroupList,ReportHeader,ReportSummary,ScanJobForm,ScanList,ScanProgress,ScreenshotViewer}.jsx`、`AccountStates.jsx`、`components/brand/IrisScore.tsx`。
- **舊版樣式限縮套用**：
  - 新增 `src/styles/legacy-member/`：由當時 `src/styles/*.css` 過濾出這五頁用得到的規則（檔名與順序不變），`90-compat.css` 補共用元件（`AppShared.jsx`）改版後的差異（嚴重度／類別色、長條圖 `sev-*`、`color-scheme`）；`00-tailwind.css` 以 `@config` 使用 `tailwind.member-legacy.config.js`（當時設定、系統字型）。
  - 新增 `postcss-member-legacy.js`（掛在 `postcss.config.js` 的 tailwind 之後）：所有舊規則加 `:is(.member-legacy, #…)` 前綴（ID 等級特異度），範圍內元素先 `all: revert` 擋掉新版同名 class；`:root`／`html`／`body` 規則改掛在包裝上，`.argus-app`／`.argus-main` 改 `:has()`，keyframes 加 `ml-` 前綴。
  - `App.jsx` 新增 `MemberLegacy` 包裝（`display: contents`）包住 `/dashboard`、`/scans/*`、`/domains`、`/history`、`/billing`。
  - `04-app-shell.css`：這五頁的導覽列改不透明底（半透明玻璃在舊版淺灰底上會被透成灰色）。
  - 清掉因刪除元件而成為孤兒的新版規則（`05`、`10`、`11`、`13`、`14`、`15`、`16`、`19`、`60`、`61`，只刪 HEAD 時仍有使用、現在已無任何程式引用的選擇器）。
- `package.json`：`postcss-selector-parser` 由 tailwind 的間接相依改為明確 devDependency（外掛直接 import，版本同 lock 既有的 6.1.2）。

## 原因
使用者要求把 Dashboard、掃描、網域驗證、歷史、購點頁全部換回 `462848b` 的版本（延續同日公開頁恢復改版前視覺的處理）。導覽列、設定頁不在要求內，維持改版後版本。

## 影響範圍
- 只影響上述五類路由（含 `/scans/:id`、拓樸、複刻工作區）；導覽列、設定、登入、後台、公開頁不變。
- 已知與 462848b 的差異：`CountUp` 數字改版後加了千分位（例 `1,280`）；估價多出 AI Agent UX 附加費一行。
- 舊版本身在 390px 寬的 Dashboard 與掃描詳情頁有水平捲動（462848b 即如此），本次照原樣恢復、未修正。
- 文件同步：`frontend/CLAUDE.md`（樣式規範、核心檔案）、`docs/brand-guidelines.md`（適用範圍、移除 IrisScore／ghost-button）、`argus-ui-design` skill（`.claude` 與 `.agents` 兩份）。未改對外功能，競賽 Word 內容 md 不需同步。

## 驗證方式
- `npm run lint`（0 error，1 個既有 warning）、`npm run typecheck`、`npm test`、`vite build` 全部通過。
- 以 mock API 用 Playwright 截圖比對（1440／390 × 深／淺，只比 `<main>`）：
  - 本次 vs 462848b：`/dashboard`、`/scans`、`/scans/:id`、`/domains`、`/history`、`/billing` 在 1440 寬差異 0–0.1%（`/scans` 1.6% 為新增的附加費說明行）；390 寬 2–4% 為整頁約 1px 垂直位移與千分位。
  - 本次 vs 修改前（HEAD）：`/settings`、`/project`、`/purchase`、`/free-tools`、`/verify`、`/download` 全部 0%（`/project` 0.1% 為動圖）。
  - 檢查 build 產物：956 條舊規則全部帶範圍前綴，沒有未限縮的規則外洩。
- 未能驗證：後台頁面未截圖（舊樣式全部限縮在 `.member-legacy`，後台不含此包裝）；真實後端資料下的畫面需人工確認。
