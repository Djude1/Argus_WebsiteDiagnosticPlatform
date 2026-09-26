# 後台共用元件與格式化工具的測試，並轉為 TypeScript

**日期**：2026-09-26
**操作者**：Claude

## 變更內容
- 新增測試（與元件同目錄）：
  - `src/shared/formatters.test.ts`（32 項）：壞輸入的 fallback、相對時間單位切換邊界、0 不被當空值、數字字串
  - `src/components/admin/AdminPagination.test.tsx`、`AdminSortableTh.test.tsx`、`AdminModal.test.tsx`、`AdminStates.test.tsx`
  - 前端測試由 14 項增至 **72 項**
- `AdminModal`／`AdminStates`／`AdminPagination`／`AdminSortableTh` 由 `.jsx` 轉 `.tsx`，寫明 props 型別（哪些必填、哪些選填）。
- `AdminModal`：原本以 `const Tag = isForm ? "form" : "div"` 動態選外殼，TS 無法安全推導；改成兩個明確分支共用同一組屬性，輸出的 DOM 與屬性不變。
- `shared/AppShared.jsx::useDialogFocus`：`useRef` 加 JSDoc 型別（僅供 TS 呼叫端推導，執行期不變）。
- 三處 `import ... "useListQuery.js"`（實體已是 `.ts`）與四個元件的 `.jsx` 引用改為不帶副檔名。
- `frontend/CLAUDE.md`：更新元件路徑、補測試撰寫原則與本次踩到的注意事項。

## 原因
使用者同意的前端現代化計畫中「元件層測試」一項。先補測試，之後轉 TypeScript、換 headless 元件時才有東西能擋住改壞的地方。

挑這幾個是因為它們被所有後台列表頁共用，且每個元件的註解都寫明了行為承諾（Esc 與遮罩可關、focus 困在對話框內、錯誤一定有重試出口、第一次點排序用降冪……），測試直接驗證這些承諾。

## 影響範圍
- 執行期行為不變（CSS 輸出與拆分前逐位元組相同；Modal 的 DOM 結構與屬性相同，由測試涵蓋 form／div 兩個分支）。
- 這四個元件往後的呼叫端若漏給必填 props 或給錯型別，在 `.tsx` 中會是編譯錯誤（在 `.jsx` 中因 `checkJs: false` 仍不檢查）。

## 驗證方式
- `npm test`：72 passed；`npm run typecheck`：0 錯誤；`vite build` 成功，CSS 與基準逐位元組相同。
- **反證測試**：刻意植入五個錯誤，各自都讓恰好一項測試失敗，還原後全數通過：
  1. 拿掉 Modal 內部的 `stopPropagation`（點對話框內部會誤關）
  2. 分頁「上一頁」在第一頁仍可點
  3. 排序表頭改用 `includes` 判斷（`amount_total` 被誤判為 `amount` 排序中）
  4. 空狀態沒有 `onAction` 也顯示按鈕（按了沒反應）
  5. `formatNumber` 用 `!value` 判空（0 顯示成破折號）
