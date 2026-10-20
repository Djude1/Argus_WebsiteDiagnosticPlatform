# scans/security 子模組規則

Claude Code 進 `backend/apps/scans/security/` 工作時，本檔在 `scans/CLAUDE.md` 之後自動載入；**ZCode／Codex 不會自動載入本檔**，動手前必須先讀（見根 `AGENTS.md` 模組規則必讀閘門）。

---

## 職責定義

此 sub-package 負責**深度主動式資安檢查**，與 `scanners.py` 的被動式基本檢查嚴格分離。

| 位置 | 負責什麼 | 不負責什麼 |
|---|---|---|
| `scanners.py` → `analyze_security()` | HTTPS 判斷、安全 header 存在性、CSRF token 偵測（被動、已有的） | 任何深度分析 |
| `scanners.py` → `analyze_data_exposure()` | PII 偵測（被動、已有的） | 主動掃描 |
| **此 sub-package（security/）** | SSL/TLS 深度、Cookie 旗標、CORS/CSP 品質、OWASP 對映、Kali 呼叫 | 修改 ScanJob.status、呼叫 billing |

**規則：** 凡是「被動讀取已有 response headers/HTML」的安全性判斷留在 `scanners.py`；凡是「需要額外連線、工具呼叫、或深度解析」的放進此 sub-package。

---

## 檔案規劃

