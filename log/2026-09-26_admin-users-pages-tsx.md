# 後台使用者頁拆出並轉 TypeScript；修正 schema 的必填與 nullable 失真

**日期**：2026-09-26
**操作者**：Claude

## 變更內容

### 前端
- 新增 `features/admin/AdminUsersPages.tsx`：自 `AdminPages.jsx` 搬出 `AdminUsersPage`、`AdminUserDetailPage`（516 行），改用型別化 API。
- 新增 `features/admin/adminHelpers.ts`：`toAllowed`、`toPositiveInt`、`statusLabel`、`STATUS_OPTIONS`、`errorDetail`；`AdminScansPages.tsx` 改用（原為其內部函式）。
- `api.ts` 新增 `fetchAdminUserDetail`、`adminAdjustCoin`；`fetchUserLoginEvents`／`fetchUserSubscription`／`adminUserSubscriptionAction`／`fetchAdminSubscriptionPlans` 補上回傳型別。
- 新增 `AdminUsersPages.test.tsx`（14 項）；前端測試共 100 項。
- `AdminPages.jsx` 2,107 → 1,588 行；移除因搬移而成為孤兒的 8 個 import（`AdminEmptyState`、`useMemo` 在搬移前即未使用，非本次造成，未動）。
- `App.jsx`：使用者兩個路由改從新檔 lazy 載入。

### 後端
- `admin_api/views.py`：`user_detail`、`adjust_coin`、`user_login_events`、`user_subscription`（GET／POST 分開）、`subscription_plans` 加 schema 標註。
- `admin_api/schema.py`：新增 `AdminUserDetailResponseSerializer` 等文件用 serializer（`user_detail` 在 serializer 輸出後附加 `ai_usage`／`recent_scans`／`scans_total`，serializer 本身描述不到）。
- `admin_api/serializers.py`：`get_wallet`／`get_recent_transactions` 加 `@extend_schema_field`、`get_scan_origin` 加回傳型別；**5 個 `source="x.y", default=None` 欄位補 `allow_null=True`**。
- 新增 `config/spectacular_hooks.py` 並在 `SPECTACULAR_SETTINGS` 啟用：回應 component 的欄位一律標為必填。
- `admin_api/tests.py`：新增 `AdminResponseMatchesSchemaTests`，打實際端點比對「回傳鍵集合＝schema 欄位」與「實際為 null 的欄位 schema 必須 nullable」。

## 原因
延續前端現代化：使用者詳情串五個端點，是後台欄位最多、最容易接錯的頁面。

轉換過程中型別揭露了兩個 **schema 與實際回傳不符** 的問題：

1. **選填失真**：drf-spectacular 把「model 欄位有 default」的欄位在回應中也標為選填，前端型別變成 `status?:`、`balance?:`，被迫處理不會發生的缺欄位。DRF 序列化 model instance 時一定輸出每個可讀欄位，因此以 postprocessing hook 將回應欄位一律標為必填（請求用的 `…Request` component 不動）。
2. **nullable 漏宣告**：`plan_name`、`admin_actor_username`、`target_username` 等以 `source="關聯.欄位", default=None` 宣告，關聯不存在時實際回傳 `null`，schema 卻寫 `string`。是測試 fixture 以型別宣告時編譯失敗才發現的。前端若照型別寫 `.toUpperCase()` 會在執行期出錯。

兩者對執行期都沒有影響（只改 schema 描述）；新的契約測試確保之後不再漂移。

## 影響範圍
- 畫面與行為不變。
- `AdminPages` chunk 56 KB → 41 KB；使用者頁獨立為 15 KB chunk。
- 後端 schema 變動只影響產生的前端型別，執行期無影響。
- **發現但未處理**：專案沒有 ESLint，`.jsx` 內引用不存在的名稱不會讓 build 失敗。本次以逐一 grep 確認；建議另案導入。

## 驗證方式
- 前端：`npm test` 100 passed、`npm run typecheck` 0 錯誤、`vite build` 成功、CSS 與基準逐位元組相同。
- 後端：`manage.py test apps.admin_api` 97 passed、`ruff` 通過。
- **反證**：
  - `user_detail` 多附加一個欄位 → `AdminResponseMatchesSchemaTests` 失敗並指出多出的欄位名
  - 加入 nullable 檢查後、修正 `allow_null` 前 → 失敗於 `AdminCoinTransaction.plan_name`；修正後通過
  - 使用者詳情「查看全部」不帶 `?user=` → 頁面測試失敗
  - 預設訂閱方案不略過停用方案 → 頁面測試失敗
