# 掃描管道重構：相位分離與工具去重疊（Pipeline Phasing & Tool De-overlap）

Argus 的 `SCAN_PIPELINE` 目前有 21 個階段（前端進度條顯示 17 個細分步驟），其中資安相關有 8 個：
`site_security`、`active_probe`（Nuclei／Katana）、`deep_security`、`zap_passive`、`zap_active`、
`exposure`、`agent`、`kali`。這些階段是**一個一個工具疊加上去**的：每個工具自帶「發現攻擊面 →
偵測 → 產出 finding」整條流程，彼此的重疊**在事後清理**（`zap_passive` 的 `OVERLAP_RULES` 手動
抑制表、`cross_layer.consolidate_cross_layer` 跨層去重、`findings.consolidate_security_findings`
Agent 內部合併）。結果是同一個問題可能被多個工具各測一次、各報一次，再靠去重把重複刪掉。

> 更正常見誤解：目前的去重**都是確定性的**（欄位比對、規則表），不是「AI Agent 事後再審一遍」。
> 但「重疊是事後清、不是一開始就不產生」這個架構債確實存在，本 ADR 處理它。

本 ADR 從第一性原理重排管道，定義**相位分離**與**單一攻擊面模型**，讓重疊從源頭不發生，而不是
產生後再刪。與 [ADR-0004 智慧動態掃描](0004-smart-dynamic-scan.md) 正交：0004 決定「依網站特徵
加掃哪些模組」，本 ADR 決定「這些模組怎麼排、怎麼不互相重複」。

> 這份文件是**實作計劃**，撰寫時尚未改動任何掃描程式。所有「現況」敘述對照 2026-10-17 的
> `backend/apps/scans/`。落地時每一刀完成都要回來更新本檔與 `backend/apps/scans/CLAUDE.md`。
>
> **前提（使用者 2026-10-17 裁定）**：對授權目標**不限制重複請求／重抓**。因此凡是「為了省請求數
> 而縮小範圍」的既有設計（Nuclei 只掃根網址、authz 探測 20 個端點上限等）都可以放寬，換取更高涵蓋率。
> 但請求量放寬**不能解決 Cloudflare 攔截**——那是「非真瀏覽器會吃 challenge」的問題，只能靠真瀏覽器
> （crawler）或瀏覽器 context 重抓解決，見決策 §2。

---

## 原則（先定錨，其餘服從）

1. **發現一次、共享給所有人**：攻擊面（頁面、端點、表單、技術、JS、HAR）只由 crawler 建立一次，
   當作唯一真相來源餵給所有下游工具。任何工具都不自己再爬一遍去建立自己的攻擊面。
2. **一個 (端點 × 弱點類) 只由一個工具負責**：主動探測與利用階段要有明確分工，從源頭不重疊；
   事後去重只當**最後一道保險**，不當主要手段。
3. **CF 盲區靠真瀏覽器補，不靠加請求**：繞過 Cloudflare 的唯一管道是 crawler（真瀏覽器、帶 clearance）。
   需要 CF 後面資料的分析，一律走 crawler 已抓到的 bytes 或瀏覽器 context 重抓，不交給會被 challenge
   的獨立 HTTP client（Katana、ZAP spider、Nuclei）。
4. **Agent 吃前面的結果當輸入**：Agent 不重新發現、不重跑確定性檢查；它拿到「攻擊面＋已找到的
   deterministic findings」，只做「要推理才找得到的」與「驗證／升級既有發現」。

---

## 第一性原理：只有五種偵測機制

每一筆資安發現本質上只來自其中一種，先把工具按機制歸位，重疊就現形：

| 機制 | 本質 | 現在誰做 | 應該屬於的相位 |
|---|---|---|---|
| A 被動分析已抓到的 bytes | 0 新請求、確定性 | `site_security`、`deep_security`、`zap_passive` | 相位 2 被動 |
| B 主動探測已知/猜測路徑 | 發請求、無推理 | `exposure`（檔案/authz）、Nuclei(KEV) | 相位 3 主動探測 |
| C 主動爬行找攻擊面 | 發請求找端點 | crawler、Katana、ZAP spider | 相位 1 發現 |
| D 送 payload 打弱點 | 攻擊流量 | ZAP ascan、Nuclei(fuzz)、sqlmap、agent | 相位 4 利用 |
| E 代理推理 | 情境判斷、串接 | Hermes-Agent | 相位 5 推理 |

---

## 現況的四個重疊（問題陳述）

