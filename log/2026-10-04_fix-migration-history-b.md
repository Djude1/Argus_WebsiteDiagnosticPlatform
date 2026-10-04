# 同步 XiuJie2/main 與 Djude1/main；正式 migrate 仍失敗的原因

**日期**：2026-10-04  
**操作者**：Claude

## 變更內容
- `claude/relaxed-hypatia-8xjr49` 以 merge commit 合入 Djude1/main（`2510cd0`）與 XiuJie2/main（`616a8ea`）的歷史，檔案內容與 Djude1/main 完全相同：scans `0024` 只依賴 `0022`、`0025` 取代 `0023_verifieddomain_search_console`、k8s image `sha-ae04222`。合入 XiuJie2/main 後，XiuJie2/main → Djude1/main 的 PR 不會衝突、不會蓋回 image 版本。

## 原因
- 回退（`60cc602`）後的恢復 commit `ee22e8c` 把 migration 修正蓋回舊版，正式 migrate 再次出現 `InconsistentMigrationHistory`；`ae04222` 已重新套用修正。
- `ae04222` 部署後仍看到同一錯誤：錯誤訊息提到的依賴只存在於 `sha-ee22e8c` 的 image。migrate Job 是 `restartPolicy: OnFailure`、`backoffLimit: 6`，舊 Job 會持續重試，Argo 的同步卡在這個 PreSync hook，沒有換到新 revision。需要終止 Argo 目前的同步、刪除舊 `migrate` Job 後重新同步。

## 驗證方式
- `git diff upstream/main HEAD` 只差本 log；`makemigrations --check`、`ruff check backend` 通過。
- 正式叢集待確認：`migrate` Job image 為 `sha-ae04222`、狀態 `Completed`／exit 0、log 為 `Applying scans.0025… OK` 或 `No migrations to apply`。
