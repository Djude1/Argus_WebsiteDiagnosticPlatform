# P0-3：probe_payload_injection 家族化注入探測工具

**日期**：2026-09-26
**操作者**：ZCode（GLM-5.3）

## 變更內容
- `backend/apps/agent/tools.py`：
  - 新增 `probe_payload_injection`（第 22 個工具）——family∈nosql/ssti/xxe/command/lfi，
    一次跑整組無害 payload（3-4 個/家族）：nosql（$gt/$ne/$where 操作子）、ssti（{{7*7}}
    四型模板語法）、xxe（ENTITY 讀 file://）、command（;echo ARGUSCMDPROBE 四型）、
    lfi（dotdot/絕對路徑 passwd＋php filter）
  - **baseline 比對消誤報**：先打原值請求，marker 需「payload 回應出現且 baseline
    不出現」才算命中（回應本含 49/root: 不誤報）
  - GET 換 query_param 值、POST 塞 body[inject_field]；帶登入態（token+cookies）
  - 憑證抽取 refactor 成 `_session_credentials()`＋`_http_headers_for()`，
    replay_request 改共用（行為不變）
  - 三層閘：deep_only schema＋runtime deep_mode 再驗＋runtime 同源再驗；
    `redact_tool_arguments` url 遮罩＋`redact_tool_result` 白名單（不含 payload 原文）
- `backend/apps/agent/tests.py`：`ProbePayloadInjectionTests`（8 測試：passive 擋/
  跨源擋/未知 family/缺 query_param/缺 inject_field/baseline 命中/baseline 已含不命中/
  redact 白名單）；ToolSchemaTests expected 21→22
- 文件同步：架構文件（21→22＋工具說明）、agent CLAUDE.md（工具數＋主動工具列舉）

## 原因
缺口分析 P0-3：#33/#34 實證 ssti/xxe 0 次觸碰、nosql 1-2 次——SQL 以外的注入面
完全沒有探測原語；Juice Shop 未解鎖挑戰中 NoSQL×3/SSTi/XXE×2 直接受此工具覆蓋。
payload 屬工具配備（使用者裁定：給工具不等於給答案）。

## 影響範圍
- 僅 deep_mode 掃描可用；injection specialist 與其他角色行為面新增探測路徑
- replay_request 憑證邏輯抽共用（無行為變化，測試 56 全過覆蓋）

## 驗證方式
- `uv run python backend/manage.py test apps.agent`：56 tests OK（新 8）
- `uv run ruff check backend/apps/agent`：All checks passed
- 實機 Juice Shop 輪測與 P0-1/P0-2 統一驗證（後續 log）
