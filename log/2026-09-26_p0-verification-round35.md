# P0 三項實測驗證（#35 輪）＋XSS hash 路由提示修正

**日期**：2026-09-26
**操作者**：ZCode（GLM-5.3）

## 變更內容
- `backend/apps/agent/runner.py` XSS_HUNTER_AGENT_PROMPT 補 SPA hash 路由常識：
  「輸入多由前端路由頁渲染（/#/…）；API 端點回 JSON 不渲染——導航必須打前端
  頁面 URL（hash 路由）；不確定形式先操作一次該功能觀察 page.url」
- demo 環境：worker rebuild、demo DB 補跑積壓 migration（admin_api.0005/0006＋
  scans.0017 categories）、Juice Shop 重啟（黑箱乾淨起點）

## 原因
#35 實測（20 findings、10 sessions、34 分鐘）驗證 P0 三項：
1. **navigate_and_observe 採用成功**：7 sessions 共 27 次（XSS specialist 從
   #33/#34 的 replay 54/27 次轉向瀏覽器路徑）✓
2. **orchestrator 二次派工**（xss×2、jwt×2 極簡任務重試）＝假設紀律影子 ✓
3. **XSS 仍 0 report**：agent 導航到 API URL（/rest/products/search?q= 回 JSON
   不渲染）而非前端 hash 路由頁——差最後一步 SPA 常識 → 本 log 修正
4. **probe_payload_injection 0 呼叫**：orchestrator 本輪未派 injection 角色
   （recon 已 2 次 probe_sql 後判斷覆蓋——M3 非決定性波動，靠多輪聯集）
5. 新發現：admin123 弱密碼（35 輪首見）＋customer 讀 admin 端點

記分板量測路徑棄用：v20 挑戰解鎖與攻擊特徵偵測綁定機制不明（SQLi 特徵登入
成功 200 仍 solved=0），非 agent 能力訊號——評估回歸 findings 聯集方法論。

## 影響範圍
- XSS specialist 導航目標預期從 API URL 轉向前端路由 URL
- probe_payload_injection 首輪未上場屬派工波動，待 #36 觀察

## 驗證方式
- apps.agent 56 tests OK＋ruff 通過（修正後）
- #36 驗證輪（hash 路由提示後）執行中，結果另 log
