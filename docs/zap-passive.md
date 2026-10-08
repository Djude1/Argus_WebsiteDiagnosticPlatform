# OWASP ZAP 被動分析（啟用與回滾）

Argus 把爬蟲已經取得的同網站流量（HAR）交給獨立的 OWASP ZAP daemon，只跑 ZAP 的**被動規則**，
補上 Argus 自建規則沒有的檢查（混合內容、引用外站腳本、原始碼註解、除錯訊息、內部 IP、網址含敏感資訊等）。
**ZAP 不會對目標網站發出任何請求**；Spider、AJAX Spider 與 Active Scan 不在這個階段的範圍（roadmap §7）。

程式：`backend/apps/scans/security/zap_passive.py`、`tasks.stage_zap_passive`、`crawler.crawl_site(har_dir=...)`。

## 流程

1. 勾資安且 `ARGUS_ZAP_ENABLED` 時，爬蟲每個瀏覽器 context 錄一個 HAR（只錄同 origin，暫存在 worker 的系統暫存目錄）。
2. `deep_security` 之後，`stage_zap_passive` 整理 HAR：
   - 去掉請求的 Cookie／Authorization。
   - 遮蔽 Set-Cookie 的值，屬性保留。
   - 只留文字類回應內容，每筆最多 `ARGUS_ZAP_MAX_BODY_CHARS`，總共最多 `ARGUS_ZAP_MAX_ENTRIES` 筆。
3. 呼叫 ZAP API：
   1. `core/other/fileUpload` 上傳 HAR。
   2. `exim/action/importHar` 匯入。
   3. 等 `pscan/view/recordsToScan` 歸零，上限 `ARGUS_ZAP_TIMEOUT_SECONDS`；逾時記為 partial。
   4. `alert/view/alerts?baseurl=<origin>` 讀告警。
4. 不論成功、失敗或取消，都會做下列清理：
   - 刪掉這個 origin 的告警與網站節點。
   - 把 ZAP 上的 HAR 檔覆寫成 `{}`。
   - 刪掉 worker 的 HAR 暫存目錄。
5. 告警轉成 Argus 問題（`rule_id=zap-<pluginId>`），每條規則合併成一筆，處理方式如下：
   - **與 Argus 既有檢查重複**的規則（CSP、HSTS、X-Frame-Options、nosniff、Cookie HttpOnly／Secure、Server／X-Powered-By 版本、CSRF、CORS、JS 函式庫漏洞、SRI、個資）不另外列出，只在掃描紀錄寫「印證」筆數。
   - 純資訊類雜訊（Modern Web Application、可快取內容、時間戳記…）略過。
   - 嚴重度依 ZAP 的 risk 換算：High→高、Medium→中、Low→低、Informational→資訊。ZAP 信心為 Low 時再降一級，標為 False Positive 的捨棄。
6. 覆蓋檢查 `zap_passive`（資安維度）的狀態：
   - completed：完成。
   - partial：ZAP 規則逾時沒跑完。
   - failed：ZAP 無法連線或 API 錯誤，掃描照常完成。
   - skipped：同網站的另一次掃描正在用 ZAP（以 Redis cache 的 `argus-zap:<origin>` 鎖），或沒有錄到流量。

## 啟用：Docker Compose

```bash
# .env（金鑰自行產生，例如 openssl rand -hex 24；不得 commit）
ARGUS_ZAP_ENABLED=true
ARGUS_ZAP_API_URL=http://zap:8090
ARGUS_ZAP_API_KEY=<隨機字串>

docker compose --profile zap up -d zap
docker compose up -d worker   # 重啟 worker 讀新設定
```

`zap` 只接在 `zap_internal`（`internal: true`，沒有對外連線），worker 同時接 `default` 與 `zap_internal`。

## 啟用：Kubernetes

`k8s/optional/zap-passive.yaml` **沒有列在 `k8s/kustomization.yaml`**，Argo CD 不會自動部署。內容：

- `argus-zap` namespace，套用 PSA restricted。
- ZAP Deployment：映像以 digest 固定版本、非 root、資源上限 2Gi、工作目錄用 emptyDir。
- Service。
- NetworkPolicy：只收 `argus` namespace `app: worker` 的 8090 連線，egress 全擋。

1. 建 Secret：`kubectl -n argus-zap create secret generic zap-api --from-literal=api-key=<隨機字串>`
2. 同一個值放進 `argus` namespace worker 讀的 Secret（`ARGUS_ZAP_API_KEY`）。
3. `kubectl apply -f k8s/optional/zap-passive.yaml`，等 Pod Ready。
4. worker 設定 `ARGUS_ZAP_ENABLED=true`、`ARGUS_ZAP_API_URL=http://zap.argus-zap.svc.cluster.local:8090`，rollout worker。
5. 驗證：對已授權的測試網站跑一次勾資安的掃描，掃描紀錄要出現「ZAP 2.16.1 被動分析：N 筆流量…」，
   覆蓋紀錄 `zap_passive=completed`；ZAP 上 `alert/view/numberOfAlerts?baseurl=<origin>` 回 0（已清理）。

## 回滾

worker 設回 `ARGUS_ZAP_ENABLED=false` 並重啟：爬蟲不再錄 HAR、不呼叫 ZAP，掃描行為回到原本。
之後可刪除 ZAP 資源（`kubectl delete -f k8s/optional/zap-passive.yaml`／`docker compose --profile zap down`）。

## 驗證紀錄（2026-10-07）

- 本機 ZAP 2.16.1 daemon（cross-platform 版，`-config api.filexfer=true`）：
  - `tests_zap_passive.RealZapTests` 跑通上傳、匯入、規則、讀告警與清理，結束後 ZAP 上這個網站的告警與訊息都是 0。
- 端到端：本機 Chromium 爬兩頁的測試網站並錄 HAR。
  - 錄到 4 筆同網站流量（含 JS 發出的 `/api/items`），session 值沒有出現在送給 ZAP 的內容裡。
  - ZAP 產生 30 則告警：3 項轉成 Argus 問題，其餘是重複或雜訊。
- 這次也抓到一個只有實機會出現的錯誤：ZAP 告警沒有數字風險代碼，只有文字 `risk`。原本照代碼換算，全部變成「資訊」，已修正，並把真實 ZAP 的嚴重度斷言加進測試。
- 尚未在正式叢集部署與量測 CPU／記憶體／耗時；計費維持不另收費（不新增對目標的請求），量測後再依 `business-model-plan.md` 決定。

## 測試

- `uv run python backend/manage.py test apps.scans.tests_zap_passive`（不需要 ZAP）
- 連真實 ZAP：`ARGUS_TEST_ZAP_URL=http://127.0.0.1:8090 ARGUS_TEST_ZAP_KEY=<key>` 再跑同一組
- 部署契約：`uv run python -m unittest tests.test_zap_optional_contract`