| 檔案 | 職責（待建） | 狀態 |
|---|---|---|
| `ssl_scanner.py` | SSL/TLS 深度分析：憑證到期、弱 cipher、過期協議（TLS 1.0/1.1）| 已建 |
| `cookie_scanner.py` | Cookie 安全旗標：Secure（`cookie-no-secure`）、HttpOnly（`cookie-no-httponly`）、SameSite＝None 無 Secure（`cookie-samesite-none`）、**SameSite 屬性缺失（`cookie-no-samesite`，低；ZAP 10054 移植，2026-10-17 退 ZAP 被動後補回，原本只報 None 不報缺失）** | 已建 |
| `header_scanner.py` | 資訊洩露標頭（X-Powered-By 技術棧；帶版本的值交給 service_cve_scanner 報 `service-version-exposed`，不重複開 `header-x-powered-by`，2026-10-20）、CORS 設定、CSP 品質分析、HSTS 標示 preload 卻不符預載條件（info）、**Permissions-Policy 缺失**（`header-permissions-policy`，低，ADR-0005 §2 移植自 ZAP 10063）；Server 版本→CVE 已移交 service_cve_scanner | 已建 |
| `passive_checks.py` | 自家被動 HTML 檢查（ADR-0005 §2，移植自退役的 ZAP 被動；只讀已抓頁面、零新請求）：`analyze_mixed_content`（`security-mixed-content`，HTTPS 載 http:// 子資源，active 類中／passive 類低）、`analyze_sensitive_url_params`（`security-sensitive-url-param`，網址查詢字串帶 password／token／apikey 等敏感參數，中）、`analyze_error_disclosure`（`security-error-disclosure`，頁面含堆疊追蹤／框架除錯頁，重用 api_scanner 的 `_stack_kind`，中）；`analyze_passive_html` 彙整，由 `stage_deep_security` 呼叫。ZAP 10027「註解可疑字詞」不移植（低訊號、秘鑰已由 secret_scanner 覆蓋） | 已建 |
| `owasp_mapper.py` | Finding 對映 **OWASP Top 10:2025**（A01~A10）與 CWE 編號（`tag()` + `backfill()`）。**2026-10-18 起原生 2025**：三張對映表（`_RULE_OWASP_MAP`／`_KEYWORD_OWASP_MAP`／`_AGENT_CLASS_OWASP`）的 OWASP 值直接是 2025 代號，`Finding.owasp_category` 直接存 2025（不再存 2021、不再推導）；`owasp_label()` 給顯示字串，`Finding.owasp_label` property、`FindingSerializer.owasp_label`、報告技術索引（`Axx:2025`）與掃描詳情顯示。舊資料由 **migration 0038** 依官方 2021→2025 對照回填（CWE-209→A10）。每月 `.github/workflows/scanner-update-check.yml` 比對 Dockerfile 鎖定的 Nuclei 引擎／模板版本與最新版，有新版就開 issue（只提醒、不自動升級） | 已建 |
| `authz_probe.py` | 未授權存取探測（確定性 BOLA 補位，2026-10-17）：`probe_unauthorized_endpoints` 對發現的同網站 API 端點（`_observed_api_paths`：被動攔截＋JS 靜態抽出）做**無憑證 GET**（全新 context、無 cookie、`max_redirects=0`、active RPS、最多 `ARGUS_AUTHZ_PROBE_MAX_ENDPOINTS`＝預設 60 個，ADR-0005 §3 放寬、可調）；`analyze_unauthorized_results`：先要是成批記錄（頂層陣列或 data／result… 底下非空物件陣列），再滿足**任一**才報 `security-unauth-api-records`（A01／CWE-862，`VERIFIED`）——(1) 身分欄位（姓名／帳號／email／member…）**且**內部帳號欄位（memberId／roleId／啟用狀態／時間…）＝後台名單；(2) 敏感欄位名（password／token／secret／身分證／idcard／ssn）；(3) 回應夾帶強個資（身分證／信用卡）。嚴重度 high 的條件：有任何 PII、敏感欄位或強個資，否則 medium。**email／手機是弱個資不單獨成立**（公開聯絡清單也有，要配合條件 1 的內部欄位）；公開 JSON 清單、公開人員目錄、單筆、非 JSON、非 200 都排除——誤報防線。**只在全站＋主動＋已授權**由 `tasks._run_authz_probe`（stage_exposure 內、同 exposure 閘）呼叫；把 Agent 偶然打到的未授權個資 API 沉澱成每次都跑得到的確定性檢查。**IDOR／BOLA 枚舉＋父集合反推（2026-10-18）**：`expand_idor_candidates` 對觀察到的 `/集合/:id`（結尾純數字，`_id_template`）反推兩種額外探測目標——父集合（去 id，淺爬時成批外洩其實在這）與鄰近 id（1／2／3＋觀察值），每模板只展一次、最多 `MAX_IDOR_TEMPLATES`＝5，併進候選後統一去重套 `MAX_ENDPOINTS`；`analyze_idor_results` 判單筆物件型 IDOR：同一模板 ≥2 個不同 id 未授權都回 200、內容**互異**的單筆物件（排除所有 id 回同一頁的 SPA／靜態）、且帶身分／內部／個資欄位（共用 `_sensitivity` 門檻，排除公開 `/產品/:id` 目錄）→ `security-idor-enumerable-object`（A01／CWE-639）。只打得到**未授權**就能枚舉的 IDOR；需登入的 IDOR 仍要靠 agent 或帶帳密掃描。頂層陣列交回 `analyze_unauthorized_results`（成批名單）不在此重複。判定門檻 `_sensitivity` 由成批與 IDOR 共用。**OpenAPI／Swagger 規格端點（2026-10-20）**：`exposure_scanner.extract_openapi_operations` 從本次 exposure 探到的 api-docs 規格解析 `paths`＋方法（外部路徑＝規格所在前綴＋basePath＋path；3.x 的 servers 多為內網不用），`openapi_probe_plan` 拆成「GET 讀取候選（併入無憑證讀取探測，path 參數代入 1）」與「寫入授權探測目標」。前端不呼叫的後台端點（`/members/all`）原本只有 AI Agent 偶然發現，現在變確定性項目。**寫入型端點授權探測（BFLA）**：`probe_write_endpoints` 對 POST／PUT／PATCH／DELETE 送**未登入＋無 body** 請求（`ARGUS_AUTHZ_PROBE_WRITE_ENABLED` 預設開、`ARGUS_AUTHZ_PROBE_MAX_WRITE`＝40、`_PacedRequester.fetch`）；**硬性安全界線：絕不送有效資料、不做真正的新增／修改／刪除**——path 參數一律代入不存在的 id（`987654321`）、裸集合的 DELETE 直接跳過。`analyze_write_probe_results` 只在未登入請求「到達處理邏輯」（不是 401／403／404／405／429、非 3xx）時才算缺授權閘門，每個端點一筆（合併多方法）：2xx＝真的執行了寫入＝`security-unauth-api-write`（A01／CWE-862）high；400／415／422／500 的欄位驗證錯誤＝進了 handler 但因空 body 被擋＝medium。頂層陣列交回 `analyze_unauthorized_results`（成批名單）不在此重複。判定門檻 `_sensitivity` 由成批與 IDOR 共用。**成批資料夾帶內部基礎設施訊號也成立（2026-10-20）**：`analyze_unauthorized_results` 除了帳號／成員名單，另一成立條件是成批記錄的回應裡含私有／內部 IP（`ip_context.private_ips`）或內部檔案路徑（`_INTERNAL_PATH_RE`：`/file/protected/`、伺服器檔案系統絕對路徑、`file://`、磁碟代號），升 high——即使不是帳號名單（產學課程、校園專案等），匿名可讀整批含內網拓樸／檔案路徑仍是存取控制缺失；公開清單只有公開網址（`/images/x.png`、`https://…`）不會命中。**OpenAPI 端點在多前綴下探測（2026-10-20）**：`exposure_scanner.extract_openapi_operations(results, extra_prefixes=)` 把規格的每條相對路徑在「規格所在前綴」與「觀察到的 API 前綴」底下各組一次，`tasks.stage_exposure` 傳入 `api_prefixes(_observed_api_paths)`——規格常掛在某代理前綴（`/api_proxy`），但同一後端可能從別的前綴（`/backend`）未授權暴露，只探規格所在前綴會漏掉 members 這種端點。殘留限制：只有從未在流量／JS／規格任一處出現過的前綴仍探不到 | 已建 |
| `cross_layer.py` | 跨層資安發現去重（2026-10-17）：`consolidate_cross_layer(findings)` 在「確定性層已有同端點的敏感檔案外洩發現（`exposure-*`／`evidence_source=exposure_probe`／`impact_area=information_exposure`）」時，丟掉 Agent 層（`agent-observed-security-*`）指向同一端點的那筆，回傳（保留清單, 被丟的 Agent 發現）。端點比對靠 exposure 存 `evidence_json.endpoint`、Agent 存 `evidence_json.observed_endpoint`（同一正規化）。`tasks.stage_scoring` 計分前呼叫並刪除被丟的 DB 列——否則同一件事計分扣兩次、報告列兩次。**兩個 pass**：(1) 確定性 exposure 同端點 → 丟 Agent（確定性可重現、其 rule_id 可能涵蓋多端點不宜刪）；(2) **Agent ↔ Agent 同後端資源**（2026-10-17 第二版）：`_canonical_resource` 剝掉反向代理／BFF 掛載前綴（`_MOUNT_SEGMENTS`＝api／api_proxy／backend／bff／gateway／proxy／rest，通用命名慣例非目標特定，只剝開頭一段且後面要還有資源，裸 `/api` 不剝），`/api_proxy/x` 與 `/backend/x`（Next.js rewrite → Spring Boot 同一後端資源）正規化成同一鍵，**同資源＋同弱點類型**（`findings.vuln_class`）的 Agent 發現只留最嚴重那筆（`findings.rank`，實測某授權掃描同一個 `visits` 錯誤洩內網 IP，`/api_proxy/visits` 報高、`/backend/visits` 報低，原本計分扣兩次又嚴重度打架）。只併 Agent 層（確定性層身分不動）、不同弱點類型不併（修法不同）。**(3) 確定性規則 ↔ Agent 跨類別橋接**（2026-10-18）：少數問題確定性規則與 Agent 文字觀察各報一次、rule_id 與 vuln_class 不同，Pass 2 配不起來（實測 `/management/login` 密碼欄 `type="text"`：form_scanner 報 `form-password-unmasked`、Agent 另報一筆，Agent 的 vuln_class 落在 other）。`_BRIDGE_CONCEPTS` 列舉實際重疊的少數組合（確定性 rule_id → 能認出等義 Agent 觀察的關鍵字群，每群任一命中、各群都要命中），同一頁（canonical resource，form_scanner 的頁面網址存在 `evidence_json.url`，由 `_resource_of` 回退取得）同時出現時保留確定性、丟 Agent；必須有對應確定性發現在同一頁才併，避免誤丟 Agent 獨有觀察 | 已建 |
| `api_scanner.py` | 被動 API 檢查（2026-10-11，回應評審 3-7）：`analyze_api(observations, origin)` 只分析爬取期間前端自己呼叫的同網站 API 回應摘要，不發請求、不讀後端原始碼。`api-error-stack-trace`（中，A05／CWE-209→A10:2025；Python／Django／Java／.NET／Node.js／PHP／Ruby／SQL 錯誤的結構性特徵，證據片段遮罩個資與金鑰）、`api-cors-wildcard`（低，回傳 JSON 且 `Access-Control-Allow-Origin: *`）；另回 `api_surface`（最多 50 個端點，有問題的排前面），顯示在資安分析頁與 PDF 附錄「API 端點清單」。**前端 JS 靜態發現、執行期未呼叫的端點由 `tasks._passive_api_check` 併入 `api_surface`**（`source="js_static"`、`method="靜態"`、`static_discovered` 計數），避免公開頁不呼叫後端 API 時附錄誤報成「沒有可檢查的端點」；`analyze_api` 本身仍只看觀察到的回應，不處理靜態路徑 | 已建 |
| `secret_scanner.py` | 硬編碼/外洩秘鑰偵測（AWS/Google/GitHub/Stripe/連線字串/私鑰/明文密碼）+ 遮罩 `redact_secrets_in_text`。**賦值型（`pwd=…`／`password:…`）的值若是程式運算式（`_looks_like_code`：含括號／反引號、`識別字.[(` 成員存取、jQuery `$(`／範本 `{{`、或開頭是 `document`／`req`／`process` 等程式關鍵字）就不算明文密碼**（2026-10-17：登入頁 `pwd=document.getElementById(...)` 被誤判成硬編碼秘鑰）；字面值（`pwd=hunter2`、引號字串）照常偵測 | 已建 |
| `content_injection.py` | 頁面 AI 提示詞注入偵測（2026-10-10，方法移植自 GeoReady/geo-optimizer-skill MIT）：`detect_content_injection(html)`（stdlib `html.parser`，純解析零請求）＋`build_injection_finding`。**刻意保守避免誤報**：只有命中明確 LLM 操縱指令字樣（可見文字／HTML 註解／隱藏區塊）或 AI 專用 `data-*` 屬性才判定；一般 `display:none`／摺疊選單不成立。命中指令＝high `security-ai-prompt-injection`（A03/CWE-74；隱藏或在註解＝刻意隱藏；只在可見文字且頁面有留言區＝可能第三方 UGC 降 medium）；只有 `data-ai-*` 或異常不可見字元＝low `security-ai-suspicious-markup`（A05/CWE-451）。由 tasks.py `_analyze_one_page` 資安分支被動呼叫（同 secret_scanner） | 已建 |
| `redaction.py` | 共用 finding/log 遮罩：URL query（**明顯是路由／語系／分頁的參數值保留**：`_SAFE_QUERY_KEYS`（lang／locale／page／sort／plugin／action…）且值是短而規則的字詞或 ≤6 位數字，2026-10-20——原本 50 頁的 log 全成 `index.php?Lang=[REDACTED]`；token／email 等名稱一律遮）、PII、任意短 secret；持久化前使用 。卡號遮罩只遮通過 Luhn 且開頭與位數符合卡組織的數字串（2026-10-17：原本任何 13–19 位數字都遮，網址頁面編號 `/p/404-1043-117736.php` 被遮成 `4041*****7736`；真卡號一定通過 Luhn，不會漏遮）。**0.0.0.0 不算內網外洩（2026-10-18）**：`_is_internal` 排除 `is_unspecified`——0.0.0.0/8 在 ipaddress 會被 `is_private` 判 True，但它是空值哨兵（如 `lastLoginIp` 從未登入），不是內網拓樸外洩（`private_ips`／`describe_ips` 都套用）。**掃描器自己的出口 IP（2026-10-20，`ip_context.is_scanner_ip`／`only_scanner_ips`）**：`ARGUS_SCANNER_EGRESS_IPS`（K8s ConfigMap 已填正式出口）裡的 IP／CIDR 在 `describe_ips` 判讀為「掃描器自己的出口位址，不是內部 IP 外洩」；沒設定時維持「需人工確認」 | 已建 |
| `exposure_scanner.py` | 敏感檔案主動探測（content discovery）：重用 crawler 的 robots 結果 + 內建字典 → Playwright 探測 → 檔案分類 + 秘鑰/PII 解析。**`probe_paths(stats=)` 回填 targets／unreachable／error**（2026-10-20），`tasks._exposure_probe_status` 據此標覆蓋：探針全部打不到＝`blocked`（WAF 擋探針）、一半以上打不到＝`partial`、整段例外＝`failed`——原本「探測 0 路徑」與探完全部正常一樣標 completed，報告寫「本次未執行的檢查：無」。**API 前綴底下也探測 API 文件（2026-10-16）**：`api_prefixes()` 從觀察到或 JS 抽出的同網站 API 路徑（`site_signals.api_observations`＋攔截到的端點＋**JS bundle 靜態抽出的 `site_signals.js_api_paths`**）推出前綴（第一段，接版本號時連版本，最多 5 個；單段路徑時只有該段本身是 API 基底才算前綴——JS 裡 rewrite base 常是裸字串 `/api_proxy`、`/graphql`），每個前綴加探 `API_DOC_SUFFIXES`（`v3/api-docs`、`v2/api-docs`、`api-docs`、`swagger.json`、`openapi.json`；Swagger UI 是 HTML 會被 soft-404 判斷擋掉，不列）；根目錄字典同時補上 `v3/api-docs`（Spring Boot 3 預設）。實測站台的規格就在代理前綴底下的 `v3/api-docs`，原本只有 AI Agent 偶然發現。**命中檔案的回應夾帶私有／內部網段 IP 時提升嚴重度（2026-10-16）**：`analyze_probe_results` 在秘鑰／PII 升級之後，用 `ip_context.private_ips(body)` 偵測內網 IP（例：OpenAPI 規格的 `servers` 寫 `http://10.x.x.x`），有就至少升到 high（內部網路拓樸外洩比「只是文件公開」更實質），描述與證據附內網位址判讀（`describe_ips`）；公網 IP 不升級。之前同一份規格只有 AI Agent 會因 `servers` 內網 IP 判成嚴重，確定性探測漏掉 。證據順序固定為命中→內網位址→秘鑰→個資→內容片段（報告檢測依據只取前 300 字）；每筆附 `evidence_json.assessment`（主動探測已實際取得檔案，不套用「範本比對未經重現」的預設判定依據）；API 文件的修法加上關閉 springdoc／springfox 與移除 host／servers 內網位址（2026-10-17）。**SPA soft-404 保險支援註解開頭的首頁（2026-10-18）**：baseline 沒攔到時的內容啟發式改用 `_starts_html_document`——先去掉前導 HTML 註解再判斷是不是 `<!doctype html>`／`<html` 開頭；juice-shop 的 index.html 以授權條款註解 `<!-- Copyright… -->` 開頭、`<!doctype>` 在註解之後，原本 `startswith` 判不到，讓 `/actuator/env.json`、`/bundle.js.map`、`/wp-content/debug.log` 等回同一份 SPA 首頁的 catch-all 被當成真檔案報成嚴重／高（8AC2 實測 8 筆誤報）；`_HTML_EXPECTED_TYPES`（phpinfo／server_status／admin／dir_listing）照舊豁免。**技術棧暴露確定性補位（2026-10-20）**：`probe_paths` 在主探測後跑 `_probe_tech_disclosure`——對根目錄與 API 前綴（上限 `MAX_TECH_PREFIXES`＝4）探 `SWAGGER_UI_SUFFIXES`（`swagger-ui/index.html` 等）與 `ERROR_PAGE_SUFFIXES`（`WEB-INF/web.xml`，觸發後端預設錯誤頁、無論狀態碼都讀 body），結果帶 `kind` 併進 `results`。`analyze_swagger_ui`：body 帶 Swagger UI 專屬標記（`_SWAGGER_UI_MARKERS`，排除 SPA catch-all）→ `exposure-swagger-ui`（低，A05／CWE-200，互動式 UI 公開；規格本身的外洩仍由 `exposure-file-apidoc` 另計）。`analyze_server_banner`：只看 `kind=error_page` 的 body，比對 `_SERVER_BANNER_RE`（`Apache Tomcat/9.0.102` 等精確版本橫幅）→ `exposure-server-error-banner`（低，A05／CWE-200，預設錯誤頁洩版本）。兩者由 `tasks.stage_exposure` 併入 `exposure_findings`、覆蓋檢查同 `exposure_probe`——把原本只有 AI Agent 偶然發現、代號會漂的 Swagger UI 與版本洩漏沉澱成每次都跑得到的確定性項目。第二組內網 IP（v2 api-docs 的 `host`）已由 `analyze_probe_results` 的內網 IP 升級涵蓋（根字典與前綴都探 `v2/api-docs`） | 已建 |
| `form_scanner.py` | 密碼欄位未遮蔽（2026-10-16）：`analyze_password_fields(html, location)` 被動解析已抓 HTML，欄位名稱／id／autocomplete／placeholder／aria-label／`<label>`，或緊接在欄位前 20 字以內的短標題（不用 `<label>` 的框架常寫 `<p>密碼</p><input>`）明確是密碼，且 `type` 是 text 或沒寫 → `form-password-unmasked`（中，A04／CWE-549，類型＝設定建議）；驗證碼、hidden、email 等不算。由 tasks.py `_analyze_one_page` 資安分支呼叫。原本只有 Agent UX 測試偶然回報（歸 UX） | 已建 |
| `kali_tools.py` | Facade：`run_sqlmap` / `run_sqlmap_batch` / `validate_findings_with_kali` / `run_metasploit`；統一走 `reserve_sqlmap_targets` 預算 + backend dispatcher | 已建 |
| `kali_contracts.py` | 安全結果契約：`KaliResult` / `ReservedSqlmapTarget` / `SqlmapExecutor` protocol / `parse_runner_result` / `redact_url_query_values` | 已建（Task 1） |
| `kali_policy.py` | 原子授權 + Redis 三目標預算 + 900s deadline + SHA-256 去重：`reserve_sqlmap_targets()` | 已建（Task 2） |
| `kali_kubernetes.py` | K8s Job executor：`KubernetesSqlmapExecutor`、Redis 單一 owner global lock、Job-first/Secret-second lifecycle、cancellation-aware watch | 已建（Task 4） |
| `sri_scanner.py` | SRI 缺失偵測：外部跨來源 `<script>/<link>` 缺 `integrity` | 已建 |
| `dns_scanner.py` | DNS/郵件安全：SPF / DMARC / DNSSEC（不做 DKIM）；`email_dns_posture()` 給「網站優勢」用 | 已建 |
| `infra_scanner.py` | 網站基礎架構：A／AAAA／CNAME／NS、IP 反解、Cloudflare 公告網段、標頭與 CNAME 指紋 → 判斷掃到的是 CDN／WAF／反向代理邊緣還是主機，產生報告提醒文字（只查目標自身網域、不發 HTTP） | 已建 |
| `js_library_scanner.py` | 第三方 JS 庫版本→CVE 比對：解析 <script> 用 Retire.js 規則庫離線比對已知漏洞 | 已建 |
| `service_cve_scanner.py` | 後端服務指紋→CVE：解析 Server/X-Powered-By 版本，比對 vendored backend_services.json（nginx/Apache/PHP） | 已建 |
| `zap_passive.py` | **被動掃描階段已於 ADR-0005 §2 退役**（獨有規則移植到 `passive_checks.py`／`header_scanner.py`，不再並存兩個被動引擎）；本模組**保留為 ZAP 共用元件**供 `zap_active` 使用：HAR 整理（`build_har`：同 origin、去 Cookie／Authorization、遮蔽 Set-Cookie）、`ZapClient`（上傳→匯入→掃描→讀告警→**一律清理**；httpx client 固定送 `Host: zap`——ZAP 用 Host 判斷是不是呼叫自己的 API，只認內建別名 zap／localhost，用服務 FQDN 連進去時不帶會被當成要轉發的流量並回 502，2026-10-18 實機確認）、`alerts_to_findings(active=...)`（與既有檢查重複的不列、雜訊略過、信心低降一級）、`OVERLAP_RULES`。`run_passive` 函式保留但未接線（備查／手動用）。見 [`docs/zap-passive.md`](../../../../docs/zap-passive.md) | 已建（被動階段退役，模組供主動共用） |
| `zap_active.py` | OWASP ZAP 主動掃描（spider＋active scan，送攻擊 payload）：先用爬蟲 HAR 匯進 ZAP 建站台樹（繞過 CF）再對節點 active scan；重用 `ZapClient`／`build_har`／`alerts_to_findings(active=True)`；時間預算＋取消＋一律清理（清 origin、覆寫上傳 HAR 為 `{}`）。**攻擊型、預設關**：`ARGUS_ZAP_ACTIVE_ENABLED` ＋ `scan_plan.run_zap_active`（全站＋主動＋已授權，同 Nuclei／Kali 閘）。被動仍是地板。**大站逾時治理（2026-10-18，P0）**：`run_active` 的 `build_har(representative=True, max_entries=ARGUS_ZAP_ACTIVE_MAX_NODES=40)`——同一路徑模板（`_template_key`：去查詢字串、數字段換 #）只留一筆，大站幾十頁同模板不把 active scan 節點灌爆；`ZapClient` 的 HTTP 逾時改用 `ARGUS_ZAP_HTTP_TIMEOUT_SECONDS`（120，原 httpx 預設 30s 會在大站 importHar／讀告警時被砍斷 → 整段以「ZAP 逾時」失敗，實測 imd.ntub 50 頁即如此）。見 [`docs/zap-passive.md`](../../../../docs/zap-passive.md) | 已建（程式預設關閉） |
| `vuln_intel.py` | 已知漏洞優先序補強（`stage_deep_security` 寫入前呼叫）：`js-lib-known-vuln`／`service-known-cve` 的 CVE 查 EPSS（FIRST.org，被利用機率與百分位）→ `evidence_json.epss`、描述加一句、`priority_score` 最多加 `EPSS_PRIORITY_BOOST`（14，小於嚴重度間距，不越級）；前端函式庫查 OSV.dev（npm）→ `evidence_json.osv`（公告數、Retire.js 沒列的 CVE、涵蓋目前版本的最高修補版本）並改寫修法。**不改嚴重度**；只送函式庫名稱／版本／CVE；結果快取 1 天；查不到寫 `evidence_json.vuln_intel` 原因。`ARGUS_VULN_INTEL_ENABLED`（預設開） | 已建 |
| `observatory.py` | 安全標頭參考等第：依 Mozilla HTTP Observatory（v2）公開評分規則離線計算 CSP、Cookie、CORS、HTTP→HTTPS、Referrer-Policy、HSTS、SRI、nosniff、X-Frame-Options／frame-ancestors、CORP 十項，100 分起算、加分只在 ≥ 90 時計入、A+～F。只用首頁回應與 SEO 的轉址檢查，**不呼叫 Mozilla、不發請求、不產生問題、不計入 Argus 分數**；判斷不了的標「未評估」。結果在 `site_profile.observatory`（勾資安時），報告「網站架構」表一列（`summary_line`）、前端網站架構分頁 。**HTTP→HTTPS 讀 SEO 站台檢查 `http_to_https` 的 `level`（2026-10-17 修正：原本讀不存在的 `verdict`，有勾 SEO 的網站一律被誤扣 20 分，與網站優勢「HTTP 會自動轉到 HTTPS」矛盾；測試改用 `link_check._site_check` 產生的真實格式鎖定）** | 已建 |
| `finding_kind.py` | 資安發現類型（roadmap §5 第 1 項第一階段，2026-10-08）：`security_kind()` 依 rule_id、標題、證據來源把資安發現分成設定建議（config）／曝露面（exposure）／疑似弱點（suspected）／已驗證弱點（verified），掃描說明（例如 WAF 之後 0 項發現）回 None。**不看 `Finding.confidence`**（既有 1.0 是未校準，不是已確認）、**不影響分數與排序**、不寫 DB（`Finding.security_kind`／`security_kind_label` property 顯示時推得，舊掃描也有）。用在 `FindingSerializer`、`projects.issue_groups`、報告每項追蹤列（`RENDERER_VERSION` 16）。新增資安規則時要在這裡歸類，否則不顯示類型 | 已建 |
| `nvd_db.py` | NVD CVE→backend_services.json 純函式轉換（CPE 過濾 + 版本區間），供 refresh 命令與單元測試 | 已建 |

