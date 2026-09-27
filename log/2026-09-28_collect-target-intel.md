# B 選項落地：collect_target_intel（第 26 工具）——答案來源推理檢索化

**日期**：2026-09-28
**操作者**：ZCode（GLM-5.3）

## 變更內容
- `backend/apps/agent/tools.py`：`collect_target_intel(target, urls)`（第 26 工具，
  deep_only 三層閘）——對 ≤8 個同源端點帶憑證 GET，全文搜目標（email＋
  前綴雙鍵），命中抽前後 250 字上下文（≤15 片段）彙整單一視圖；
  GET only、單 URL 容錯、urls redact
- `backend/apps/agent/runner.py` auth prompt 5b 改引導用工具（移除人肉
  逐檔讀引導——#48 實證線索在 context 裡被淹沒）
- 文件同步：架構文件/CLAUDE.md 工具數 26

## 原因
使用者裁定動 B（A 換模型不做——專題策略＝便宜模型最低成本做最多事）。
#48 實證：agent 已讀備份檔但未連到答案——「找線索」是 M3 推理負擔，
工具化降為檢索（WSTG-ATHN-09 答案來源推理的機械前置）。

## 影響範圍
- deep_mode 掃描 auth_idor 角色新增檢索路徑；泛化（任何站帳號接管適用）

## 驗證方式
- apps.agent 70 tests OK（新 3：跨源拒/上下文抽取/redact）；ruff 通過
- 定向驗證輪（reset Bender/Bjoern）執行中，結果另 log
