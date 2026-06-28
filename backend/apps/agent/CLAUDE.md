# agent 模組規則

Claude 操作 `backend/apps/agent/` 時，本檔在專案層 `CLAUDE.md` 之後自動載入。

## 職責
Phase 2 **Hermes-Agent**（掃描後的動態 UX 測試）。**預設關閉**（`ARGUS_AGENT_ENABLED=false`）；關閉時 `runner.run_agent_for_scan` 直接 `return None`，向下相容既有掃描流程。

## 關鍵檔案
| 檔案 | 職責 |
|---|---|
| `runner.py` | `run_agent_for_scan`（async，Celery 掃描流程呼叫；挑已成功爬到的 Page 當起點；**強制 same-origin**） |
| `providers.py` | `ChatProvider` / `ProviderChain`（MiniMax / GLM = OpenAI-compatible tool calling；Gemini = 純文字 fallback）；`ProviderError` 只帶公開資訊 |
| `loop.py` | `HermesAgent` tool-calling 迴圈、`AgentRunResult` |
| `tools.py` | `ToolExecutor`（8 個 tool）：`click` / `type_text` / `scroll` / `get_visible_text` / `get_dom_summary` / `take_screenshot` / `report_ux_issue` / `finish` |
| `findings.py` | `persist_agent_issues` 寫回 DB |

## 安全（硬規則）
- **嚴禁**在 log / exception / repr 印出 API key（金鑰一律 `.env`）。
- agent **沒有** `navigate(url)` tool → 隱含 same-origin 約束；**不要**新增可跨站導覽的 tool。
- 沿用 `SiteSense-AI-Scanner` User-Agent；Playwright 路徑由 settings 注入（`.ms-playwright`）。

## 禁止事項
| 禁止 | 原因 | 正確做法 |
|---|---|---|
| 印出 / 記錄 API key 或 raw response body | 機密外洩 | 只記 provider / HTTP 狀態 / model ID |
| 給 agent `navigate(url)` 類 tool | 繞過 same-origin、可打他站 | 維持只能操作當前頁元素 |
| 把 `ARGUS_AGENT_ENABLED` 預設改成 True | 計費與風險不可控 | 預設 False，明確授權才開 |
| 硬編碼任一 provider 的 key / endpoint | 機密外洩 | 放 `.env` |