1. **被動分析做兩遍**：`site_security`＋`deep_security` 已從回應算出 header/cookie/TLS/CSP/CORS/SRI/
   JS-CVE/PII……，`zap_passive` 又把同一份 HAR 餵進 ZAP 的被動規則**再算一遍**。證據：`zap_passive.py`
   有 13 條 `OVERLAP_RULES` 手動抑制＋10 條 `IGNORED_RULES`。ZAP 被動真正獨有的只剩約 5 條（混合內容
   10040、註解殘留 10027、debug 錯誤頁 10023/90022、URL 帶敏感資訊 10024、Permissions-Policy 10063）。
2. **爬行做三遍**：crawler（真瀏覽器、繞得過 CF，已抽 XHR 端點＋JS 靜態路徑）、Katana（主動重爬，CF 後
   歸零）、ZAP spider（主動重爬，CF 後歸零，所以 `zap_active` 才改用 crawler HAR 建站台樹）。
3. **利用沒有分工表**：Nuclei、ZAP ascan、sqlmap、agent 各自對重疊端點送各自 payload（同一個 XSS 可能
   被三個引擎各打一次），撞了才由 `cross_layer`／`consolidate_security_findings` 事後刪。
4. **Katana JS 功能與 crawler 半重疊、又有真漏洞**：Katana 的「JS 端點挖掘（-jc）」與 crawler 的
   `extract_api_paths_from_js` 重疊（jsluice AST 較深、crawler regex 較淺）；但 Katana 的「JS 秘鑰（-jsl）」
   **crawler 完全沒做**——`_collect_js_api_paths` 讀完 JS body「抽完路徑就丟」，Argus 自家 `secret_scanner`
   只掃 HTML＋inline script，**不掃外部 .js bundle**。而 Katana 這塊在 CF 後面又歸零——等於「需要它的場景
   它失效，它有效的場景 crawler 也有效」。

---

## 決策：五相位管道 ＋ 單一攻擊面模型

重排資安階段為清楚的相位，前一相位的產出是後一相位的輸入：

```
相位 1 發現（crawler 唯一真相來源）
  → 頁面、表單、XHR/fetch 端點、JS（透過瀏覽器 context 抓齊）、技術指紋、HAR
相位 2 被動分析（單一引擎，0 新請求）
  → header/cookie/TLS/DNS/CSP/CORS/SRI/JS-CVE/service-CVE/secret(HTML+JS)/PII/混合內容/debug 洩漏
相位 3 主動探測（確定性、發請求、無推理）
  → 檔案內容探測、API-docs、未授權存取(authz)、Nuclei KEV
相位 4 利用（送 payload，由「利用計畫」分工）
  → 每個 (端點 × 弱點類) 指派給唯一工具：ZAP ascan / Nuclei fuzz / sqlmap
相位 5 Agent 推理（吃相位 1–4 的全部產出當輸入）
  → 只做情境判斷（差異式未授權、串接）與既有發現的驗證／升級
```

### §1 發現相位：JS 分析搬進 crawler，取代 Katana JS 功能
- crawler 對讀到的 JS body 除了抽端點，另跑秘鑰偵測（`_collect_js_secrets`）。補上「外部 .js 秘鑰
  偵測」這個現有真實漏報，且走真瀏覽器（CF-safe）。**（已實作 2026-10-17，見下方進度）**
- 後續（同刀未完）：主動抓齊頁面沒自然載入的 .js（透過瀏覽器 request API 帶 CF clearance），
  不只被動攔截到的；提高 JS 端點抽取深度。被動載入已涵蓋導航會載入的 bundle，此為增量補強。
- Katana **不刪**，降為非 CF 站的補充：主動爬到瀏覽器沒點進去的頁、較廣的技術辨識（`-td`）。
  CF 後面它本就歸零，降級不損失覆蓋。

### §2 被動相位：ZAP 被動與自家被動二選一 **（已實作 2026-10-17）**
- 不再兩個引擎並存＋手動抑制。**保留 Argus 自家被動**，把 ZAP 被動獨有規則移植成自家規則，
  `zap_passive` 階段退役（`zap_passive.py` 模組保留為 ZAP 共用元件供 `zap_active` 用）。
- 移植：混合內容（`security-mixed-content`）、URL 敏感參數（`security-sensitive-url-param`）、
  頁面錯誤洩漏（`security-error-disclosure`）放 `security/passive_checks.py`；Permissions-Policy 缺失
  （`header-permissions-policy`）放 `header_scanner`。ZAP 10027「註解可疑字詞」不移植（低訊號）。