---

## 整合規則

- **所有 scanner 函式回傳 `list[dict]`**，格式與 `scanners.py` 的 `make_finding()` 相同
- **不直接寫入 DB**：回傳 findings list，由 `tasks.py` 統一寫入
- **呼叫點在 `tasks.py`**：在 Nuclei 掃描完成後，`tasks.py` 依 `scan_plan.py` 的範圍／授權閘門呼叫此 sub-package 的各 scanner
- **Kali 工具呼叫順序**：Nuclei 偵測完成 → Hermes-Agent 判斷 → `kali_tools.py` 執行，不可與 Nuclei 同時對同一目標打

---

## SSL Scanner 設計原則

```python
# ssl_scanner.py 的函式簽名
def analyze_ssl(hostname: str, port: int = 443, scan_job_id: int = 0) -> list[dict]:
    """連線取得憑證資訊，回傳 Finding list。任何例外 silent-fail 回傳 []。"""
```

- 使用 Python 內建 `ssl` 模組，不依賴外部 binary
- 憑證已過期 → CRITICAL；≤ 7 天 → HIGH；≤ 14 天 → MEDIUM；15–30 天 → INFO（Let's Encrypt、Cloudflare 等自動續期憑證剩約 30 天才續期，屬正常週期；2026-10-06 調整，舊版 30 天內一律 HIGH）
- 協議版本低於 TLS 1.2 → HIGH
- 弱 cipher（RC4、DES、3DES）→ HIGH

