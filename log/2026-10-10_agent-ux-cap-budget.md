# AI Agent UX 測試：嚴重度封頂中風險、另設 token 預算

**日期**：2026-10-10  
**操作者**：Claude

## 變更內容
- `apps/agent/findings.py`：新增 `cap_ux_severity`，Agent UX 問題的 critical／high 降為 medium，未知值當 low；`persist_agent_issues` 改用它。
- `apps/agent/tools.py`：`report_ux_issue` 的 severity 列舉改為 medium／low／info，並說明各等級的意思；工具回傳時也套用 `cap_ux_severity`。
- `config/settings.py`、`.env.example`：新增 `ARGUS_AGENT_UX_MAX_TOKENS`（預設 120000）。後台系統資訊頁的 agent 區塊也顯示這個值。
- `apps/agent/runner.py`：`_run_session` 加 `max_tokens` 參數，只有擬真使用者 UX session 傳入 `ARGUS_AGENT_UX_MAX_TOKENS`。資安各角色仍用 `ARGUS_AGENT_MAX_TOKENS`（60000）。
- `apps/scans/tasks.py`：`_mark_agent_coverage` 遇到 `token_budget_exceeded` 時標 partial（「token 預算內未完成」），不再標 failed。
- `apps/scans/versions.py`：`RULESET_VERSION` 改為 2026.10.10.4，因為嚴重度規則有變。
- 文件：`docs/hermes-agent-architecture.md`（1b 節、調校參數表）、`docs/scan-stage-checks.md`（AI Agent 節）、`backend/apps/agent/CLAUDE.md`、`backend/apps/scans/CLAUDE.md`、競賽需求書 ARGUS-F-015。

## 原因
用 MiniMax-M3 實際跑示範網站的 AI Agent 測試（scan 11）時發現兩個問題：
1. Agent 把「加入購物車導向聯絡表單」自評為 critical。這一筆就讓 UX 從 41 分掉到 23 分。AI 觀察沒有規則依據，不應比規則式檢查扣得更重。
2. 6 萬 token 只走了 14 步就用完，整個 Agent 被標為 failed，雖然它已經回報了有效問題。如果直接調高全域的 `ARGUS_AGENT_MAX_TOKENS`，深度資安模式每位專家的上限會一起翻倍，所以改成只給 UX 測試另設預算。

## 影響範圍
- 新產生的 Agent UX 問題最高是中風險。舊掃描已存的嚴重度不變。
- UX 測試每次掃描的 token 上限從 6 萬提高到 12 萬，單次成本上限約增加一倍（固定附加費 `ARGUS_COIN_AGENT_UX` 不變）。
- 預算用完時，`agent_ux` 覆蓋紀錄標 partial，UX 維度照常評分，但會顯示為部分評估。

## 驗證方式
- 新增測試：`report_ux_issue` 的列舉、`persist_agent_issues` 封頂（critical／high → medium、info 不變），以及 `_mark_agent_coverage` 遇到 token 預算用完時標 partial、遇到其他錯誤時標 failed。
- `manage.py test apps.agent apps.scans.tests_coverage`：94 項全部通過。`ruff check backend` 通過。完整後端測試 `manage.py test apps`：1825 項通過（10 項略過）。
- 沙箱用 MiniMax 實際掃描示範網站（scan 12，152 秒）：
  - Agent 回報同一個購物車問題，嚴重度為 medium。
  - UX 分數 37（scan 11 是 23）。
  - 覆蓋紀錄為 `agent_ux=partial`（「token 預算內未完成」）。
  - 這次走了 27 步、用了 121880 token，仍在 12 萬內用完，但已回報的問題有保存。
