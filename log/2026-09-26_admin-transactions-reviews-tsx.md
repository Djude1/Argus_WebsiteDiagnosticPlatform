# 後台交易紀錄與評論治理拆出並轉 TypeScript；交易類型篩選補齊、評論頁補錯誤狀態

**日期**：2026-09-26
**操作者**：Claude

## 變更內容

### 前端
- 新增 `features/admin/AdminTransactionsPage.tsx`、`features/admin/AdminReviewsPage.tsx`，自 `AdminPages.jsx` 搬出（331 行）；`AdminPages.jsx` 1,588 → 1,248 行。
- **交易類型篩選補齊**：原本下拉只寫死 5 種，後端 `CoinTransaction.Kind` 有 11 種（網頁複刻預扣／退款、修正產出贈與／扣款／退款、訂閱月贈點皆缺），管理員無法只看這幾類交易。改以 `Record<CoinTransactionKind, string>` 宣告標籤，後端新增類型而前端未補會是編譯錯誤。
- **評論頁補載入錯誤狀態**：原本 `load()` 沒有 try/catch，請求失敗時 promise 未處理、整頁空白且無重試出口。改為與其他後台頁一致的 `AdminErrorState`（含重試）與載入骨架。
- 網址參數窄化：`kind`、`ordering`、`filter` 只送白名單內的值；不認得的 `filter` 視為「全部」，下拉選單也才對得上。
- `components/admin/AdminStatCard.jsx` → `.tsx`（寫明 props 型別）。
- `api.ts` 新增 `adminReplyReview`、`adminDeleteReviewReply`、`adminModerateReview`；`apiContracts.ts` 新增 `CoinTransactionKind`。
- 移除先前搬走掃描頁時遺留在 `AdminPages.jsx` 的孤兒註解（原屬 `SCANS_QUERY_DEFAULTS`）。
- 本次搬移造成的 7 個孤兒 import 由 ESLint 直接指出並移除（不再需要人工 grep）。
- 新增 `AdminTransactionsAndReviews.test.tsx`（9 項）；前端測試共 109 項。

### 後端
- `admin_api/serializers.py`：新增 `AdminReviewOfficialResponseSerializer`，`AdminReviewSerializer.get_response` 加 `@extend_schema_field`（可為 null）。
- `admin_api/views.py`：`reply_review`（POST／DELETE 分開）、`moderate_review` 加 schema 標註；交易列表 `kind` 篩選加 `enum=CoinTransaction.Kind.values`。
- `admin_api/tests.py`：實際回傳比對擴及評論（含巢狀官方回覆、回覆與審核回傳）與交易；新增「kind 篩選 enum 等於 model choices」測試。

## 原因
延續後台頁面 TypeScript 化；轉換時型別與測試揭露上述兩個既有問題。

## 影響範圍
- 交易頁類型下拉由 5 項增為 11 項（其餘行為不變）。
- 評論頁載入失敗時改顯示錯誤與重試，而非空白。
- `AdminPages` chunk 41 KB → 31 KB；交易、評論各自獨立 chunk。
- 其餘畫面與行為不變。

## 驗證方式
- 前端：`npm run lint` 0 error（1 個既有 warning）、`npm run typecheck` 0 錯誤、`npm test` 109 passed、`vite build` 成功、CSS 與基準逐位元組相同。
- 後端：`manage.py test apps.admin_api` 100 passed、`ruff` 通過。
- **反證**：
  - 從 `KIND_LABELS` 刪掉 `subscription_grant` → `TS2741 Property 'subscription_grant' is missing`
  - 拿掉評論頁的載入錯誤處理 → 「載入失敗時顯示錯誤與重試」測試失敗
