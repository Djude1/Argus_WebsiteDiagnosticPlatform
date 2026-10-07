# 智慧動態掃描（Smart Dynamic Scan）

Argus 目前三種掃描都跑**固定管線**：不論對象是 WordPress 部落格、Laravel API、還是純靜態
行銷頁，`tasks.py` 的 `SCAN_PIPELINE` 都依同一組階段執行，模組的開關只由
`scan_plan.build_scan_execution_plan()` 依三個 `ScanJob` 欄位（`max_pages` 推出的 scope、
`scan_mode`、`active_testing_authorized`）決定。這是「固定 checklist 掃描器」的做法：
穩定、不漏檢，但**對每個網站都問一樣的問題**，既掃了用不到的項目（純靜態站仍跑 Auth/API
相關邏輯的空轉），也漏了該站特有的深度檢查（WordPress 的外掛 CVE、API 的授權缺陷、
登入頁的 Session 安全）。

商用掃描器（如 Acunetix 的 Advanced Dynamic Scan）的差異化在於**先認識網站、再決定怎麼掃**。
本 ADR 定義 Argus 的第三種掃描模式「智慧動態掃描」，流程為：

```
指紋辨識 Fingerprint
  ↓
風險面發現 Risk Surface Discovery（登入頁？API？CMS？上傳點？）
  ↓
動態模組選擇 Dynamic Module Selection（依指紋「加掃」專屬模組）
  ↓
深度掃描 Deep Scan
```

> 這份文件是**實作計劃**，撰寫時尚未改動任何掃描程式。所有「現況」敘述都對照
> 2026-10-07 的 `backend/apps/scans/`。落地時每個階段完成都要回來更新本檔與
> `backend/apps/scans/CLAUDE.md`。

---

## 決策

### 0. 兩條不可違反的原則（先定錨，其餘都服從這兩條）

1. **只加不減（Additive-only）。** 智慧動態掃描 = 「基礎全掃」+「依指紋追加的深度模組」。
   動態選擇**永遠只決定要不要『多掃』，不決定『少掃』**。理由：指紋一定會有判錯
   （WordPress 藏在 `/blog/`、API 沒有在首頁露出），若「判不到就不掃」，使用者會在
   不知情的狀況下被漏檢——這比固定模式更危險，等於把工具的可靠性賭在指紋準確度上。
   固定三模式的行為完全不變；智慧模式是在它們之上疊加。

2. **成本事前不可全知，就改「預扣上限 + 實跑結算」。** 動態掃描的本質是「掃到一半才
   知道要不要加跑 API / CMS 模組」，與現行 `hold_for_scan`（掃描前依
   `max_pages × 維度數 × 單價` 精算預扣）相衝突。智慧模式必須改用
   「**預扣一個上限、依實際啟用的模組結算、退回差額**」——這套 Argus 已經在
   網頁優化（rebuild）用過（`hold_for_rebuild` → `settle_rebuild_actual`），複用其模式，
   不發明新機制。

這兩條之外的所有設計，衝突時一律服從這兩條。

### 1. 資料模型

不新增掃描模式以外的頂層概念，盡量複用現有欄位。

- **`ScanJob.scan_mode` 增加第三值 `smart`**（現有 `passive` / `active`）。
  `smart` 在授權層面等同 `active`（會跑主動探測），但模組集改由動態決策層決定。
  沿用現有網域驗證閘門：`smart` 同樣要求主動測試授權（`active_testing_authorized`）才會
  執行任何主動模組；未授權時退化為「智慧被動」（只加被動類深度模組）。

- **新增 `ScanJob.fingerprint`（JSONField，預設 `{}`）**：收斂後的網站特徵快照，由新的
  指紋階段寫入。結構見第 2 節 `SiteFingerprint`。空 dict = 舊掃描或非智慧模式。

- **新增 `ScanJob.dynamic_modules`（JSONField，預設 `{}`）**：記錄「這次因為指紋判定，
  額外啟用了哪些模組、各自的觸發原因」，供報告呈現與計費結算對帳。結構：
  ```json
  {
    "auth_session":  {"enabled": true,  "reason": "偵測到登入表單 /wp-login.php"},
    "api_security":  {"enabled": true,  "reason": "偵測到 /api/ 下的 JSON 端點 7 個"},
    "cms_wordpress": {"enabled": false, "reason": "未偵測到 CMS"}
  }
  ```

