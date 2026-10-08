# OWASP ZAP 被動分析（roadmap 第 8 項第一步）

**日期**：2026-10-07  
**操作者**：Claude

## 變更內容
- 範圍依使用者選擇：只做 Passive Analysis，用 HAR 匯入；ZAP 是獨立 daemon，功能預設關閉。
- `crawler.crawl_site(har_dir=...)`／`_make_context(har_path=...)`：
  - Playwright 每個 context 錄一個 HAR，只錄同 origin。
  - 沒傳 `har_dir` 時行為不變。
- 新增 `security/zap_passive.py`：
  - `build_har`：只留同 origin；去掉請求的 Cookie／Authorization；遮蔽 Set-Cookie 的值、保留屬性；只留文字內容，筆數與長度有上限。
  - `ZapClient`：`fileUpload` → `importHar` → 等 `recordsToScan` 歸零 → 讀 `alerts`。
  - 不論成功、失敗或取消都會清理：刪告警、刪網站節點、上傳的檔案覆寫成 `{}`。
  - 同 origin 以 cache 鎖（正式環境是 Redis）。
  - `alerts_to_findings`：
    - 與既有檢查重複的 14 條規則不列，只記印證筆數；11 條雜訊略過。
    - 每條規則合併成一筆；risk 換算成 Argus 嚴重度，信心 Low 降一級，False Positive 捨棄。
    - 常見規則有中文標題與修法；帶上 CWE。
- `tasks.stage_zap_passive`：接在 `deep_security` 之後。
  - 執行條件：勾資安且 `ARGUS_ZAP_ENABLED`；被動模式也可以跑。
  - 覆蓋檢查 `zap_passive`：completed／partial／failed／skipped。
  - HAR 在 stage 結束與 `run_scan_job` finally 都會刪除。
  - 進度步驟加 `zap_passive`，前端 `SCAN_STEP_META` 同步。
- 設定：`ARGUS_ZAP_ENABLED`、`ARGUS_ZAP_API_URL`、`ARGUS_ZAP_API_KEY`、`ARGUS_ZAP_TIMEOUT_SECONDS`、`ARGUS_ZAP_MAX_ENTRIES`、`ARGUS_ZAP_MAX_BODY_CHARS`。
- 報告：ZAP 問題的來源標「外部工具（OWASP ZAP 被動分析…未另行驗證）」；`RENDERER_VERSION` 11 → 12。
- 部署（預設都不啟動）：
  - `docker-compose.yml`：新增 profile `zap` 的服務。
    - 只接 `zap_internal`（internal 網路，沒有對外連線），worker 加入 `zap_internal`。
    - 金鑰取自 `.env`，空值時容器拒絕啟動。
  - `k8s/optional/zap-passive.yaml`，未列入 kustomization：
    - 獨立 namespace，套用 PSA restricted。
    - 映像以 digest 固定版本：`ghcr.io/zaproxy/zaproxy:2.16.1@sha256:7840969c…`。
    - Pod 非 root、drop ALL、有資源上限、工作目錄用 emptyDir。
    - NetworkPolicy 只收 worker 的 8090 連線，egress 全擋。
- 文件：
  - 新增 `docs/zap-passive.md`：流程、啟用、回滾、驗證紀錄。
  - scans、security、frontend CLAUDE.md。
  - roadmap 第 8 項與 §7、business-model-plan 深度資安列。
  - k8s/README 檔案表、需求書 F-014、`.env.example`。

## 原因
roadmap §7：ZAP 補足 Argus 自建規則沒有的 Web 被動檢查。依 roadmap 先做 Passive Analysis，對目標零新增請求。告警須先由 Argus 正規化，不照搬 ZAP 的風險等級；與既有檢查重複的不再列一次。

## 影響範圍
- 預設關閉：沒設 `ARGUS_ZAP_ENABLED` 時不錄 HAR、不呼叫 ZAP，掃描行為與計費不變。
- 啟用後：
  - 勾資安的掃描在爬取時會多錄 HAR，暫存在 worker 的暫存目錄、用完即刪。
  - 資安維度可能多出 ZAP 規則的問題，分數可能因此變動。
  - `RULESET_VERSION` 沒有改，因為功能預設關閉；正式啟用 ZAP 時應一併更新，讓前後分數不被直接比較。
- 報告版本號 +1，下次下載會重新產生。
- 尚未做：
  - 正式叢集部署與 CPU／記憶體／耗時量測（計費依量測結果決定，目前不另收費）。
  - Spider／AJAX Spider、Active Scan。
  - 告警進 Shared Evidence Store。

## 驗證方式
- 在沙盒以 Java 跑 ZAP 2.16.1 cross-platform daemon（`-config api.filexfer=true`）實測 API。
  - 發現 `fileUpload` 需要開啟 `api.filexfer`。
  - 發現 `deleteAlerts` 以 baseurl 呼叫會回 internal_error，改成逐筆 `deleteAlert`；網站節點用 `deleteSiteNode`（不帶結尾斜線）。
- 端到端：本機 Chromium 爬兩頁測試網站並錄 HAR。
  - 錄到 4 筆同網站流量，含 JS 發出的 `/api/items`。
  - session 值沒有出現在送給 ZAP 的內容中。
  - ZAP 產生 30 則告警，轉成 3 項 Argus 問題，其餘是重複或雜訊。
- 實機抓到的錯誤：ZAP 告警只有文字 `risk`，沒有數字代碼，原本全部變成「資訊」。已改讀 `risk`，單元測試資料改成真實 ZAP 欄位，真實 ZAP 測試加上嚴重度斷言。
- 新測試：
  - `tests_zap_passive.py` 19 項，含 1 項連真實 ZAP，以 `ARGUS_TEST_ZAP_URL`／`ARGUS_TEST_ZAP_KEY` 啟用。
  - root `tests/test_zap_optional_contract.py` 6 項，鎖預設不部署、digest、無 egress、restricted、compose profile。
- 全套 `uv run python backend/manage.py test apps`：1609 項 OK（1 skipped），連真實 ZAP 與 Chromium 跑。
- `ruff check backend`（exit 0）、`makemigrations --check`：通過。
- 前端 lint／typecheck／225 項測試／vite build：通過。
- root `tests/` 中 `test_kali_k8s_contract` 需要 kubectl，沙盒沒有安裝而無法執行，與本次無關。