- **補遺（2026-10-17，實機重掃發現）**：ZAP 10054「Cookie 未設定 SameSite（屬性缺失）」當初漏列——
  `cookie_scanner` 原本只報 SameSite=None 無 Secure，不報「屬性完全缺失」，退 ZAP 被動後這塊變成沒人查。
  已補 `cookie-no-samesite`（低）回 `cookie_scanner`。教訓：退引擎前的獨有規則審計要逐條核到「自家是否
  真的等價覆蓋」，不能看到相近檢查就當覆蓋。
- 審計發現：ZAP 被動的「重複發現」早由 `OVERLAP_RULES`（13 條）抑制表解掉，退階段屬**簡化＋補獨有**，
  不是修去重。

### §3 主動探測相位：放寬可安全放寬的預算
- **authz 探測端點上限放寬**（已實作 2026-10-17）：`ARGUS_AUTHZ_PROBE_MAX_ENDPOINTS` 預設 20→60、可調；
  不限重抓時提高 BOLA 涵蓋率。60 端點 ÷ active RPS 仍在掃描時間預算內。
- **Nuclei 刻意不盲目放寬**（審計結論）：`CLAUDE.md`「Nuclei 模板治理」已實測——全模板集 6680 個、
  9535 請求、1–2 RPS 要約 80 分鐘，KEV 是 511／628；「只掃根網址」是因模板多為站台層級、逐頁重掃只是
  乘頁數。這兩個是**噪音與時間的產品取捨**，不是「為省請求」，不因不限重抓而該放寬；盲目放寬＝掃描動輒
  一小時＋大量低訊號告警＝退步。若要放寬模板集，是需要明確拍板＋實機量噪音的獨立決定，不在本刀。
- **階段合併刻意不做**：exposure 與 active_probe 本就循序執行、無 RPS 競用，合併成單一相位是 cosmetic
  結構搬動，效益小而動覆蓋契約／測試，風險不值得。保持現狀。

### §4 利用相位：正式「利用計畫」分工——審計後**刻意不建**（2026-10-17）
原構想：把每個 (端點 × 弱點類) 指派給唯一一個工具（SQLi→sqlmap、注入/XSS→ZAP ascan、CVE→Nuclei），
從源頭不重打。實作審計後**放棄建這個框架**，理由：

1. **黑箱引擎無法被細緻約束**：Nuclei 吃的是整組模板策略（`-tags/-severity/-etags`），**沒有「對某端點
   排除某弱點類」的 API**；ZAP ascan 跑的是掃描政策、sqlmap 天生只做 SQLi。無法真的叫 Nuclei「XSS 交給
   ZAP 別測」。一個控制不了引擎的 dispatch 框架＝架構裝飾，給「有在協調」的錯覺卻無實效，違反簡潔優先。
2. **真實重疊早已處理**：唯一會實際重疊的利用情境 agent↔sqlmap 的 SQLi，已由 `kali_policy.reserve_sqlmap_targets`
   的 SHA-256 指紋＋Redis `sismember` 去重（fallback 只處理 agent 沒驗證過的 target）。
3. **預設部署下是假想問題**：`ARGUS_ZAP_ACTIVE_ENABLED` 與 Kali 預設都關，「三引擎對同一端點各打一次」
   在預設部署不會發生。

利用層的重疊因此由三道既有機制覆蓋，不需正式 planner：(a) agent↔sqlmap Redis 指紋去重；
(b) §5 agent 吃確定性發現、不重報；(c) `cross_layer` 跨層去重（最後保險）。ZAP active 維持獨立階段
（§6 的「併入利用相位」屬 §3 同款 cosmetic 合併，一併不做）。

### §5 Agent 相位：吃既有結果，不盲跑 **（已實作 2026-10-17）**
- `run_agent_for_scan(known_findings=...)` 由 `tasks.stage_agent` 傳入本次確定性工具已找到的資安發現；
  `_summarize_known_findings` 組成摘要（只給標題／端點／嚴重度，**不送 evidence**，去重上限 20）放進
  `ORCHESTRATOR_PROMPT` 的「確定性工具已找到的問題——不要重報」段。
- prompt 明示：這些已被確定性層找到，不要派專家重複確認或重報；你的工作是（a）情境判斷找出確定性層
  找不到的（差異式未授權、邏輯串接），（b）對既有發現做工具驗證/升級。
