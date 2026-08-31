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

## 分數計算契約（`scanners.py::calculate_scores`）

2026-08-30 依 [`docs/scan-report-quality-audit-2026-08-30.md`](../../../docs/scan-report-quality-audit-2026-08-30.md) 修正，四條規則都有測試鎖定（`tests_scoring_and_report_grouping.py`）：

1. **同一分類內同一 `rule_id` 只扣一次分**。一個問題出現在幾頁是「廣度」不是「嚴重度」；報告本來就把它們合併成一筆顯示，計分不跟著去重會讓使用者看到一項卻被扣了 N 次。
2. **`info` 不扣分**。info 多半是純資訊甚至正向指標（例如「Nuclei 探針被 WAF 攔截，代表防護有效」）。**同理 `info` 不進 `top_actions`**——它對應的建議修補是「無需修復」，列進「優先改善建議」會被當成待辦。
3. **指數衰減 `100 * exp(-penalty / SCORE_DECAY_CONSTANT)`**，不是 `max(0, 100 - penalty)`。舊公式累積 100 分懲罰後永遠是 0，無法分辨「4 個高風險」與「40 個高風險」。`SCORE_DECAY_CONSTANT` 是可調的產品參數，不是演算法細節。
4. **未評估的分類不寫進 `category_scores`，缺鍵即代表未評估**。`category_scores` **不保證含全部 5 個分類，取值一律用 `.get()`**。這同時保證「報告列出的分數」與「`overall_score` 平均的分母」是同一組，使用者算得出總分。

`Finding.Meta.ordering` 一併鎖定兩件事：`priority_score` 必須明確 `nulls_last=True`（PostgreSQL 的 `DESC` 預設 NULLS FIRST、SQLite 是 NULLS LAST，不指定的話同一份報告在本機與正式站排序相反），`severity` 必須用 `Case/When` 的風險序（CharField 直接排是字母序 `critical < high < info < low < medium`，info 會插到 low 與 medium 前面）。

`make_finding()` 在呼叫端沒傳 `priority_score` 時，依 severity 給預設值——`security/` 子套件的 scanner 全都不傳，留 `None` 會被 PostgreSQL 頂到報告最前面。

---

## 報告內容契約（`reports.py`）

`.docx` 會被下載、轉寄、存檔給第三方，內容邊界是硬規則：

| 必須有 | 為什麼 |
|---|---|
| 掃描範圍（範圍／模式／頁數上限／實際頁數／robots） | 收件者要能判斷涵蓋範圍，「沒發現問題」才有意義 |
| 掃描授權聲明（`AuthorizationConsent`） | Argus 是授權式掃描平台，報告沒有授權依據等於放棄核心合規主張；查無紀錄要明講，不能讓章節消失 |
| 掃描警示（`scan_effectiveness` / 略過與失敗頁數） | 爬 0 頁的掃描會產出看起來正常的報告，分數只反映站台層級檢查 |

| 絕對不能寫進報告 | 為什麼 |
|---|---|
| `AuthorizationConsent.ip_address`、`user_agent`、授權帳號 | 個資與瀏覽器指紋，對收件者零價值只增加外洩面；稽核走 DB 與 `AdminAuditLog` |
| `warning_summary["settlement_error"]`、`agent` 的 token 用量 | 內部運維／計費資訊，不是客戶要看的東西 |
| 未實作功能的描述 | 附錄曾聲稱「交由 AI 進行自然語言解釋」，但 `ai_explanation` / `ai_remediation` 全 backend 只被寫入空字串——對外文件的不實陳述 |

### 報告要短：樣板只講一次（scan 38 事後修正）

scan 38 是 34 頁，使用者回饋「結構跟之前差不多、優化不明顯」。實測分布：發現項目佔全文 78.9%，其中

- 逐項的 AI 提示詞佔發現項目 **43%**，內容是把上方「問題是什麼／檢測依據／怎麼修」原封不動再抄一遍
- 「為什麼要在意」出現 14 次卻只有 **6 種**內容；「修好了怎麼確認」14 次只有 **3 種**

所以規則是：**只跟分類有關的講一次、只跟流程有關的講一次，每項發現只留屬於它自己的內容。**

