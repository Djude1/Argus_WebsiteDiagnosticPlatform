# AI Agent 深度資安測試改為可選付費加項（使用者勾選才跑才收）

**日期**：2026-10-18
**操作者**：Claude
**來源**：使用者要求「AI Agent 變成掃描可選的一個項目，且勾 AI Agent 要加收點數」。

## 背景
深度資安 Hermes-Agent 原本只要「全站＋主動＋已授權」就**自動跑**、且自動收 `agent_deep_fee`
（50 點）。agent 跑一次 30+ 分鐘、耗 token，使用者希望改成**明確勾選才跑才收**，沒勾就只做
較快的確定性主動掃描。

## 改法（opt-in，預設 False）
- **model**：`ScanJob.deep_agent_requested = BooleanField(default=False)`（scans migration 0036）。
- **scan_plan**：`run_agent = site_active 且 deep_agent_requested`。沒勾時主動掃描照跑 Nuclei／
  Katana／敏感檔探測／未授權探測，只是不跑 LLM pentest agent。
- **billing**：`_scan_is_deep` 多判 `deep_agent_requested`（預扣 `scan_hold_amount`、結算
  `settle_scan_actual`、`scan_plan.run_agent` 三處一致）。serializer 的餘額預檢同步加這條件。
- **serializer**：收 `deep_agent_requested`（預設 False）、create 寫入。
- **前端**（`ScanJobForm`）：主動＋已授權＋全站時顯示勾選框「加做 AI Agent 深度資安測試（另加 N 點）」，
  勾了才送 `deep_agent_requested=true`、才在估價加 `agent_deep_fee`；`deepAgent` state 存草稿、送出後重置。
- UX 擬真測試（`run_agent_ux`，綁 UX 維度、+20）**不受影響**。

## 行為變更（注意）
- 這是刻意的 opt-in：**既有「主動＋已授權」掃描不再自動跑深度 agent、不再自動收 50 點**，要勾才有。
- MCP／其他非 UI 建立路徑走同一 serializer，預設 False＝不跑深度 agent（之後要再開可加參數）。

## 驗證
- 後端：`makemigrations --check` 無遺漏、`manage.py check` 乾淨；`apps.billing`＋`tests_scan_plan`
  ＋`tests_coverage`＋`tests_pipeline_stages`＋`apps.mcp_access`（200+44）通過；`ruff check backend` 乾淨。
  更新既有測試：pricing 的 `_active_scan`、scan_plan `_job`（預設勾、另加 opt-in 不跑測試）、
  coverage 的 nuclei 預算測試都補上 `deep_agent_requested=True`；新增 `test_deep_agent_requires_opt_in`。
- 前端：`lint`／`typecheck` 乾淨；`ScanJobForm.test.tsx`（10，+3：沒勾不收且送 false、勾了收且送 true、
  勾選前後費用文字）通過。重新產 `apiTypes.ts`（加 `deep_agent_requested`，diff 極小）。
- 文件同步：`backend/CLAUDE.md`（ScanJob 欄位）、`apps/scans/CLAUDE.md`（工具矩陣）、
  `apps/billing/CLAUDE.md`（深度附加費 opt-in）、`frontend/CLAUDE.md`（ScanExperience）。

## 待辦
- 待前後端 image rebuild＋部署後生效。
- 與先前的 coverage_summary revert 相互獨立：agent 登入穩定性（juice-shop 8AC2 的空手問題）仍是另案。
