# 後台操作日誌拆出並轉 TypeScript；動作篩選補齊、篩選進網址、補錯誤狀態

**日期**：2026-09-26
**操作者**：Claude

## 變更內容

### 前端
- 新增 `features/admin/AdminAuditLogPage.tsx`，自 `AdminPages.jsx` 搬出 `AdminAuditLogPage`、`AuditLogTab`（更名 `AuditLogTable`）與 `AUDIT_ACTION_OPTIONS`（共 113 行）；`AdminPages.jsx` 1,058 → 943 行。
- **動作篩選補齊**：原本只列 6 種＋「其他」，漏了程式中實際會寫入的 `subscription_adjust`（調整訂閱）、`domain_override`（網域驗證人工審核）、`scan_control`（掃描終止／重排）。超級管理員先前無法只看這三類紀錄。改以 `Record<AdminAuditAction, string>` 宣告，後端新增動作而前端未補會是編譯錯誤。
- **篩選與頁碼改進網址**（原本存在元件 state）；新增「清除篩選」。
- **補載入錯誤狀態**：原本 `load()` 沒有 try/catch，失敗時停在「載入中…」。
- 下拉補 `aria-label`；分頁補 `total`；`payload`（後端 JSONField、schema 為 `unknown`）先確認為物件再展開。
- `apiContracts.ts` 新增 `AdminAuditAction`（由 `AdminAuditLog["action"]` 索引取得）。
- 新增 `AdminAuditLogPage.test.tsx`（7 項）；前端測試共 123 項。

### 後端
- `audit-log` 的 `action` 篩選帶 `enum=AdminAuditLog.Action.values`。
- 契約測試：實際回傳比對擴及操作日誌；新增「action 篩選 enum 等於 model choices」。

## 原因
延續後台頁面 TypeScript 化。操作日誌是合規稽核軌跡，篩選漏掉實際存在的動作等於部分紀錄查不到。

## 影響範圍
- 操作日誌動作下拉由 7 項增為 9 項＋全部；篩選出現在網址上；載入失敗改顯示錯誤與重試。
- `AdminPages` chunk 27 KB → 24 KB。

## 驗證方式
- 前端：lint／typecheck／test／build 結束碼皆為 0；`npm test` 123 passed；CSS content hash 不變（`index-DvJ2Sx5a`）。
- 後端：`manage.py test apps.admin_api` 103 passed。
- **反證**：
  - 拿掉超級管理員檢查 → 「非超級管理員看不到，也不打 API」測試失敗
  - 刪掉 `scan_control` 標籤 → `TS2741 Property 'scan_control' is missing`
- **過程中的疏失**：搬移後以 `grep " error "` 檢查 lint，因終端機色碼而誤判為乾淨，漏掉 2 個孤兒 import；由完整 `npm run lint` 抓到並修正。已在 `frontend/CLAUDE.md` 記下「看結束碼，不要 grep 輸出」。
