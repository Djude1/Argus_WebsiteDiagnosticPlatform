# scans 模組規則

Claude 操作 `backend/apps/scans/` 時，本檔在專案層 `CLAUDE.md` 之後自動載入。

---

## ScanJob 狀態機

狀態只能按以下順序推進，**禁止跳轉或逆轉**：

```
queued → crawling → scanning → [agent_testing] → completed
    ↘ cancelled（任何階段可轉）
    ↘ failed（任何階段可轉）
```

- 狀態推進只能在 `tasks.py` 中進行
- `scanners.py` 和 `crawler.py` 禁止直接修改 `ScanJob.status`
- 原因：集中在 `tasks.py` 管理讓狀態轉換可追蹤，也讓 signal 可以統一監聽

---

## 各檔案職責

| 檔案 | 職責 | 禁止做的事 |
|---|---|---|
| `tasks.py` | Celery task 入口、狀態機推進、呼叫 billing | 直接執行爬蟲邏輯 |
| `scan_plan.py` | 將單頁／全網站範圍與主動授權集中轉成各工具的執行閘門 | 寫 DB、執行任何掃描工具 |
| `process_runner.py` | 以 `Popen` 執行 Nuclei/Katana，輪詢 DB 取消並終止 process tree | 吞掉 `ScanCancelled`、記錄 raw stdout/stderr |
| `crawler.py` | Playwright BFS 爬蟲、收集頁面 | 修改 ScanJob.status、呼叫 billing |
| `scanners.py` | SEO/AEO/GEO 掃描 + 被動式基本安全檢查（HTTPS/header 存在性/CSRF/PII）、產生 findings | 修改 ScanJob.status、深度資安分析 |
| `cancellation.py` | 合作式取消：`is_cancelled` / `raise_if_cancelled` 直接查 DB `ScanJob.status` 是否為 `CANCELLED`（**非 Redis 旗標**），供 worker 在檢查點輪詢 | 直接終止 worker process |
| `reports.py` | 產生 Word 報告（.docx） | 任何 DB 寫入 |
| `nuclei_scanner.py` | Nuclei binary 封裝；工具預算、JSONL 解析、Finding mapping | 在 passive 或未授權模式執行 |
| `katana_scanner.py` | Katana 全站 JS/端點探索封裝；時間、大小、同主機與 RPS 預算 | 在單頁、passive 或未授權模式執行 |
| `security/` | 深度主動式資安檢查（SSL/TLS、Cookie、CORS、CSP 品質、敏感檔外洩探測、硬編碼秘鑰偵測、OWASP 對映、Kali 工具）| 修改 ScanJob.status、呼叫 billing |

### 掃描範圍與工具矩陣

產品範圍只有兩種：前端以 `max_pages=1` 表示**單頁**，其餘合法值表示**全網站**。`passive/active` 是探測授權層級，不是第三種掃描範圍。所有工具閘門集中由 `scan_plan.py` 決定：

| 範圍與授權 | Nuclei | Katana | 敏感路徑探測 | Hermes-Agent | Kali |
|---|---:|---:|---:|---:|---:|
| 單頁 + passive | 否 | 否 | 否 | 否 | 否 |
| 全網站 + passive | 否 | 否 | 否 | 否 | 否 |
| 單頁 + active 且已授權 | 僅輸入頁 | 否 | 否 | 否 | 可執行既有同源候選驗證 |
| 全網站 + active 且已授權 | 已爬 URL | 是 | 是 | 是（另受總開關控制） | 可執行既有同源候選驗證 |

Katana 與 Nuclei 並行時必須共享 `ARGUS_ACTIVE_MAX_RPS`；若總預算只有 1 RPS，必須改為依序執行。單頁不得用 Katana、敏感路徑字典或 Agent 擴張成全站掃描。

### 資安邊界（重要）

`scanners.py` 的 `analyze_security()` 與 `security/` sub-package 的分工：

