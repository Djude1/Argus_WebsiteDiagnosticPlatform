# AI Agent 資安發現：工具驗證過才可破 medium 封頂

**日期**：2026-10-10  
**操作者**：Claude

## 變更內容
- `apps/agent/tools.py`：
  - `ToolExecutor` 新增 `self._active_confirmations` 集合，`_track_verification` 在 `replay_request`／`probe_payload_injection`／`probe_unauthorized_access`／`probe_sql_injection`／`run_nuclei` 成功時記錄工具名稱（在 `run()` dispatch 包起來）。
  - `report_security_issue` schema：severity enum 加回 `critical`／`high`，新增 `verified` 布林欄位，描述說明高風險以上的條件。
  - `_report_security_issue`：severity 為 high／critical 時，只有 `verified=true` **且** `_active_confirmations` 非空才保留，否則降 medium；`evidence_json.tool_verified` 記錄結果，description／assessment 依是否驗證給不同文字。
- `apps/scans/reports.py`：`_report_severity` 對 `agent-` 規則的封頂改成「`evidence_json.tool_verified` 為真就不封頂」，未驗證（含舊資料）仍降中風險。
- 測試：`apps/agent/tests.py` 三項（未驗證降 medium、宣稱 verified 但沒呼叫工具仍降 medium、真的呼叫過工具＋verified 保留 critical）；`apps/scans/tests_report_evidence_quality.py` 一項（tool_verified 報告保留嚴重風險）。
- 文件：`backend/apps/agent/CLAUDE.md`、`docs/hermes-agent-architecture.md`、`docs/scan-stage-checks.md`、競賽需求書 ARGUS-F-015 同步。

## 原因
對本機 Docker OWASP Juice Shop 跑完整主動掃描（scan 13）時，Agent 實際挖到登入 SQL 注入繞過、IDOR 個資洩漏、/ftp 目錄列表等真漏洞，但因為「AI 觀察一律封頂 medium、high 以上只給 Kali sqlmap 確認」的舊規則，全部顯示 medium。正式環境 Kali 停用，等於這些確認過的漏洞永遠無法標到應有的嚴重度。使用者要求放低門檻、不需 Kali sqlmap 驗證。

採「工具確認才可破 medium」而非完全移除封頂：Agent 用自己的主動工具（重送請求／注入探測／未授權存取探測）實際重現確認後才可到 high／critical，純觀察仍封頂 medium。保留「要先真的呼叫過工具」這道關卡，避免把先前為 UX 修掉的「AI 過度自評」問題在資安端重新打開。

## 影響範圍
- 新產生、且 Agent 以主動工具驗證過的資安發現可顯示並計分為 high／critical（計分權重 35／60，原本一律當 medium 的 12）。純觀察、舊資料仍封頂 medium。
- `verified=true` 但 Agent 從沒成功呼叫過主動工具時仍降 medium（防純自評）。
- 報告層同步放行，不會把已存成 critical 的發現在排版時又降回中風險。

## 驗證方式
- 新增 4 項單元測試涵蓋三種閘門情境與報告層保留。
- `manage.py test apps.agent apps.scans.tests_report_evidence_quality apps.scans.tests_accuracy_review apps.scans.tests_coverage apps.scans.tests_ai_insight`：134 項通過。`ruff check backend` 通過。
- 待辦（成本考量未在此次執行）：對 Juice Shop 重跑一次主動掃描，確認 MiniMax 實際會依新 schema 帶 `verified=true`、讓登入 SQLi 繞過等顯示為 high／critical。