- 這直接消掉「Agent 盲跑 → 撞一堆重複 → 事後去重」的浪費（使用者最在意的點）。

### §6 階段順序
原構想：相依順序固定為 **發現 → 被動 → 主動探測 → 利用 → Agent → 計分**，修掉兩個倒置。審計後：
- 「Agent 排最後卻重新發現前面已找到的端點」——**已由 §5 解決**（agent 吃 `known_findings`，不重報）。
- 「`zap_active` 排在 `exposure` 之前」——`zap_active` 從**爬蟲 HAR** 建站台樹、不吃 exposure 結果，
  重排不會讓它多拿到端點；純 cosmetic，**不做**（同 §3/§4 的階段搬動結論）。
非資安階段（seo_links、geo_site、pagespeed、favicon、aeo_answers）與資安相位正交，維持現狀交錯。

---

## 非目標與不可消除的重疊（誠實邊界）
- **零事後對帳做不到**：Nuclei/ZAP/sqlmap 是各自帶規則庫的獨立引擎，連商業 DAST 也得去重。
  `cross_layer` 這類最後保險**保留**，但只處理「分工計畫沒攔住的殘餘」，不再是主要手段。
- **不重寫掃描引擎**：不自己實作一套 DAST 取代 ZAP/Nuclei；只調度它們、分工、共享攻擊面。
- **jsluice 等級的 JS 解析**：crawler 端若 regex 不夠，可移植 jsluice 邏輯，但不保證完全等價；
  以「補上秘鑰漏報」為第一優先，解析深度逐步逼近。

---

## 遷移計畫（逐刀，依價值／風險排序）

每一刀都獨立可上、可回滾，完成後更新本檔進度與 `CLAUDE.md`，跑全套測試。

| # | 刀 | 價值 | 風險 | 說明 |
|---|---|---|---|---|
| 1 | crawler 抓齊 JS → 端點＋秘鑰分析 | 高（補真實漏報＋CF 盲區） | 低（純增偵測） | §1；Katana 降級但不刪 |
| 2 | Agent 吃既有 findings 當輸入、prompt 不重報 | 高（消浪費） | 中（改 runner/prompt） | §5 |
| 3 | ZAP 被動二選一、移植獨有規則、退 `zap_passive` | 中（刪一個引擎＋抑制表） | 中（少數規則行為變） | §2；注意 `RENDERER_VERSION`/覆蓋 |
| 4 | 主動探測合併階段＋放寬 Nuclei/authz 預算 | 中（涵蓋率） | 中（逾時/計分） | §3 |
| 5 | 利用相位＋利用計畫分工（ZAP active 併入） | 中（源頭去重） | 高（動到授權/計分/取消） | §4；最後做 |
| 6 | 階段順序校正 | 低 | 低 | §6；併在前幾刀一起 |

**建議先做第 1 刀**（低風險、純補洞、CF 內外都生效），再做第 2 刀。第 3–5 刀動到計分與覆蓋契約，
要逐一驗證 `SCORING_VERSION`／`RULESET_VERSION`／`RENDERER_VERSION`／覆蓋狀態。

---

## 風險
- 任一刀改到「找出哪些問題／多嚴重」就要調 `RULESET_VERSION`；改計分公式調 `SCORING_VERSION`；
  改報告版面調 `RENDERER_VERSION`。歷史比較靠 `versions.comparable`，版本一變就不可直接比分。
- 退 `zap_passive`、合併階段會改覆蓋契約的 check 名單，`coverage.py` 與歷史比較要同步，舊掃描的
  coverage 仍要讀得動。
- 利用相位的分工若把某工具原本會測的 (端點×類) 指派錯，可能漏檢；每刀都要有對照測試。

---

## 狀態／進度（2026-10-17）
- 既有相關已落地（本輪稍早）：`cross_layer` 跨層去重（最後保險，將保留）、`zap_active` 觀測性
  skip 原因、`authz_probe` 未授權存取確定性探測。
- **第 1 刀核心已實作**：crawler 對讀到的 JS body 加跑秘鑰偵測（`crawler._collect_js_secrets` →
  `site_signals.js_secrets`，`tasks._js_secret_findings` 於 `stage_deep_security` 轉 finding），
  補上外部 .js bundle 秘鑰的真實漏報；JS 讀取上限 40→80。測試 `tests_js_secrets.py`。
  **未完**：主動抓齊未自然載入的 .js（瀏覽器 context 重抓）、強化端點抽取深度——因動到無單元測試
  保護的爬行迴圈，列為此刀後續增量，先不混入。
