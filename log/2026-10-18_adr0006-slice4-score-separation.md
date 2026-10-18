# ADR-0006 第 4 刀：確定性基準分與 AI 深度測試分數分離

**日期**：2026-10-18
**操作者**：Claude
**來源**：ADR-0006 落地順序第 4 刀（決策 C）。使用者拍板：**只分離 agent 資安觀察**（保留 agent UX 與
Kali 於分數內）、**一次做到位**（後端＋報告＋前端＋競賽 Word）。

## 做了什麼
- **scanners.py**：`is_agent_observation`（rule_id `agent-observed-security-*`）、`summarize_agent_security`
  （`{count, severity_counts, max_severity}`）。`calculate_scores` 本身不變（仍計傳入的 findings）。
- **tasks.stage_scoring**：以 `is_agent_observation` 濾出確定性層餵 `calculate_scores`（headline／
  `category_scores`／`overall_score`／`top_actions`）；AI 觀察另出 `agent_findings_summary` 持久化。
  Kali 已驗證與其他確定性規則照常計分；agent 觀察（含 tool_verified）一律不進基準分。
- **model**：`ScanJob.agent_findings_summary` JSONField（migration 0037）。
- **versions**：`SCORING_VERSION` 4→5（公式改了，與舊掃描不可直接比較）。
- **serializer**：`ScanJobSerializer` 出 `agent_findings_summary`；`projects.project_security` 回同欄位。
- **報告**：`_headline` 導讀句註明分數為「確定性檢查基準分，不含 AI 深度測試」，並於有 AI 發現時加一句
  「另有 AI 深度測試發現 N 項（獨立呈現、不計入基準分）」；`RENDERER_VERSION` 34→35。
- **前端**：`ProjectSecurityPage` 資安分數卡 hint 改「確定性檢查；不含 AI 深度測試」，並在有 AI 發現時
  加一則說明（獨立列於問題清單、不計入基準分，趨勢以基準分為準）；重新產生 openapi.json 與 apiTypes.ts。
- **競賽 Word 內容 md**（`需求書_複賽版完整內容.md`）：ARGUS-F-015 與計分段落改為「AI 代理資安觀察不計入
  可比較基準分、另以 AI 深度測試獨立呈現；Kali 等確定性工具確認的漏洞仍計入」。

## 驗證
- 新測試 `tests_scoring_and_report_grouping.AgentScoreSeparationTests`（3）：is_agent_observation 只認
  agent 前綴、摘要計數與最高嚴重度、agent 濾掉後分數＝只算確定性。
- 後端 `apps.scans`＋`apps.agent`＋`apps.billing` **1717 passed（skipped 12）**；`makemigrations --check` 無遺漏；
  `ruff` 乾淨。前端 `typecheck` 乾淨、`lint` 僅既有 AdminPages 警告、`ProjectSecurityPage.test` 6 綠。

## 備註
- 範圍：只分離 `agent-observed-security-*`。agent UX（`AGENT_UX_*`，封頂中風險、UX 的主要訊號）仍計入
  UX 分數；Kali（`kali-*`）仍計入資安分數。
- `comparable` 語意不變（版本相同才可比較）；分數分離讓同站同碼的 headline 不再被 agent 運氣帶動。
- 前端需 build 才生效（本環境未跑 build）；openapi.json／apiTypes.ts 已更新並通過 typecheck。
- 第 1～4 刀完成；第 5 刀收尾（doc-sync、ADR 回填落地狀態、push）。
