# 後台 UI 重構 S4：掃描處置（終止／重排）

**日期**：2026-09-25  
**操作者**：Claude

## 變更內容

### 後端
- `AdminAuditLog.Action` 新增 `SCAN_CONTROL`，並一併產生 migration `0006_alter_adminauditlog_action.py`（`sqlmigrate` 確認為 `(no-op)`）。
- 新增 `POST /api/admin/scans/<id>/cancel/`：合作式終止（只設 `status=CANCELLED`），退款交由 `billing.services.refund_full_for_scan`。
- 新增 `POST /api/admin/scans/<id>/requeue/`：從 `failed`／`cancelled` 重排，**不重複扣點**；派工失敗時還原原狀態。
- `AdminScanJobSerializer` 新增 `user_id`。
- 新增 `ScanControlTests` 8 項。

### 前端
- `AdminScanDetailPage` 頁首新增處置按鈕組（依狀態顯示「終止掃描」或「重新排入佇列」），破壞性操作走既有 `useConfirmDialogs` 二次確認並說明後果。
- 錯誤改為區塊級 `AdminErrorState`（含重試），載入改為骨架。
- 頁尾新增「查看使用者 / 調整點數 →」連結。

## 原因
規劃 §1-1：掃描詳情原本**整頁只有兩個互動元素**（返回鍵與「以使用者視角查看」），不能取消、不能重排。使用者端反而有取消功能。這是「後台只能看、不能做」最明顯的一處。

## 關於「重排不重複扣點」（使用者 2026-09-25 決策，Q6）

實作前查證了一個會改變語意的前提：**`tasks.py` 在失敗、取消、超時、回收與排程失敗五處都會呼叫 `refund_full_for_scan`**，所以進入 `failed`／`cancelled` 的掃描，預扣早已全額退回。

因此「重排不重複扣點」在實際行為上等同**免費重跑一次**。這是刻意接受的：使用者不該為我們這邊失敗的同一次掃描付兩次錢。也正因為是免費，每次重排都會寫入 `AdminAuditLog`（`operation: requeue`、`charged: 0`）留下可稽核軌跡。

`completed` 狀態**不得重排**——那等於提供免費的重新掃描，已在後端擋下並有測試涵蓋。

## 關於「退點」的設計調整（與原規劃不同）
原規劃 §4-3 列了「退還點數（帶入建議金額）」作為掃描詳情的動作之一。實作時發現：
- 失敗／取消的掃描已自動退款，`refund_full_for_scan` 對它們是冪等的 no-op；
- 已完成的掃描其預扣已由 `settle_scan_actual` 結算，不適用該函式。

所以掃描層級不需要、也不應該有第二套退款路徑。已完成掃描的補償走使用者頁既有的「調整點數」（`admin_adjust`，本來就會寫稽核紀錄），掃描詳情只提供跳轉連結。**這比原規劃更正確，避免了兩條會產生不一致交易紀錄的退款路徑。**

## 影響範圍
- 遵守專案禁令：未直接操作 `CoinWallet`／`CoinTransaction`，一律走 `billing/services.py`；狀態變更沿用使用者端 `cancel` 的既有模式（`views.py` 設狀態，worker 合作式停下）。
- 重排會實際派工到 Celery；派工失敗回 503 並還原狀態，不會把掃描留在假的 `queued`。

## 驗證方式
- `apps.admin_api` 共 71 項測試全過（新增 8 項），涵蓋：終止進行中、不可終止已完成、終止寫稽核、重排不扣款且確實派工、不可重排已完成、派工失敗還原狀態、重排寫稽核、serializer 含 `user_id`。
- `uv run ruff check backend` 全過；`manage.py check` 0 issues。
- `npx vite build` 通過。
- **實作中發現並修掉的第二個靜默失效**：前端用了 `s.user_id`，但 `AdminScanJobSerializer` 原本沒有這個欄位，連結會永遠不顯示且不報錯。已補入 serializer 並加測試鎖住。
- **待人工確認**：實際終止一個進行中的掃描、重排一個失敗的掃描，確認狀態轉換與稽核紀錄。
