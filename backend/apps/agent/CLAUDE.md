# agent 模組規則

Claude Code 進 `backend/apps/agent/` 工作時，本檔在專案層 `CLAUDE.md` 之後自動載入；**ZCode／Codex 不會自動載入本檔**，動手前必須先讀（見根 `AGENTS.md` 模組規則必讀閘門）。

**完整架構文件（角色目錄／工具清單／調校參數／迭代教訓）見
[`../../../docs/hermes-agent-architecture.md`](../../../docs/hermes-agent-architecture.md)
——改本模組前必讀。**

## 職責

掃描後的動態測試（deep_mode＝active＋authorized 才全開）：recon agent →
orchestrator agent（subagent 派工）→ specialist subagent（6 角色）。
`ARGUS_AGENT_ENABLED=false`（預設）時 `runner.run_agent_for_scan` 直接
`return None`。

## 關鍵檔案

| 檔案 | 職責 |
|---|---|
| `runner.py` | 流程編排：recon→orchestrator（首步 tool_choice 強制派工）→specialist；`SPECIALIST_ROLES` 角色目錄（desc＋when）；authenticated scan 帳密解密注入；`_merge` 結果合併 |
| `providers.py` | `ChatProvider`／`ProviderChain`（**MiniMax-M3** 主力→GLM→Gemini 純文字 fallback）；`ProviderError` 只帶公開資訊 |
| `loop.py` | `HermesAgent` tool-calling 迴圈；`_compact_stale_tool_results`（bulky 觀察快照壓縮）；`_inject_stall_hint`（連續 click 空轉導正）；`_inject_endgame_hint`（剩 10 步強制 report）；`forced_first_tool`（orchestrator 首步鎖定） |
| `tools.py` | `ToolExecutor`：**20 個工具**（見架構文件清單）；deep_only 閘；`redact_tool_arguments/result` 持久化遮罩；JWT 於 snippet 壓縮 |
| `findings.py` | `persist_agent_issues`＋`persist_agent_security_findings`（description 去重；owasp tag） |

## 安全（硬規則）

- **嚴禁**在 log／exception／repr／AgentStep 印出 API key；authenticated scan 帳密只以 Signer 加密入 DB、只在 prompt 注入處解密，**不得**進 log/findings/報告。
- Playwright context 套 public target policy＋same-origin 主文件/WebSocket 攔截；agent 無 `navigate(url)`，**不得新增**可繞過此邊界的導覽能力。
- 主動工具（`probe_sql_injection`／`probe_unauthorized_access`／`replay_request`／`run_nuclei`）＝deep_mode schema 隔離＋runtime 再驗＋同源閘三層；任何新主動工具必須接同邊界。
- `replay_request`：method 限 GET/POST/PUT/PATCH（禁 DELETE）；不跟隨 redirect；`store_token_key` 只寫 agent 自己的 browser context。
- `report_security_issue` severity 封頂 high（critical 保留給 sqlmap 工具確認）；evidence 必填、經遮罩。
- specialist 不掛 `dispatch_specialist`（防遞迴）；orchestrator 只掛 dispatch/finish/report。
- Kali 攻擊鏈正式環境 disabled；啟用 runbook 見 `docs/runbooks/kali-sqlmap-rollout.md`。

## 禁止事項

| 禁止 | 原因 | 正確做法 |
|---|---|---|
| 印出／持久化 API key、測試帳密明文 | 機密外洩 | 只記 provider／HTTP 狀態／model ID |
| 給 agent `navigate(url)` 類 tool | 繞過 same-origin | 維持操作當前頁／同源重放 |
| `ARGUS_AGENT_ENABLED` 預設改 True | 成本與風險不可控 | 預設 False，明確授權才開 |
| prompt 寫入任何目標特定路徑／答案 | 破壞黑箱泛化（#22 稽核先例：通用路徑例子 `/rest/`、`/api/` 也移除） | 只寫方法論與工具描述；payload／字典屬工具配備（使用者裁定） |
| 硬編碼 provider key／endpoint | 機密外洩 | 放 `.env` |
