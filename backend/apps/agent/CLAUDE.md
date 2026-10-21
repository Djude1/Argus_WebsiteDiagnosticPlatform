# agent 模組規則

Claude Code 進 `backend/apps/agent/` 工作時，本檔在專案層 `CLAUDE.md` 之後自動載入；**ZCode／Codex 不會自動載入本檔**，動手前必須先讀（見根 `AGENTS.md` 模組規則必讀閘門）。

**完整架構文件（角色目錄／工具清單／調校參數／迭代教訓）見
[`../../../docs/hermes-agent-architecture.md`](../../../docs/hermes-agent-architecture.md)
——改本模組前必讀。**

## 職責

掃描後的動態測試，兩種角色共用 `runner.run_agent_for_scan`（都受 `ARGUS_AGENT_ENABLED`
總開關控制，預設 `false` 時直接 `return None`）：

- **資安（deep_mode＝active＋authorized＋`deep_agent_requested` 才全開；2026-10-18 起加上 opt-in 閘）**：recon agent → orchestrator agent
  （subagent 派工）→ specialist subagent（8 角色：auth_idor/injection/logic_abuse/
  info_leak/xss_hunter/jwt_token_abuse/file_upload/crypto）。
- **資安與 UX 不互斥（2026-10-21）**：deep_mode 與 UX 由兩道獨立閘門控制，可同時成立。
  勾了深度 AI Agent 又勾了 `ux` 維度時，`run_agent_for_scan` 先跑完整條資安滲透鏈，
  再跑一個擬真使用者 UX session（`deep_tools=False` 掛 UX 工具集）併入結果——**兩者都要有**。
  由 `tasks.stage_agent` 以 `run_agent_for_scan(run_ux=plan.run_agent_ux)` 傳入；
  進度分母 `agent_total` 把兩種 session 的步數估計各自累加。先前 `elif deep_mode` 分支會略過 UX，
  造成「點了 AI Agent 反而沒有 UX 測試」。
- **擬真使用者 UX 測試（passive 也跑）**：全網站掃描且勾選 `ux` 維度時（`scan_plan.run_agent_ux`）
  走 `DEFAULT_TASK_PROMPT_TEMPLATE` 單 session，像真實使用者操作找可用性問題，產生
  `report_ux_issue`（UX 類 finding）。**不需要主動授權**，但 `may_submit_forms` 閘門決定能否
  送出表單：deep_mode 或掃描目標已通過 `user_owns_domain` 才可送出；否則 runner 隱藏
  `send_message` 工具、prompt 只填欄位不送出，避免在未驗證網域留下測試資料。
  計費見 billing 的 `agent_ux_fee`（固定附加點數）。`report_ux_issue` severity 封頂 **medium**
  （`findings.cap_ux_severity`，2026-10-10）；**例外 `blocking`（2026-10-20）**：工具多一個 `blocking`
  旗標＝核心任務被完全卡死、根本無法完成（登入頁打不了字／按鈕點了沒反應、結帳送不出去，不是繞得過去
  的困擾），設 true 時 `cap_ux_severity(severity, blocking=True)` 允許升到 **high**（仍封頂 high、不給
  critical）；一般卡住仍 medium 上限。1D47 報告「登入頁完全壞掉」只給中風險偏輕，故開此窄例外。**開新分頁不是死按鈕（2026-10-21）**：6821 報告把「加入我們」（`<button>` 用 `window.open` 開 Instagram）判成「點擊完全無反應」並以 blocking 回報高風險，UX 51→30。`_make_agent_context` 掛 init script 鉤住 `window.open` 記錄目標（`_WINDOW_OPEN_HOOK_JS`），`ToolExecutor` 另聽 context `page` 事件記下 popup 目標後關閉；`click` 結果多 `url_changed`、`opened_new_tab`（網址清單）與 note「這代表按鈕有效，不是死按鈕」；`report_ux_issue` 對點過會開新分頁的 selector 不採信 `blocking`（降回一般 UX 觀察、描述附系統核對註記、result 回 `blocking_rejected`）。提示詞同步寫明。
  token 上限另用 `ARGUS_AGENT_UX_MAX_TOKENS`（120000），
  用完時覆蓋紀錄標 partial。

## 關鍵檔案

