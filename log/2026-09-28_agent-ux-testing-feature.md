# 新增 AI Agent 擬真使用者 UX 測試功能（含規則式 UX 檢查與固定附加計費）

**日期**：2026-09-28
**操作者**：Claude

## 變更內容

### 1. 規則式 UX 檢查（每頁都跑、不需 LLM）
- `apps/scans/crawler.py`
  - 新增 `collect_ux_signals(page)`：以 `page.evaluate` 偵測手機上過小的觸控目標
    （寬或高 < `_MIN_TAP_TARGET_PX`＝40）與缺少可及名稱（label／aria／title／
    placeholder）的表單欄位，各類上限 `_MAX_UX_OFFENDERS`＝8。
  - 新增 `pageerror` 監聽，收集頁面未攔截的 JavaScript 例外（去重、設上限）。
  - 於 `collect_mobile_layout` 之後、其他擷取之後呼叫 `collect_ux_signals`；
    page dict 新增 `ux_signals` 與 `js_errors`；跨源／過大／離站三個重置分支
    同步清空 `ux_signals`／`js_errors`。
- `apps/scans/scanners.py`
  - `PageAnalysisInput` 新增 `ux_signals` / `js_errors` 欄位。
  - `analyze_ux` 拆為 `_ux_mobile_overflow` ＋ `_ux_tap_targets`（LOW，≥5 升
    MEDIUM）＋ `_ux_unlabeled_fields`（MEDIUM，accessibility）＋ `_ux_js_errors`
    （MEDIUM，證據上限 `_MAX_JS_ERROR_EVIDENCE_CHARS`＝800），全部產出
    `category=UX` finding。
- `apps/scans/tasks.py`：`PageAnalysisInput` 呼叫傳入 `ux_signals` / `js_errors`。

### 2. Agent 擬真使用者 UX 測試（passive 也跑）
- `apps/scans/scan_plan.py`：`ScanExecutionPlan` 新增 `run_agent_ux`
  ＝`scope=="site" and "ux" in effective_categories`（不需主動授權）。
- `apps/scans/tasks.py`：agent 觸發條件改為 `run_agent or run_agent_ux`；
  新增 `may_submit_forms = run_agent(deep_mode) or user_owns_domain(user, hostname)`
  並傳入 `run_agent_for_scan`。
- `apps/agent/runner.py`：`run_agent_for_scan(..., may_submit_forms=False)`；
  `DEFAULT_TASK_PROMPT_TEMPLATE` 改寫為純 UX 測試並帶 `{submit_clause}`；passive
  分支依 `allow_form_submit` 組送出／只填不送的 clause，並傳
  `_run_session(..., allow_form_submit=...)`。
- `apps/agent/tools.py`：`build_tool_schemas(..., allow_form_submit=True)`，不允許
  送出時另隱藏 `send_message`。

### 3. 固定附加計費
- `config/settings.py`：新增 `ARGUS_COIN_AGENT_UX`（預設 20）。
- `apps/billing/services.py`：新增 `agent_ux_fee(max_pages, categories)`（agent 關、
  單頁或未勾 ux 回 0）；`estimate_scan_cost` 折入這筆費用（hold／settle／全退自動
  對稱一致，不新增交易類別、不需 migration）。
- `apps/billing/serializers.py`：`CoinWalletSerializer` 新增 `agent_ux_fee`。
- `apps/scans/views.py`：`estimate_scan` 回應新增 `agent_ux_fee`。
- `frontend/src/components/scans/ScanJobForm.jsx`：整站＋勾 UX 時估價加上
  `wallet.agent_ux_fee`，公式列顯示「＋ AI Agent UX 測試 N coin」。

### 4. 測試與文件
- 新增 `apps/scans/tests_ux_signals.py`（tap target／unlabeled field／js error／
  組合案例）。
- `apps/scans/tests_scan_plan.py`：`_job` fixture 加 `categories`／
  `effective_categories`；新增 3 個 `run_agent_ux` 純函式測試；整合測試
  `test_passive_site_does_not_call_active_tools` 更新為「主動資安工具不跑、但
  Agent UX 會以 `may_submit_forms=False` 執行」，並新增
  `test_passive_site_without_ux_category_skips_agent`。
- `apps/billing/tests.py`：新增 `agent_ux_fee` 三項測試。
- 同步文件：`backend/apps/scans/CLAUDE.md`、`backend/apps/billing/CLAUDE.md`、
  `backend/apps/agent/CLAUDE.md`、`docs/hermes-agent-architecture.md`、
  `frontend/CLAUDE.md`、`專題文件/本機資料/歷史需求書/需求書_複賽版完整內容.md`（ARGUS-F-015、
  成本估算、工具啟用條件）。

## 原因
購點比較表宣稱有「AI Agent 擬真使用者 UX 測試」，但先前只有 UX 版面量測、
並無擬真操作實作。使用者要求補上此功能。經確認：勾 UX 就在整站掃描執行、
未驗證網域只填欄位不送出；以固定附加點數計費；同時補上不需 LLM 的規則式
UX 檢查作為地板。

## 影響範圍
- 掃描費用：整站＋勾 UX 時每次多收 `ARGUS_COIN_AGENT_UX`（預設 20）；agent 總開關
  關閉時（正式預設）不收、不執行 agent，行為與先前一致。
- 被動整站掃描在勾 UX 時會呼叫 agent（先前完全不呼叫）——僅 UX 角色、非主動資安。
- 未通過網域所有權驗證的目標，UX 代理不會送出任何表單。

## 驗證方式
- `apps.scans.tests_ux_signals` + `apps.scans.tests_scan_plan`：23 passed。
- `apps.billing.tests` + 上述兩檔合跑：73 passed。
- `apps.agent`：70 passed。
- `ruff check` 變更檔全綠；`collect_ux_signals` 內嵌 JS 以 `node --check` 驗證可解析。
- 前端 lint／build 尚未於本機重跑（本環境無 portable Node 22）——列入待人工確認。
