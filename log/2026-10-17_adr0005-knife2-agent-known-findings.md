# ADR-0005 第二刀：Agent 吃既有確定性發現、不盲跑重報

**日期**：2026-10-17
**操作者**：Claude
**依據**：[ADR-0005](../docs/adr/0005-scan-pipeline-tool-integration.md) §5、遷移計畫第 2 刀。

## 背景
現況 Agent 盲跑：不知道確定性工具（Nuclei／被動分析／檔案探測／未授權探測）這次已找到什麼，
於是重複測、重複報同一個問題，再靠 `cross_layer`／`consolidate_security_findings` 事後去重——
浪費步數與 token（使用者最在意的點）。

## 變更內容

### `backend/apps/agent/runner.py`
- `run_agent_for_scan(..., known_findings=None)`：新增參數。
- `_summarize_known_findings(known)`：把確定性層已找到的資安發現組成摘要——**只給標題／端點／
  嚴重度，不送 evidence**（避免把遮罩過的證據再攤進 prompt），依 (rule_id 或 title) 去重、上限 20 筆。
- `ORCHESTRATOR_PROMPT` 新增「確定性工具已找到的問題——不要重報」段與規則：別派專家重複確認/重報
  這些，把步數花在要推理才找得到的（相鄰端點要登入、某端點漏授權的差異；多步驟商業邏輯濫用；
  跨端點串接）與對既有發現做工具驗證／升級。

### `backend/apps/scans/tasks.py`
- `stage_agent` 從 `ctx.all_findings` 取本次 `category=="security"` 的發現當 `known_findings` 傳入。
  此時 agent／kali 尚未產出，所以這些全是確定性發現。

## 驗證
- `agent/tests_known_findings.py`（6）：只列資安、帶端點/嚴重度、rule_id 去重、空輸入回「（無）」、
  **不洩漏 evidence**（excerpt/evidence 不進摘要）、`ORCHESTRATOR_PROMPT.format` 新鍵不缺（回歸）。
- `apps.agent` 全套 87 通過；`apps.scans` 全套 1433 通過（stage_agent 呼叫簽名變動未破壞既有 mock）；
  ruff 通過。
- 這是 prompt／輸入層變更，實際「少重報多少」要在正式環境接真模型重掃才量得到；本刀確保資料正確
  餵入且不洩漏，行為改善屬模型端。

## 備註（安全）
摘要刻意不含 evidence；測試用虛構網址與 canonical 範例，不含真實站名、路徑或秘鑰。
