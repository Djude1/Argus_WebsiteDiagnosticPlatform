# Nuclei 整合設計文件

**日期**：2026-06-03
**狀態**：待實作
**範疇**：Phase 1 — 快速掃描（免費）+ 深度掃描（付費）雙模式

---

## 背景與目標

Argus 目前的資安掃描涵蓋：被動 header 檢查、PII 偵測、Katana JS 秘鑰分析，以及 active_probes（admin 路徑枚舉、SQLi boolean、開放目錄）。覆蓋範圍有限，缺少 XSS、CORS、CVE、JWT、SSRF 等常見漏洞類別。

本次整合目標：
- 引入 **Nuclei**（29k stars，ProjectDiscovery）補強資安偵測廣度
- 將 Katana 從 Docker 改為本機 binary，消除 Docker 啟動 overhead
- 以 **並行執行** 控制總掃描時間（快速掃描優先）
- 刪除 `active_probes.py`，由 Nuclei 取代其功能並大幅擴展

---

## 商業分層設計

| 層級 | 觸發條件 | 包含內容 |
|---|---|---|
| **免費（快速掃描）** | `scan_mode=passive`（預設） | crawl + 四維 scan + Katana binary + Nuclei 精選模板，timeout 6 分鐘 |
| **付費（深度掃描）** | `scan_mode=active` + `active_testing_authorized=True` | 免費全部 + Nuclei **全部模板**（無 `-tags` 限制），timeout 12 分鐘，`-c 50` |

兩個層級均在 Phase 1 實作並可測試。`ScanJob` schema 不變，沿用現有 `active_testing_authorized` 欄位作為付費授權旗標。

---

## 架構變動

### 流程對比

```
改前：
crawl → scan → katana(Docker) → site_signals → active_probes → agent

改後：
crawl → scan → ┌ katana(binary)  ┐ ThreadPoolExecutor 並行
               └ nuclei(binary)  ┘
               → merge findings → site_signals → agent
```

### 檔案異動清單

| 動作 | 檔案 | 說明 |
|---|---|---|
| 新增 | `apps/scans/nuclei_scanner.py` | Nuclei subprocess 封裝 |
| 修改 | `apps/scans/katana_scanner.py` | Docker → binary |
| 修改 | `apps/scans/tasks.py` | 並行執行 + 移除 active_probes 呼叫 |
| 刪除 | `apps/scans/active_probes.py` | Nuclei 已完整取代 |
| 刪除 | `apps/scans/tests_active_probes.py` | 對應測試一併移除 |
| 新增 | `apps/scans/tests_nuclei_scanner.py` | Nuclei 模組單元測試 |

---

## nuclei_scanner.py 設計

### 執行模式對照

| 參數 | 免費（fast） | 付費（deep） |
|---|---|---|
| 觸發條件 | `scan_mode=passive` | `scan_mode=active` + `active_testing_authorized=True` |
| `-tags` | `cves,vulnerabilities,misconfigurations,exposures,default-logins` | 不加（全部模板） |
| `-timeout` | `15`（每 request 15 秒） | `30`（每 request 30 秒） |
| `-c`（執行緒） | `25` | `50` |
| subprocess 硬限 | `360` 秒（6 分鐘） | `720` 秒（12 分鐘） |

```bash
# 免費模式
nuclei -u <url> -tags cves,vulnerabilities,misconfigurations,exposures,default-logins \
  -timeout 15 -c 25 -j -o /tmp/nuclei_<id>.jsonl -silent

# 付費模式
nuclei -u <url> -timeout 30 -c 50 -j -o /tmp/nuclei_<id>.jsonl -silent
```

### Binary 偵測與模式選擇（silent-fail）

```python
def run_nuclei(url: str, scan_job_id: int, *, deep: bool = False) -> list[dict]:
    if not shutil.which("nuclei"):
        append_log(scan_job_id, "Nuclei binary 未安裝，略過", level="warn")
        return []
    # deep=True 時不加 -tags，跑全部模板
    # ... 依 deep 決定參數後執行 subprocess
```

### Finding Mapping

| Nuclei JSON 欄位 | Finding 欄位 | 備註 |
|---|---|---|
| `info.name` | `title` | 直接對應 |
| `info.severity` | `severity` | critical/high/medium/low 已相容 |
| `info.description` | `description` | |
| `info.remediation` | `remediation` | 空時填「請參考官方修補建議」|
| `matched-at` | `evidence` | 命中 URL |
| `extracted-results` | `evidence`（附加） | 額外證據字串 |
| 固定 `"security"` | `category` | 所有 Nuclei finding 歸入 security |
| 固定 `None` | `page` | 不綁定特定頁面（同 Katana） |
| 依 severity | `priority_score` | critical=90, high=75, medium=55, low=30 |
| 固定 `0.85` | `confidence` | 社群驗證模板，預設高信心值 |