- **migration 一律新增**（遵守 Migration 鐵律），兩個欄位都可空、對既有掃描無影響。

### 2. 指紋收斂層 `SiteFingerprint`（本案的核心新零件）

現況：`tech_stack.identify_tech_stack()`、`katana_scanner._extract_technologies()`、
`security/infra_scanner`（CDN/WAF/反代）都已經在產生技術訊號，但**結果只流向報告的
「網站架構」分頁，沒有任何東西把它回饋成「要掃什麼」的決策**。

本案新增 `backend/apps/scans/fingerprint.py`，把分散的訊號收斂成一個**決策導向**的結構
（與「給人看的技術棧」分開：技術棧是展示，指紋是決策輸入）：

```python
@dataclass(frozen=True)
class SiteFingerprint:
    cms: str | None                 # "wordpress" | "drupal" | "joomla" | None
    frameworks: tuple[str, ...]     # ("laravel", "nextjs", ...)
    server: str | None              # "nginx" | "apache" | ...
    edge: str | None                # "cloudflare" | "fastly" | None（來自 infra_scanner）
    has_login: bool                 # 偵測到登入表單 / 已知登入路徑
    login_urls: tuple[str, ...]
    has_api: bool                   # 偵測到 JSON/REST/GraphQL 端點
    api_urls: tuple[str, ...]
    has_upload: bool                # 偵測到檔案上傳欄位
    auth_scheme: str | None         # "cookie-session" | "jwt" | "basic" | None
    confidence: dict[str, float]    # 每項判定的信心（供報告標示、不影響「只加不減」）
```

資料來源（全部是**被動**訊號，不為指紋另發破壞性請求）：
- `cms` / `frameworks` / `server`：`tech_stack.py` 既有簽名 + generator meta。
- `edge`：`infra_scanner` 既有結果。
- `has_login` / `login_urls`：掃描已爬頁面的 `<form>` 含 password 欄位，或命中已知登入路徑
  （`/wp-login.php`、`/login`、`/admin`、`/user/login`…），或 401/`WWW-Authenticate` 標頭。
- `has_api` / `api_urls`：爬蟲 `_attach_page_listeners` 已收集的 `api_endpoints`（回應
  `content-type: application/json`）、`/api/`・`/graphql`・`/wp-json/` 路徑、
  Katana 抽出的端點。
- `has_upload`：頁面 `<input type="file">`。
- `auth_scheme`：Set-Cookie 的 session cookie 樣式、`Authorization: Bearer`、Basic。

**放在哪個階段**：新增 `stage_fingerprint`，排在 `stage_crawl`（頁面已抓好）之後、
所有分析／主動模組之前。它**不發新請求、不花錢、不可失敗中斷**（例外一律吞掉回空指紋，
退化為「當作什麼都沒偵測到」→ 依原則 1，只少加模組、不影響基礎全掃）。

### 3. 動態模組選擇層

`scan_plan.py` 現在是「單次、純靠 `ScanJob` 欄位」的計畫。改成**兩段式**：

1. **基礎計畫（維持現狀）**：`build_scan_execution_plan(scan_job)` 不動，智慧模式先得到
   與 active 模式相同的基礎模組集（Nuclei / Katana / exposure / agent…）。這保證
   「基礎全掃」底線。
2. **動態加掛**：新增 `augment_plan_with_fingerprint(plan, fingerprint) -> ScanExecutionPlan`，
   依指紋把下列**新**旗標打開（只會從 False → True，呼應原則 1）：

   | 指紋條件 | 追加模組旗標 | 對應新 stage |
   |---|---|---|
   | `has_login` | `run_auth_session` | `stage_auth_session` |
   | `has_api` | `run_api_security` | `stage_api_security` |
   | `cms == "wordpress"` | `run_cms_wordpress` | `stage_cms_wordpress` |
   | `cms in {drupal, joomla}` | `run_cms_generic` | `stage_cms_generic` |
   | `has_upload`（且已授權主動） | `run_upload_checks` | 併入 `stage_auth_session` 或獨立 |

   `ScanExecutionPlan` 增加這幾個 `run_*` 欄位，預設全 False；只有 `smart` 模式會進
   augment。非智慧模式永遠拿不到這些旗標 → 行為零變動。

