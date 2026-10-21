# UX 代理：點擊開新分頁不再誤判為死按鈕

**日期**：2026-10-21
**操作者**：Claude

## 變更內容
- `backend/apps/agent/runner.py`：`_make_agent_context` 掛 init script `_WINDOW_OPEN_HOOK_JS`，鉤住 `window.open` 把目標網址記進 `window.__argusOpened`（只記錄、不改行為）；UX 任務提示補一句「click 回傳 opened_new_tab 代表按鈕有效，不是死按鈕」。
- `backend/apps/agent/loop.py`：共用規則同樣補上這句。
- `backend/apps/agent/tools.py`：
  - `ToolExecutor` 新增 `_popups`／`_opened_by_selector`，並聽 browser context 的 `page` 事件（`_on_new_page`：取第一個導覽請求的網址，拿不到才用 `page.url`，記下後關閉新分頁，agent 留在原分頁）。
  - `_click`：點擊前後比對 `window.__argusOpened` 與 `_popups`，結果新增 `url_changed`、`opened_new_tab`（去重網址清單）與 note；同時記到 `_opened_by_selector`。
  - `_report_ux_issue`：`blocking=true` 但 selector 點過會開新分頁 → 不採信（`blocking=False`、嚴重度照一般 UX 封頂 medium、描述尾端附「系統核對：…blocking 不採信」、result 回 `blocking_rejected`）。
- `backend/apps/agent/tests.py`：新增 `ClickOpensNewTabTests`（window.open 目標回報、popup 事件回報、一般點擊無新欄位、對開新分頁元素的 blocking 被拒、其他元素的 blocking 仍升 high）。
- `backend/apps/agent/CLAUDE.md`：補「開新分頁不是死按鈕」規則。

## 原因
使用者比對 3FAC（含 AI Agent，67 分）與 6821（不含，62 分）：6821 的 UX 由 51 掉到 30，唯一差別是擬真使用者測試把導覽列「加入我們」判成「主要 CTA 點擊完全無反應（死按鈕）」並以 blocking 回報高風險（高風險扣 35 分）。實際上該按鈕是 `<button>` 用 JS 開新分頁到 https://www.instagram.com/ntub_imd_birc/ ——`click` 工具只回目前分頁的網址，新分頁又因跨源被 context route 擋下，agent 看到網址沒變、沒有 API 請求，就依提示詞的「按鈕點了沒反應＝blocking」回報。2026-10-20 才開的 blocking 升級通道被這個盲點放大成 −21 分。修法是把「開了新分頁、目標是哪裡」明確回給 agent，並在工具層對這類元素拒絕 blocking，不只靠提示詞。

## 影響範圍
- 只影響 agent 的 `click` 與 `report_ux_issue`；資安代理共用同一個 `click`，多出的欄位是加法，不影響既有流程。
- 跨源 popup 仍被 `_enforce_agent_request` 擋住（不跟過去、只回報目標網址），同源邊界不變。
- 6821 這筆既有的誤報需重掃才會消失（finding 已落地，無法回溯判定 agent 當時看到什麼）。

## 驗證方式
- `uv run ruff check backend/apps/agent`：All checks passed。
- `uv run python backend/manage.py test apps.agent.tests.ClickOpensNewTabTests apps.agent.tests.CapUxSeverityTests apps.agent.tests.ToolExecutorTests apps.agent.tests.ToolSchemaTests`：25 pass；`manage.py test apps.agent`：106 pass。
- 未自動驗證：需部署後對 ntubimdbirc.tw 重跑一次不含深度資安的全站掃描，確認「加入我們」不再被列為死按鈕、UX 分數回到 50 上下。