| 檔案 | 職責 |
|---|---|
| `runner.py` | 流程編排：recon→orchestrator（首步 tool_choice 強制派工）→specialist；`SPECIALIST_ROLES` 角色目錄（desc＋when）；authenticated scan 帳密解密注入；`_merge` 結果合併。**吃確定性發現不重報**（ADR-0005 §5，2026-10-17）：`run_agent_for_scan(known_findings=...)` 由 `tasks.stage_agent` 傳入本次確定性工具已找到的資安發現；`_summarize_known_findings` 組成摘要（只給標題／端點／嚴重度，**不送 evidence**，去重上限 20）放進 `ORCHESTRATOR_PROMPT` 的「確定性工具已找到的問題——不要重報」段，叫 orchestrator 別派專家重複確認、把步數花在要推理才找得到的（差異式未授權、串接）與驗證升級既有發現。**即時進度回呼**（2026-10-18）：`run_agent_for_scan(progress_cb=...)` 由 `tasks.stage_agent` 傳入；`_run_session(role_label=...)` 把回呼包成 `HermesAgent(step_callback=...)`，`loop.HermesAgent.run` 每個 round 開始經 `sync_to_async` 呼叫一次（fail-safe，爆炸只吞掉），讓外層回寫累計步數——agent 跑十餘分鐘過去進度一路停在 0／20（那 20 還只是單一子代理上限）像卡住。分母用 `runner.max_total_steps_estimate()`（recon＋orchestrator 各 `ARGUS_AGENT_MAX_STEPS`＋最多 `ARGUS_AGENT_MAX_SPECIALIST_DISPATCH` 位專家 ×`_SPECIALIST_MAX_STEPS`=60）。**顯示「目前在跑哪個專家」**（2026-10-18）：回呼帶的 role_label（recon／orchestrator／ux／specialist／specialist:<role>）由 `tasks._agent_role_label` 轉中文寫進 `progress.step_detail`，前端 agent 階段顯示；8 種 specialist 代號須與 `SPECIALIST_ROLES` 同步。**一律繁中回報**（2026-10-18）：`_run_session` 在每個 session 的 task_prompt 尾端接上 `_LANGUAGE_RULE`——不論目標網站是中文或英文，report_security_issue／report_ux_issue 的 title／description／remediation 一律繁體中文，技術字串（URL／payload／標頭／JSON 欄位名）保留原文；英文站（如 Juice Shop）過去會讓 agent 整段英文回報、在全繁中報告裡很突兀|
| `providers.py` | `ChatProvider`／`ProviderChain`（**MiniMax-M3** 主力→GLM→Gemini 純文字 fallback）；`ProviderError` 只帶公開資訊 |
| `loop.py` | `HermesAgent` tool-calling 迴圈；`_compact_stale_tool_results`（bulky 觀察快照壓縮）；`_inject_stall_hint`（連續 click 空轉導正）；`_inject_endgame_hint`（剩 10 步強制 report）；`forced_first_tool`（orchestrator 首步鎖定） |
| `tools.py` | `ToolExecutor`：**25 個工具**（`TOOL_SCHEMAS`）＋離線知識庫 `knowledge/*.md`（search_knowledge 檢索；內容限通用方法論，禁目標特定）；`build_tool_schemas(..., allow_form_submit=True)`——deep_only 閘＋`allow_form_submit=False` 時另隱藏 `send_message`（未驗證網域 UX 測試不得送出表單）；`redact_tool_arguments/result` 持久化遮罩；JWT 於 snippet 壓縮 |
| `findings.py` | `persist_agent_issues`＋`persist_agent_security_findings`（owasp tag）；`consolidate_security_findings`：同一次掃描裡不同專家對同一個問題的回報（代號相同，或同類型且標題相似度 ≥ 0.6）合併成一筆，保留最嚴重、已驗證的，`evidence_json.merged_reports` 記次數；runner 合併後計分與落地共用同一份；sqlmap 結果仍依 description 去重 |

## 安全（硬規則）