### 4. 新增的深度模組（依 OWASP 既有知識，不重造輪子）

每個都遵守 `scans/CLAUDE.md` 既有鐵律：回傳 `list[dict]`（`make_finding` 格式）、不寫
`ScanJob.status`、不呼叫 billing、例外 silent-fail 回 `[]`、被動偵測的 severity 封頂 HIGH。

- **`stage_auth_session`（Auth / Session / Cookie 深查）**：登入頁的傳輸是否 HTTPS、
  表單是否有 CSRF token（現已有基礎版，這裡深化）、session cookie 的 Secure/HttpOnly/
  SameSite（`cookie_scanner` 已有，這裡對「登入後」cookie 重點標示）、密碼欄位 autocomplete、
  是否有帳號列舉跡象（登入錯誤訊息差異——**唯讀觀察，不做暴力嘗試**）。
- **`stage_api_security`（API 安全）**：對發現的 JSON 端點做**唯讀**檢查——是否無認證即回
  資料、CORS 是否 `*` + 憑證、錯誤訊息是否洩漏堆疊、是否有 Swagger/OpenAPI 文件暴露
  （`/swagger.json`、`/openapi.json`、`/api-docs`）。可接 **Nuclei 的 `exposures/apis`
  模板集**與 **OWASP API Top 10** 的可被動判定項。**不做**需要有效帳號或會改資料的測試。
- **`stage_cms_wordpress`（WordPress 專屬）**：`/wp-json/wp/v2/users`（使用者列舉）、
  版本偵測 → 對照 CVE（沿用現有 `nvd_db` / 擬接 OSV）、外掛/佈景列舉（被動從 HTML 的
  `/wp-content/plugins/<name>/` 路徑）、`xmlrpc.php` 開放、`/wp-admin/` 可達性。
  規則思路參考 **WPScan**，但以離線被動為主。
- **`stage_cms_generic`（Drupal/Joomla）**：對應版本端點與已知敏感路徑。

### 5. 計費（實作原則 2 的具體化）

- 智慧模式建立時，`hold_for_scan` 改走**上限預扣**：以「基礎全掃 + 所有可能動態模組
  全開」的最壞成本預扣（讓餘額檢查不會事後爆）。
- 掃描結束的 `stage_settlement` 依 `dynamic_modules` 實際啟用的模組**重算**應收，退回差額，
  沿用 `settle_scan_actual` 的對稱退款路徑（就像 rebuild 的 `settle_rebuild_actual`）。
- 失敗／取消一律全額退款（現有 `_refund_or_raise` / `finish_*` 已處理，智慧模式沿用）。
- 計價參數進 settings（`ARGUS_COIN_SMART_*`），預設關閉模組不計費。

### 6. 前端與呈現

- 掃描建立表單新增第三個模式「智慧動態掃描（建議）」，說明「Argus 會先辨識你的網站，
  再決定要加做哪些深度檢查」。沿用現有被動/主動的 UI 結構。
- 掃描進度：`stage_fingerprint` 與各動態 stage 都進 `progress.steps`，前端現有的分階段
  進度條直接吃（需在 `SCAN_STEP_META` 補對照），讓使用者看到「正在依你的網站特性加掃 X」。
- 掃描詳情／報告新增一塊「Argus 為這個網站特別做了什麼」：列出 `dynamic_modules` 中
  `enabled` 的模組與觸發原因——**這是對外最大的差異化賣點的可視化**。
- 指紋信心低的判定在報告標示「推論」，呼應現有「網站優勢」的推論標示慣例。

### 7. 分階段落地（每階段可獨立上線、獨立驗證）

> 驗證一律：先寫可驗證的測試（`tests_*.py`）→ 跑 `uv run python backend/manage.py test apps.scans`
> 全綠 + `ruff` → 必要時 Docker 整合實掃。遵守 preflight 與行為準則第 6 條。

