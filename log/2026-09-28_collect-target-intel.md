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

## 首測（reset 定向輪，sess235）
- 工具**未被呼叫**（16 步 session：navigate 探端點×10→註冊登入→reset 500→
  淺嘗即 finish）——與 send_message 首輪同型（M3 指令遵循弱，新工具採用
  需 1-3 輪醞釀，歷史規律：prober 三輪、forge_jwt 兩輪）
- reset API 參數（securityContext 格式）agent 未摸對＝500 早退

## reverse-skill 查證（使用者指示補查）
- **repo 實質性**：181 commits、15 contributors、v1.0.1+ releases（8/8）、
  CI/tests 結構、field-journal 帶真實案例細節、昨仍活躍——非殼專案
- **star 高速**（4.5 月 38k）＝資安 skill 熱潮＋推廣成分無法排除；第三方
  評價待 WebSearch 限額重置（09-28 10:22）後補查
- **我方風險**：零（僅取方法論文字自寫蒸餾，無代碼/供應鏈依賴）
- **效用實證現況**：檢索品質已驗（6 查詢全中）；實戰直接貢獻（新種）
  未證——graphql/ws 本站無對應面、llm-chatbot 鏈未穿。誠實標定：
  參考價值中性偏正，非決定性
