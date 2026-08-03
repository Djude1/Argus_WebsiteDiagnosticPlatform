# 後台剩餘 11 個面板標頭補上圖示 chip，新增 AdminAlertIcon

**日期**：2026-08-03
**操作者**：Claude
**呼叫者**：無檔案 import 此變更涉及的內部函式；純 UI 呈現層，無資料檔案異動。

## 背景

延續前一輪「統一特色風格」，補齊上次記錄裡列為「未覆蓋」的 11 個 `.admin-panel h3` 標頭圖示，讓 `AdminUserDetailPage`、`AdminScanDetailPage`、`AdminCmsManager`(`/admin/content` 用)、`AdminSettingsPage` 也跟 Overview 頁一樣,每個面板標頭都有圖示 chip。

## 變更內容

- `frontend/src/components/admin/AdminIcons.jsx`:新增 `AdminAlertIcon`(警示三角形 + 驚嘆號,沿用同一套 IconShell/右上角 ⟡ 品牌角標語言),供「錯誤訊息」面板使用——現有圖示中沒有語意合適的可用。
- `frontend/src/features/admin/AdminPages.jsx`:11 處 `<h3>` 全部包上 `<span className="admin-panel-icon-chip">`,圖示對應:
  - `AdminUserDetailPage`:基本資料→`AdminUsersIcon`、點數錢包→`AdminTransactionsIcon`、調整點數→`AdminSettingsIcon`、AI 使用量→`AdminTokensIcon`、最近 30 筆交易→`AdminOrdersIcon`
  - `AdminScanDetailPage`:狀態→`AdminScansIcon`、結果摘要→`AdminOrdersIcon`、各類別分數→`AdminTrendIcon`、錯誤訊息→`AdminAlertIcon`(新)
  - `AdminCmsManager`(`{schema.title}`,內容管理各分類共用)→`AdminContentIcon`
  - `AdminSettingsPage` 的 `Section` 共用元件(計費/Hermes-Agent/Email 寄送/第三方登入 API 金鑰/部署,5 個呼叫點共用同一元件)→統一用 `AdminSettingsIcon`:系統設定頁是唯讀系統狀態總覽,5 個分類本質上都是「系統設定分類」,用同一圖示比硬湊 5 個語意不同但其實都很勉強的圖示更誠實,也避免過度發明弱語意圖示。

## 檔案

- `frontend/src/components/admin/AdminIcons.jsx`
- `frontend/src/features/admin/AdminPages.jsx`(11 處 `<h3>` + import 清單新增 `AdminAlertIcon`)

## 驗證方式

- `npm run build`(WSL/Linux Node 20):✓ 2039 modules、4.10s、無錯誤
- `docker compose build frontend && docker compose up -d --no-deps frontend`:成功
- chrome-devtools MCP 實際登入截圖驗證:
  - `/admin/settings`:5 個區塊皆正確顯示 gear icon chip
  - `/admin/users/1`:5 個面板圖示皆正確且彼此可辨(人像/硬幣/齒輪/晶片/收據)
  - 新圖示 `AdminAlertIcon`:本機測試資料庫無任何掃描紀錄,無法開出真實 `/admin/scans/:id` 頁面;改用獨立離線 HTML(複製相同 SVG markup,置於 session scratchpad)渲染確認三角警示圖示清晰可辨、⟡ 角標正常疊加,視覺上無問題
- **仍待補**:`AdminScanDetailPage` 的 4 個圖示(狀態/結果摘要/各類別分數/錯誤訊息)因無測試掃描資料,未能用真實頁面截圖驗證整體版面(只驗證了其中新圖示本身的圖形),邏輯上與已驗證的其他 10 處寫法完全一致,風險低,但仍記錄此差異待有真實掃描資料時再補一次目視確認。
