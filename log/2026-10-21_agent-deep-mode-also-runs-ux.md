# 2026-10-21 勾 AI Agent 時資安與 UX 測試兩者都要跑

## 問題（使用者回報）

> 似乎掃描的時候點選 AI Agent 並不會進行 AI UX 測試。我想要的：沒點選 AI Agent 時只有
> AI UX 測試；有點選 AI Agent 的話兩個都要有。

確認屬實。`runner.run_agent_for_scan` 的分支是 `if task_prompt / elif deep_mode / else`，
三者互斥：`deep_mode`（使用者勾深度 AI Agent＝active＋authorized＋`deep_agent_requested`）
為真時只跑資安滲透鏈（recon→orchestrator→specialist），`else` 的擬真使用者 UX session
被整個跳過。`scan_plan` 的 `run_agent`（deep）與 `run_agent_ux` 本來就是兩道獨立閘門、可同時
成立，但 runner 只擇一執行——所以「勾了 AI Agent 反而沒有 UX 測試」。

## 修改

- `backend/apps/agent/runner.py`
  - `run_agent_for_scan` 新增參數 `run_ux: bool = False`。
  - 抽出 `_run_ux_session()`：組 `DEFAULT_TASK_PROMPT_TEMPLATE`、以 `deep_tools=False`
    掛 UX 工具集跑單一 UX session（送出授權仍由 `allow_form_submit` 決定）。
  - `_run_session` 新增 `deep_tools: bool | None = None`：覆寫該 session 要不要掛深度資安
    工具（None＝沿用本次掃描的 `deep_mode`）。UX session 固定 `deep_tools=False`，不會拿到
    資安滲透工具。
  - `elif deep_mode` 分支：資安鏈跑完後，若 `run_ux` 再跑一個 `_run_ux_session()` 併入
    `_merge`；`else` 分支改呼叫同一個 `_run_ux_session()`（行為不變）。
- `backend/apps/scans/tasks.py`
  - `stage_agent` 以 `run_ux=plan.run_agent_ux` 呼叫 `run_agent_for_scan`。
  - 進度分母 `agent_total` 改為「深度資安估計（勾 run_agent 時）＋ UX 估計（勾 run_agent_ux
    時）」各自累加，涵蓋實際會跑的 session 數。

行為矩陣（都在 `ARGUS_AGENT_ENABLED=True` 前提）：

| 勾 AI Agent（deep） | 勾 UX 維度 | 結果 |
|---|---|---|
| 否 | 是 | 只跑 UX（與過去相同）|
| 是 | 是 | 先資安滲透鏈，再跑 UX session，兩者併入 |
| 是 | 否 | 只跑資安滲透鏈（`run_ux=False`）|

計費不受影響：`agent_deep_fee`／`agent_ux_fee` 原本就各自依 plan 旗標獨立計算。

## 驗證

- `uv run ruff check backend/apps/agent backend/apps/scans/tasks.py` → All checks passed
- `uv run python backend/manage.py test apps.agent apps.scans.tests_scan_plan apps.scans.tests_kali_pipeline`
  → 133 passed（新增 4 項）
- 新增測試：
  - `apps/agent/tests.py::RunAgentForScanBranchTests`：以假瀏覽器／假 HermesAgent 驗證
    deep_mode＋`run_ux=True` 會額外跑一個含「擬真使用者的 UX」提示詞的 session；
    `run_ux=False` 不跑（資安鏈仍在）。
  - `apps/scans/tests_scan_plan.py`：`stage_agent` 對深度掃描傳 `run_ux=True`；取消 UX
    維度時傳 `run_ux=False`。

## 文件同步

- `backend/apps/agent/CLAUDE.md`「職責」：新增「資安與 UX 不互斥」條。
- `backend/apps/scans/CLAUDE.md` agent 段：新增「兩者不互斥」條。
