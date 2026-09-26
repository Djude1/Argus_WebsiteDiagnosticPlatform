# 後台掃描頁拆出並轉 TypeScript，接上型別化 API

**日期**：2026-09-26
**操作者**：Claude

## 變更內容
- 新增 `frontend/src/features/admin/AdminScansPages.tsx`：自 `AdminPages.jsx` 搬出 `AdminScansPage`、`AdminScanDetailPage`、`AdminScanWarnings`（共 391 行），改用 `fetchAdminScans`／`fetchAdminScanDetail`／`adminCancelScan`／`adminRequeueScan`。
  - 網址參數送出前窄化：`?user=` 轉正整數、`ordering` 只送後端白名單內的值（以 `satisfies` 綁定產生的型別），壞值送 `undefined`，交給後端預設。
  - `top_actions`／`warning_summary` 在後端是 `JSONField`，schema 只能是 `unknown`；在頁面內以本地 type 描述，並註明產生端（`scanners.py`／`crawler.py`）。
- 新增 `AdminScansPages.test.tsx`（14 項）：頁面層鎖定 `?user=` 篩選、使用者連結、ordering 白名單、錯誤重試、終止／重排流程。
- 新增 `components/admin/activateAdminRow.ts`（原為 `AdminPages.jsx` 內部函式，兩邊共用）。
- `App.jsx`：兩個掃描路由改從新檔 lazy 載入。
- `AdminPages.jsx`：移除搬走的程式與因此成為孤兒的 import（`formatDuration`、`AdminTrendIcon`），2,506 → 2,107 行。
- 後端 `admin_api/views.py`：`scan_cancel`、`scan_requeue` 加 `@extend_schema` 宣告回傳（`refunded`／`charged`）；契約測試新增一項。
- `api.ts` 新增 `adminCancelScan`、`adminRequeueScan`；重新產生 `openapi.json` 與 `apiTypes.ts`。
- 同步 `frontend/CLAUDE.md`、`backend/apps/admin_api/CLAUDE.md`。

## 原因
型別化 API 只有在 `.tsx` 呼叫端才有保護作用（`.jsx` 因 `checkJs: false` 不檢查）。掃描頁是後台兩次靜默失效的現場（`?user=` 沒送、`user_id` 沒接上），所以先轉這裡。

## 影響範圍
- 畫面與行為不變；唯一差異是壞的網址參數（非整數的 `user`、白名單外的 `ordering`）現在不送給後端。原本就會被後端忽略或回退預設，結果相同。
- `AdminPages` chunk 67 KB → 56 KB；掃描頁獨立為 11 KB chunk，只在進入掃描頁時載入。

## 驗證方式
- 前端：`npm test` 86 passed、`npm run typecheck` 0 錯誤、`vite build` 成功、CSS 與基準逐位元組相同。
- 後端：`manage.py test apps.admin_api` 93 passed；`ruff` 通過。
- **反證**：
  - 拿掉送出 `user` 的那一行 → 「?user=5 會以整數送給後端」測試失敗
  - 使用者連結改讀不存在的欄位 → 「有 user_id 時提供查看使用者連結」測試失敗
  - 直接把 `s.user_id` 打成 `s.userId` → typecheck 報 `TS2551 Property 'userId' does not exist`
  - 三者還原後全數通過