- **`scanners.py` 留著**：被動讀取已有 response headers/HTML，不需要額外連線（HTTPS 判斷、header 存在性、CSRF token、PII 偵測）
- **`security/` 新增**：需要額外連線或工具呼叫的深度分析（SSL 憑證讀取、Cookie API、OPTIONS 探測、敏感檔主動探測 content discovery、docker exec kali）
- **例外（被動但放 security/）**：硬編碼秘鑰偵測 `secret_scanner.detect_secrets_in_text` 是純解析，但因屬「深度解析」歸 security/；由 tasks.py 對已抓 HTML 被動呼叫（零額外請求）
- **新的資安功能一律寫進 `security/`**，不要再擴充 `scanners.py` 的資安部分

詳細規則見 [`security/CLAUDE.md`](security/CLAUDE.md)。

---

## ScanJob.progress 格式

Worker 每完成一頁需更新此 JSON 欄位，前端輪詢後顯示進度條：

```json
{
  "pages_done": 12,
  "pages_total": 50,
  "phase": "crawling",
  "phase_started_at": "2026-05-26T10:30:00Z"
}
```

`phase` 值必須是 `"crawling"` / `"scanning"` / `"agent_testing"` 其中之一。

---

## 合作式取消機制（Cancellation）

實作在 `cancellation.py`，**完全 DB-status-based**（沒有 Redis 旗標）：

1. 使用者呼叫 Cancel API → `views.py` 把 `ScanJob.status` 直接 update 成 `CANCELLED` 後立即回應。
2. `is_cancelled(scan_job_id)` 用 `ScanJob.objects.filter(id=..., status=CANCELLED).exists()` 即時查 DB（**不**用 ORM 物件快取、**不**經 Redis）；`raise_if_cancelled(scan_job_id)` 在檢查點呼叫它，命中就 raise `ScanCancelled`。
3. Worker 各階段（爬蟲每頁、scanners、agent、Kali fallback、Kubernetes executor 的 watch / Pod list / log I/O 前後）透過 `raise_if_cancelled` 主動輪詢；偵測到取消 → 停止當前工作 → `tasks.py` 主迴圈的 try/except 收到 `ScanCancelled` 後走 cancelled/refund 分支。

選擇 DB-status 而非 Celery `revoke(terminate=True)` 或 Redis 旗標的理由見 `cancellation.py` 模組 docstring：terminate 會送 SIGTERM 給 worker process 可能波及同 worker 其他 task；DB-status 讓 worker 在「安全點」停下，DB 不會留下半完成狀態。

重要：Cancel API 也會呼叫 `refund_full_for_scan`，兩邊都呼叫是安全的（冪等）。

---

## Playwright 規則

**Chromium 必須安裝在專案 `.ms-playwright`，禁止安裝到全域路徑。**

```powershell
# 正確安裝方式
$env:PLAYWRIGHT_BROWSERS_PATH=".ms-playwright"
uv run playwright install chromium

# 禁止（會污染全域）
uv run playwright install chromium
playwright install chromium
```

原因：全域 Playwright 路徑（`%USERPROFILE%\AppData\Local\ms-playwright`）若被覆蓋，會影響其他使用相同機器的開發者。

所有掃描入口、redirect、子資源與 WebSocket 都必須經 `services.py` 的公開 HTTP 目標政策；禁止 localhost、非 global IP、userinfo 與非 80/443 port。應用層驗證仍不能消除 DNS rebinding 的解析/連線競態，production 必須另以受控 egress proxy / firewall 阻擋 private、loopback、link-local 與 metadata 網段。

主 frame navigation 與 WebSocket 在送出前還必須符合 `ScanJob.origin`；公開 CDN 子資源可通過 public HTTP policy，但不可把主頁或 WebSocket 擴張到其他 origin。Nuclei 必須啟用 `-lna`、`-ni`、`-pt http` 並使用授權 User-Agent；Katana 必須使用 exact-origin `-cs`，不可只用僅限制 hostname 的 `fqdn`。

---

## Coin 扣點流程（與 billing 整合）

