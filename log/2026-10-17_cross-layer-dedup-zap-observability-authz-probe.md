# 掃描第二份報告審查後續：跨層去重、ZAP 主動觀測性、未授權存取確定性探測

**日期**：2026-10-17
**操作者**：Claude
**觸發**：使用者提供某授權掃描（scan 2）完整報告（Docker 完整堆疊實跑，驗證 ZAP 主動階段與 token 計帳修正生效），審查後依使用者選定做三項平台改進。

## 背景（審查結論）
scan 2 security 7 分如實反映真實風險（2 critical／3 high，agent 實打後端）。審查發現：
- **同一端點被兩層各報一次**：同一個 API 規格端點同時出現在確定性 `exposure-file-apidoc`（high）與 agent 觀察（high），計分扣兩次、報告列兩次。
- **ZAP 主動沒跑卻無痕跡**：覆蓋只見 `zap_passive`，判讀者分不清主動是旗標沒開、沒授權還是跑了沒發現（根因＝該次 Docker 沒設 `ARGUS_ZAP_ACTIVE_ENABLED`，非 bug，但缺觀測性）。
- agent 偶然打到某個未授權個資 API 靠運氣，沒有確定性檢查每次都抓。

## 變更內容

### 1. 跨層去重（`security/cross_layer.py`，新）
`consolidate_cross_layer(findings)`：確定性層已有同端點的「敏感檔案外洩」發現（`exposure-*`／`evidence_source=exposure_probe`／`impact_area=information_exposure`）時，丟掉 agent 層（`agent-observed-security-*`）指向同一端點那筆，回傳（保留清單, 被丟的 agent 發現）。
- 端點比對：exposure 存 `evidence_json.endpoint`、agent 存 `evidence_json.observed_endpoint`（同一正規化，小寫去結尾斜線）。**不比對弱點類型**——agent 標題含「未授權」會被歸 auth 類、與確定性 exposure 對不上，反而漏併；api-docs 這種「檔案可讀」端點兩層講的必然是同一件事，以端點比對即可。
- **只丟 agent**：確定性可重現、其 rule_id 可能涵蓋多端點（v2／v3 api-docs 共用 `exposure-file-apidoc`）刪 DB 列不精準；agent 雜湊 rule_id 對應單一端點，刪得乾淨。
- `tasks.stage_scoring` 計分前呼叫，並 `Finding.objects.filter(scan_job, rule_id__in=被丟的).delete()`，讓計分與報告一致。
- exposure_scanner／agent tools.py 各補一個端點欄位。

### 2. ZAP 主動觀測性（`tasks._zap_active_skip_reason`）
`stage_zap_active` 沒跑時不再靜默 return：勾資安但未授權／旗標關／ZAP 未部署時標 `zap_active=skipped` 並寫原因（授權不足／`ARGUS_ZAP_ACTIVE_ENABLED` 未開／ZAP 未部署）。未勾資安不標。

### 3. 未授權存取確定性探測（`security/authz_probe.py`，新）
把 agent 偶然打到的未授權個資 API 沉澱成確定性檢查。
- `probe_unauthorized_endpoints`：對 `_observed_api_paths` 的 API 端點做**無憑證 GET**（全新 context、無 cookie、`max_redirects=0`、active RPS、最多 20 個）。
- `analyze_unauthorized_results`（純函式，誤報防線是重點）：先要是成批記錄（頂層陣列或 data／result… 底下非空物件陣列），再滿足**任一**才報 `security-unauth-api-records`（A01／CWE-862，VERIFIED）——(1) 身分欄位（姓名／帳號／email／member…）**且**內部帳號欄位（memberId／roleId／啟用狀態／時間…）；(2) 敏感欄位名（password／token／secret／身分證／idcard／ssn）；(3) 回應夾帶強個資（身分證／信用卡）。有 PII／敏感欄位／強個資升 high，否則 medium。**email／手機屬弱個資不單獨成立**（公開聯絡清單也有，要配合條件 1 的內部欄位）——使用者指出「三者同時」對 credential／ID dump 太嚴，改成 OR，讓「純 token／身分證成批外洩」不帶一般身分欄位時也報；公開 JSON 清單、公開人員目錄、姓名＋email 清單、單筆、非 JSON、非 200 仍不報。
- 由 `tasks._run_authz_probe`（stage_exposure 內、同 exposure 閘：全站＋主動＋已授權）呼叫，覆蓋檢查 `authz_probe`，失敗不影響主掃描。
- owasp_mapper／finding_kind 登記新規則。
- **刻意不處理的**：「非個資但內部」的資料端點外洩，確定性難與正常公開 API 區分（agent 是靠「其他端點要驗證、這個漏了」的差異判斷），留給 agent，不硬做以免誤報。

## 影響範圍
- 不新增 model／migration／計費；不改計分公式（`SCORING_VERSION` 不變）；新增一條資安規則 `security-unauth-api-records`。
- authz 探測是既有 exposure 主動階段下的額外請求（最多 20 個端點、受 active RPS 限制），只在授權掃描跑。

## 驗證
- `ruff check backend` 通過。
- 新增測試：`tests_cross_layer.py`（6，含 agent 措辭含「未授權」仍併、不同端點不併、無端點保留、非 exposure 不併）、`tests_authz_probe.py`（9，重點在誤報防線：公開目錄／商品清單／單筆／非 JSON／非 200 都不報，PII 與 password 升 high）、`tests_zap_active.py` 加 4（skip 原因）。
- `apps.scans` ＋ `apps.agent` 全套 1507 通過（skipped 12）。
- **無法在本容器實機驗證**：沒有真實目標與 ZAP／worker 堆疊；authz 探測與 ZAP 觀測性要在正式環境對已授權目標重掃確認。

## 備註（安全）
程式、測試、文件一律用虛構網址（`site.example.test`）與虛構記錄；不含真實站名配路徑、內網 IP 或個資。使用者提供的 scan 2 報告含靶機未修補細節，不進任何會 push 的檔案。
