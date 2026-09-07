# Agent 呈現重做：回覆與思考流分離、加入追問

**日期**：2026-09-07
**操作者**：Claude

## 變更內容

### 後端
- `models.py`：新增 `reply`（agent 的回答）、`conversation`（追問往返）、
  `Status.ASKING`（migration `rebuild/0005`）
- `services.py`：串流的 `text` 事件改導向 `reply` 而非 `trace`；
  新增 `ask_followup()` 在**同一個 opencode session** 裡追問
- `billing/services.py`：新增 `charge_rebuild_usage()`——追問的事後按量扣款
- `views.py`：`POST /api/rebuilds/<id>/ask/`，含餘額前置檢查與進行中衝突擋阻
- `tasks.py`：`ask_rebuild_agent`（同樣不重試）
- `_extract_edits` 容忍 `old`/`new` 等欄位別名

### 前端（`RebuildWorkspace.jsx`）
照 AI-Wealth-Manager 的資訊層級重做：

| | 之前 | 現在 |
|---|---|---|
| 狀態 | 無 | 脈動點＋當前動作＋經過秒數＋工具呼叫次數 |
| 思考 | 一則一則的方框、每則有標籤 | 等寬淡色、**連續流動**；工具呼叫獨立成強調色單行 |
| 回覆 | 混在思考流裡當一種標籤 | **獨立卡片**、正常字級 |
| 互動 | 無 | 追問輸入框＋往返紀錄 |

自動捲動改成**只在使用者沒往上捲時**才捲（沿用 AIWM 的 pinned 判斷），
否則正在讀舊內容的人會一直被拉回底部。

## 原因

使用者回報「Agent 回覆和思考流都感覺怪怪的」，並要求參考 AI-Wealth-Manager
的做法、加上可以提問的輸入。

實際讀了 AIWM 的 `web/app.js` 與 `styles.css` 後，差異最大的一點是：
**他們把「過程」和「結論」分成兩個視覺層級**，而我把 agent 的回覆當成 trace
的一種 kind，跟推理片段混在一起——結論因此被埋掉了。

## 影響範圍

- 新增 migration `rebuild/0005`
- `trace` 不再含 `text` 類型；任何依賴它的程式要改讀 `reply`（已一併調整）
- 追問**會計費**（事後按用量），並在送出前檢查餘額 ≥ `ARGUS_COIN_REBUILD_MIN`
- 追問失敗不會把 `status` 改成 `failed`——優化版已經產出了，那樣會讓它看起來
  像整個沒做成；錯誤只寫進對話

## 驗證方式

- `apps.rebuild` + `apps.billing` **103 tests OK**（新增 `FollowupTests` 8 項、
  `EditSchemaToleranceTests` 4 項）
- ruff / check / makemigrations 通過；前端 `vite build` 通過
- **對真實 agent 實測追問**：同一 session 第二輪回覆
  「根據頁面標題「咖啡」與 h1「本店」的語境，採用與內容主題一致的中性描述，
  未杜撰圖片實際內容」——確認 agent 記得上下文；
  累計成本 0.004866 → 0.005983，本輪增量 0.001117 正確隔離

## 未驗證（需使用者）

- **畫面外觀沒有親眼看過**：這台沒有瀏覽器工具，只驗到進 bundle
- 追問的端到端（含 Celery）在正式站尚未跑過
