# 修：UX 擬真測試進度分母用 UX 估計（不再顯示像資安的 400 步）

**日期**：2026-10-18
**操作者**：Claude
**來源**：使用者回報沒勾深度資安，進度卻顯示「AI 擬真測試：15/400 步」。

## 說明（兩件事）
1. **執行分支**：上一刀 `e25dee9`（`is_deep_security_mode` 需 `deep_agent_requested`）才是讓沒勾時
   不跑資安 pentest（recon→specialist）的修正——**該 commit 尚未部署**時，線上仍跑資安分支、顯示
   「偵察目標」。部署並重啟 worker、重跑一次新掃描後才會生效。
2. **進度分母（本刀）**：`stage_agent` 不論哪個分支都用 `max_total_steps_estimate()`＝400
   （recon＋orchestrator＋6 專家×60）當分母，於是 UX-only 也顯示 /400，看起來像在跑資安 agent。

## 修法（本刀）
- `runner.ux_steps_estimate()`：UX 只跑單一 session，上限 `_SPECIALIST_MAX_STEPS`（60）。
- `stage_agent`：`agent_total = max_total_steps_estimate() if plan.run_agent else ux_steps_estimate()`。
  沒勾深度資安（UX-only）分母＝60，不再是 400。

## 驗證
- `apps.agent`＋`apps.scans.tests_progress` **113 passed**；`ruff` 乾淨。

## 使用者需知
- 要讓「沒勾就完全不跑資安」真正生效：**部署含 `e25dee9` 與本 commit 的後端、重啟 worker、再開一次新掃描**。
  目前正在跑或已開始的掃描是舊程式，會跑完舊行為。
