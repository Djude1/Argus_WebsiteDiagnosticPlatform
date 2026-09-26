# 前端 TypeScript 導入與 API 型別契約

**日期**：2026-09-25
**操作者**：Claude

## 變更內容

### 工具鏈
- 新增 `frontend/tsconfig.json`：漸進導入（`allowJs: true` + `checkJs: false`），開 `strict` 與 `noUncheckedIndexedAccess`；`paths` 用相對路徑（TS 7 已移除 `baseUrl`）。
- 新增 `frontend/vitest.setup.ts`，`vite.config.js` 加 `test` 區塊（jsdom + Testing Library）。
- `package.json` 新增 `test` / `test:watch` / `typecheck`。
- 後端 `uv add drf-spectacular`；`settings.py` 設 `DEFAULT_SCHEMA_CLASS` 與 `SPECTACULAR_SETTINGS`（`SERVE_PUBLIC: False`，schema 只離線產生，**不開公開端點**）。
- 前端 `typescript` 固定在 `^5.7`：`openapi-typescript` 依賴 `ts.factory`，TS 7（Go 改寫版）沒有暴露它，會 crash。

### 後端 schema 標註
- 新增 `backend/apps/admin_api/schema.py`：`list_schema()` / `query_param()` / `ordering_param()`。
- `views.py` 為 7 個列表端點（scans / users / transactions / audit-log / domains / orders / reviews）與 `scan_detail` 加上標註，宣告回傳信封與查詢參數。
- 新增 `AdminOpenAPISchemaTests`（6 項）鎖定契約。

### 前端型別
- `src/api.js` → `src/api.ts`，補上參數型別，並新增 7 個後台列表函式（先前散在各頁面直接 `api.get`，沒有型別）。
- 新增 `src/shared/apiTypes.ts`（產生物，禁止手改）與 `src/shared/apiContracts.ts`（取好名字的型別出入口）。
- `src/shared/useListQuery.js` → `.ts`，泛型把 `params` / `setParam` 的鍵綁到 `defaults`。
- 新增 `src/shared/useListQuery.test.tsx`（14 項）——本專案第一批前端測試。

## 原因

後台先前出過兩次**靜默失效**：畫面照常顯示、沒有任何錯誤，但結果是錯的。

1. `?user=` 沒列進 `useListQuery` 的 `defaults`：網址帶著參數，列表完全不篩選。
2. `user_id` 沒進 `AdminScanJobSerializer`：掃描列表連到使用者的連結永遠不會出現。

兩者都只能靠人眼發現，前端當時既沒有型別也沒有測試。這次讓這兩類錯誤都變成編譯錯誤。

## 影響範圍

- **執行期行為未改變**：只加型別標註與 schema 標註，沒有動任何業務邏輯。
- `admin_api` 全是 function-based view，`@extend_schema` 系列**必須放在 `@api_view` 之上**；放下面不會報錯，schema 只是靜默空白（本次實際踩到）。
- **schema 名稱撞名會靜默壞掉**：drf-spectacular 去掉 serializer 的 `Serializer` 後綴後，`AdminUserListSerializer` → `AdminUserList`；信封原本也叫這名字，後者覆蓋前者，陣列元素的 `$ref` 指回信封自己。因此信封一律 `…Response` 結尾，並由測試鎖住。
- 後端改了 serializer 或查詢參數後**必須重新產生前端型別**，指令記在 `frontend/CLAUDE.md`。
- 尚未完成（後續）：其餘 `.js`／`.jsx` 的轉換、`styles.css` 拆分、元件層測試。

## 驗證方式

- `uv run ruff check backend/apps/admin_api` → 通過
- `uv run python backend/manage.py check` → 0 issues
- `uv run python backend/manage.py test apps.admin_api` → **92 tests OK**
- `npm run typecheck` → 無錯誤
- `npm test -- --run` → **14 tests passed**
- `npx vite build` → 成功
- **反證測試**（確認擋得住，不是只跑得過）：
  - 臨時寫入 `fetchAdminScans({ usr: 5 })`、`ordering: "-created"`、`r.scans[0].user_idd` → 三者皆為編譯錯誤，其中打錯的鍵名被提示 `Did you mean to write 'user'?`
  - 臨時把信封名稱改回 `AdminUserList` 重現撞名 → `test_list_items_point_at_the_item_serializer_not_the_envelope` FAIL，還原後 OK
