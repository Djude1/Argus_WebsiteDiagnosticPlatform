# Agent 一律用繁體中文回報（#7）

**日期**：2026-10-18
**操作者**：Claude
**來源**：三站報告審查第 #7 項——目標網站是英文（OWASP Juice Shop）時，Hermes-Agent 整段用英文
回報（4.11／4.21/4.28/4.33），在全繁中報告裡夾大段英文標題與內文。使用者要求「一律讓 Agent 用繁中」。

## 修法
`runner.py` 新增 `_LANGUAGE_RULE`，由 `_run_session` 接在**每個 session** 的 task_prompt 尾端
（recon／orchestrator／8 專家／UX 都走 `_run_session`，一處接全部）：

- 不論目標網站是中文或英文，`report_security_issue`／`report_ux_issue` 的 title／description／
  remediation 等「給人看的」欄位一律**繁體中文**，不得整段英文。
- URL、HTTP 方法、標頭名、參數名、payload、程式碼、JSON 欄位名等**技術字串保留原文、不翻譯**
  （避免把端點路徑、payload 翻壞）。

角色 prompt 本來就是中文，但沒明確規定「輸出語言」；模型遇到英文站就跟著英文。這條鐵律補上該規則。

## 驗證
- `tests_progress_callback.AgentLanguageRuleTests`（2）：`_LANGUAGE_RULE` 含「繁體中文」與
  report_security_issue 字樣；`HermesAgent.run` 把含該規則的 task_prompt 放進送模型的 messages
  （模型一定看得到）。`apps.agent` 全套 93 項通過；ruff 乾淨。
- 文件同步 `agent/CLAUDE.md` runner 行。

## 限制
- 這是 prompt 層的強制規則，實際輸出仍由模型遵循；絕大多數情況會照做，但不是 100% 保證。若日後
  仍偶有英文漏網，再考慮在 report 工具 schema 或落地時加後處理。本次先用最小、低風險的 prompt 規則。

## 備註
不影響掃描範圍、授權閘門或嚴重度判定；純輸出語言。待 rebuild backend image 後生效。
