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
| `crawler.py` | Playwright BFS 爬蟲、收集頁面 | 修改 ScanJob.status、呼叫 billing |
| `scanners.py` | 四維掃描（SEO/AEO/GEO/Security）、產生 findings | 修改 ScanJob.status |
| `cancellation.py` | CancellationToken，供 worker 輪詢是否要終止 | 直接終止 worker process |
| `reports.py` | 產生 Word 報告（.docx） | 任何 DB 寫入 |
| `nuclei_scanner.py` | Nuclei binary 封裝；fast/deep 雙模式；JSONL 解析；Finding mapping | 在 passive mode 執行（已由 deep 旗標控制） |

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

取消流程：
1. 使用者呼叫 Cancel API → 在 Redis 設置取消旗標
2. `CancellationToken.is_cancelled()` 在 worker 每處理幾頁時輪詢
3. Worker 偵測到取消 → 停止爬蟲 → 呼叫 `refund_full_for_scan(scan)` → 狀態設為 `cancelled`

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

---

## 整合測試規則（必讀）

**掃描功能整合測試一律使用 Docker 環境（`localhost:8080`），禁止用本機 runserver 測試。**

原因：本機 runserver 缺少 Redis（Celery broker 無法運作）、Celery worker、正確前端 dist，繞過這些限制需要大量額外工作且驗證不完整。

```powershell
# 標準整合測試流程
docker compose up -d --build web worker   # 含最新程式碼重建

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
| Nuclei deep mode 需 `scan_mode=active AND active_testing_authorized` | 未授權的主動測試 |
| 直接 `ScanJob.objects.filter(...).update(status=...)` | 繞過 signal，狀態不一致 |
| 用本機 `runserver` 做掃描整合測試 | 缺少 Redis/Celery，驗證不完整 |
