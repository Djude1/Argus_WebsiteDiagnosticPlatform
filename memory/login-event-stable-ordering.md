# 登入事件的穩定排序

**日期**：2026-10-04

完整測試重現：時鐘解析度較低時，連續建立的登入事件可能有相同的 `created_at`；只按時間降冪會把較早事件排在前面。後台透過 `user.login_events.all()[:50]` 採用 model 的預設排序。

`LoginEvent.Meta.ordering` 改成 `-created_at`、`-id`，讓相同時間的事件按建立次序降冪。新增 `accounts.0007_loginevent_stable_ordering`（僅 model options，不更動欄位或既有紀錄），以及固定相同時間的 API 回歸測試。回歸先失敗再通過，與既有登入事件 API 案例共四項通過；輸出 whitelist 不變。

事實來源：`backend/apps/accounts/models.py`、`backend/apps/admin_api/tests_login_event_ordering.py`。適用權限及登入記錄寫入方式見 [accounts 模組規則](../backend/apps/accounts/CLAUDE.md)。
