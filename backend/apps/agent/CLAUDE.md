# agent 模組規則

Claude 操作 `backend/apps/agent/` 時，本檔在專案層 `CLAUDE.md` 之後自動載入。

## 職責
Phase 2 **Hermes-Agent**（掃描後的動態 UX 測試）。**預設關閉**（`ARGUS_AGENT_ENABLED=false`）；關閉時 `runner.run_agent_for_scan` 直接 `return None`，向下相容既有掃描流程。

## 關鍵檔案
| 檔案 | 職責 |
|---|---|
| `runner.py` | `run_agent_for_scan`（async，Celery 掃描流程呼叫；挑已成功爬到的 Page 當起點；**強制 same-origin**） |
| `providers.py` | `ChatProvider` / `ProviderChain`（MiniMax / GLM = OpenAI-compatible tool calling；Gemini = 純文字 fallback）；`ProviderError` 只帶公開資訊 |
| `loop.py` | `HermesAgent` tool-calling 迴圈、`AgentRunResult`（含 `issues` 與 `security_findings`） |
| `tools.py` | `ToolExecutor`（9 個 tool）：`click` / `type_text` / `scroll` / `get_visible_text` / `get_dom_summary` / `take_screenshot` / `report_ux_issue` / `probe_sql_injection` / `finish` |
| `findings.py` | `persist_agent_issues`（UX findings）+ `persist_agent_security_findings`（`probe_sql_injection` 確認的 security findings）寫回 DB |

## 安全（硬規則）
- **嚴禁**在 log / exception / repr 印出 API key（金鑰一律 `.env`）。
- Playwright context 對所有請求套用 public target policy，停用 Service Worker，並阻擋跨 origin 主文件與 WebSocket；agent 沒有 `navigate(url)` tool，仍不得新增可繞過此邊界的導覽能力。
- `probe_sql_injection(url)`（LLM 自主觸發的 SQLi 主動驗證）**必須維持三層防護**，不可放寬：
  ① `tools.py` 內強制**同源**（比對 `scan_job.origin`）+ 需帶 query 參數；
  ② 實際攻擊委派 `kali_tools.run_sqlmap` 的**三重授權鎖**（`ARGUS_KALI_ENABLED` + active + authorized）；
  ③ 提示層只在 `deep_mode`（active+authorized）才把此能力寫進 prompt。確認可注入才由 runner 落地 `kali-sqlmap-sqli`（A03/CWE-89）critical finding。
- **AI-first 工具暴露與遮罩（Task 6）**：
  - `build_tool_schemas(allow_sqlmap)` 在非 `deep_mode` 掃描**完全排除** `probe_sql_injection`（深拷貝 `TOOL_SCHEMAS`，避免 LLM 看到能力）；回傳獨立 list，避免共用 mutable schema。
  - `redact_tool_arguments("probe_sql_injection", args)` 持久化到 `AgentStep` 前對 `url` 套用 `redact_url_query_values`；`redact_tool_result` 只保留 `confirmed` / `blocked` / `error` / `correlation_id`，移除 target URL 與其他欄位。
  - `tasks.py` 的順序固定為 scanner → **Hermes-Agent（先）** → **Kali fallback（後）** → scoring；Agent 確認的 `security_findings` 會餵進 scoring。Redis 指紋讓 fallback 只處理 agent 沒驗證過的獨特 target，避免重打。
- 沿用 `SiteSense-AI-Scanner` User-Agent；Playwright 路徑由 settings 注入（`.ms-playwright`）。
- Kali 攻擊鏈目前 disabled（`ARGUS_KALI_ENABLED=false` / `ARGUS_KALI_BACKEND=disabled`）；啟用 runbook 見 [`../../../docs/runbooks/kali-sqlmap-rollout.md`](../../../docs/runbooks/kali-sqlmap-rollout.md)，靜態加密前置見 [`../../../docs/runbooks/kubernetes-secret-at-rest-encryption.md`](../../../docs/runbooks/kubernetes-secret-at-rest-encryption.md)。

## 禁止事項
| 禁止 | 原因 | 正確做法 |
|---|---|---|
| 印出 / 記錄 API key 或 raw response body | 機密外洩 | 只記 provider / HTTP 狀態 / model ID |
| 給 agent `navigate(url)` 類 tool | 繞過 same-origin、可打他站 | 維持只能操作當前頁元素 |
| 把 `ARGUS_AGENT_ENABLED` 預設改成 True | 計費與風險不可控 | 預設 False，明確授權才開 |
| 硬編碼任一 provider 的 key / endpoint | 機密外洩 | 放 `.env` |