---

## Cookie Scanner 設計原則

```python
# cookie_scanner.py 的函式簽名
def analyze_cookies(cookies: list[dict], url: str) -> list[dict]:
    """接收 Playwright 的 context.cookies()，回傳 Finding list。"""
```

- Secure flag 缺失且 URL 為 HTTPS → MEDIUM
- HttpOnly flag 缺失 → LOW
- SameSite 為 None 且無 Secure → MEDIUM；SameSite 屬性完全缺失 → LOW（`cookie-no-samesite`）

---

## SRI Scanner 設計原則

```python
def analyze_sri(pages: list[dict]) -> list[dict]:
    """掃 crawled_pages 的外部無 integrity <script>/<link>，回 Finding list。"""
```

- 解析用 stdlib `html.parser.HTMLParser`，不引入 BeautifulSoup
- 只報**跨來源**資源（同源/相對路徑跳過，避免噪音）；已有 `integrity` 跳過
- 依解析後資源 URL 去重，整個 scan 同一 CDN URL 只報一次 → 一律 LOW
- **不報無法鎖雜湊的服務**（`_DYNAMIC_SCRIPT_HOSTS`）：內容會隨時更新、官方不提供 SRI 的腳本與樣式（Google Analytics／Tag Manager、Stripe、reCAPTCHA、Cloudflare Turnstile、Google Fonts、hCaptcha 等），加上 integrity 反而會在更新後被瀏覽器擋掉，改由 CSP 限制來源。2026-10-11 補 Turnstile、Google Fonts、recaptcha.net、hCaptcha；2026-10-12 補 Google 登入（`accounts.google.com/gsi/client`）

