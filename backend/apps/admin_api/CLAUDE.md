# admin_api 模組規則

Claude Code 進 `backend/apps/admin_api/` 工作時，本檔在專案層 `CLAUDE.md` 之後自動載入；**ZCode／Codex 不會自動載入本檔**，動手前必須先讀（見根 `AGENTS.md` 模組規則必讀閘門）。

## 職責
React `/admin/*` 後台用的 REST API + `AdminAuditLog` 稽核。端點**刻意扁平、隱藏內部 model**（AgentSession / Page / Finding 等不外露）。

## 權限（超管 / 一般管理員分權）
登入唯一入口為前台 email / Google（`accounts`）；`is_staff` 才能進 React `/admin`，`is_superuser` 為超級管理員。授予 staff / superuser 只能用 `manage.py seed_admin`（或 shell），**auth 端點一律不簽發**（防權限提升）。

| 層級 | 可用功能 | 權限類別 |
|---|---|---|
| 一般管理員（is_staff） | 總覽 / 儀表板 / 使用者（檢視＋調點＋掃描紀錄） / 交易 / 訂單 / 評論（回覆·審核） / 掃描（檢視＋終止＋重排） / 網域驗證 / **系統健康** / CMS（features·team·releases·plans） | `IsAdminUser` |
| 超級管理員（is_superuser） | 上述全部 ＋ 操作日誌（audit-log） ＋ 公告管理（announcements） | `IsSuperuser` |

前端 `AdminLayout` 依 `me.is_superuser` 顯示「操作日誌📜 / 公告管理📢」，與後端 `IsSuperuser` 一致。（django-admin 已移除，不再有第二後台。）

## 關鍵檔案 / 端點（`/api/admin/`）
- `views.py`：`overview`（含 `triage` 待辦統計）、`users`、`users/<id>`（含該使用者的 `recent_scans`）、`users/<id>/adjust-coin`、`users/<id>/login-events`（最近 50 筆登入事件）、`users/<id>/subscription`（grant/cancel 訂閱）、`subscriptions/plans`（訂閱方案唯讀）、`transactions`、`reviews`、`reviews/<id>/reply`、`scans`、`scans/<id>`、**`scans/<id>/cancel`（合作式終止＋退款）**、**`scans/<id>/requeue`（重排，不重複扣點）**、`domains`（網域所有權驗證清單）、`domains/<id>/override`（人工核准／否決網域驗證）、`orders`、`dashboard`、**`health`（掃描鏈路與系統資源即時探測）**、`audit-log`、`announcements/*`
- `system_metrics.py`：CPU／記憶體／磁碟／網路／運行時間。**純標準庫，未引入 psutil**——容器內 psutil 讀到的是宿主機數字，會讓 pod 的資源使用率嚴重失真；此模組優先讀 cgroup v2，並在每個指標標示 `scope`（`container`／`host`）
- `cms_views.py`：`cms/(features|team|releases|plans)` 寫入端點（ModelViewSet）
- `models.py`：`AdminAuditLog`（action：`coin_adjust` / `subscription_adjust` / `review_reply` / `review_moderate` / `review_delete` / `user_toggle_staff` / `domain_override` / `scan_control` / `other`；`log_admin_action()` 集中寫入、**失敗不擋業務**）、`Announcement`（常駐/臨時公告）
- `serializers.py`：輸出欄位 **whitelist**

## 重點
- 調點數一律走 `billing.services.admin_adjust`，**禁止**直接改 `CoinWallet`。
- 訂閱調整一律走 `billing.services.grant_subscription` / `cancel_subscription` / `settle_subscription`（grant 的稽核在 services 內寫、cancel 在 view 寫，各恰好一筆 `subscription_adjust`）。
- 每筆後台敏感操作都呼叫 `log_admin_action` 留痕。

## 列表排序（`ordering` 白名單）

`users` / `scans` / `transactions` / `orders` 支援 `ordering` 查詢參數（前綴 `-` 為降冪），由 `_apply_ordering()` 依 `*_ORDERING` 白名單映射到 ORM 欄位。

- **排序必須做在資料庫層**：分頁是 server side（`PAGE_SIZE=25`），只排當頁會讓管理員誤以為看到的是全域最大的幾筆。
- **必須用白名單**：直接把查詢參數丟進 `order_by()` 等於開放任意欄位與關聯走訪。白名單外的值退回預設，不報錯。
- `ScanJob.duration_sec` **不可排序**：它是 serializer 由 `started_at`／`completed_at` 現算的，資料庫無此欄位。

## 掃描處置（cancel / requeue）

- `cancel`：沿用使用者端的**合作式**機制，只設 `status=CANCELLED`，worker 在下個檢查點自行停下；退款走 `refund_full_for_scan`（冪等）。
- `requeue`：**只允許 `failed` / `cancelled`**；`completed` 重排等於提供免費的重新掃描，必須擋下。
- **重排不重複扣點**（2026-09-25 產品決策）。由於 `tasks.py` 在失敗／取消／超時／回收／排程失敗五處都會退款，這些掃描的預扣早已退回，因此重排實際上是免費重跑——這是刻意的，使用者不該為我們這邊失敗的同一次掃描付兩次錢。也因此每次重排都必須寫 `AdminAuditLog`。
- 派工失敗要**還原原狀態**，不可把掃描留在假的 `queued`（會永遠卡住）。

## 禁止事項
| 禁止 | 原因 | 正確做法 |
|---|---|---|
| 刪除 / 修改 `AdminAuditLog` | 破壞合規稽核軌跡 | 僅可查詢 |
| 直接 `CoinWallet` / `CoinTransaction` `.save()` | 繞過冪等與原子交易 | `billing.services.admin_adjust` |
| 在 `views` 直接 render 個資欄位 | 個資外洩 | 透過 serializer whitelist |
| 敏感操作不寫 audit | 合規破口 | 呼叫 `log_admin_action` |

## 評論檢舉治理

- `AdminReviewSerializer` 必須將使用者評論與官方回覆的檢舉數分開輸出，前端不得合併成無法辨識目標的單一數字。
- `moderate_review` 只處理 `response__isnull=True` 的父評論檢舉；隱藏或重新公開評論不得連帶結案官方回覆檢舉。
- `reported=true` 篩選仍需涵蓋任一目標有待審檢舉的評論，避免官方回覆檢舉從治理清單消失。
