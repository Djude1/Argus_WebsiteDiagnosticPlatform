# /download PWA 安裝修復 + /team 四宮格 UI

**日期**：2026-06-10
**操作者**：Claude

## 變更內容

**1) /download：「查看安裝步驟」改成可真正安裝的「點擊下載」**
- `frontend/src/main.jsx`：在 app 進入點**全域捕捉** `beforeinstallprompt`，存到
  `window.__argusInstallPrompt` 並派發 `argus-installable` 事件；`appinstalled` 時設旗標。
- `frontend/src/App.jsx` `useInstallPrompt`：改為掛載時先讀 `window.__argusInstallPrompt`、
  並監聽 `beforeinstallprompt` / `argus-installable` / `appinstalled`；新增 `isStandalone()`
  以 `display-mode: standalone` 與 `navigator.standalone` 偵測已安裝。
- `DownloadPage` hero 按鈕：三分支簡化為單一「⬇ 點擊下載」——可安裝時直接 `trigger()` 跳出
  瀏覽器安裝視窗；不可安裝（iOS Safari 或事件未就緒）時捲到「安裝步驟」。

**2) /team：四宮格 + 多 icon + RWD**
- `frontend/src/App.jsx` `TeamMemberCard`：學號徽章加 🎓；技能熟練度區加 `⚡ 技能熟練度` 小標；
  負責項目標題加 🎯；技術棧 chips 上方加 `🧩 技術棧` 小標。
- `frontend/src/styles.css`：`.public-team-grid-pro` 由 4 欄改 **2×2 四宮格**（`max-width:1040px` 置中），
  手機（≤640px）單欄；新增 `.public-team-block-label`（區塊小標）與 `.public-team-skills-label`
  （flex-basis:100% 讓技術棧小標獨佔一行）；含 light theme 對應。

## 原因

使用者回報公開站 `https://xn--gst.tw/download` 的「查看安裝步驟」按鈕只會往下捲、**無法安裝 PWA**。
根因：`beforeinstallprompt` 常在 React 掛載前觸發，而原本只在 `DownloadPage` 掛載後才掛監聽 →
事件錯過 → `canInstall=false` → 落到只會捲動的 fallback。並要求團隊頁改四宮格、多用 icon、好看且 RWD。

## 影響範圍

- 公開頁 `/download`（安裝行為）與 `/team`（版面）。皆為前端，需 build 後生效。
- iOS Safari 不支援程式化安裝（瀏覽器限制）→ 該情境按鈕仍是捲到步驟、由使用者手動「加入主畫面」，非程式可控。
- 純前端改動，不動後端 / API / DB。

## 驗證方式

- 本機 `docker compose -p argusnew up -d --build frontend` 重建成功（exit 0）。
- `/download`、`/team` 皆回 HTTP 200。
- 重建後 JS bundle 含「點擊下載」「argus-installable」「技能熟練度」；CSS bundle 含
  `public-team-block-label` 與 `repeat(2,minmax(0,1fr))`（四宮格）。
- 需使用者肉眼確認（瀏覽器，Ctrl+Shift+R）：
  1. `/team` 為 2×2 四宮格、各卡片有 🎓⚡🎯🧩 icon、手機縮為單欄。
  2. `/download` 在 Chrome/Edge 顯示「⬇ 點擊下載」，點擊跳出瀏覽器安裝視窗（需可安裝狀態）。
