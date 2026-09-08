# 中斷的那一輪，思考過程不再消失

**日期**：2026-09-08
**操作者**：Claude

接續 `8b27bf7`（思考過程改為每輪獨立）。那次把思考流改成每輪歸檔，但漏了一個會
讓歸檔變成空的路徑。

## 變更內容

- `services._run_streaming()`：串流迴圈包進 try/except，中斷時先把已收集的
  `entries` 落地再往上拋。落地邏輯抽成內部的 `flush()`，正常結束與中斷共用。
- 保存失敗只記 `logger.exception`，不改變往上拋的例外型別。
- 測試 +1（`apps.rebuild` 77 → 78）。
- `backend/apps/rebuild/CLAUDE.md` 補上這條契約。

## 原因

`_run_streaming` 每 `_TRACE_FLUSH_EVERY`（8）個事件才把 trace 寫進 DB，中間都只
存在區域變數。所以「開跑沒幾步就失敗」的那一輪，過程完全不會落地——而那正是
使用者最想看的情況：跑兩三步就卡住時，想問的就是「它到底想了什麼才卡住」。

保存失敗不可讓 `DatabaseError` 取代原始例外：`ask_followup` 與 `run_rebuild` 是依
`OpenCodeError` / `requests.RequestException` 決定要不要把整次複刻標成失敗的，
換成別的型別會走到完全不同的分支。

## 影響範圍

- 只影響失敗路徑；正常完成的行為完全不變（`flush()` 就是原本那三行）。
- 失敗那輪的 `reply` 會保留部分內容——與修復前跨過落地門檻時的行為一致，
  且前端有 conversation 時不讀 `reply`。

## 驗證方式

- `apps.rebuild` → **78 tests OK**（`8b27bf7` 是 77）
- **移掉中斷落地後確認會紅**，不是僥倖通過
- `ruff check backend`、`manage.py check`、`makemigrations --check` 皆通過
- `manage.py test apps` → **898 tests OK (skipped=1)**（`8b27bf7` 是 897）

## 過程中修正了自己一個測試的定位

`test_a_long_round_that_dies_persists_the_whole_trace` 原本被我當成「能證明中斷
落地」的測試，實際上**不能**：第一次落地之後 `rebuild.trace` 與 `_run_streaming`
內部的 `entries` 指向同一個 list，後續片段會直接出現在記憶體物件上，而
`ask_followup` 的歸檔正是從那個物件讀的。所以拿掉中斷落地它照樣過——連改成從 DB
重讀也一樣，因為歸檔那一步又把記憶體內容寫回去了。

真正證明修復的是只給兩個事件（遠不到落地門檻）的那一項。docstring 已改成誠實
說明這一項鎖的是端到端行為，並指明哪一項才是修復的證明。

教訓：「改壞了會紅嗎」必須實際驗，不能靠推理——我推理錯了兩次（先以為兩項都會
紅，再以為改成讀 DB 就會紅）。
