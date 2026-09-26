# P0-2：攻擊假設生成＋換道紀律（規劃層）

**日期**：2026-09-26
**操作者**：ZCode（GLM-5.3）

## 變更內容
- `backend/apps/agent/loop.py` `DEFAULT_SYSTEM_PROMPT`：新增「假設與換道紀律」條——
  行動前想清楚假設與推翻條件；同手法重試 >3 次無新資訊＝列未試假設換道；
  發新請求前先交叉比對既有觀察資料
- `backend/apps/agent/runner.py` `_dispatcher()`：specialist prompt 尾巴新增
  「攻擊假設紀律」——(1)假設 (2)驗證步驟 (3)放棄條件 三元模板＋換道規則＋
  「組合既有線索常比新探測快」引導
- `backend/apps/agent/tests.py`：`SystemPromptDisciplineTests`（2 測試：system prompt
  含紀律關鍵詞、runner source 含假設模板——防回歸鎖）
- `docs/hermes-agent-architecture.md`：迴圈治理表新增「假設與換道」列

## 原因
缺口分析 P0-2＋外部文獻雙重指向：
- Excalibur（arXiv:2602.17622）：瓶頸＝缺乏任務難度即時估算→過度投入低值分支
- arXiv:2609.10780：記憶假說被否定；失敗運行「手握前進證據卻未形成攻擊假設」
- 本地實證：#33/#34 SecurityQuestion 觸碰 77/43 次未組出「洩漏→推答案→重置」鏈

## 影響範圍
- 所有 agent session（system prompt 層）＋所有 specialist（dispatcher 層）；
  無程式介面變動，純提示詞治理
- 與既有「單一路徑優先」效率紀律互補：深挖→確認失敗→換假設

## 驗證方式
- `uv run python backend/manage.py test apps.agent`：48 tests OK（新 2）
- 行為面效果待 Juice Shop 實測輪（與 P0-1/P0-3 一起驗證）
