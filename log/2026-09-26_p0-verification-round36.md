# #36 驗證輪——XSS 首件命中＋injection 提示詞補家族探測

**日期**：2026-09-26（#36 於 09-27 清晨完成）
**操作者**：ZCode（GLM-5.3）

## #36 結果（25 findings、5 sessions、22 分鐘）
- **`Reflected XSS in /#/search?q= fragment — DOM execution confirmed`**——
  35+ 輪首件 XSS 命中，且正是 hash 路由形式＋DOM 執行確認：#35 補的 SPA
  hash 路由常識＋navigate_and_observe 執行閉環鏈路驗證成功
- injection 角色歸位：SQLi login bypass＋search full DB read＋auth bypass
  with valid JWT；orchestrator dispatch brief 帶證據（「單引號→SQLITE_ERROR」）
- 新表述：CAPTCHA continue-code static reusable（bypasses email-verification gate）
- 單輪 findings 25（#35=20、#34=40、#33=51）——M3 波動仍在，質變在 XSS

## 變更內容
- `backend/apps/agent/runner.py` INJECT_AGENT_PROMPT：
  - 第 2 點 XSS 改「瀏覽器執行驗證優先」（原「API 優先」與 XSS_HUNTER 舊版
    同病灶；#36 模型自行越過壞指引才命中——現指引與行為一致化）
  - 新增第 3 點：非 SQL 家族（NoSQL/SSTi/XXE/指令/LFI）用 probe_payload_injection
    （GET 給 query_param／POST 給 body+inject_field；markers_hit 非空即附證 report）
  - SPECIALIST_ROLES.desc 同步
- worker rebuild（injection prompt 入 image）

## 原因
#36 實測 probe_payload_injection 仍 0 呼叫——injection 角色被派工（dispatch 1）
但提示詞沒有引導使用新工具；工具在 schema 裡≠角色知道何時用。

## 影響範圍
- injection specialist 行為面：XSS 驗證路徑與家族探測雙補
- #37 驗證輪驗證 prober 首次上場

## 驗證方式
- apps.agent 56 tests OK＋ruff 通過
- #36 證據：Finding「Reflected XSS in /#/search?q=」＋sess96 navigate_and_observe
  2 次（recon 後 injection specialist 深挖 search 端點時執行）
