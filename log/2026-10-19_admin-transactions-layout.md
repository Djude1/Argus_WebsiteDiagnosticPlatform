# 後台點數交易頁審閱：補使用者欄與單一使用者篩選（2026-10-19）

## 問題
`/admin/transactions` 是跨所有使用者的 coin 帳本，但列裡**沒有使用者**——後端 `AdminCoinTransactionSerializer` 根本沒回 username，
後台看到「+500 管理員調整」卻不知道是誰的錢包；「來源對象」與「操作者 / 方案」兩欄重複顯示掃描網址／方案名。
後端 `?user_id=` 篩選早就有，前端沒接。標題「交易紀錄」與側欄「點數交易」不一致。

## 變更
- 後端 `apps/admin_api/serializers.py`：`AdminCoinTransactionSerializer` 補 `user_id`、`username`（queryset 已 `select_related("wallet__user")`）。
  重產 `frontend/openapi.json`（維持既有 YAML 格式，diff 8 行）與 `apiTypes.ts`。
- `AdminTransactionsPage.tsx`：欄位改 時間｜使用者（連到使用者詳情）｜類型｜對象（掃描網址或方案）｜變動｜餘額｜操作者（只有管理員調整有值）｜備註；
  `?user=` 只看單一使用者＋「顯示全部使用者」提示（與掃描頁同一套）；標題「點數交易」。
- `AdminUsersPages.tsx`：「最近 30 筆交易」標題列加「查看全部交易 →」連到 `/admin/transactions?user=<id>`。
- 測試 mock 依型別補 `user_id`／`username`（typecheck 擋下，正是型別管線的用途）。文件：`frontend/CLAUDE.md` 路由表。
- 競賽文件：管理後台 API 欄位層級的補充，需求書未列到此粒度，不需同步。

## 驗證
`uv run python backend/manage.py test apps.admin_api`（含 OpenAPI schema key 鎖定）OK；`ruff check`；
`npm run lint`、`npm run typecheck`、`npx vitest run`。
