# 後台公告管理拆出並轉 TypeScript；補齊載入、儲存、刪除的錯誤回饋

**日期**：2026-09-26
**操作者**：Claude

## 變更內容

### 前端
- 新增 `features/admin/AdminAnnouncementsPage.tsx`，自 `AdminPages.jsx` 搬出（111 行）。
- **載入失敗**：原本 `loadList` 沒有 catch，失敗時清單為空、顯示「尚無公告」——把「讀不到」說成「沒有」。改為錯誤＋重試。
- **儲存失敗**：原本 `handleSave` 沒有 try/catch，失敗時例外未處理；彈窗留著但沒有任何訊息，按「儲存」看起來毫無反應。改為：
  - DRF 400 的欄位錯誤顯示在對應欄位旁（`AdminField` 的 `error`，並以 `aria-describedby` 連到輸入框）
  - 其他錯誤（網路、權限）在彈窗內以 `role="alert"` 顯示
  - 送出中停用「儲存」並顯示「儲存中…」，避免重複送出
  - 重新開啟編輯時清除上一次的錯誤
- **刪除失敗**：原本同樣無聲無息，改為提示。
- `adminHelpers.ts` 新增 `fieldErrors()`：DRF 400 `{欄位: [訊息]}` → `{欄位: 訊息}`。
- `api.ts` 新增 `fetchAdminAnnouncements`、`createAnnouncement`、`updateAnnouncement`、`deleteAnnouncement`；`apiContracts.ts` 新增公告相關型別。
- 新增 `AdminAnnouncementsPage.test.tsx`（7 項）；前端測試共 130 項。

### 後端
- `announcements_admin`（GET／POST）、`announcement_detail`（GET／PATCH／DELETE）、`active_announcements` 加 schema 標註。
- 契約測試：實際回傳比對擴及公告的建立、列表、更新與前台有效公告。

## 原因
延續後台頁面 TypeScript 化。公告會直接顯示給所有登入使用者，編輯失敗卻沒有回饋，管理員無從得知公告沒存進去。

## 影響範圍
- 公告管理頁的畫面與操作流程不變；差別只在各種失敗情況現在有明確回饋。
- `AdminPages.jsx` 943 → 831 行；`AdminPages` chunk 24 KB → 21 KB。

## 驗證方式
- 前端：lint／typecheck 結束碼 0、`npm test` 130 passed、`vite build` 成功、CSS content hash 不變（`index-DvJ2Sx5a`）。
- 後端：`manage.py test apps.admin_api` 104 passed。
- **反證**：讓儲存失敗時直接拋出（回到原本無回饋的行為）→ 3 項測試失敗；還原後全數通過。
