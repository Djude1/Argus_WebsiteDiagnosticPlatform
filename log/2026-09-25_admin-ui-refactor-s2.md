# 後台 UI 重構 S2：篩選狀態進網址 ＋ 伺服器端排序

**日期**：2026-09-25  
**操作者**：Claude

## 變更內容

### 後端（先行，見 commit 7e447bf）
- `apps/admin_api/views.py` 新增 `_apply_ordering()` 與四份欄位白名單（USERS／SCANS／TRANSACTIONS／ORDERS_ORDERING）；`users_list`／`scans_list`／`transactions_list`／`orders_list` 接上 `ordering` 查詢參數。
- 新增 `OrderingTests` 5 項。

### 前端
- 新增 `shared/useListQuery.js`：列表頁的搜尋／篩選／排序／分頁狀態與網址雙向同步。只有「非預設值」寫進 query string。
- 新增 `components/admin/AdminSortableTh.jsx`：可排序表頭，含 `aria-sort` 與箭頭＋螢幕閱讀器文字雙重呈現。
- 五個列表頁接上：使用者、掃描、交易、訂單（排序＋篩選）、評論（篩選）。
- **移除操作日誌的內嵌分頁**（S5 的 IA 重整提前執行，原因見下）。
- 順帶修正：交易頁「使用者」欄名與內容不符（實際顯示的是 `scan_origin` 或方案名），改為「來源對象」；末欄改為「操作者 / 方案」。
- 各列表補上骨架載入、區塊級錯誤（含重試）、「清除篩選」出口。

## 原因
規劃 §1-2 問題 E：`AdminPages.jsx` 的 `useSearchParams` 用量為 0，造成篩選後畫面無法分享、Back 不還原、從詳情頁返回列表時篩選與頁碼全失。

**排序為何做在後端**：規劃時我假設前端排序即可，實際查核後發現後端完全沒有排序參數，而分頁是 server side（`PAGE_SIZE=25`）。純前端排序只會排當頁 25 筆，卻讓管理員以為那是全域最高分／最大金額的幾筆——那是會誤導決策的假排序，因此改為後端白名單排序。

**為何提前做 S5 的一部分**：`AdminScansPage` 與 `AdminTransactionsPage` 原有 `embedded` 模式被內嵌在操作日誌頁，三個列表在同一頁會搶同一組網址參數，使 S2 的可分享網址無法成立。兩者各自已是 top-level nav，移除內嵌不損失任何能力，改以頁首連結導向。

**為何評論頁也要進網址**：規劃的流程 D 是「待辦中心『待審檢舉』→ 已篩選的評論列表」，該跳轉需要 `/admin/reviews?filter=reported` 成立。

## 影響範圍
- 後台五個列表頁的網址行為改變；深層連結現在可分享。
- 操作日誌頁不再包含交易與掃描分頁（superuser 可見範圍不變，入口改為頁首連結）。
- `duration_sec` 刻意不可排序：它是 serializer 由 `started_at`／`completed_at` 現算的 `SerializerMethodField`，資料庫無此欄位。表格中已加註解說明。

## 驗證方式
- 後端：`OrderingTests` 5 項通過（預設新到舊、升冪、降冪、白名單外欄位退回預設而非 500、使用者依錢包關聯欄位排序）；`apps.admin_api` 共 55 項全過；`uv run ruff check backend` 全過。
- 前端：`npx vite build` 通過（13.18s）。
- 確認 `react-router-dom@7.15.1` 的 `SetURLSearchParams` 型別支援函式式更新（`(prev: URLSearchParams) => URLSearchParamsInit`），本次用法成立。
- `embedded` 殘留檢查歸零。
- **待人工確認（前端無測試框架，無法自動驗）**：瀏覽器中實際操作篩選→複製網址→新分頁開啟是否還原同一畫面；列表→詳情→Back 是否回到原篩選與頁碼；排序箭頭與 `aria-sort` 在螢幕閱讀器下的表現。

## 對原規劃的修正
規劃 §6 S2 的驗收標準原本寫「Back 逐步退回前一組篩選」。實作時採用 `replace: true`，**Back 不會逐一退回每次篩選變更**，而是直接離開列表頁。這是刻意的：專案 `argus-ui-design` skill 第 6 條明訂「篩選／排序不要污染 history stack（這是業界最常見的 Back 破壞點）」。原驗收標準與該規則衝突，以 skill 為準。

真正需要成立的是「列表→詳情→Back 回到原篩選」，這在 `replace` 模式下仍然成立（詳情是 push 進去的）。
