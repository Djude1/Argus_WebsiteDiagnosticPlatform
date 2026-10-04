# 修復：K8s migrate 失敗（InconsistentMigrationHistory，scans 0024）

**日期**：2026-10-04  
**操作者**：Claude

## 症狀
Argo PreSync `migrate` Job 失敗：`Migration scans.0024_search_console_account_level is applied before its dependency scans.0023_verifieddomain_search_console`。

## 原因
正式資料庫（部署 `d89be90` 時）已套用舊鏈：`0019_alter_verifieddomain_method → 0023_merge_gsc_and_projects → 0024_search_console_account_level`（舊 0024 會把 `method` 改成 varchar(32)，並允許 `google_search_console`）。上游 `b918254` 刪掉前兩個、新增 `0023_verifieddomain_search_console`，並把 0024 改成依賴它——正式庫的 0024 已套用、新 0023 卻沒有，`check_consistent_history` 直接拒絕。

## 變更內容
- `0024_search_console_account_level`：依賴改為 `0022_seo_analysis_and_search_console`（舊鏈與新鏈都已套用，兩種資料庫都一致）。
- 刪除 `0023_verifieddomain_search_console`，以新的 `0025_verifieddomain_method_search_console` 取代：先把 `google_search_console` 轉成 `search_console`，再把 `method` 改成 32 再改回 16（遷移狀態本來就是 16，單一 AlterField 不會動正式庫的 varchar(32)）；`atomic=False` 讓資料更新與 ALTER TABLE 不在同一個交易。
- `accounts` 被刪的 `0007_loginevent_stable_ordering`／`0008_merge_…` 不需處理：已套用但不存在的 migration 會被忽略，且現存 migration 沒有依賴它們（只差 Meta ordering，無資料表變更）。
- 文件：`backend/CLAUDE.md` 新增「Migration 鐵律」並更新 VerifiedDomain migration 編號；根 `AGENTS.md`／`CLAUDE.md` K8s 段落加一條指向它。

## 驗證方式
本機 PostgreSQL 16 建三個資料庫：
- `prod`：以 `d89be90` 程式碼 migrate（重現正式庫舊鏈），手動插入 `method='google_search_console'` 的網域；先用上游 `main` migrate → 重現同一個 `InconsistentMigrationHistory`；再用修正版 migrate → 只套用 0025，欄位 varchar(16)，資料轉為 `search_console`，再跑一次「No migrations to apply」。
- `dev`：以上游 `main`（`b918254`，新鏈）migrate 後，修正版 migrate 成功、欄位 16。
- `fresh`：空庫完整 migrate 成功。
三庫 `makemigrations --check` 皆無變更；`ruff check backend`、後端測試通過。