- **第 2 刀已實作**：Agent 吃確定性發現、不重報（`runner._summarize_known_findings` →
  `ORCHESTRATOR_PROMPT`，`stage_agent` 傳 `known_findings`）。測試 `agent/tests_known_findings.py`。
- **第 3 刀已實作**：退 `zap_passive` 階段，移植 4 條獨有規則成自家被動檢查
  （`security/passive_checks.py` ＋ `header_scanner` 的 Permissions-Policy）。測試 `tests_passive_checks.py`；
  更新 `tests_pipeline_stages`（階段順序去 zap_passive）、`tests_zap_passive`（移除 StageTests）、
  `tests_security_scanners`（clean headers 補 permissions-policy）。
- **第 4 刀已實作（縮小範圍）**：authz 探測端點上限改 `ARGUS_AUTHZ_PROBE_MAX_ENDPOINTS`（20→60、可調）。
  審計後**刻意不做**：盲目放寬 Nuclei 模板集／掃描範圍（噪音與時間退步，需獨立拍板＋實機量測）、
  exposure＋active_probe 階段合併（cosmetic、風險不值得）。
- **第 5 刀：評估後決定不建**（§4）。正式「利用計畫」分工對黑箱引擎（Nuclei/ZAP/sqlmap）控制不了，
  且真實利用重疊已由 agent↔sqlmap Redis 指紋去重＋§5＋`cross_layer` 覆蓋，預設部署下更是假想問題；
  硬建＝架構裝飾。階段搬動（§6）同屬 cosmetic，一併不做。

## 收尾（2026-10-17）
ADR-0005 的五相位分析完成，落地成果：
- **實作**：§1 crawler JS 秘鑰（第 1 刀）、§5 agent 吃確定性發現不重報（第 2 刀）、§2 退 ZAP 被動＋移植
  獨有規則（第 3 刀）、§3 authz 端點上限可調（第 4 刀）。加上本輪稍早的 `cross_layer` 跨層去重、
  `zap_active` 觀測性、`authz_probe` BOLA 確定性探測。
- **評估後不建**：§4 利用計畫 planner、§3/§4/§6 的階段合併與重排（cosmetic 或引擎控制不了）、
  §1 主動重抓未載入 .js（增量，待需要時再做）、Nuclei 模板集放寬（需產品拍板＋實機量噪音）。
- **去重現況**：設計性重疊已從源頭消除（被動不再跑兩引擎、agent 不盲跑重報）；殘餘由三道確定性
  機制（Redis 指紋、known_findings、cross_layer）覆蓋，**非 AI 事後審查**。

## 補遺（2026-10-17，17AF 報告逐項審查）
一次實機重掃（17AF）逐項審查後補強 `cross_layer`，並記錄一個刻意不做：
- **`cross_layer` 第二個 pass（已實作）**：原本只處理「確定性 exposure ↔ Agent 同端點」。17AF 出現
  Agent↔Agent 跨掛載路徑的同資源重複——`/api_proxy/visits`（高）與 `/backend/visits`（低）是 Next.js
  rewrite 指向的**同一個後端資源**，被計分扣兩次、嚴重度還一高一低。新增 `_canonical_resource` 剝除
  反向代理／BFF 掛載前綴（`_MOUNT_SEGMENTS`，通用命名慣例），**同資源＋同弱點類型**的 Agent 發現
  只留最嚴重那筆（不同弱點類型不併，修法不同）。測試 `tests_cross_layer.AgentCrossPathMergeTests`。
- **跨類別同源收斂（評估後不做）**：17AF 的密碼欄位明碼同時出現在資安（`form-password-unmasked`，
  確定性）與 UX（Agent 觀察）兩節。原先設想以「同 URL＋同 selector」收斂，但 `form_scanner` 的確定性
  發現**不存 CSS selector**（只有 url＋fields），key 對不上；且明碼密碼欄位本就是資安（CWE-549）與
  可用性兩個不同面向的問題，各自扣各自分類的分數可辯護，硬併反而抹掉一個合理訊號。以模糊措辭比對
  風險（誤殺真發現）不值得，故不做；若日後要降 Agent 重覆噪音，較穩的是把確定性發現餵給 UX agent
  （第 2 刀對資安 orchestrator 的做法），但那是建議性、無法保證消除，另案再議。