## DNS Scanner 設計原則

```python
def analyze_dns(host: str) -> list[dict]:
    """用 dnspython 查 SPF/DMARC/DNSSEC，回 Finding list。例外回 []。"""
```

- SPF 缺失 → MEDIUM；SPF `+all` → HIGH
- DMARC 缺失 / `p=none` → LOW；DNSSEC 缺失 → LOW（措辭採最佳實務建議）
- SPF/DMARC 查不到時退父網域一層；**不做 DKIM**（黑盒無法可靠列舉 selector）
- 只查目標自身網域，無 SSRF 面；新增相依 `dnspython`

---

## JS Library Scanner 設計原則

```python
def analyze_js_libraries(pages: list[dict]) -> list[dict]:
    """解析爬蟲已抓 HTML 的 <script>，用 vendored Retire.js 規則庫離線比對版本→CVE。例外回 []。"""
```

- 被動、零額外 HTTP（只讀 `page["html"]` 的外部 src URL + inline 內容）、零新第三方套件（純 stdlib）
- 版本萃取用 Retire.js `extractors` 的 uri/filename/filecontent（`§§version§§` 替換為 `([0-9][0-9.a-z_\-]+)`）；不做 func（需 runtime eval）/ hashes（需完整檔位元組）
- severity 沿用 Retire.js 值但 **critical 封頂 HIGH**（被動偵測未實機確認可利用）
- 單一 rule_id `js-lib-known-vuln` → A06/CWE-1104；per-CVE 的具體 CWE/CVE/summary/連結進 `evidence_json`
- 以 `(庫名, 版本)` 去重；規則庫 vendored 於 `data/jsrepository.json`（Apache-2.0），手動更新