| 內容 | 放哪裡 |
|---|---|
| 分類的「沒處理會怎樣」 | 摘要的「這些分類為什麼重要」表，**且只列有非 info 發現的分類**——某分類若只有正向資訊提示，寫「會被攻擊者利用」就是把好消息說成威脅 |
| 修補後怎麼驗證 | 附錄，一次 |
| 怎麼用 AI 深入了解 | 附錄，一次（叫讀者複製該項的三段文字，不逐項重印提示詞）|
| 問題是什麼／怎麼修／檢測依據 | 逐項 |

其他硬性上限：每項發現的中繼資料壓成**一行**不用表格（19 項就是 19 張表，在 Word 裡非常吃垂直空間）；受影響頁面最多列 `_MAX_LISTED_PAGES` 個、其餘收成「…另 N 處」；證據顯示上限 `_MAX_EVIDENCE_CHARS`。

成效：總字元 15848 → 6669（−58%），表格 30 → 10，發現項目數不變。由 `tests_report_compactness.py` 鎖定。

### 報告的讀者是網站主，不是資安工程師

| 規則 | 為什麼 |
|---|---|
| 內部識別碼（`rule_id`、`evidence_source`、`evidence_type`）不進正文 | 對讀者零意義。`rule_id` / OWASP / CWE 收進附錄「技術索引」供工程師與稽核查用 |
| 每筆發現固定四段：問題是什麼 / 為什麼要在意 / 怎麼修 / 修好了怎麼確認 | 舊版依 severity 給同一個結構三種標題（風險描述／改善重點／建議優化），讀者會以為是三種不同的東西 |
| **`info` 走不同結構**（這代表什麼，且沒有「怎麼修」） | info 常是正向指標。實際產出報告時發現「Nuclei 探針受 WAF 攔截」（代表防護有效）底下寫著「這類問題會被攻擊者利用」——與該項意義完全相反，還叫讀者去修一個沒壞的東西 |
| 「修好了怎麼確認」不得假設問題型態 | 舊文字寫「用 curl -I 檢查回應標頭」，但頁面外洩個資這類問題根本不是標頭問題 |
| 名詞解釋只列這份報告真的出現過的術語 | 貼固定清單會塞進一堆與本次無關的名詞 |

排版下限：**必須有**封面、目錄、章節分頁、表格、頁首頁尾與頁碼 field、嚴重度顏色。舊版是 328 段純文字流（其中 293 段 Normal、0 表格、0 分頁），有 `tests_report_layout.py` 鎖定。

中文字型要同時設 `run.font.name` 與 `w:eastAsia`（`_styled_run()` 已封裝），只設前者 Word 會對中文退回預設字型。

`styles.css` 的 `--argus-cyan (#38bdf8)` 是為深色背景設計的，**印在白紙上對比不足**；報告標題用 `--argus-cyan-deep (#0c4a6e)`，cyan 只當強調線。

**`Finding.ai_explanation` / `ai_remediation` / `llm_model` / `llm_generated_at` 目前無任何寫入點**，報告不得聲稱有 AI 解釋。

報告改為輸出 **`ai_handoff_prompt`**（`scanners.build_ai_handoff_prompt()` 產生，每筆 finding 都有值）——使用者可直接貼進 ChatGPT / Claude 取得深入說明。**這段必須跟 `evidence` 一樣套 `mask_pii_evidence()`**：提示詞內嵌了原始 evidence，不遮罩等於從後門把個資漏回這份會被轉寄的報告。

---

## 截圖失敗不得讓整頁分析作廢（2026-08-31 事故）

`page.screenshot()` 在 `crawler.py` 裡是在 **`pages.append()` 之前**執行的。
舊版讓它的例外直接冒出去，會被外層的 `except Exception` 接住，**整頁被丟進 `failed_urls`**——連帶該頁的 `Page` 紀錄與 SEO/AEO finding 一起消失。

**SEO 與 AEO finding 只由 `analyze_page()` 逐頁產生**，所以「爬到 0 頁」＝這兩類完全沒有結果。正式站的實際症狀是：掃描顯示完成，但畫面截圖空白、SEO 分析整個不見，只剩站台層級的 DNS/SSL/header 檢查。

