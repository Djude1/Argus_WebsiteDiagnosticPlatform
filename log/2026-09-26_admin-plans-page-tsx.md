# 後台方案管理拆出並轉 TypeScript；修正毛利試算高估成本 10 倍、新增方案從未成功、刪除有訂單的方案回 500

**日期**：2026-09-26
**操作者**：Claude

## 變更內容

### 修正的三個既有 bug
1. **毛利試算高估成本 10 倍**：`planEconomics` 以 `coin × NT$0.67` 計算成本，沿用「1 coin = 1 頁」的舊假設；但後端 `ARGUS_COIN_PER_PAGE` 預設每頁 10 coin（同一函式的頁數估算用的也是 `coin / 10`）。以種子方案驗算，後台顯示的毛利為 2%～33% 並全部標為「須重新定價」，實際約 90%～93%：

   | 方案 | 售價 | coin | 原顯示毛利 | 修正後 |
   |---|---|---|---|---|
   | 入門 | 100 | 100 | 33% | 93% |
   | 標準 | 450 | 500 | 26% | 93% |
   | 進階 | 800 | 1000 | 16% | 92% |
   | 旗艦 | 1500 | 2200 | 2% | 90% |

   修正：成本以「頁」計（`COST_PER_PAGE_NTD = 0.67`），coin → 頁用後端回傳的 `coin_per_page`。
2. **後台新增方案從未成功**：後端 `PricingPlan.code` 必填（unique slug），表單卻沒有此欄位，送出一律 400；`handleSave` 無錯誤處理，按「儲存」毫無反應（以測試資料庫重現確認）。補上「方案代碼」欄位；編輯時唯讀且不送出（購點以 `plan_code` 識別、購點頁以 `code` 判斷「推薦」）。
3. **刪除已有訂單的方案回 500**：`PurchaseOrder.plan` 為 PROTECT，`ProtectedError` 未處理（以測試資料庫重現確認）。CMS 共用基底改為回 409，訊息引導「改為停用」；稽核紀錄不會誤寫。

### 前端
- 新增 `features/admin/AdminPlansPage.tsx`、`features/admin/planEconomics.ts`（純函式，含 `COST_PER_PAGE_NTD`），自 `AdminPages.jsx` 移除方案頁、舊 `COIN_COST_NTD` 與 `planEconomics`（150 行）。
- 補齊錯誤回饋：載入失敗（原本被吞掉並顯示「尚無方案」）、儲存欄位錯誤、刪除失敗。
- `api.ts` 新增 `fetchAdminPlans`／`createPlan`／`updatePlan`／`deletePlan`。
- 新增 `planEconomics.test.ts`（8 項，以種子方案驗算）、`AdminPlansPage.test.tsx`（7 項）；前端測試共 145 項。

### 後端
- `cms_views.py`：
  - 五個 CMS ViewSet 的 `list` 以 `_items_list_schema()` 描述實際的 `{"items": [...]}`（原本 schema 描述成純陣列，與實際不符）。
  - 方案列表附 `coin_per_page`。
  - `_AuditedModelViewSet.destroy` 捕捉 `ProtectedError` 回 409。
- `tests.py`：CMS 列表回傳比對、`coin_per_page`、`code` 必填；新增 `CmsProtectedDeleteTests`（3 項）。

## 原因
延續後台頁面 TypeScript 化；轉換時發現上述三個問題。第 1 點會讓管理員依錯誤數字調價，影響最大。

## 影響範圍
- **後台方案卡與編輯試算的成本／毛利數字改變**（約降為原本的 1/10 成本）；門檻（80%／50%）不變。
- 後台可以新增方案了（需填方案代碼）。
- 刪除有訂單的方案改顯示可讀的 409 說明。
- `AdminPages.jsx` 831 → 679 行；`AdminPages` chunk 21 KB → 16 KB。

## 合併組員「掃描維度多選計費」後的調整（rebase 時）
- 組員 `9445948` 移除了 `ARGUS_COIN_PER_PAGE`，改為 `ARGUS_COIN_PER_CATEGORY`（每頁每維度 2 coin，五維全選＝每頁 10 coin）。
- 方案列表的 `coin_per_page` 改為 `billing.services.estimate_scan_cost(1)`（五維全選時一頁的費用），直接沿用計費本身的公式，不另外維護換算；契約測試同時比對「＝維度數 × ARGUS_COIN_PER_CATEGORY」。
- 試算一律以五維全選估算：只勾部分維度時一頁更便宜，因此這是保守（成本最高）的算法。

## 待決定（未處理）
- **每頁成本 NT$0.67 是否改由後端設定提供**（稽核 Q2）：目前仍在前端 `planEconomics.ts`，已標註待決定。每頁 coin 數已改由後端提供。

## 驗證方式
- 前端：lint／typecheck 結束碼 0、`npm test` 145 passed、`vite build` 成功、CSS content hash 不變。
- 後端：`manage.py test apps.admin_api` 110 passed、`ruff` 通過。
- **反證**：改回舊公式（每 coin 當每頁成本）→ 8 項測試失敗；`CmsProtectedDeleteTests` 在修正前 3 項皆因 `ProtectedError` 失敗、修正後通過。
