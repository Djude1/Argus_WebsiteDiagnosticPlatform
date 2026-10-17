# Hermes-Agent 即時進度回報（修「0/20 不動像卡住」）

**日期**：2026-10-18
**操作者**：Claude
**來源**：使用者實機掃描時回報——agent 階段 ~18 分鐘，進度一路顯示「AI Agent：0/20 步」不動，
看不出在幹嘛、也不知是否卡住（實際是正常運作，recon→orchestrator→最多 6 專家共數百回合 LLM）。

## 根因
`runner.py`／`loop.py` 完全沒有進度回報：agent 整段跑完才由 `stage_agent` 一次寫回進度。
且畫面顯示的「20」只是**單一子代理**的 `ARGUS_AGENT_MAX_STEPS`，不是整體（專家各跑最多
`_SPECIALIST_MAX_STEPS`=60），雙重誤導。

## 修法（只加即時進度，不砍深度、不減 critical——使用者選擇）
- `loop.HermesAgent`：新增 `step_callback`，`run()` 每個 round 開始經 `sync_to_async` 呼叫一次，
  try/except 吞掉任何例外（回報失敗不得中斷 agent 迴圈）。
- `runner.run_agent_for_scan(progress_cb=...)`：`_run_session(role_label=...)` 把回呼包成
  `step_callback=lambda rnd: progress_cb(role_label, rnd)`；recon／orchestrator／各專家／UX 各帶角色標籤。
  新增 `max_total_steps_estimate()`（recon＋orchestrator 各 20 ＋ 最多 6 專家 ×60）當進度分母。
- `tasks.stage_agent`：定義 `_report_agent_step`（累加全域步數→`_write_progress`，fail-safe），
  傳 `progress_cb`；初始與收尾進度的 `step_total` 都改用估算值（不再是 20）。

前端無需改：`ScanExperience.scanProgress` 本來就讀 `step_done／step_total` 算整體 %，後端餵真實
累計數字後進度條與百分比就會動（避免在部署吃緊時引入未經 build 的前端改動）。

## 刻意不做
- 不砍 `ARGUS_AGENT_MAX_SPECIALIST_DISPATCH`／`_SPECIALIST_MAX_STEPS`／加牆鐘上限——那會少跑專家、
  可能少抓 critical，是另一個取捨；使用者這次只要「看得出活著」。

## 追加：前端顯示「專家名稱」（2026-10-18，使用者要求「補上前端的『專家名稱』顯示」）
前一版回呼已帶 role_label，只差落地到進度與前端顯示，這次補上：
- 後端 `tasks._write_progress` 新增 `detail=""` 參數，有值才寫入 `progress["step_detail"]`（其他步驟不留此鍵）。
- `tasks.stage_agent`：`_AGENT_ROLE_LABELS`／`_AGENT_SPECIALIST_LABELS`＋`_agent_role_label()` 把 runner 的
  role_label（recon／orchestrator／ux／specialist／specialist:<8 角色>）轉成中文；`_report_agent_step`
  每步帶 `detail=_agent_role_label(role_label)`。8 種專家代號對齊 `runner.SPECIALIST_ROLES`。
- 前端 `ScanExperience.CrawlingAnimation`：agent 階段時 `crawl-anim-step-hint` 顯示 `progress.step_detail`
  （`agentDetail || current.hint`），其餘階段不受影響；`scanProgress()` 既有邏輯不動、免動 build 以外的計算。
- 測試：`tests_progress.py` 加 `AgentStepDetailTests`（detail 只在有值時寫入、角色→中文對映含未知 fallback）；
  前端 `ScanExperience.jsx` 過 ESLint。`apps.scans.tests_progress`＋`apps.agent.tests_progress_callback` 19 項通過。

## 驗證
- 新增 `agent/tests_progress_callback.py`（4）：回呼第一步就觸發、回呼爆炸不中斷迴圈、無回呼正常、
  估算為正。`apps.agent`＋`apps.scans` 全套 1544 通過（skipped 12）；ruff 乾淨。
- 文件同步 `agent/CLAUDE.md`、`scans/CLAUDE.md` 的進度格式說明。

## 備註
不含真實站名／路徑／機密值。
