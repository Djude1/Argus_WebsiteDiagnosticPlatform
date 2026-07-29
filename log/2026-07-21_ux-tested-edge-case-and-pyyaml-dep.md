# UX 評分邊界情況修正 + pyyaml 相依宣告補齊

**日期**：2026-07-21
**操作者**：Claude

## 變更內容
- `backend/apps/scans/tasks.py`：`tested_categories` 判斷 UX 是否「有測」的條件，從 `if agent_meta:` 收緊為 `if agent_meta and agent_meta.get("status") != "error":`。
- `pyproject.toml`：`[dependency-groups] dev` 補上 `"pyyaml>=6.0,<7"`（用 `uv add --dev pyyaml` 執行）。

## 原因
- **tasks.py**：Hermes-Agent 執行拋例外時，`agent_meta` 會是 `{"status": "error", ...}`，仍是 truthy，會被舊條件誤判為「UX 有測」。此時 UX 根本沒被真正測過，`category_scores["ux"]` 只是恰好維持在 100（因為沒有 UX finding），若計入 `overall_score` 平均，等於把「測到一半就掛掉」誤當「測過了、乾淨」而虛增總分。此問題是在覆核使用者提供的最新掃描報告（`overall_score=51`）時，順帶審查 `tested_categories` 邏輯發現的既有邊界情況，非該次報告實際觸發（該次 agent 未出錯）。
- **pyproject.toml**：`backend/apps/scans/tests_k8s_network_policy.py` 需要 `import yaml` 解析 k8s manifest 做測試，但 `pyproject.toml` 的 dev group 原本沒宣告 `pyyaml`，只有 `uv.lock` 裡有殘留紀錄。兩者不一致導致每次 `uv run` 都會把 `uv.lock` 的 pyyaml 項目清掉，使該測試檔案 `ModuleNotFoundError`、且每次驗證後都要手動 `git checkout -- uv.lock` 復原一個無關的 diff。

## 影響範圍
- `run_scan_job()` 的 `overall_score` 計算：僅在 Hermes-Agent 執行失敗（`ARGUS_AGENT_ENABLED=true` 且跑出例外）這個既有邊界情況下行為改變，正常路徑（未啟用 / 啟用且成功）不受影響。
- 開發環境測試：`tests_k8s_network_policy.py` 現在能穩定執行，不再因 lockfile 被意外改動而失敗或需人工復原。

## 驗證方式
- `uv run ruff check backend` → All checks passed
- `uv run python backend/manage.py test apps.scans` → 297 tests passed（較先前 293 項多 4 項，即原本因 `import yaml` 失敗而未被計入的 `tests_k8s_network_policy.py` 測試）
- `git diff --stat uv.lock` → 無變動（`pyproject.toml` 補上宣告後與既有 `uv.lock` 內容一致，不再需要 revert）