**階段 1 — 指紋只記錄、不改行為（風險最低，先驗準確度）**
- 新增 `fingerprint.py` 的 `SiteFingerprint` 與 `build_fingerprint(ctx)`。
- 新增 `stage_fingerprint`，寫入 `ScanJob.fingerprint`，**不接任何決策**。
- migration 新增 `fingerprint` 欄位。
- 驗證：對示範專案與數個真實站（WordPress、Next.js、純靜態、有 API 的站）實掃，
  人工核對指紋判定對不對；單元測試覆蓋各訊號來源。**此階段所有現有掃描行為零變動。**
- 成功條件：指紋對主流 CMS/框架/登入頁/API 的判定準確率可接受（先定義「可接受」門檻）。

**階段 2 — 動態「加掃」+ 計費改上限結算**
- `ScanExecutionPlan` 加 `run_*` 旗標；`augment_plan_with_fingerprint`；`ScanJob.scan_mode`
  加 `smart`；`dynamic_modules` 欄位 + migration。
- 實作 `stage_auth_session`、`stage_api_security`、`stage_cms_wordpress`、`stage_cms_generic`。
- 計費改上限預扣 + 結算退差額。
- 驗證：單元測試每個新 stage（給定指紋 → 正確啟用/不啟用、finding 格式正確）；
  計費對稱性測試（全開 vs 部分開 vs 全不開的結算金額）；端對端實掃對 WordPress 站確認
  CMS 模組真的多跑了、對純靜態站確認沒多跑也沒多收。

**階段 3 — 包裝為旗艦模式 + 前端差異化呈現**
- 前端第三模式、進度步驟、報告「為你特別做了什麼」區塊。
- 競賽 Word 內容 md 同步（對外可見新功能）。
- 驗證：Playwright 端對端走完建立→進度→報告；lint/typecheck/test/build 全綠。

### 8. 值得接入的外部工具（對應各新模組）

| 模組 | 可接工具 / 資料源 | 性質 |
|---|---|---|
| API 安全 | Nuclei `exposures/`・`misconfiguration/` 模板、OpenAPI/Swagger 自動發現 | 已有 Nuclei，只需擴模板集 |
| CMS WordPress | WPScan 規則思路（離線）、OSV.dev（外掛 CVE） | 離線比對，沿用現有 CVE 路線 |
| 漏洞優先序 | OSV.dev + EPSS 分數 | 免費 API，補在 CVE 類 finding |
| 無障礙（既有 UX） | axe-core（Playwright 注入） | 與本案平行，另案 |
| 效能基準（既有 SEO/UX） | Lighthouse / PageSpeed Insights（CrUX） | 與本案平行，另案 |

### 9. 風險與緩解

| 風險 | 緩解 |
|---|---|
| 指紋判錯 → 漏掉整類檢查 | **原則 1 只加不減**：判不到頂多不加掃，基礎全掃仍覆蓋；低信心標「推論」 |
| 動態模組誤報升高（尤其 API/CMS） | 被動偵測 severity 封頂 HIGH、加 `confidence` 分級、結算與評分對低信心打折 |
| 成本不可預期嚇退使用者 | 預扣上限先講清楚、結算退差額、前端顯示「實際使用 N 點」 |
| 掃描時間變長且不固定 | 進度條表達「依網站特性加掃中」；無相依的新 stage 可並發 |
| 主動模組誤觸破壞性操作 | 新模組一律**唯讀**；沿用網域驗證 + 授權閘門；不做暴力/寫入測試 |
| API/CMS 模組把掃描帶出授權範圍 | 所有探測目標必須同 origin（沿用 `_enforce_public_request` 與現有邊界） |

---

## 不這麼做的替代方案（與為何不選）

- **讓使用者自己勾要掃哪些深度模組（＝Advanced Scan / 專家自訂）**：可做，但那是另一個模式
  （把選擇權丟回使用者）。智慧動態的價值正是「使用者不必懂，系統自己判斷」。兩者不衝突，
  專家自訂可作為後續第四模式，但不是本案目標。
- **把動態選擇做成「判不到就跳過」以省成本**：違反原則 1，等於用指紋準確度賭漏檢風險，
  否決。省成本靠「結算退差額」達成，不靠少掃。
- **指紋另發主動請求求準**：增加對目標的侵入與 SSRF 面，且與「被動指紋」定位衝突；
  需要主動確認的留給已授權的深度模組階段，不放在指紋層。