---

## Service CVE Scanner 設計原則

```python
def analyze_services(pages: list[dict]) -> list[dict]:
    """依序解析每頁 Server／X-Powered-By 的 (產品,版本)，比對 vendored NVD DB，回 Finding list。例外回 []。"""
```

- 被動、零額外 HTTP（只讀 `page["headers"]` 的 Server/X-Powered-By）；每次掃描都跑、**不掛任何 active/deep gate**
- 版本區間比對**重用** `js_library_scanner._is_vulnerable`（DB 欄位格式與 jsrepository.json 一致），不重寫 matcher
- 命中 → `service-known-cve`（severity 取命中 CVE 最高、critical 封頂 high、A06/CWE-1104；per-CVE 進 `evidence_json`）
- 無命中（或 DB 缺失）→ LOW `service-version-exposed`（A05/CWE-200）；**版本暴露不依賴 DB**，以完整接手舊 `header-server-version` 而不回歸
- **只憑標頭版本號，一律是疑似**（2026-10-10）：標題寫「版本號落在已知漏洞範圍」，`evidence_json.assessment` 寫明沒有實際驗證；標頭帶作業系統發行版註記（`(Ubuntu)`、`+deb9u3`、`-4ubuntu2`、`.el8`…，`_DISTRO_MARKER`）時 `backport_possible=true`、嚴重度封頂中——發行版會把修補補進舊版本、版本號不變
- 以 `(產品, 版本)` 去重；DB 為 `data/backend_services.json`（NVD public domain），以 `manage.py refresh_backend_cve_db` 手動更新；轉換純函式 `nvd_db.build_db_from_nvd` 的正確性由 `tests_nvd_db.py` 已知答案 fixture 鎖定

---

## Secret / Exposure Scanner 設計原則

