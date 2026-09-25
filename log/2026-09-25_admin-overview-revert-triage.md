# 後台首頁移除待辦中心區塊，改回概覽

**日期**：2026-09-25  
**操作者**：Claude

## 變更內容
- `AdminOverviewPage.jsx`：移除 `TriageCard` 元件、四張待辦卡片、`allClear` 空狀態區塊；頁首標題由「待辦中心／需要處理的事項，以及系統整體狀態」改回「概覽／系統整體狀態與最近 14 天活動」。
- `AdminPages.jsx`：側欄「營運」組的第一項由「待辦中心」改回「概覽」。
- `styles.css`：移除 55 行 `.admin-triage-*` 樣式與其 `prefers-reduced-motion` 規則（因本次改動而成為孤兒）。
- 清除不再使用的匯入：`AdminAlertIcon`、`StatusDoneGlyph`、`formatRelative`。
- 同步 `frontend/CLAUDE.md` 的導覽分組表與路由地圖。

## 原因
使用者要求把側欄與頁面改回原本的「概覽」，並指名移除待辦卡片與「目前沒有待處理事項」那段空狀態文字。

## 保留未動的部分
- **後端 `overview` 的 `triage` 區塊保留且仍在使用**：頁面「今日」那一區的「今日掃描」與「進行中」兩個數字來自 `triage.scans_today` 與 `triage.scans_in_progress`。因此它不是死碼，`TriageTests` 也繼續有效。
- 其餘 S1～S3 的改善維持不變：`recent_scans` 區塊、formatters、骨架載入、區塊級錯誤與重試、統計卡的 `hero` 取消。

## 影響範圍
- 只影響 `/admin/overview` 的第一屏與側欄標籤；其他頁面未改動。
- `AdminOverviewPage` chunk 由 11.96 kB 降至 10.10 kB。

## 驗證方式
- 殘留檢查全為 0：`TriageCard`、`allClear`、`admin-triage-grid`（JSX）、`admin-triage`（CSS）、`formatRelative`、`StatusDoneGlyph`、`AdminAlertIcon`。
- `npx vite build` 通過（13.75s）。
- **待人工確認**：瀏覽器中確認側欄顯示「概覽」、頁面不再出現待辦卡片，且「今日」區塊的數字仍正常顯示。
