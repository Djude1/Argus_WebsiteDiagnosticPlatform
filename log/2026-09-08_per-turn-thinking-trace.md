# 思考過程改為每輪獨立，附在該輪答案上方

**日期**：2026-09-08
**操作者**：Claude

## 變更內容

### 前端 `RebuildWorkspace.jsx`
- 移除釘在最上方的全域 `思考過程與工具呼叫` 面板。
- 新增 `TraceEntries`（live 與歸檔共用的渲染）與 `TurnTrace`（展開才抓、只抓一次）。
- 每一輪 agent 回覆改為 `.rebuild-ws-turn-block`：思考過程收合在答案正上方。
- 進行中那一輪用 `liveTrace`，**預設展開**並保留原本的自動跟隨捲動
  （`traceBodyRef` / `handleTraceScroll` 原樣沿用，未動 `fc13fe5` 的修復）。

### 後端
- `services._archive_turn()`：每輪結束把該輪 `trace` 歸檔進 `conversation` 那一則。
  上限 `_ARCHIVED_TRACE_MAX_ENTRIES = 60`，裁切時**優先保留工具呼叫**。
- `serializers`：detail 的 `conversation` 改為 SerializerMethodField，只送
  `has_trace` 旗標，不送歸檔內容。
- `views.turn_trace`：`GET /api/rebuilds/{id}/turn-trace/?index=N`，按需取單輪思考流。

### 樣式
- 新增 `.rebuild-ws-turn-block`、`.rebuild-ws-turn-trace`（含 `.is-live`）。
- 移除孤兒 `.rebuild-ws-trace-wrap`（本次改動造成的）。

## 原因

使用者回報：「隨著我的追問，思考過程和工具呼叫就會在最上面」。

查證後發現不只是版面問題——`SiteRebuild` 只有一個全域 `trace` 欄位，`ask_followup`
每次都 `trace=[]`，**過去每一輪的思考是真的被丟掉了**。所以單純搬動 UI 位置無法
做到「每次追問都有獨立思考過程」，資料層根本沒有那些資料。

採 DeepSeek 做法（思考收合在該輪答案上方）而非「固定在輸入框附近」：後者只解決
「離得遠」，沒解決「這段思考是哪一輪產生的」；且版面是左右兩欄、右欄還有產出
預覽，再釘一塊常駐面板會持續吃掉垂直空間。

## 影響範圍

- **`turn-trace` 是新端點**，前端舊版不會呼叫，可安全先後部署。
- detail 端點 payload **與改動前一樣大**：歸檔的思考流不隨它送出。這是刻意的——
  單輪 trace 上限 180KB（120 則 × 1500 字）× 20 輪，而 workspace **每秒** polling
  detail，直接塞進去等於每秒 3.6MB。
- 既有資料相容：舊的 `conversation` 沒有 `trace` 鍵，`has_trace` 一律 False，
  該輪就不顯示思考過程（那些資料本來就已經遺失，不是這次弄丟的）。
- 未動 migration：`conversation` 是 JSONField，新增鍵不需要 schema 變更。

## 驗證方式

- `manage.py test apps` → **897 tests OK (skipped=1)**
- `apps.rebuild` → **77 tests OK**（改動前 69，+8）
- 新測試確實抓得到迴歸：拿掉 `_archive_turn` 的歸檔後 3 個測試失敗
- `ruff check backend`、`manage.py check`、`makemigrations --check` 皆通過
- 前端 `vite build` 通過
- 新增的 5 個 API 測試含權限：`turn-trace` 對別人的 rebuild 回 404
  （思考流含被掃描站的內容，不能靠猜 id 取得）

### 測試數字的說明
9/5 的紀錄是 813，本次是 897，差額**不是**本次造成的：期間有三個 rebuild 修復
commit（`460ece6`、`fc13fe5`、`a5e3a17`）各自加了測試，`apps.scans` 也從 617
變成 632。靜態計數佐證：改動前 883、改動後 891，差 8 正好等於本次新增數。

## 尚未處理

- **視覺觀感未經人工確認**：本機無瀏覽器，間距、收合樣式、`.is-live` 藍色 accent
  的實際效果需要人工看過。build 通過只代表語法正確。
- `_run_streaming` 每 `_TRACE_FLUSH_EVERY`（8）個事件才把 trace 落地，因此
  「開跑不到 8 個事件就失敗」的那一輪，過程留不下來。已在測試 docstring 註明，
  未修（不在本次需求範圍）。