- **`secret_scanner.detect_secrets_in_text(text)`**：純函式，高訊號前綴 regex（避免誤報）；回傳遮罩後結果。
  - **被動使用**（任何模式）：`tasks.py` per-page 對已抓到的 HTML/inline script 偵測（零額外請求）。
  - **瀏覽器用金鑰**（`BROWSER_PUBLIC_KINDS`＝Google `AIza` 金鑰）：Google 地圖／Firebase 金鑰必須放在前端，靠 Google Cloud 的參照網址與 API 限制保護。頁面中出現時 `build_secret_finding` 不算，另由 `build_browser_key_finding` 產生低風險 `exposure-browser-api-key`（確認已設限制）；Katana jsluice 的 `AIza` 值同樣降為低（2026-10-10，原本高／嚴重）。值已被特定格式抓到時，泛用賦值（`apiKey: "AIza…"`）不重複列。
  - `redact_secrets_in_text(text)` 用於把「檔案內容片段」當證據前遮罩，**一律遮罩**（不因 placeholder 子字串豁免，否則真密碼會二次外洩）。
- **`exposure_scanner.probe_paths(...)`**：整站主動內容探測，**只在全網站且 `scan_mode==ACTIVE and active_testing_authorized` 時由 tasks.py 呼叫**；單頁、被動或未授權模式不得發探測請求。
  - `build_probe_targets` 強制 **same-origin**（內建字典含 dotted/非 dotted/.txt 變體）。
  - `probe_paths` 的逐路徑 GET 用 `max_redirects=0`，避免目標站 open-redirect 把探針導向 metadata/外站。
  - 優先重用 crawler 已取得的 `robots_disallow`，不再重抓 robots 或解析 sitemap，避免重複 I/O 與把公開頁面清單誤當敏感路徑。
  - robots fallback、soft-404 baseline 與正式 probe 共用同一個 active RPS pacer；每次請求前檢查取消，`ScanCancelled` 不得被 silent-fail 吞掉。
  - body 片段在寫 Finding 前依序遮罩 secret 與 PII；命中 URL 的 query value 也必須遮罩，不得把外洩資料二次複製進 DB。
- **`analyze_robots_disclosure(disallow)`**：被動，robots.txt 列出 ≥3 條敏感路徑時報「以 Disallow 當地圖洩露」。
- 掃描入口、redirect、子資源與 WebSocket 均須通過 `services.py` 的 public HTTP policy；production 仍須用 egress proxy/firewall 補上 DNS rebinding 的解析／連線競態防護。

## Kali Tools 設計原則

架構由四個模組串接：`kali_contracts.py`（安全結果契約）→ `kali_policy.py`（原子授權 + Redis 預算）
→ `kali_tools.py`（facade / dispatcher）→ `kali_kubernetes.py` 或 Docker executor（backend 實作）。

```python
# kali_tools.py 的對外 facade 簽名
def run_sqlmap(target_url: str, scan_job_id: int) -> dict:
    """單目標：一律先 reserve_sqlmap_targets(max_count=1) 再依 backend 派發。
    回傳 dict（{ok, tool, blocked_reason, returncode, stdout, error, confirmed, evidence_summary}）
    與 agent/tools.py 既有契約相容；stdout 固定為 ""。"""

def run_sqlmap_batch(scan_job_id: int, candidate_urls: list[str], max_targets: int = 3) -> dict:
    """批次：reserve max_count=min(max_targets, 3)；每個 admitted target 執行一次。
    回傳 {blocked_reason, executions: tuple[SqlmapExecution, ...]}。"""

def validate_findings_with_kali(scan_job_id: int, candidate_urls: list[str], max_targets: int = 3) -> list[dict]:
    """tasks.py 編排層入口：先挑帶 query parameter 的候選，再跑 run_sqlmap_batch；
    只信任 KaliResult.confirmed；產出 rule_id=kali-sqlmap-sqli (A03/CWE-89) critical Finding。"""

def run_metasploit(module: str, options: dict, scan_job_id: int) -> dict:
    """僅 docker backend 支援；kubernetes / 未知 backend 一律回
    blocked_reason=tool_not_supported_by_backend，不會呼叫 docker。"""
```

### Backend dispatcher（Task 3 / Task 4）

- `_executor_for_backend()` 依 `settings.ARGUS_KALI_BACKEND` 選擇 executor：
  - `docker` → `DockerSqlmapExecutor`：raw stdout 只在 process 內解析，回 `KaliResult`（`stdout=""`），
    `evidence_summary` 限 `parameter` / `techniques` / `dbms` / `ARGUS_KALI_SQLMAP_VERSION`。
  - `kubernetes` → lazy import `KubernetesSqlmapExecutor`：見下方「Kubernetes executor」。
  - `disabled` / 未知 → 回 `None`；facade 走 `backend_misconfigured` blocked 分支並寫 warn audit。
- base `docker-compose.yml` **完全不掛** docker.sock、不裝 docker CLI；Docker demo 走獨立
  `docker-compose.attack.yml` override（worker environment 加 `ARGUS_KALI_BACKEND: "docker"`）。
  正式 K8s 參集則設 `ARGUS_KALI_BACKEND=kubernetes`，由 worker 透過 in-cluster config 操作叢集。

### Settings（Task 1 新增，全預設停用）

| Setting | 預設 | 說明 |
|---|---|---|
| `ARGUS_KALI_ENABLED` | `False` | 總開關；必須為 True 才會進一步 dispatch |
| `ARGUS_KALI_BACKEND` | `"disabled"` | `disabled` / `docker` / `kubernetes` |
| `ARGUS_KALI_CONTAINER` | `"argus-kali-1"` | 僅 Docker backend 使用 |
| `ARGUS_KALI_NAMESPACE` | `"argus-kali"` | 僅 Kubernetes backend 使用 |
| `ARGUS_KALI_RUNNER_IMAGE` | `""` | K8s runner image，正式啟用時為 `repository@sha256:<64 hex>` |
| `ARGUS_KALI_SQLMAP_VERSION` | `"1.10"` | 寫進 evidence_summary 的版本標籤 |
| `ARGUS_KALI_TIMEOUT` | `120` | 單一 target SQLmap timeout（秒） |
| `ARGUS_KALI_MAX_TARGETS` | `3` | 每 scan 最多目標數（policy 強制上限） |
| `ARGUS_KALI_LOCK_WAIT_SECONDS` | `420` | K8s global lock 等待上限 |
| `ARGUS_KALI_SCAN_DEADLINE_SECONDS` | `900` | 每 scan Kali 總 deadline（policy 端） |
| `ARGUS_KALI_STATE_TTL_SECONDS` | `86400` | Redis 去重 fingerprint TTL |
| `ARGUS_KALI_RESULT_MAX_BYTES` | `16384` | runner stdout JSON 上限（contract 端） |
| `ARGUS_KALI_REDIS_URL` | `redis://localhost:6379/0` | policy + K8s global lock 共用 Redis |

