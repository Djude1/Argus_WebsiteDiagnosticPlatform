# 前端 UI/UX 修補：品牌 ICON、settings 對比、掃描頁導覽、後台 logo 回前台

**日期**：2026-06-09
**操作者**：Claude

## 背景
本地 `main` 落後 `origin/main` 26 個 commit（組員推了被動安全 scanner 等），已分叉無法直接 push。
依使用者指示「以組員為準、只負責 UI/UX」，採 **cherry-pick 路線**：從最新 `origin/main`
開分支 `ui-fix-on-origin`，只把前端 UI/UX 改動疊加上去，**計分（移除 UX 維度、scanners.py 去重）完全不含**、留在本地 `ac49ef7` 不推。

## 變更內容
- `frontend/index.html`：分頁 favicon / shortcut icon / apple-touch-icon 由舊菱形 `favicon.svg`、`pwa-icon.svg` 改指向品牌眼睛圖 `/brand-logo.png`。（og:image / twitter:image 社群分享卡設定未動。）
- 新增 `frontend/public/brand-logo.png`：複製自 `src/assets/brand-logo.png`，讓 favicon 能以根路徑 `/brand-logo.png` 取得。
- `frontend/src/App.jsx`（疊加到組員最新版本，僅兩處 UI 改動）：
  - 後台 `AdminLayout` 左上 logo 由菱形字符 `⟡` 改為品牌眼睛圖 `brandLogo`；外層 `<div className="admin-brand">` 改為 `<button onClick={replayIntro}>`，點擊重播開場動畫並導向 `/project`，行為與前台 logo 一致 → 後台 logo 可點回前台。
  - `TopNav` 依 `location.pathname.startsWith("/scans")` 過濾掉「評論」導覽項：掃描頁不顯示評論入口，首頁等其他頁保留。
  - 註：計分相關的 `CATEGORY_FILTERS` 移除 ux 選項**未納入**，保持組員版本。
- `frontend/src/styles.css`：
  - `.settings-field label` 顏色 `#64748b` → `#94a3b8`，修正帳號設定（含名字/姓氏 label）灰到看不清的對比。
  - `.admin-brand` 改直排並加按鈕重置（`border:none` + 保留 `border-bottom`、`background:transparent`、`cursor:pointer`、`:hover` 高亮）；移除孤兒樣式 `.admin-brand-glyph`、`.admin-brand-title`，新增 `.admin-brand-logo`。

## 原因
使用者實機回報四點：(1) 分頁與後台 ICON 沒換成品牌 logo；(2) `/settings` 帳號設定字體灰色看不清（含姓名設定）；(3) 進掃描頁後 top bar 不需要「評論」跳轉；(4) 後台點 logo 要能像前台一樣跳回前台。

## 影響範圍
- 瀏覽器分頁 icon、後台側邊欄品牌區、`/settings` 頁、前台 TopNav（掃描頁）。
- 後台 logo 由純顯示變為可互動按鈕；點擊重播開場動畫並導向前台首頁。
- 後端、計分邏輯完全未動（以組員 `origin/main` 為準）。

## 驗證方式
- **diff 乾淨**：staged 僅 UI 四檔（index.html / brand-logo.png / App.jsx / styles.css）；`App.jsx` staged diff 只有 TopNav、AdminLayout 兩處 UI 改動，無 `CATEGORY_FILTERS` 與任何 scanners.py 計分混入。
- **CSS/JSX 一致**：`.admin-brand-glyph` / `.admin-brand-title` 在 App.jsx 與 styles.css 皆零殘留（無孤兒）；`.admin-brand-logo` 定義（styles.css）與使用（App.jsx）配對。
- **依賴存在**：`brandLogo`（`./assets/brand-logo.png`）import 已存在；`replayIntro` 為 store 既有（組員 TopNav 已使用同一函式）。
- **本機無法 build**（已知環境限制：本開發機無 `D:\node22` 與 `node_modules`）→ vite build 待部署機 / 有 node22 環境確認。
- 待使用者肉眼確認（強制重整 Ctrl+Shift+R）：分頁 icon、後台 logo、settings 對比、掃描頁無評論、後台 logo 點擊回前台。