### 去重邏輯

同一 `(template-id, matched-at)` 組合在 parse 階段用 `set` 去重，不依賴 DB constraint。

---

## katana_scanner.py 變動

移除 `docker run projectdiscovery/katana ...`，改為直接呼叫本機 `katana` binary：

```bash
katana -u <url> -d <depth> -jc -jsl -td -json-output /tmp/katana_<id>.json
```

同樣加上 `shutil.which("katana")` 偵測，binary 不存在則 silent-fail。

---

## tasks.py 並行段落

```python
import threading
from concurrent.futures import ThreadPoolExecutor

# scanning 主迴圈結束後
cancel_event = threading.Event()

def _watch_cancel(scan_job_id: int, event: threading.Event) -> None:
    while not event.wait(timeout=5):
        if is_cancelled(scan_job_id):
            event.set()

watcher = threading.Thread(
    target=_watch_cancel, args=(scan_job_id, cancel_event), daemon=True
)
watcher.start()

deep_mode = (
    scan_job.scan_mode == ScanJob.ScanMode.ACTIVE
    and scan_job.active_testing_authorized
)
append_log(scan_job_id, f"Nuclei 模式：{'深度（付費）' if deep_mode else '快速（免費）'}")

try:
    with ThreadPoolExecutor(max_workers=2) as executor:
        f_katana = executor.submit(run_katana, scan_job.normalized_url,
                                   scan_job.max_depth, scan_job.max_pages,
                                   cancel_event)
        f_nuclei = executor.submit(run_nuclei, scan_job.normalized_url, scan_job_id,
                                   cancel_event, deep=deep_mode)

    katana_findings, katana_tech = f_katana.result()
    nuclei_findings = f_nuclei.result()
finally:
    cancel_event.set()  # 確保 watcher thread 退出

for finding in katana_findings + nuclei_findings:
    Finding.objects.create(scan_job=scan_job, page=None, **finding)
```

---

## 錯誤處理

| 情境 | 處理方式 |
|---|---|
| Binary 不存在 | silent-fail，`append_log` warn，回傳空 list |
| Subprocess timeout（360s） | `proc.kill()`，silent-fail |
| JSON parse 錯誤（單筆） | 跳過該筆，記錄 warn，繼續處理其他結果 |
| 使用者取消 | `cancel_event.set()` 通知兩個 subprocess terminate |
| 兩個 thread 都失敗 | 主流程繼續（site_signals、agent 不受影響） |

---

## 測試策略

### 新增：`tests_nuclei_scanner.py`

| 測試案例 | Mock 方式 | 驗證重點 |
|---|---|---|
| Binary 不存在 | `shutil.which` 回傳 None | 回傳 `[]`，不拋例外 |
| 正常 JSON 輸出解析 | mock subprocess stdout | Finding dict 欄位正確 |
| severity → priority_score mapping | 各 severity 值逐一測 | critical=90, high=75... |
| 重複結果去重 | 兩筆相同 template-id + matched-at | 只產出一筆 |
| Subprocess timeout | mock `subprocess.run` raise TimeoutExpired | silent-fail，回傳 `[]` |
| **免費模式參數** | `deep=False`，mock subprocess | 指令含 `-tags`，硬限 360 秒 |
| **付費模式參數** | `deep=True`，mock subprocess | 指令**不含** `-tags`，硬限 720 秒，`-c 50` |

### 修改：現有測試

- `tests_active_probes.py`：整個刪除
- Katana 相關 mock：更新 mock target 從 `docker run` 改為 `katana` binary 路徑

### 手動整合驗證

對 DVWA 或 OWASP Juice Shop 靶機執行兩次掃描，確認：

**免費模式（passive）：**
1. scan log 出現「Nuclei 模式：快速（免費）」
2. `Finding` 表有 `category=security` 的 Nuclei 結果
3. 總掃描時間 < 10 分鐘

**付費模式（active + authorized）：**
1. scan log 出現「Nuclei 模式：深度（付費）」
2. Finding 數量明顯多於免費模式（全部模板 > 精選模板）
3. 總掃描時間 < 15 分鐘

---

## 未來展望（Phase 2）

Phase 1 已實作免費（快速）與付費（深度）雙模式。Phase 2 可在付費模式下加入額外工具：

- **dalfox**（XSS 深度掃描）：針對所有含輸入的頁面自動注入 XSS payload
- **sqlmap**（完整 SQLi）：取代 Nuclei SQLi 模板，涵蓋 union/time-based/error-based
- 上述工具以並行 subprocess 加入 `ThreadPoolExecutor`，不影響現有流程

---

## 安裝需求

```powershell
# Nuclei
go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
nuclei -update-templates

# Katana（取代現有 Docker image）
go install github.com/projectdiscovery/katana/cmd/katana@latest
```

或透過 Docker Desktop 內已有的 Go 環境，或直接下載 release binary。
