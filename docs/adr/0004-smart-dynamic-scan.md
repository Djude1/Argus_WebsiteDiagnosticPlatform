# 智慧動態掃描（Smart Dynamic Scan）

Argus 目前有**被動／主動兩種掃描模式**（各可選單頁或整站），都跑**固定管線**：不論對象是
WordPress 部落格、Laravel API、還是純靜態行銷頁，`tasks.py` 的 `SCAN_PIPELINE` 都依同一組階段
執行，模組的開關只由 `scan_plan.build_scan_execution_plan()` 依 `ScanJob` 欄位（`max_pages` 推出的
scope、`scan_mode`、`active_testing_authorized`、勾選的面向）決定。這是「固定 checklist 掃描器」
的做法：穩定、不漏檢，但**對每個網站都問一樣的問題**——該站特有的深度檢查（WordPress 的外掛
CVE、API 的授權缺陷、登入頁的 Session 安全）目前沒有對應模組可以啟用。

**命名參考與差異**：「Advanced Dynamic Scan」是 Tenable Nessus 的掃描範本名稱，它的「動態」是
**使用者自訂外掛篩選條件**、新外掛符合條件就自動納入
（[Tenable 文件](https://docs.tenable.com/nessus/Content/DynamicPlugins.htm)）。Argus 的智慧掃描
做法不同：**系統依網站指紋自動決定要加掃哪些模組**，使用者不需要懂掃描設定。
本 ADR 定義新的掃描策略「智慧動態掃描」（與被動／主動測試層級正交，見決策 §1）。第一版採 **Adaptive Deepening（適應式加深）**：
基礎掃描不減少，只根據網站特徵追加專屬深度檢查；因此賣點是「更貼合網站特性、檢查更深」，
**不是**「一定更快」或「只掃需要的東西」。流程為：

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
>
> **進度（2026-10-07）**：階段 1 已實作——`apps/scans/fingerprint.py`（`SiteFingerprint`、`build_fingerprint`）、
> `stage_fingerprint`（接在 `enter_scanning` 之後）、`ScanJob.fingerprint`（migration 0031）、準確率資料集
> `fingerprint_gold.py` 與 `manage.py fingerprint_benchmark`。階段 2、3 尚未開始，`scan_strategy` 欄位也還沒加。

---

## 決策

### 0. 兩條不可違反的原則（先定錨，其餘都服從這兩條）

1. **只加不減（Additive-only）。** 智慧動態掃描 = 「基礎全掃」+「依指紋追加的深度模組」。
   動態選擇**永遠只決定要不要『多掃』，不決定『少掃』**。理由：指紋一定會有判錯
   （WordPress 藏在 `/blog/`、API 沒有在首頁露出），若「判不到就不掃」，使用者會在
   不知情的狀況下被漏檢——這比固定模式更危險，等於把工具的可靠性賭在指紋準確度上。
   既有被動／主動標準掃描的行為完全不變；智慧策略是在它們之上疊加。

2. **延伸現有「預扣上限 + 實跑結算」，結算依據從頁數擴到模組。** 現行掃描計費**已經**是
   上限預扣＋實際結算：建立時 `hold_for_scan` 依 `max_pages × 維度數 × 單價`（＋UX 附加費）
   預扣，完成後 `settle_scan_actual` 依**實際頁數**重算並退差額；網頁優化也是同一套
   （`hold_for_rebuild` → `settle_rebuild_actual`）。動態掃描的差別只在「掃到一半才知道要不要
   加跑 API / CMS 模組」，所以預扣上限要涵蓋可能啟用的動態模組，結算時再依**實際執行的模組**
   重算。延伸現有機制，不發明新機制。

這兩條之外的所有設計，衝突時一律服從這兩條。

### 1. Strategy / Testing Level：先把語義拆開

「smart」與「active」不是同一個維度：
- **strategy** 回答「如何決定要掃哪些模組」：`standard | smart`
- **testing_level** 回答「允許多主動的測試」：`passive | active`

理想矩陣：

| strategy | testing_level | 行為 |
|---|---|---|
| standard | passive | 現有被動標準掃描 |
| standard | active | 現有授權主動掃描 |
| smart | passive | 基礎被動 + 高信心被動深查 |
| smart | active | 基礎主動 + 高信心動態深查 / DAST |

**資料模型**：既有 `scan_mode`（`passive`／`active`）就是 testing_level，**不改名、不加值**；新增
`ScanJob.scan_strategy`（CharField，`standard`／`smart`，預設 `standard`）存放策略。這只是新增一個
有預設值的欄位，既有掃描自動是 `standard`，向後相容、成本很低；**禁止**把 smart 塞進 `scan_mode`
當第三個值，ADR、planner、billing 與前端都依二維語義實作。未取得主動授權時，smart 只能執行 smart+passive
能力，不是「active 失敗後偷偷降級」。

- 新增 `ScanJob.fingerprint`（JSONField，預設 `{}`）：收斂後網站特徵快照。
- 新增 `ScanJob.dynamic_modules`（JSONField，預設 `{}`）：記錄額外啟用模組、理由、confidence、
  evidence、coverage 與實際計費項目。
- migration 一律新增，對既有掃描保持向後相容。

### 2. Signal Collection → Fingerprint Builder（避免 stage dependency 反轉）

原規劃把 fingerprint 放在 crawl 後，卻同時依賴 Katana / infra_scanner 的後續輸出，會形成
「前面的 stage 依賴後面的資料」。因此改成兩層：

1. **Pre-scan Signals（crawl 後即可取得）**
   - HTML / rendered DOM / headers / status / redirect
   - password form、upload input、401/`WWW-Authenticate`
   - crawler network listeners 發現的 JSON/REST/GraphQL endpoint
   - generator meta / basic tech signatures
2. **Fingerprint Enrichment（相關 scanner 完成後補強）**
   - Katana technology / endpoint evidence
   - infra scanner 的 CDN/WAF/reverse proxy
   - 其他已完成 stage 產生的非破壞性 signal

`fingerprint.py` 本身**不主動發 request**，只消費當下已存在的 signal；缺資料就標 `unknown`
或 `not_observed`，不能假設為 false。

```python
@dataclass(frozen=True)
class SiteFingerprint:
    cms: str | None
    frameworks: tuple[str, ...]
    server: str | None
    edge: str | None
    has_login: bool | None
    login_urls: tuple[str, ...]
    has_api: bool | None
    api_urls: tuple[str, ...]
    has_upload: bool | None
    auth_scheme: str | None
    confidence: dict[str, float]
    evidence: dict[str, tuple[str, ...]]
    completeness: dict[str, str]   # complete | partial | not_observed | unavailable
```

**Phase 1 只記錄 Pre-scan Fingerprint，不改任何掃描決策**。Enrichment 可以晚於部分 baseline scanner；
只有在要執行 Dynamic Planner 前，才以「目前可用 signal」重建/補強 fingerprint。

**觸發額外模組**：confidence 不影響 baseline，但會影響 extra scan。原則上
`confidence >= 0.8` 或至少兩個獨立 evidence；同時必須檢查對應 signal completeness。

### 3. 動態模組選擇層

Planner 分三步，不再假設 smart = active：

1. **Baseline plan**：依 `testing_level` 取得現有 passive 或 active 的基礎模組集。
2. **Fingerprint enrichment**：收斂目前已完成 stage 的 signal。
3. **Dynamic augment**：只有 `strategy=smart` 才依 fingerprint 把額外旗標 False → True。

| 指紋條件 | 額外模組 | testing_level 要求 |
|---|---|---|
| `has_login` 高信心 | `run_auth_session` | passive 可做唯讀檢查；主動互動需 active |
| `has_api` 高信心 | `run_api_security` | passive 唯讀；主動 probe 需 active |
| WordPress/Drupal/Joomla 高信心 | CMS 專項 | 被動列舉可 passive；額外 probe 需 active |
| `has_upload` | upload checks | active |
| login/api/upload 等 attack surface + 已授權 | `run_zap_dast` | active；Passive Analysis 可獨立啟用 |

非 smart strategy 永遠不進 Dynamic augment，既有 standard 行為不變。

### 4. 新增的深度模組（依 OWASP 既有知識，不重造輪子）

每個都遵守 `scans/CLAUDE.md` 既有鐵律：回傳 `list[dict]`（`make_finding` 格式）、不寫
`ScanJob.status`、不呼叫 billing、被動偵測的 severity 原則封頂 HIGH。單一模組例外不得中斷
整場掃描，但 orchestrator 必須記錄 `COMPLETED / FAILED / SKIPPED / BLOCKED / LIMITED`；
**不得把 scanner crash 或 WAF 阻擋等同於 0 findings。**

- **`stage_auth_session`（Auth / Session / Cookie 深查）**：登入頁的傳輸是否 HTTPS、
  表單是否有 CSRF token（現已有基礎版，這裡深化）、session cookie 的 Secure/HttpOnly/
  SameSite（`cookie_scanner` 已有，這裡對「登入後」cookie 重點標示）、密碼欄位 autocomplete、
  是否有帳號列舉跡象（登入錯誤訊息差異——**唯讀觀察，不做暴力嘗試**）。
- **`stage_api_security`（API 安全）**：對發現的 JSON 端點做**唯讀**檢查——CORS、錯誤訊息、
  Swagger/OpenAPI 暴露與未登入狀態可取得的資料。**「無認證即可回 200」本身不得直接判漏洞**：
  公開 API 預設只列 exposure / informational；僅在回傳資料呈現敏感性、端點語意明顯應受保護，
  或有可驗證授權繞過時，才提高 severity / confidence。可接 Nuclei `exposures/apis`、
  `misconfiguration` 與 OWASP API Top 10 可被動判定項。**不做**需要有效帳號或會改資料的測試。
- **`stage_cms_wordpress`（WordPress 專屬）**：`/wp-json/wp/v2/users`、版本 → CVE、
  外掛/佈景列舉、`xmlrpc.php`、`/wp-admin/` 等。**存在 ≠ 漏洞**：`/wp-admin/` 可達、
  XML-RPC 開啟、公開 REST API 預設只列 exposure / attack-surface；只有版本/CVE、錯誤配置或
  可驗證利用條件成立才升級為 vulnerability。規則思路參考 **WPScan**，但以離線被動為主。
- **`stage_cms_generic`（Drupal/Joomla）**：對應版本端點與已知敏感路徑。
- **`stage_zap_dast`（OWASP ZAP 深度 Web DAST）**：
  - **Passive Analysis**：只分析既有 HTTP messages，不新增目標流量。
  - **Traditional Spider / AJAX Spider = Discovery Traffic**：必須受 Authorized Scope 約束；預設 exact-origin，只有明確授權的 host 才可擴張。
  - Redirect 到 scope 外立即停止追蹤與內容分析；禁止自動提交會改變狀態的表單/按鈕（logout、delete、purchase、password reset、upload submit 等）。
  - Active Scan 只有在 `testing_level=active`、`active_testing_authorized=true` 且 target 在 Authorized Scope 時才能啟動。
  - Spider + Active + 自建 probe 共用 request budget / RPS / timeout，避免每個工具各自吃滿上限。
  - **取消驗收**：scan cancel 後必須停止 ZAP spider、active scanner、subprocess/container，並驗證不再新增網路請求；coverage 記錄 CANCELLED/PARTIAL。
  - ZAP alert 先轉 Shared Evidence，再由 Argus 形成 Finding；不直接照搬 ZAP risk/severity。
  - WAF / Rate Limit / Auth 阻擋 → `BLOCKED/LIMITED`，不得呈現「沒有漏洞」。
  - Authenticated Context 留待有明確測試帳號/session 的版本；未登入掃描不能宣稱已完成 authenticated testing。
  - **部署與資源**：ZAP 是 Java 服務，記憶體需求明顯高於現有 scanner，不得與 web／worker 跑在同一個 Pod。
    比照 Kali SQLmap 的做法，在獨立 namespace 以 K8s Job（或固定副本的 daemon）執行：設定 CPU／記憶體
    requests 與 limits、NetworkPolicy 只放行 Authorized Scope、映像檔以 digest 固定版本、功能旗標預設關閉。
    上線前實測單次掃描的 CPU 時間、記憶體峰值與請求數，作為 `business-model-plan.md` DAST 計費的依據。

### 5. 計費（實作原則 2 的具體化）

- 智慧模式建立時，`hold_for_scan` 改走**上限預扣**：以「基礎全掃 + 所有可能動態模組
  全開」的最壞成本預扣（讓餘額檢查不會事後爆）。
- 掃描結束的 `stage_settlement` 依 `dynamic_modules` 實際啟用的模組**重算**應收，退回差額，
  沿用 `settle_scan_actual` 的對稱退款路徑（就像 rebuild 的 `settle_rebuild_actual`）。
- 失敗／取消一律全額退款（現有 `_refund_or_raise` / `finish_*` 已處理，智慧模式沿用）。
- 計價參數進 settings（`ARGUS_COIN_SMART_*`），預設關閉模組不計費。
- **必須與 `business-model-plan.md` 共用同一份 Scan SKU / Billing Matrix**：Passive、Active、
  Smart 的基礎費、Agent 附加費與 Dynamic Module 實跑費不得各自演化成重複收費。
- 前端在啟動前顯示「最高預扣」與估價明細，完成後顯示實際費用與退回點數；Smart Scan 不應
  默認吃掉「首次免費 Standard Full Scan」額度，除非另設 Smart Trial。
- Billing Matrix 必須同時考慮 `strategy × testing_level × module × coverage/status`：
  未開始、因 scope 不允許而 SKIPPED、或取消前未實際執行的模組不得按「已執行」收費；
  BLOCKED/LIMITED 是否收費必須明確定義並可在帳單中對帳。

### 6. 前端與呈現

- 前端不要把 Smart 與 Passive/Active 做成互斥三選一；應呈現為「掃描策略：Standard / Smart」+
  「測試層級：Passive / Active」。若暫時沿用舊資料模型，UI 仍需把兩個概念說清楚。
- 掃描進度：`stage_fingerprint` 與各動態 stage 都進 `progress.steps`，前端現有的分階段
  進度條直接吃（需在 `SCAN_STEP_META` 補對照），讓使用者看到「正在依你的網站特性加掃 X」。
- 掃描詳情／報告新增一塊「Argus 為這個網站特別做了什麼」：列出 `dynamic_modules` 中
  `enabled` 的模組與觸發原因——**這是對外最大的差異化賣點的可視化**。
- 指紋信心低的判定在報告標示「推論」，呼應現有「網站優勢」的推論標示慣例。

### 7. 分階段落地（每階段可獨立上線、獨立驗證）

> 驗證一律：先寫可驗證的測試（`tests_*.py`）→ 跑 `uv run python backend/manage.py test apps.scans`
> 全綠 + `ruff` → 必要時 Docker 整合實掃。遵守 preflight 與行為準則第 6 條。

**階段 1 — Pre-scan fingerprint 只記錄、不改行為**（**已實作 2026-10-07**）
- 實作結果：資料集 23 個調整用案例（含 6 個容易誤判的案例）＋5 個保留集，涵蓋 WordPress、Drupal、Joomla、
  Shopify、Next.js、Nuxt、Angular、Gatsby、純靜態、API 為主的 SPA、登入站、上傳表單、Basic／Bearer 驗證、
  Cloudflare／CloudFront／Fastly／Vercel。成功條件（`fingerprint_benchmark.THRESHOLDS`，`tests_fingerprint.py` 鎖定）：
  整體 precision、recall ≥ 0.95，且判定期間連線嘗試數＝0（以 socket patch 計數並擋下）。首次量測 precision 1.0、
  recall 1.0、每站約 0.2 ms、0 次連線；登入／API／上傳三題回「沒看到（None）」的比例 0.82（只是觀察值）。
  另以 12 個真實網站首頁做初步檢查（只抓原始 HTML＋標頭，非完整爬取），CMS、框架、邊緣服務皆與公開資訊相符；
  真實網站的完整準確率評估（以實際掃描結果人工核對）留待階段 2 之前進行。
- 新增 signal/fingerprint builder，只吃 crawl 後已存在的訊號。
- 寫入 `ScanJob.fingerprint`，不接任何 dynamic decision。
- 驗證集至少包含 WordPress、Next.js、純靜態、API-heavy、登入站與 CDN/WAF 站。
- 成功條件開工前明定：各關鍵 fingerprint 的 precision/recall、unknown rate、單次耗時與 **零新增 request**。
- 此階段所有現有掃描行為與計費零變動。

**階段 2 — Enrichment + Dynamic Planner（internal beta）**
- 接入 Katana / infra 等後續 signal 做 fingerprint enrichment。
- 新增 `scan_strategy` 欄位（migration，預設 `standard`）。
- Planner 採 strategy/testing_level 二維語義；先 internal beta，不立刻對所有使用者開 smart。
- `dynamic_modules` 記錄 enabled/reason/confidence/evidence/coverage/billing item。
- 實作 auth/API/CMS 等低風險 extra module；ZAP 先不在本階段全開 Active。
- 計費走上限預扣 + 實跑結算，但必須先完成 Billing Matrix 測試。
- 驗證：錯誤 fingerprint 不可關閉 baseline；低信心不得觸發高成本/高流量模組；coverage 與退款對稱。

**階段 3 — 包裝為旗艦模式 + 前端差異化呈現**
- 前端新增「掃描策略：Standard／Smart」選項（與既有「測試層級：被動／主動」並列，**不做成三選一**）、
  進度步驟、報告「為你特別做了什麼」區塊。
- 競賽 Word 內容 md 同步（對外可見新功能）。
- 驗證：Playwright 端對端走完建立→進度→報告；lint/typecheck/test/build 全綠。

### 8. 值得接入的外部工具（對應各新模組）

| 模組 | 可接工具 / 資料源 | 性質 |
|---|---|---|
| 深度 Web Security / DAST | **OWASP ZAP**（Passive / Spider / AJAX Spider / Active） | P1；先受控接入，再於已授權 Smart/Deep Security Scan 啟用 Active |
| API 安全 | Nuclei `exposures/`・`misconfiguration/` 模板、OpenAPI/Swagger 自動發現 | 已有 Nuclei，只需擴模板集 |
| CMS WordPress | WPScan 規則思路（離線）、OSV.dev（外掛 CVE） | 離線比對，沿用現有 CVE 路線 |
| 漏洞優先序 | OSV.dev + EPSS 分數 | 免費 API，補在 CVE 類 finding |
| 無障礙（既有 UX） | axe-core（Playwright 注入） | 與本案平行，另案 |
| 效能基準（既有 SEO/UX） | Lighthouse / PageSpeed Insights（CrUX） | 與本案平行，另案 |

### 8.1 VAPT 方法論定位

VAPT 在 Argus 中不是一個 `stage_vapt`，而是串起現有與新增資安能力的上層 workflow：

```
Discovery
  ↓
Vulnerability Assessment
  ↓
Authorized Active Validation
  ↓
Evidence / Confidence
  ↓
Exploitability / Risk Prioritization
  ↓
Remediation
  ↓
Retest / Verification
```

現階段對外建議使用 **VAPT-oriented automated security assessment** 或
**Automated Vulnerability Assessment with authorized active testing**。在沒有人工 business-logic testing、
multi-step exploit chain、privilege escalation 與人工逐項驗證前，不宣稱 Argus 等同完整 Penetration Test。

### 9. 風險與緩解

| 風險 | 緩解 |
|---|---|
| 指紋判錯 → 漏掉整類檢查 | **原則 1 只加不減**：判不到頂多不加掃，基礎全掃仍覆蓋；低信心標「推論」 |
| 動態模組誤報升高（尤其 API/CMS） | 被動偵測 severity 封頂 HIGH、加 `confidence` 分級、結算與評分對低信心打折 |
| 成本不可預期嚇退使用者 | 預扣上限先講清楚、結算退差額、前端顯示「實際使用 N 點」 |
| 掃描時間變長且不固定 | 進度條表達「依網站特性加掃中」；無相依的新 stage 可並發 |
| 主動模組誤觸破壞性操作 | ZAP Spider/AJAX Spider 也視為新增探索流量；所有 discovery/active 流量共用 Authorized Scope、request budget、RPS/timeout，預設禁止狀態改變操作；取消後必須停止子程序與新請求 |
| API/CMS 模組把掃描帶出授權範圍 | 以 **Authorized Scope** 為邊界：預設同 origin；`api.example.com`／`auth.example.com` 等只有在使用者明確驗證/授權後才能納入，禁止因同 registrable domain 就自動擴張 |

---

## 不這麼做的替代方案（與為何不選）

- **讓使用者自己勾要掃哪些深度模組（＝Advanced Scan / 專家自訂）**：可做，但那是另一個模式
  （把選擇權丟回使用者）。智慧動態的價值正是「使用者不必懂，系統自己判斷」。兩者不衝突，
  專家自訂可作為後續第四模式，但不是本案目標。
- **把動態選擇做成「判不到就跳過」以省成本**：違反原則 1，等於用指紋準確度賭漏檢風險，
  否決。省成本靠「結算退差額」達成，不靠少掃。
- **指紋另發主動請求求準**：增加對目標的侵入與 SSRF 面，且與「被動指紋」定位衝突；
  需要主動確認的留給已授權的深度模組階段，不放在指紋層。
