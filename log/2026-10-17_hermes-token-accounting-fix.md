# 修正 Hermes Agent token 計帳重複累加（資安專家假性爆表、產出 0）

**日期**：2026-10-17
**操作者**：Claude

## 背景
使用者轉來 Codex 對 Argus 的獨立審查（對 ntubimdbirc.tw 連續四次 active 全站掃描 + 程式追查），第 1 點：資安 Hermes Agent 每次燒 ~30 萬 token、`agent-` 類 finding 全部 0，各角色都撞 `token_budget_exceeded`。我追 `loop.py`／`providers.py` 確認屬實。

## 根因
- `loop.run()` 每輪：`self._total_tokens += response.total_tokens`。
- `providers._parse_openai_choice`：`total_tokens = usage["total_tokens"]`（該次請求 prompt＋completion 的總量）。
- tool-calling 迴圈每輪把整段對話歷史重送當 prompt，所以 `total_tokens` 隨 context 成長；逐輪累加＝把成長中的 context 重複計好幾次。
- 結果：`ARGUS_AGENT_MAX_TOKENS=60000` 實際只夠 ~7 次 LLM 呼叫。資安專家在 WAF／情報窄的站上，光 recon／探索就燒完，還沒呼叫 `report_security_issue` 就被砍 → `_security_findings` 空 → 回傳 0。（findings 不是被丟，是根本沒產出過。）

## 變更內容（`backend/apps/agent/loop.py`）
- 新增 `_accumulate_tokens(response)`，以「不重複計 context 的有效量」衡量預算：
  - `completion` 逐輪累加（每輪都是新產出）。
  - `prompt` 只取**最新一輪**（它已含整段歷史），不把成長中的歷史重複累加。
  - `_total_tokens = 累計 completion + 最新一輪 prompt`。
  - provider 沒給 prompt/completion 細項時：用 `total − completion` 回推 prompt；完全無細項則取最新一輪整筆（不累加）。
- `run()` 的 `self._total_tokens += response.total_tokens` 改呼叫 `_accumulate_tokens(response)`。
- 預算上限 `ARGUS_AGENT_MAX_TOKENS` 維持 60000（Codex 建議：治本是改計帳，不是單純調高上限）；現在 6 萬是真的 ~6 萬有效量。
- 每個 `AgentStep.token_count` 仍記該次請求的 `response.total_tokens`（per-call 實際花費，不變）。

## 影響範圍
- 只改 agent 迴圈的預算衡量方式；工具、派工、嚴重度、計費邏輯不變。
- 資安各角色現在能跑到足夠步數走完 recon → 探索 → 回報，才可能產出 `agent-` finding（實際有沒有產出仍取決於目標與 LLM）。
- `AgentSession.total_tokens` 數字語意改為「有效量」而非「naive sum」；沒有 prompt/completion 細項的 provider 回報值會比舊版小（不再重複計）。

## 驗證方式
- `ruff check` 通過；`apps.agent` 全套 82 項通過。
- 測試調整／新增（`tests.py`）：
  - `test_max_tokens_triggers_failure` 改用「completion 會累加」觸發上限（prompt 穩定不再假性爆表）。
  - 新增 `test_stable_context_does_not_exhaust_budget`：prompt 每輪穩定 ~8000、completion 500，跑 12 輪＋finish，不再 `token_budget_exceeded`、有效量遠低於 60k（回歸鎖定 Codex 指出的 bug）。
  - `test_finish_via_tool` 斷言由 50 改為 30（無細項時＝最新一輪 prompt，不重複累加舊 context）。

## 尚未做（需你決定／正式環境）
- **把 Hermes 預設開**：`backend/apps/agent/CLAUDE.md` 禁止事項明定「`ARGUS_AGENT_ENABLED` 預設改 True」不可（成本與風險不可控，正確做法是「明確授權才開」）。因此**不改程式預設**；正式環境要開請在 K8s env／secret 設 `ARGUS_AGENT_ENABLED=true`（本機／CI 維持 False）。另需正式環境已設 LLM 金鑰，且開啟後每次「全站＋主動＋已驗證」掃描會收 50 點深度資安附加費。
- 需正式環境重掃（開啟 agent）確認：資安專家現在能走到回報、`agent-` finding 不再恆為 0。

## 備註（安全）
程式／測試／log 不含真實站名與未修補漏洞的真實路徑／內網 IP。
