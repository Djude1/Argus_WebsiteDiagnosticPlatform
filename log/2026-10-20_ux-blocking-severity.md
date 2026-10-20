# UX 代理：核心任務卡死（blocking）可升高風險

**日期**：2026-10-20
**操作者**：Claude

## 變更內容
- `backend/apps/agent/tools.py`：`report_ux_issue` tool schema 新增 `blocking` 布林參數（定義：核心任務被完全卡死、根本無法完成，例如登入頁打不了字／按鈕點了沒反應、結帳送不出去），描述寫明「只有真的完全無法完成時才設 true」；`_report_ux_issue` 把 `blocking` 放進 issue payload，並以 `cap_ux_severity(severity, blocking=blocking)` 定嚴重度。
- `backend/apps/agent/findings.py`：`cap_ux_severity(severity, blocking=False)`——`blocking=True` 且嚴重度為 medium／high／critical 時升到 **high**（仍封頂 high、不給 critical）；其餘維持原本「high／critical 降 medium」。`persist_agent_issues` 傳 `blocking=bool(issue.get("blocking"))`。
- `loop.py`／`runner.py`：UX 測試提示補一句「核心任務完全無法完成時設 blocking=true」。
- 測試：`apps/agent/tests.py` `CapUxSeverityTests`（無 blocking 封頂 medium、blocking 升 high 但不給 critical、blocking+low 尊重 agent、落地後 severity=high）。

## 原因
1D47 報告審查:「/management/login 登入頁完全無作用——輸入框無法輸入、登入按鈕點了沒反應」只被列中風險,偏輕。原因是 agent UX 觀察一律封頂 medium(防 AI 灌高風險),且 `report_ux_issue` 的 severity enum 本來就只到 medium。但「登入功能整個失效」是功能性災難,比一般卡住嚴重。開一個定義明確的窄例外,只對「核心任務完全無法完成」升到 high,仍封頂 high 不讓 AI 自評到最高級。

## 影響範圍
- 只影響 agent UX 回報的嚴重度;一般 UX 問題仍封頂 medium,防 AI 灌分的原意不變。
- blocking 升級上限是 high,不會到 critical/嚴重(UX 觀察不應到最高級)。
- blocking 由 AI 判斷,但定義嚴格(完全無法完成,非繞得過去),且只升一級。
- 新 UX finding 仍 category=ux、rule_id `AGENT_UX_*`,不影響既有歸類與去重。

## 驗證方式
- `uv run ruff check`(findings、tools、loop、runner、tests):All checks passed。
- `manage.py test apps.agent.tests.CapUxSeverityTests apps.agent.tests.ToolSchemaTests`:9 pass。
- `manage.py test apps.agent`:101 pass(無回歸)。
- 未自動驗證:實機掃描時 AI 是否正確對登入頁壞掉設 blocking——需部署後重掃確認;提示詞與工具定義已明確引導。
