# 後台方案／公告管理頁修正深色卡片殘留，統一為全站淺色材質語言

**日期**：2026-08-03
**操作者**：Claude
**呼叫者**：無檔案 import 此變更涉及的內部函式；純 UI 呈現層，無資料檔案異動。

## 背景

使用者要求「後台其他頁面也做優化，統一特色風格」，延續前一輪 `/admin/overview` 的 Linear × Stripe 材質重設。逐一排查後發現 `/admin/plans`(方案管理)與 `/admin/announcements`(公告管理,僅 superuser)兩頁的卡片元件(`.admin-plan-card`、`.admin-ann-card`)從未被前幾輪重設觸及,仍是**深色卡片**(`background: var(--bg-card, #1e293b)` + 淺色文字),直接插在淺色 `.admin-main` 頁面背景中間——這是全站唯二還留著舊深色主題殘影的頁面,也是實際登入後台用 chrome-devtools MCP 截圖才親眼確認到的落差(先前只靠讀 CSS/JSX 沒有實際跑起來看,這次才發現)。同時發現多處與 `.admin-plan-card`/`.admin-ann-card` 搭配的按鈕/徽章/提示框仍殘留離品牌色(`#6366f1` indigo、`#0891b2` 舊 cyan 不一致色階),以及跨全站共用的確認彈窗按鈕 `.ann-btn-confirm` 也是同一個 indigo。

## 變更內容

- `.admin-plan-card`/`.admin-ann-card`:深色底 + 淺灰邊框改為與 `.admin-panel`/`.admin-stat-card` 同一套材質(白底、`rgba(15,23,42,.07)` 細邊框、18px 圓角、兩層柔和陰影、hover 浮起)。
- 文字色從「淺色文字配深底」全部反轉為「深色文字配白底」(`#e2e8f0`→`#0f172a` 等)。
- `.admin-plan-price` 改用品牌 cyan token(原本是離品牌的淺紫 `#818cf8`);`.admin-plan-badge`(折扣徽章)、`.admin-add-btn`(新增按鈕)、`.admin-sub-tab.active`、`.ann-btn-confirm`(全站共用確認彈窗的確定按鈕)統一改用 `.admin-btn.primary` 同一組 cyan 漸層,取代原本分散的 indigo/舊 cyan 混用。
- `.admin-ann-type.temporary`/`.ann-modal-type-chip`(公告「臨時」標籤)從 indigo 淡底改為 cyan 淡底;`.permanent` 維持 red(語意正確,不動)。
- `.admin-page-note`(方案頁的定價建議提示框)原本背景/文字都是深色主題殘留值,在淺色頁面上文字對比度過低幾乎看不清,改為淺 cyan 淡底 + 深色文字。
- `.ann-modal`(全站共用的確認/表單彈窗本體)刻意**不改**:它是 `useConfirmDialogs()` 共用元件,全站十幾處呼叫皆固定用深色浮層,是一致的既有設計(類似 command palette 的浮層慣例),本身沒有「這頁跟那頁不一樣」的問題,只修了裡面唯一離品牌色的確定按鈕。

## 檔案

- `frontend/src/styles.css`:改 `.ann-btn-confirm`、`.ann-modal-type-chip`、`.admin-add-btn`、`.admin-ann-*`、`.status-active/inactive`、`.admin-sub-tab.active`、`.admin-plan-*`、`.admin-page-note` 共約 15 條規則。未動 `frontend/src/features/admin/AdminPages.jsx`(JSX 結構不變,純換色/材質,class name 不變)。

## 影響範圍

- `/admin/plans`、`/admin/announcements` 兩頁卡片外觀;全站共用確認彈窗的確定按鈕顏色。
- 未觸及:`/login` 頁(`.login-*` 系列,深色主題正確、不在「後台」範圍)、前台使用者 `/settings`(`.settings-*` 系列,前台深色主題正確、非本次「後台」範圍)、`.ann-modal` 彈窗本體深色底。

## 驗證方式

- `npm run build`(WSL/Linux Node 20):✓ 2039 modules、4.86s、無錯誤
- `docker compose build frontend && docker compose up -d --no-deps frontend`:成功
- 本機已安裝 `google-chrome-stable` + `fonts-noto-cjk`(上一輪任務新增),用 chrome-devtools MCP 實際登入 bootstrap superuser 帳號,逐頁截圖驗證:
  - `/admin/plans`:4 張方案卡確認皆為白底、cyan 價格數字、cyan 折扣徽章,與 Overview 頁材質一致
  - `/admin/announcements`:公告卡確認白底、紅色「常駐」標籤、按鈕可讀
  - `/admin/users`:確認未受影響、原本就已是一致的淺色風格
- **未覆蓋**:`AdminUserDetailPage`、`AdminScanDetailPage`、`AdminCmsManager`、`AdminSettingsPage` 內部共 11 處 `<h3>` 面板標頭尚未補上 Overview 頁那種圖示 chip(非壞掉,只是還沒延伸這個裝飾性細節),因單次任務範圍與成本考量本輪先聚焦「深色卡片」這個實際壞掉的一致性問題,未做這項純裝飾性延伸,待使用者確認是否需要再做。
