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
- `schema.py`：OpenAPI 標註工具（`list_schema()` / `query_param()`），前端型別由它產生的 schema 生成

## 重點
- 調點數一律走 `billing.services.admin_adjust`，**禁止**直接改 `CoinWallet`。
- 訂閱調整一律走 `billing.services.grant_subscription` / `cancel_subscription` / `settle_subscription`（grant 的稽核在 services 內寫、cancel 在 view 寫，各恰好一筆 `subscription_adjust`）。
- 每筆後台敏感操作都呼叫 `log_admin_action` 留痕。

## 列表排序（`ordering` 白名單）

`users` / `scans` / `transactions` / `orders` 支援 `ordering` 查詢參數（前綴 `-` 為降冪），由 `_apply_ordering()` 依 `*_ORDERING` 白名單映射到 ORM 欄位。

- **排序必須做在資料庫層**：分頁是 server side（`PAGE_SIZE=25`），只排當頁會讓管理員誤以為看到的是全域最大的幾筆。
- **必須用白名單**：直接把查詢參數丟進 `order_by()` 等於開放任意欄位與關聯走訪。白名單外的值退回預設，不報錯。
- `ScanJob.duration_sec` **不可排序**：它是 serializer 由 `started_at`／`completed_at` 現算的，資料庫無此欄位。

## OpenAPI 標註（前端型別的來源）

本模組全是 function-based view（`@api_view`），drf-spectacular **推導不出回傳型別**，
沒標註的端點在 schema 裡是空的 `content`，前端就拿不到任何型別。列表端點一律用
`schema.py` 的 `@list_schema(...)` 標註回傳信封與查詢參數。

- **裝飾器順序**：`@list_schema` / `@extend_schema` 必須放在 **`@api_view` 之上**（最外層）。
  放在下面不會報錯，schema 只是靜默地照樣空白。
- **信封名稱一律 `…Response` 結尾**：drf-spectacular 會去掉 serializer 的 `Serializer`
  後綴，`AdminUserListSerializer` → `AdminUserList`。信封若也叫這個名字，後者會覆蓋前者，
  陣列元素的 `$ref` 指回信封自己——型別變成無意義的遞迴結構，而且不報錯。
- 改了 serializer 或篩選參數後，要重新產生前端型別（指令見 `frontend/CLAUDE.md`）。
- 非列表端點直接用 `@extend_schema(request=None, responses=inline_serializer(...))`；目前已標註 `scan_detail`、`scan_cancel`（`refunded`）、`scan_requeue`（`charged`）、`user_detail`、`adjust_coin`、`user_login_events`、`user_subscription`（GET／POST 分開標註）、`subscription_plans`、`reply_review`（POST／DELETE 分開）、`moderate_review`、`domain_override`；`domains` 的 `status` 篩選帶 `VerifiedDomain.Status` enum；`audit-log` 的 `action` 篩選帶 `AdminAuditLog.Action` enum。
- **CMS ViewSet（`cms_views.py`）的 `list` 回傳 `{"items": [...]}` 而非純陣列**，drf-spectacular 推導不出來，已用 `_items_list_schema()` 逐一覆寫描述；方案列表另附 `coin_per_page`（＝`billing.services.estimate_scan_cost(1)`，即五維全選時一頁的費用），供後台試算成本——前端不得自行寫死每頁 coin 數（曾因寫死成 1 導致成本高估 10 倍）。
- **CMS 刪除仍被 PROTECT 外鍵引用的項目回 409**（例：有訂單的購點方案），訊息引導改為停用；原本 `ProtectedError` 未處理會變成 500。
- 公告端點（`announcements/`、`announcements/<id>/`、`announcements/active/`）已依 HTTP 方法分別標註；PATCH 由 drf-spectacular 自動產生全欄位選填的 `PatchedAnnouncementRequest`。
- **篩選參數對應 model choices 時要帶 `enum=`**（例：交易 `kind` 用 `enum=list(CoinTransaction.Kind.values)`），前端型別才會是完整的聯集而不是 `string`；由契約測試比對 enum 與 model 一致。
- **view 在 serializer 輸出後再附加欄位**（如 `user_detail` 附加 `ai_usage`／`recent_scans`／`scans_total`）：serializer 描述不到，要在 `schema.py` 另寫文件用 serializer（`AdminUserDetailResponseSerializer`），改 view 時一起改。
- **`SerializerMethodField` 要標型別**：簡單值用回傳型別註記（`-> str | None`）；回傳巢狀 serializer 用 `@extend_schema_field(...)`。沒標的會變成 `string`／`unknown`。
- **`source="x.y"` 搭配 `default=None` 的欄位必須加 `allow_null=True`**：關聯不存在時實際回傳 `null`，沒宣告的話 schema 寫 `string`，前端型別就是錯的（2026-09-26 修正 5 處）。
- 回應 schema 的欄位一律標為必填（`config/spectacular_hooks.py`）：DRF 序列化 model instance 時一定輸出每個可讀欄位，drf-spectacular 預設卻會把「model 有 default」的欄位標成選填。
- `AdminResponseMatchesSchemaTests` 打實際端點：**回傳的鍵集合必須等於 schema 欄位**，且**實際為 null 的欄位 schema 必須宣告 nullable**——手寫描述與 view 漂移、漏 `allow_null` 都會在這裡失敗。
- 契約由 `tests.py` 的 `AdminOpenAPISchemaTests` 鎖定：端點有宣告回傳、陣列元素不指回信封、
  `ordering` enum 等於 `_apply_ordering` 的白名單、`?user=` 與 `user_id` 都在。

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
