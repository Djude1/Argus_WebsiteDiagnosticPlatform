# 正式站完整掃描主流程回歸驗證（smoke test）＋ worker1 健康確認

**日期**：2026-08-29
**操作者**：Claude（ZCode）
**依據**：[`docs/handoff-2026-08-29-production-scan-smoke-test.md`](../docs/handoff-2026-08-29-production-scan-smoke-test.md)

## 變更內容

無程式碼變更。本次為正式站（K8s）端到端驗證任務，產出：

- 本記錄（驗證證據與結論）。
- [`k8s/README.md`](../k8s/README.md)「2026-07-14 驗證覆蓋與待驗證功能」中「完整掃描主流程」與「公開入口 smoke test」兩項邊界更新。
- 正式站新增一組測試帳號（`scan-smoke-20260829@xn--gst.tw`，密碼現場產生、未記錄於任何文件）與 scan 26 紀錄（保留供日後對照）。

## 執行結果

### Step 0：三網域健康

| 網域 | `/` | `/api/health/live/` | `/api/health/ready/` | `/favicon.svg` |
|---|---|---|---|---|
| `argus.clouda.dpdns.org` | 200 | 200 | 200 | 200 |
| `xn--gst.tw` | 200 | 200 | 200 | 200 |
| `argus6.qzz.io` | DNS 無法解析（curl exit 6） | 同左 | 同左 | 同左 |

- `xn--gst.tw` 初次出現 000 為**本機 DNS 抖動**（對 8.8.8.8／1.1.1.1 的 nslookup 也常逾時），重試即 200，非伺服器問題。
- **發現**：`argus6.qzz.io` 連公共 DNS（1.1.1.1）都查無 A 紀錄（父網域 `qzz.io` 本身可解析），疑似 DNS 紀錄已移除；但 `k8s/01-namespace-config.yaml` 的 `DJANGO_ALLOWED_HOSTS`／`CORS_ALLOWED_ORIGINS`／`CSRF_TRUSTED_ORIGINS` 仍列有它。待團隊確認：補回 DNS 或從 ConfigMap 移除。主入口正常，不影響本次驗證。

### Step 1：叢集快照（ArgoCD API，唯讀）

本機 kubectl 無 context（路徑 A 不可用），改走 ArgoCD REST API（憑證取自 `.env`，未輸出值）。

- `argus` application：**Synced + Healthy**；`sync.revision = 53899db`（＝本機 main HEAD `53899db`，即本次驗證的正是目前正式影像）。
- Pod 快照（來自 resource-tree）：
  - `web` 2/2：worker1 + worker2 各一，Running 1/1
  - `worker` 2/2：worker1（restart 4）+ worker2（restart 2），Running 1/1
  - `frontend` 2/2：worker1 + worker2，Running 1/1
  - `db-0`（worker2）、`redis`（worker2）皆 Running 1/1
  - `argus-gateway-nginx` 2 pods：worker1 + worker2，1/1
  - `migrate` PreSync Job：在 worker1 上 **Completed**
  - 全叢集無 `Init:ContainerStatusUnknown`／`CrashLoopBackOff`
- **worker1 結論：已恢復**（07-24 待修事項正式結案）。證據＝web／worker／frontend／gateway／migrate 多種 workload 目前都正常調度且 Healthy 運行於 worker1。邊界：ArgoCD API 讀不到 node object 本身狀態（`kubectl get nodes` 未驗證，本機無 kubeconfig），上述為 pod 層級間接證據。

### Step 2：註冊 → 登入 → 錢包

- 註冊 201（回應含 access）、登入 200。
- 錢包 `balance = 200`（交易 id 63：`monthly_bonus` +200，「建立帳號自動發放月贈點 2026-08」）。

### Step 3：建立掃描＋預扣

- `POST /api/scans/` → **201，scan id = 26**，`status: queued`（參數：`aiglasses.qzz.io`、passive、max_depth 3、max_pages 10）。
- 錢包 200 → **100**（交易 id 64：`scan_hold` −100，「建立掃描預扣（max_pages=10）」）。
- 註：前 3 次 curl 000 為本機 DNS 抖動，第 4 次成功。

### Step 4：狀態流