- **嚴禁**在 log／exception／repr／AgentStep 印出 API key；authenticated scan 帳密只以 Signer 加密入 DB、只在 prompt 注入處解密，**不得**進 log/findings/報告。
- Playwright context 套 public target policy＋same-origin 主文件/WebSocket 攔截；`navigate_and_observe` 是唯一導覽工具，**runtime 同源再驗＋deep_mode 再驗**（不繞過 context route 邊界）；不得新增其他可跨源導覽的能力。
- 主動工具（`probe_sql_injection`／`probe_unauthorized_access`／`replay_request`／`run_nuclei`／`navigate_and_observe`／`probe_payload_injection`）＝deep_mode schema 隔離＋runtime 再驗＋同源閘三層；任何新主動工具必須接同邊界。
- `replay_request`：method 限 GET/POST/PUT/PATCH（禁 DELETE）；不跟隨 redirect；`store_token_key` 只寫 agent 自己的 browser context。
- `report_security_issue` severity 預設封頂 **medium**（2026-09-28 起；AI 觀察未經工具或人工驗證可被利用）。**2026-10-10 放寬**：agent 真的用自己的主動工具確認過（`ToolExecutor._active_confirmations` 非空：`replay_request`／`probe_payload_injection`／`probe_unauthorized_access`／`probe_sql_injection`／`run_nuclei` 任一成功）**且**本次回報帶 `verified=true` 時，才保留 high／critical（不需 Kali sqlmap）；缺任一條件一律降 medium——兩道關卡擋 AI 純臆測自評高風險，`evidence_json.tool_verified` 記錄是否通過。**2026-10-16 收緊**：主動工具成功打過的端點路徑記在 `_confirmed_paths`，回報的 `url` 路徑必須在裡面才算已驗證（原本任一工具成功過，之後每筆回報都算已驗證——讀取公開 sitemap 也被寫成「以主動工具重現並確認可被利用」）；`url` 是 robots.txt 或 sitemap 時拒收（`not_a_security_issue`：公開索引列出登入頁不是弱點）。**規則代號每個問題各自不同**：`agent-observed-security-<雜湊>`（`findings.agent_security_rule_id`：弱點類型＋端點路徑，沒有端點時用標題；不把標題放進有端點的雜湊，措辭每次不同會讓歷史比較失效）。2026-10-16 前全部共用 `agent-observed-security`，計分與優先處理只留第一筆、報告併成一張卡；判斷 Agent 觀察一律用前綴。evidence 必填、經遮罩。description 開頭固定「AI Agent 在實際操作網站時觀察到：」、附證據中 IP 的自動核對（`security/ip_context.describe_ips`：私有 IP／本站公開 IP／**掃描器自己的出口 IP**（`ARGUS_SCANNER_EGRESS_IPS`，2026-10-20）／不明，WAF 攔截頁常回顯的是掃描器自己的 IP）。**觀察在講 IP 外洩、證據中的 IP 卻全是掃描器出口時降為 info 並附 `tools.SCANNER_IP_NOTE`**（`tools.scanner_ip_disclosure`；`finding_normalization._renormalize_agent` 對既有掃描做同一件事，部署後設定出口 IP 再跑 `renormalize_findings` 即可修正舊誤報）。**同類型、不同端點但擷取回應幾乎相同（去數字後相似度 ≥ 0.9）也算同一問題**（`findings.same_issue`，同一個 WAF 攔截頁從 `.git/HEAD` 與 `.env` 各報一次只差時間戳，2026-10-19 實掃），`evidence_json.assessment` 寫成立條件／實際觀察／尚缺證據／驗證方法。
- specialist 不掛 `dispatch_specialist`（防遞迴）；orchestrator 只掛 dispatch/finish/report。
- Kali 攻擊鏈正式環境 disabled；啟用 runbook 見 `docs/runbooks/kali-sqlmap-rollout.md`。

## 已知限制（2026-09-28 定案，詳見架構文件第 9 節）

- **M3 工具採用極限**：`collect_target_intel` 三路引導×三輪 0 呼叫（auth 角色注意力在本業，條件子項被跳過）——工具正確但模型不叫；換更強模型時採用率＝第一測點
- **Chatbot 挑戰判定**：超出 OWASP LLM 通用方法論＝黑箱禁區（chat 鏈本身已通：/rest/chat 全鏈＋900k 盒下首件 report）
- **chat 場景 token**：500k 不足（回應全文進 context）——定向輪用 exec 進程同步 apply 覆寫（Celery 常駐進程不吃 exec env）
- 26/112 為 M3 架構高原（22 全掃＋8 定向窮盡）；四類別首穿（帳號接管/DOM XSS/商業邏輯/上傳）

## 禁止事項

| 禁止 | 原因 | 正確做法 |
|---|---|---|
| 印出／持久化 API key、測試帳密明文 | 機密外洩 | 只記 provider／HTTP 狀態／model ID |
| 給 agent 任意 `navigate(url)`／跨源導覽 tool | 繞過 same-origin | 導覽僅限 `navigate_and_observe`（同源＋deep_mode 三層閘） |
| `ARGUS_AGENT_ENABLED` 預設改 True | 成本與風險不可控 | 預設 False，明確授權才開 |
| prompt 寫入任何目標特定路徑／答案 | 破壞黑箱泛化（#22 稽核先例：通用路徑例子 `/rest/`、`/api/` 也移除） | 只寫方法論與工具描述；payload／字典屬工具配備（使用者裁定） |
| 硬編碼 provider key／endpoint | 機密外洩 | 放 `.env` |