| 規則 | 為什麼 |
|---|---|
| 截圖一律走 `_capture_screenshot()`，**不得直接 `await page.screenshot()`** | 截圖是輔助資料，不該有讓整頁作廢的殺傷力 |
| 建目錄一律走 `_prepare_screenshot_dir()` | 磁碟寫滿／唯讀掛載時，`mkdir` 的例外會讓整次掃描在爬第一頁前就失敗 |
| 失敗記進 `warning_summary["screenshot_failures"]`，**不是 `failed_urls`** | 那一頁其實抓到也分析過了，記進 `failed_urls` 會讓報告誤報成「頁面擷取失敗」 |

截圖有保留期限：`manage.py cleanup_screenshots --older-than-days N`（預設 90，支援 `--dry-run`）。`media/scans/<掃描id>/page-N.png` 是全頁擷取、體積遠大於報告，**是 media volume 上真正無限成長的那一塊**；磁碟寫滿正是上述事故最可能的觸發原因。

---

## 報告防偽與快取（`ReportVerification`）

每次 `build_scan_report()` 完成時寫入一列 `ReportVerification`：報告編號、檔案內容 SHA-256、產生時間。

| 規則 | 為什麼 |
|---|---|
| **報告編號跨重新產生保持不變** | 由 `HMAC(SECRET_KEY, scan_id)` 推導，不含時間戳。報告一旦交付就可能被轉寄存檔，換編號會讓已流出的副本失效 |
| **報告本身只印編號、不印雜湊** | 雜湊要涵蓋整份檔案，檔案裡又要有雜湊＝循環相依。雜湊由查驗端點提供，收件者自行 `sha256sum` 比對 |
| **`views.py` 的 report action 必須用快取** | 重新產生會改變內容雜湊，讓已交付的副本在查驗頁對不上。必須「檔案存在 **且** 有防偽紀錄」才視為可重用——舊版留在磁碟上、沒有編號的報告要重產 |
| **`/api/verify/<編號>/` 是公開端點，絕不回傳掃描發起人** | 否則用報告編號就能反查使用者身分。回應只有：編號、目標網址、掃描與產生時間、整體分數、內容雜湊 |

報告檔案有保留期限：`manage.py cleanup_reports --older-than-days N`（預設 180，支援 `--dry-run`）。**只刪檔案、不刪 `ReportVerification`**——收件者手上的報告不會因為伺服器清檔就失效，編號必須繼續查得到。代價是清掉後若重新下載會產生新的一版、指紋隨之更新，所以保留期限要設得比「使用者還可能拿舊報告來對」的時間長。

附錄小節用 `_SectionNumber` 動態編號：名詞解釋、技術索引、頁面清單都會在沒資料時整段消失，寫死號碼會跳號。

入口頁截圖**刻意只放一張**：全頁截圖體積大，50 頁的掃描全塞進去會讓 `.docx` 失控，而 header / DNS / meta 這類發現本來就沒有視覺佐證價值。

與前次掃描比較**只比對同一位使用者的掃描**：同一個網址可能被不同人掃過，拿別人的當「前次」既不合理也會洩漏他人掃描的存在。

封面 logo 走「有就用、沒有就用字標」：偵測 `frontend/public/argus-logo.png`，存在才 `add_picture`。**刻意不引入 SVG 轉檔套件**（`cairosvg` 有系統函式庫相依，會拖累 CI 與 Docker build）。

前端查驗頁在 `frontend/src/features/public/PublicPages.jsx::VerifyReportPage`，路由 `/verify` 與 `/verify/:reportNumber`。

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

`settle_scan_actual` 在 `ScanJob` 已寫成 `completed` 之後才執行，因此它的例外
**不得往上拋**：拋出去會落到 `run_scan_job` 的通用 `except`，把已完成的掃描改成
`failed` 並執行**全額**退款（頁面與 findings 仍在 DB，狀態卻是失敗，退的也不是
差額）。結算失敗必須保留 `completed`，在 `warning_summary["settlement_error"]`
與 `scan_log` 留下記錄供後續補結算。

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
