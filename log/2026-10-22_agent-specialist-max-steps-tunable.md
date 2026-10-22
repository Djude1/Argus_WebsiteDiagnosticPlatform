# 2026-10-22 專家步數上限改為可調、預設 60→30（縮短 AI Agent 階段時間）

## 背景（使用者）

勾了 AI Agent 的深度資安掃描，進度分母是 460 步、花很久。拆解後：

`max_total_steps_estimate = ARGUS_AGENT_MAX_STEPS×2 + ARGUS_AGENT_MAX_SPECIALIST_DISPATCH × 每位專家步數`
＝ `20×2 + 6×60 = 400`（深度資安），加上 UX 的 60 ＝ 460。

真正的時間大頭是「6 位專家 × 每位 60 步」（360，佔 90%）。「一步」＝ agent 的一個
observe→think→act 迴圈。`_SPECIALIST_MAX_STEPS` 原本寫死 60，不像派工上限（6）是環境變數。

使用者決定：把它改成可調，預設下修成 30。

## 修改

- `backend/config/settings.py`：新增 `ARGUS_AGENT_SPECIALIST_MAX_STEPS`
  （`int(os.getenv(..., "30"))`），附權衡說明。
- `backend/apps/agent/runner.py`：移除寫死的 `_SPECIALIST_MAX_STEPS = 60`，改成
  `_specialist_max_steps()` 讀 `settings.ARGUS_AGENT_SPECIALIST_MAX_STEPS`；
  `max_total_steps_estimate`、`ux_steps_estimate` 與 `_run_session` 的 recon／specialist
  `max_steps` 都改用它（runtime 讀取，支援 env 與 `override_settings`）。
- `.env.example`、`backend/apps/agent/CLAUDE.md`：補這顆旋鈕與權衡。

## 效果

預設 30 下：深度資安最壞分母 ＝ `20×2 + 6×30 = 220`，深度＋UX ＝ 250（原 460）；
實際 agent 階段時間約降到原本的一半上下（步數是主要成本）。orchestrator／recon 不變。

**權衡（已寫進註解與文件）**：步數調小更快，但一條「登入→枚舉→越權→驗證」的攻擊鏈常要
15–25 步，30 步夠跑一條淺鏈、深的鏈狀漏洞可能來不及做完就被砍；每位專家被要求「一確認
就立刻 report」，中途被砍仍保留已找到的。要更深可用 env 調回 40／60。

## 驗證

- `uv run ruff check backend/apps/agent backend/config/settings.py` → All checks passed
- `uv run python backend/manage.py test apps.agent` → 110 項全綠（新增 2 項：
  `MaxTotalStepsEstimateTests` 以 `override_settings` 驗證 30→220／ux 30、60→400）。

## 備註

派工上限（`ARGUS_AGENT_MAX_SPECIALIST_DISPATCH`，預設 6）本來就是環境變數，無需改；要再
壓時間也可一併調小。純行為旋鈕，無 migration。程式預設仍受 `ARGUS_AGENT_ENABLED` 總開關。
