# P0-1：navigate_and_observe 執行層觀察工具＋XSS 提示詞改寫

**日期**：2026-09-26
**操作者**：ZCode（GLM-5.3）

## 變更內容
- `backend/apps/agent/tools.py`：新增 `navigate_and_observe(url)` 工具（第 21 個）——
  - 同源 goto→dialog 事件監聽（alert/confirm/prompt＝JS 已執行金證據，自動 dismiss）＋
    console 訊息（上限 20 條）＋渲染後 DOM HTML（4000 字元）＋可見文字（1500 字元）
  - 三層閘：deep_only schema 隔離＋runtime deep_mode 再驗＋runtime 同源再驗
    （context route 主文件同源攔截仍是第一層——不繞過既有邊界）
  - `redact_tool_arguments` url 遮罩＋`redact_tool_result` 白名單（url/rendered_html
    遮罩 query 值、html 截 2000）
- `backend/apps/agent/runner.py`：`XSS_HUNTER_AGENT_PROMPT` 全面改寫——
  - 移除「全程 API 優先、不操作 UI」（#33/#34 實證：63/62 步 replay_request、
    0 report——SPA 回應空殼，方法論根本失效）
  - 改為「瀏覽器執行驗證優先」：query 輸入點→navigate_and_observe 帶 payload URL→
    dialog/DOM 判定；純輸入框→type_text＋渲染檢查；儲存型→replay 注入＋navigate 檢查
- `backend/apps/agent/tests.py`：新增 `NavigateAndObserveTests`（4 測試：passive 擋、
  跨源擋、執行觀察回傳、redact 遮罩）；`ToolSchemaTests` expected 更新
- 文件同步：`docs/hermes-agent-architecture.md`（20→21＋工具說明）、
  `backend/apps/agent/CLAUDE.md`（工具數＋導覽邊界規則改述）

## 原因
缺口分析（log/2026-09-26_agent-gap-analysis.md）P0-1：Juice Shop XSS 家族 9 挑戰全滅，
根因＝XSS specialist 用 httpx 驗 client 端渲染漏洞＋工具集無導航能力。外部文獻
（CAI/XBOW）與本地 725 步行為數據同指向「執行閉環」缺失。

## 影響範圍
- 僅 deep_mode（active＋authorized）掃描可見此工具；passive 掃描 schema 不含
- XSS specialist 行為預期從 replay_request 轉向 navigate_and_observe/type_text
- 模組規則「不得新增可繞過 same-origin 的導覽」維持——本工具三層閘把關

## 驗證方式
- `uv run python backend/manage.py test apps.agent`：46 tests OK（原 42＋新 4）
- `uv run ruff check backend/apps/agent`：All checks passed
- 實機 Juice Shop 輪測待三項 P0 完成後統一執行（見後續 log）