```
建立掃描 → hold_for_scan(max_pages × 10 coin)
  ↓ worker 完成
settle_scan_actual(actual_pages × 10 coin)  ← 退差額
  ↓ 若失敗/取消
refund_full_for_scan(scan)  ← 全退（冪等）
```

`tasks.py` 負責在適當時機呼叫這三個 `billing/services.py` 函式。

若 `run_scan_job.delay()` 在 worker 取件前失敗，`views.py` 必須呼叫
`tasks.fail_scan_job_before_start()`，以同一筆資料庫交易把 `queued` 改為
`failed` 並執行冪等全額退款；API 回 503，不得留下孤兒工作或回傳 broker 例外細節。

建立掃描的 HTTP request 不得同步執行完整掃描。正式／Docker 模式只負責將任務
publish 到 broker；本機 `CELERY_TASK_ALWAYS_EAGER=true` 時，`views.py` 必須改由
單一背景 executor 啟動獨立 Python 子程序，先回 `201 + queued + ScanJob.id` 讓前端
立即進入詳情頁。Playwright 不得直接跑在 web thread；子程序才可呼叫
`run_scan_job.apply(..., throw=True)`。父程序前後必須清理 DB connection，以容量 1
的 semaphore 限制 outstanding 工作，並設定硬逾時與 process-tree 終止。子程序異常
結束時必須把所有非終態工作收斂為 `failed` 並冪等全額退款；忙碌或提交 executor
失敗仍走 `fail_scan_job_before_start()`。這條路徑只供 `DEBUG=true` 的本機 smoke
test，不是正式 worker；部署檢查 `scans.E001` 會拒絕非 DEBUG 的 eager 設定。

---

## 整合測試規則（必讀）

**完整掃描整合測試一律使用 Docker 環境（`localhost:8080`）。本機 runserver 僅能用 eager 模式做 smoke test。**

原因：本機 eager 可快速驗證單一程序的排程與掃描結果，但不包含 Redis、Celery worker 與 PostgreSQL，不能代表完整背景任務鏈路。環境選擇與前置檢查以 [`../../../docs/environment-preflight.md`](../../../docs/environment-preflight.md) 為準。

本機 eager 的建立 API 會先回傳 queued 任務，再由 web process 內的單一背景
executor 管理獨立 Python 掃描程序；同時只接受一筆 outstanding 工作，忙碌時新任務
會失敗並全額退款。因此可驗證前端立即導頁與掃描狀態輪詢，但關閉／重啟 runserver
可能中斷工作，不能當成具持久性的正式佇列。

```powershell
# 標準整合測試流程
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build web worker   # 含最新程式碼重建

# 給測試帳號補充 coin
docker exec argus-web-1 uv run python manage.py shell -c "
from django.contrib.auth import get_user_model
from apps.billing.services import get_or_create_wallet, admin_adjust
User = get_user_model()
user = User.objects.filter(email='YOUR_EMAIL').first()
admin = User.objects.filter(is_superuser=True).first()
admin_adjust(target_user=user, delta=999999, admin_actor=admin, note='test')
"

# 開啟 localhost:8080，用 UI 建立掃描並觀察 log
```

確認 Docker worker 有安裝 nuclei/katana：
```powershell
docker exec argus-worker-1 nuclei -version
docker exec argus-worker-1 katana -version
```

---

## 禁止事項

| 禁止 | 原因 |
|---|---|
| `scanners.py` / `crawler.py` 修改 `ScanJob.status` | 狀態機只在 tasks.py 管理 |
| `crawler.py` 呼叫任何 billing 函式 | 職責分離 |
| `playwright install` 不加 `PLAYWRIGHT_BROWSERS_PATH` | 污染全域路徑 |
| Nuclei/Katana 主動工具需 `scan_mode=active AND active_testing_authorized`，並遵守單頁／全網站矩陣 | 未授權或超出使用者選擇範圍的主動測試 |
| 直接 `ScanJob.objects.filter(...).update(status=...)` | 繞過 signal，狀態不一致 |
| 把本機 eager smoke test 當成完整掃描整合 | 未涵蓋 Redis／worker／PostgreSQL，驗證不完整 |
