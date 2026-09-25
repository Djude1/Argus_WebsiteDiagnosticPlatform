# 修正掃描重排：清除舊 Page／Finding，避免 unique constraint 錯誤

**日期**：2026-09-25  
**操作者**：Claude

## 問題
`scan_requeue()`（我在 commit `7496c80` 加的）重用同一個 `ScanJob` 重跑，但**沒有清除既有的 Page 與 Finding**：

- `Page` 有 `UniqueConstraint(fields=["scan_job", "url"], name="unique_page_per_scan")`（`apps/scans/models.py:158`），而 `apps/scans/tasks.py:301` 用的是 `Page.objects.create()`——不是 `update_or_create`，也沒有 `ignore_conflicts`。重排一個「已爬了幾頁才失敗」的掃描，**第一個重複 URL 就會 `IntegrityError`**。
- `Finding` 沒有 unique constraint，舊結果不會衝突而是**累加**，造成重複發現與錯誤評分。

來源：使用者提供的 Graphify MCP 稽核報告（索引 commit `2b6da0dc`）指出此問題，我對照本機原始碼查證屬實。

## 為何選擇「清除並沿用同一個 ScanJob」而非「新建 ScanJob ＋ retry_of」

| 判準 | 清除重跑（採用） | 新建 ScanJob |
|---|---|---|
| 計費正確性 | 安全 | `settle_scan_actual` 的冪等防護以 `scan_job` 為鍵；新 scan 沒有任何 `SCAN_REFUND`，防護失效，會產生一筆 0 元交易並讓 `total_scans_used` 重複累加 |
| 使用者連結 | `/scans/<id>` 不變 | 書籤指向失敗的舊 scan，真結果在新 id，需額外 UI 串接 |
| 改動範圍 | 一個 transaction | 新欄位 ＋ migration ＋ UI ＋ 更多測試 |
| 保留失敗資料 | 會清除 | 完整保留 |

決定性因素是計費：`settle_scan_actual` 開頭以 `scan_job` 為鍵做冪等檢查，沿用同一個 ScanJob 才能繼續生效。

**「保留失敗資料」這個優勢比想像中小**：worker 進場的條件更新本來就帶 `scan_log=[]`（`tasks.py:224`），失敗那次的執行日誌無論如何都會被清掉。真正有價值的只剩失敗原因，改為寫進 `AdminAuditLog` payload——依專案規則那是不可竄改的，比留在會被覆寫的 ScanJob 欄位更可靠。

## 變更內容
- `scan_requeue()` 包進 `transaction.atomic()`，內含：
  - 刪除該 scan 的所有 `Page` 與 `Finding`
  - 重設衍生結果：`overall_score=None`、`category_scores={}`、`top_actions=[]`、`warning_summary={}`、`crawl_checkpoint={}`、`completed_at=None`（留著會讓重跑期間畫面顯示上一輪的舊分數）
- 清除前先擷取 `previous_error` 與 `scan_log` 末 5 筆，連同 `cleared_pages` / `cleared_findings` 筆數寫入 `AdminAuditLog` payload。

## 驗證方式
- 新增 4 項測試（`ScanControlTests` 由 8 項增為 12 項）：舊 Page 清除且相同 URL 可再建立、舊 Finding 清除、衍生結果重設、失敗原因保留於稽核紀錄。
- **確認測試確實會抓到該 bug**：暫時移除刪除邏輯後重跑，`test_requeue_clears_existing_pages_so_rerun_does_not_violate_unique`（`2 != 0`）與 `test_requeue_clears_findings_so_results_do_not_accumulate`（`1 != 0`）立即失敗；還原後全數通過。
- `apps.admin_api` 共 86 項測試全過；`uv run ruff check backend` 全過。

## 檢討
S4 當時寫了 8 項測試，**全部集中在狀態轉換與派工，沒有一項碰資料層**——這正是漏掉此 bug 的原因。涉及重跑既有資料的功能，測試必須涵蓋「第二次執行遇到第一次留下的資料」這個情境。