- `started_at 03:26:56`（+08:00）＝建立即被 worker 取件（queued 幾乎無等待）。
- 03:27:47 觀察到 `crawling`；03:29:22 **`completed`**。全程約 **2.5 分鐘**（遠低於 60 分鐘門檻）。
- `scan_log` 顯示完整鏈路：爬取 10 頁（首頁、`/admin/`、`/announcements`、`/api/products/search`、`/download`、`/product`、`/product/1`、`/project`、`/purchase`、`/purchase?product=…`）→「開始分析，共 10 頁」→ 逐頁分析 →「掃描完成」。無 blocked／failed URL。
- 註：45 秒輪詢間隔未直接捕到 `analyzing` 過渡，但 scan_log 有明確的分析階段紀錄。

### Step 5：findings、結算、score

- `GET /api/findings/?scan_id=26` → 200，**44 筆**（scan 18 當時 5 筆；數字不設門檻）。
- 錢包結算：balance **100**；交易 id 65：`scan_refund` +0，「實際 10 頁，無退款差額」。數學核對：200 − 10 頁 × 10 coin = 100 ✓。
- status：`completed`、`overall_score = 38`、`category_scores = {"ux": 100, "aeo": 84, "geo": 0, "seo": 62, "security": 4}`、`top_actions = null`（本次）。
- 對照 scan 18（07-24：score 92、5 findings）：本次 score 38、44 findings。**§5 第 4 列未觸發**（findings 端點正常、score 有值）；分數差異與 findings 數量增加方向一致（偵測項目隨版本增加），`geo = 0` 屬站台層級訊號（llms.txt／robots）。判定為資料差異而非回歸；如需深究另開任務。
- 觀察（非 BUG）：`/api/scans/<id>/status/` 的 `ScanJobStatusSerializer` 欄位**不含 `completed_at`**（回應中鍵不存在，非 null）；DB 端完成時有正確寫入（`tasks.py:747`）。若前端需要完成時間，需在 serializer 補欄位。

### `warning_summary`／`scan_effectiveness` 資料形狀（交接「前端 scan_effectiveness 顯示」任務）

本次實測（健康掃描，scan 26）：

```json
"warning_summary": { "failed_urls": [], "blocked_urls": [] }
```

程式碼對照（`backend/apps/scans/tasks.py`）確認 `warning_summary` 為**條件式擴充**，可能形狀共三種：

| 情境 | 額外鍵 |
|---|---|
| 正常（有頁、無 agent） | 僅 `failed_urls`、`blocked_urls` |
| 0 頁 crawled（掃描實質失效） | 加 `"scan_effectiveness": "no_pages_crawled"`（`tasks.py:710`），scan_log 同步出現「掃描有效性警示」warn |
| Hermes-Agent 有實際執行 | 加 `"agent": agent_meta`（`tasks.py:731`） |

**前端注意**：`scan_effectiveness`（與 `agent`）鍵**缺席是常態、代表無警示**，顯示邏輯應以「鍵存在才顯示警示」處理，不可假設鍵一定存在。目前正式站影像（sync revision `53899db`）已含此行為（本次 10 頁掃描正確地未出現該鍵）。

## 原因

07-24 scan 18 之後正式環境 rollout 多次（score 誤導修復、ECPay Stage、購點改版、介紹頁改版、frontend 埠 8080→8081），端到端掃描鏈路未再驗證；worker1 故障（07-24 標記待修）無已修復結論。本次補上兩者。

## 影響範圍

- 無程式碼變更；正式站多一筆測試帳號與 scan 26（保留供對照，不影響他人）。
- [`k8s/README.md`](../k8s/README.md) 驗證矩陣兩項邊界收斂（本文件同 commit）。
- 後續任務「前端 `scan_effectiveness` 顯示」可直接引用上方資料形狀。
- `argus6.qzz.io` DNS 失效與 ConfigMap 殘留，待團隊決策（補 DNS 或移除設定）。

## 驗證方式

Handoff §4 成功條件逐項核對：

- [x] 三網域健康：主域與 `xn--gst.tw` 全 200（`argus6.qzz.io` 為 DNS 層問題，非平台層，已記錄）
- [x] 叢集快照已記錄；web Ready = desired 2/2；worker1 有明確結論（已恢復）
- [x] 註冊 201、登入 200、錢包 200 coin
- [x] `POST /api/scans/` 201 + id 26 + `queued`；即時預扣 200→100
- [x] `queued → crawling → analyzing（scan_log 證據）→ completed`，全程約 2.5 分鐘 ≤ 60 分鐘
- [x] findings 可取回（44 筆）；score／`warning_summary` 已截錄
- [x] 錢包結算正確：hold −100、實際 10 頁退款差額 0、balance 100

全程未輸出任何密碼／token／Secret 值；對叢集僅唯讀查詢（ArgoCD REST API）；僅掃團隊自有靶機。
