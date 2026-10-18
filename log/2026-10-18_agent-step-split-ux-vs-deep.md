# 掃描進度：區分「AI 深度資安測試」與「AI 擬真使用者測試」步驟

**日期**：2026-10-18
**操作者**：Claude
**來源**：使用者回報——沒勾「加做 AI Agent 深度資安測試（另加 50 點）」，掃描時卻仍出現「AI Agent」階段。

## 根因（不是 bug，是命名誤導）
深度資安 AI Agent（`run_agent`）確實已因沒勾 `deep_agent_requested` 而不執行；但**擬真使用者
UX 測試 agent（`run_agent_ux`）是獨立功能**——只要全站掃描且勾了 UX 維度就跑（不需主動授權、
不收深度費），而進度步驟與前端 `SCAN_STEP_META` 都把兩者都叫成通用的「AI Agent」，使用者便以為
是沒買的付費滲透測試。

## 修法（把兩種 agent 的步驟鍵與名稱分開）
- `tasks.planned_scan_steps`：勾深度資安 → 步驟 `agent`；否則只跑 UX → 步驟 `agent_ux`（兩者互斥）。
- `tasks.stage_agent`：`agent_step_key = "agent" if plan.run_agent else "agent_ux"`，進度回寫一律用它。
- `_first_step` 的候選清單補上 `agent_ux`（讓「下一步」跳轉在 UX-only 時找得到該步驟）。
- 前端 `SCAN_STEP_META`：`agent`＝「AI 深度資安測試」（像滲透測試員找越權／業務邏輯），
  新增 `agent_ux`＝「AI 擬真使用者測試」（擬真操作測互動流程，註明非資安深度測試）；
  `stepUnit`／`agentDetail` 的 `=== "agent"` 判斷改成涵蓋 `agent_ux`。
- coverage 的 `agent`／`agent_ux` 兩個 check 標籤本就分開，未動。

## 驗證
- 新測試 `tests_progress`：UX-only 全站掃描 → 步驟含 `agent_ux`、不含 `agent`；
  全站＋主動＋已授權＋deep_agent_requested → 含 `agent`、不含 `agent_ux`。
- 後端 `apps.scans` **1511 passed**；前端 `typecheck` 乾淨、`src/features/scans` 測試 10 綠。
- 文件：`frontend/CLAUDE.md` SCAN_STEP_META 條目同步。

## 備註
- 行為本身未變（UX agent 該跑時照跑）；這刀只把顯示名稱與步驟鍵講清楚，消除「以為是付費深度資安」的誤會。
- 前端需 build 才生效（本環境未跑 build）。
