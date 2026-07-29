# UX 評分邊界情況修正 + pyyaml 相依宣告補齊

**日期**：2026-07-29
**操作者**：Claude

## 變更內容
- `backend/apps/scans/tasks.py`：`tested_categories` 判斷 UX 是否「有測」的條件，從 `if agent_meta:` 收緊為 `if agent_meta and agent_meta.get("status") != "error" and agent_meta.get("steps", 0) > 0:`（分兩輪修正，見下）。
- `pyproject.toml`：`[dependency-groups] dev` 補上 `"pyyaml>=6.0,<7"`（用 `uv add --dev pyyaml` 執行）。
- `backend/apps/scans/tests_kali_pipeline.py`：新增 3 個 `tested_categories` 邊界情況回歸測試（第二輪，見下）。

## 原因
- **tasks.py 第一輪**：Hermes-Agent 執行拋例外時，`agent_meta` 會是 `{"status": "error", ...}`，仍是 truthy，會被舊條件誤判為「UX 有測」。此時 UX 根本沒被真正測過，`category_scores["ux"]` 只是恰好維持在 100（因為沒有 UX finding），若計入 `overall_score` 平均，等於把「測到一半就掛掉」誤當「測過了、乾淨」而虛增總分。此問題是在覆核使用者提供的最新掃描報告（`overall_score=51`）時，順帶審查 `tested_categories` 邏輯發現的既有邊界情況，非該次報告實際觸發（該次 agent 未出錯）。已 commit 為 `3a6ec38` 並 push。
- **tasks.py 第二輪（security-reviewer 複查後追加）**：呼叫 security-reviewer 覆核 `3a6ec38` 時，發現第一輪的 `status != "error"` 判斷不夠精準——`AgentSession.Status`（`backend/apps/scans/models.py`）只有 `queued`/`running`/`completed`/`failed` 四種值，`loop.py` 內部絕不會產生 `"error"`；`"error"` 只在 `run_agent_for_scan()` 本身於 `tasks.py` 外層 except 拋例外時才出現。若 agent 在**第一輪呼叫 provider 就失敗**（例如所有 provider API Key 同時失效/逾時），`status` 會是 `"failed"` 且 `steps=0`——這種「完全沒跑」的情況第一輪判斷仍會誤判為「已測且乾淨」。改用 `steps > 0` 作為判斷依據：只要 agent 真正執行過至少一輪（不論最終是 `completed` 乾淨結束，還是 `failed` 於 `max_steps_reached`/`token_budget_exceeded` 中止），過程中若有發現真實問題就會反映在 `category_scores["ux"]`，不應被排除在 `overall_score` 平均之外；只有 `steps=0`（根本沒跑）或 `status="error"`（外層基礎設施例外）才排除。
- **pyproject.toml**：`backend/apps/scans/tests_k8s_network_policy.py` 需要 `import yaml` 解析 k8s manifest 做測試，但 `pyproject.toml` 的 dev group 原本沒宣告 `pyyaml`，只有 `uv.lock` 裡有殘留紀錄。兩者不一致導致每次 `uv run` 都會把 `uv.lock` 的 pyyaml 項目清掉，使該測試檔案 `ModuleNotFoundError`、且每次驗證後都要手動 `git checkout -- uv.lock` 復原一個無關的 diff。

## 影響範圍
- `run_scan_job()` 的 `overall_score` 計算：僅在 Hermes-Agent 執行異常（外層例外，或第一輪呼叫 provider 就失敗導致 `steps=0`）這兩個既有邊界情況下行為改變，正常路徑（未啟用 / 啟用且至少跑過一輪）不受影響。
- 開發環境測試：`tests_k8s_network_policy.py` 現在能穩定執行，不再因 lockfile 被意外改動而失敗或需人工復原。

## 驗證方式
- `uv run ruff check backend` → All checks passed
- `uv run python backend/manage.py test apps.scans.tests_kali_pipeline` → 10 tests passed（含 3 個新增的 `tested_categories` 邊界回歸測試）
- `uv run python backend/manage.py test apps.scans` → 466 tests passed（skipped=1，既有跳過項目，與本次變更無關）
- `git diff --stat uv.lock` → 無變動（`pyproject.toml` 補上宣告後與既有 `uv.lock` 內容一致，不再需要 revert）
