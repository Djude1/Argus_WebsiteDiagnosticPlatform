# 未授權探測：多前綴探測＋內部基礎設施訊號也成立

**日期**：2026-10-20
**操作者**：Claude

## 變更內容
- `security/exposure_scanner.py` `extract_openapi_operations(results, extra_prefixes=None)`：每條規格相對路徑（`basePath`＋`paths` 鍵）會在「規格所在前綴」與 `extra_prefixes`（觀察到的 API 前綴）底下各組一次、去重，保留 `MAX_OPENAPI_OPERATIONS` 上限。
- `tasks.stage_exposure`：呼叫 `extract_openapi_operations` 時傳 `extra_prefixes=api_prefixes(_observed_api_paths(ctx))`。
- `security/authz_probe.py`：
  - 新增 `_INTERNAL_PATH_RE`（內部檔案路徑：`/file/protected/`、伺服器檔案系統絕對路徑、`file://`、磁碟代號）與 `_internal_infra(body)`（回私有 IP 清單＋是否含內部路徑），`import private_ips`。
  - `analyze_unauthorized_results`：成批記錄的回應若含私有／內部 IP 或內部檔案路徑，即使不是帳號名單也成立（存取控制缺失）、升 high，描述與證據另附內網 IP／內部路徑。
- 測試：`tests_authz_probe.py`（內部路徑／私有 IP 成立、公開清單公開圖片網址不成立）、`tests_exposure_scanner.py`（多前綴展開、無 extra 維持單一）。

## 原因
1D47 報告獨立審查發現兩個確定性漏報：(1) AI 找到 `/backend/members/all` 等匿名可讀個資，但確定性 authz 探測回 0——規格掛在 `/api_proxy`、未授權實際暴露在 `/backend`，只探規格所在前綴會漏；(2) industry／campus 端點匿名回傳完整課程／校園資料含內網 IP 與內部檔案路徑，但不是帳號名單、原本門檻（身分＋內部帳號欄位）不收，只有 AI 抓得到、又被排除在分數外。使用者要求兩件都補成確定性。

## 影響範圍
- 只在「全站＋主動＋已驗證」授權掃描執行（沿用既有閘門）。
- 多前綴展開增加探測候選數，仍受 `ARGUS_AUTHZ_PROBE_MAX_ENDPOINTS` 與 active RPS 限制。
- 新成立條件沿用 `security-unauth-api-records`（A01／CWE-862），不新增 rule_id／owasp 對映；finding_kind 不變。
- 誤報防線：仍要求「成批記錄」，且內部路徑只認受保護資源／伺服器絕對路徑／`file://`／磁碟代號，公開圖片網址（`/images/x.png`、`https://…`）不命中。
- 殘留限制：從未在流量／JS／規格任一處出現過的前綴仍探不到（已於文件註明）。

## 驗證方式
- `uv run ruff check`（authz_probe、exposure_scanner、tasks、tests）：All checks passed。
- `uv run python backend/manage.py check`：no issues。
- `manage.py test apps.scans.tests_authz_probe apps.scans.tests_exposure_scanner apps.scans.tests_pipeline_stages`：90 pass。
- 未自動驗證：正式站重掃後 members／industry／campus 是否由確定性層抓到並進資安分數——需部署後實機確認。