### 共用授權與預算（kali_policy）

`reserve_sqlmap_targets()` 是 docker / kubernetes / agent-tool-call / fallback **共用**的入口，
依固定順序檢查：Kali 開關 → backend → ScanJob 存在 → cancel → active mode → 主動授權 → 公網 →
同源 → query parameter；通過後才以 Redis Lua 原子套用 900s deadline、最多 3 個目標、SHA-256
去重與 86400s TTL。Policy 不保存完整 target URL 或 query value（只用標準化後的 SHA-256 指紋）。

### Kubernetes executor（kali_kubernetes.py，Task 4）

- 僅 `config.load_incluster_config()`，無本機 kubeconfig fallback；worker 必須掛
  `argus-worker-kali-orchestrator` SA（見 `k8s/10-kali-runtime.yaml`）。
- 單一 owner global lock：`SET NX PX` + Lua compare-and-* ；mismatched token 無法續約或釋放。
- Job-first / Secret-second：先建 Job 拿 UID，再建 owner-referenced Secret（只含 `targets.json`）；
  worker 只 `create` / `delete` Secret，**不** get/list/read 回。
- 動態 deadline = `min(active_deadline + 30, 420)`；watch 5s/片，每片 I/O 前後皆做 cancellation
  + ownership checkpoint；`ScanCancelled` 原樣重拋，不遮蔽。
- `append_log` 只記 `correlation_id` / phase / fixed safe error code（如 `job_deadline_exceeded`、
  `runner_failed`、`invalid_result`），**不記** URL、query value、API exception body、raw log。
- Cleanup 在 finally 必跑；NotFound 視為成功。

### 掃描流程接線（AI-first，Task 6）

`tasks.py` 的順序固定為：被動 + 主動 scanner → **Hermes-Agent（先）** → **Kali fallback（後）** → scoring。
Agent 確認的 `security_findings` 會餵進 scoring（DB 落地由 `runner.persist_agent_security_findings`）；
Redis 指紋讓 fallback 只處理 agent 沒驗證過的獨特 target（單一 batch）。`probe_sql_injection` 在
agent 端額外有同源 + query parameter + active 授權三層閘，AgentStep 持久化前經
`redact_tool_arguments` / `redact_tool_result` 遮罩 URL 與 raw 結果。

### 不可放寬的硬性規則

- **授權與預算一律經 `reserve_sqlmap_targets`**：facade / executor / agent 都不再自做 scan_mode /
  active_testing_authorized 檢查；任何新增 backend 都必須接在同一個 policy 入口後。
- **任何例外 silent-fail**，回結構化 `KaliResult` / dict，**不**影響主掃描流程；唯一例外是
  `ScanCancelled` 必須原樣重拋讓取消流程傳遞。
- **所有呼叫（含被擋）都記錄進 `scan_logger.append_log`**；helper `_log_kali_decision` 只記
  fixed structured reason，嚴禁拼接 URL / query value / raw stdout / exception body。同一原因一次掃描只記一次（`scan_logger.already_logged`，2026-10-20：agent 工具、批次驗證、stage_kali 各一次，log 連三行「已略過（kali_disabled）」）。
- **runner raw stdout 永不離開 executor process**：持久化內容必經 `KaliResult` schema 與
  `redact_url_query_values`；Finding 的 `evidence_json` 只放 `evidence_summary`。
- subprocess 一律 list 形式（非 shell=True）+ module/option/URL 輸入驗證，防命令注入。

### 目前狀態與啟用

軟體已 merge 並通過單元／合約測試，但正式叢集仍維持 disabled：`ARGUS_KALI_ENABLED=false`、
`ARGUS_KALI_BACKEND=disabled`、runner image 為 disabled sentinel digest
`shijie85/argus-kali-runner@sha256:0000…`（見 `k8s/01-namespace-config.yaml` 與
`k8s/11-kali-admission.yaml`）。啟用流程（靜態加密 → digest 推廣 → dry-run → RBAC/Admission/
Network 實機 → disabled smoke → enablement → 授權 positive test → rollback）見 operator runbook
[`../../../../docs/runbooks/kali-sqlmap-rollout.md`](../../../../docs/runbooks/kali-sqlmap-rollout.md)；
靜態加密前置見 [`../../../../docs/runbooks/kubernetes-secret-at-rest-encryption.md`](../../../../docs/runbooks/kubernetes-secret-at-rest-encryption.md)。
Docker Compose demo（`docker-compose.attack.yml`，本機或隔離 demo 專用）維持原狀，不在本啟用鏈上。

---

## 禁止事項

| 禁止 | 原因 |
|---|---|
| `kali_tools.py` 在 passive mode 執行 | 未授權主動攻擊 |
| 任何函式直接寫入 Finding model | 職責分離，DB 寫入只在 tasks.py |
| 修改 `ScanJob.status` | 狀態機只在 tasks.py 管理 |
| Kali 工具與 Nuclei 同時對同一目標執行 | 目標可能因流量異常封鎖 IP |

---

## 長遠遷移計畫（專題後）

目前 `scanners.py` 的 `analyze_security()` 和 `analyze_data_exposure()` 仍留在原處（被動式）。
專題結束後可將這兩個函式移至此 sub-package 的 `passive_scanner.py`，同時將 `nuclei_scanner.py`
和 `katana_scanner.py` 也移進來，使資安邏輯完全集中。遷移不涉及 model 或 migration 變更，
只需更新 `tasks.py` 的 import 路徑。
