# Finding 正典身分與分數分離（Canonical Finding Identity & Score Split）

Argus 的掃描分兩層產生 finding：**確定性層**（規則引擎、Nuclei、ZAP、敏感檔探測、未授權／IDOR
探測…）與 **AI Agent 層**（recon→orchestrator→specialist 的 LLM 滲透測試）。這兩層目前各自算
「這是哪一筆問題」的身分，跨掃描比較與「已修好」判定、以及計分，都建立在這個不統一的身分上。
結果是三個反覆咬人的症狀：

1. **「已修好」誤判**：舊掃描有、新掃描沒有的問題，靠「消失」推斷為 resolved。Agent finding 的
   `rule_id` 是「弱點類型＋端點路徑」的雜湊（`findings.agent_security_rule_id`），描述或端點一微調
   就換鍵——鍵消失不代表修好。實測重掃描述微調後舊鍵被誤標「已修好」而問題仍在。
2. **分數隨 agent 運氣跳動**：帶 high／critical 的 agent finding 時有時無（同站同碼，`members` API、
   登入明文密碼等 scan 之間 0 交集），headline 分數跟著 7→10→20、UX 26→53，破壞「看趨勢」。
3. **打地鼠**：每種 finding 各自補身分判定（2026-10-16 agent 資安獨立代號、2026-10-17 agent-observed
   一律不判 resolved）——是逐類打補丁，不是一次解決。

本 ADR 把「問題身分」與「分數組成」當成**架構層**處理，一次解掉上述三症狀的共同根因。這是
**實作計劃**，撰寫時尚未改動任何計分或比較程式；所有「現況」對照 2026-10-18 的
`backend/apps/scans/`（`coverage.py`、`projects.py`、`scanners.py`、`versions.py`）。

> **與既有工作的關係**：這份 ADR 承接、不取代以下這個 session 已落地的局部修補——
> `security-unauth-api-records`／`security-idor-enumerable-object`（未授權 BOLA 已沉澱成確定性，
> Codex #1 已大致完成）、agent-observed 一律不判 resolved（#3 的半套）、深度 agent 改 opt-in
> （#5 的壓力已降低）。本 ADR 把這些點收斂成一個統一模型。與 [ADR-0005](0005-scan-pipeline-tool-integration.md)
> 正交：0005 管「工具怎麼排、不重複產生」，本檔管「產生後怎麼認身分、怎麼算分」。

---

## 現況（錨點，其餘敘述服從）

- **跨掃描鍵** `coverage.issue_key(rule_id, category, title)` ＝ `rule_id or f"{category}:{title}"`。
  確定性 finding 的 `rule_id` 穩定（如 `security-unauth-api-records`），但**不含端點**——同一條規則
  打到不同端點會被當成同一筆合併。Agent finding 的 `rule_id` 是雜湊、會漂。兩者用同一個 `issue_key`
  但穩定性天差地遠。
- **resolved 判定** `coverage.absent_issue_status(...)`：前次有、本次沒有的問題，回查「是哪一項
  檢查產生的」，只有該檢查本次 completed 且受影響頁面有重新分析才算 `resolved`；agent-observed
  一律 `not_observed`。**「沒再出現」是目前唯一訊號**——沒有「重探同端點、確認真的回 401/403/404」
  這個正向驗證。
- **分數** `scanners.calculate_scores`：每維度一個 0–100 分，所有 finding（含 agent）一起衰減扣分，
  產出單一 `category_scores`。`versions.comparable(a, b)` 只在 `scoring_version`＋`ruleset_version`
  相同時允許直接比較——但**同版本下**，agent finding 的有無仍讓同站分數跳動，`comparable=True`
  卻不穩定。

---

## 原則

1. **身分屬於「問題」，不屬於「哪個工具找到它」**。同一個洞不論被確定性規則還是 agent 打到，
   跨掃描都該是同一筆。
2. **「已修好」是一個主張，必須有正向證據**。問題從報告消失有很多原因（工具沒跑、agent 沒探到、
   端點改名、被 WAF 擋）——只有「重探同一個資源、確認防護已生效」才能說修好。
3. **headline 分數要可比較**。使用者看趨勢的那個數字，不能被非確定性的 agent 運氣帶著走。
4. **Agent 的價值要被看見，但要隔離**。agent 的深測發現照樣要呈現、要能影響決策，只是不污染
   可比較的基準分。

---

## 決策 A：正典身分 ＝ 正規化資源 ＋ 穩定弱點類別

兩層共用一個 `finding_identity(finding) -> str`（新增在 `coverage.py` 或獨立 `finding_identity.py`），
鍵由兩段組成：

- **正規化資源**：端點路徑經 `_canonical_resource`（已存在於 `cross_layer.py`：剝 `/api_proxy`
  `/backend` 等掛載前綴、數字段換 `#`、去查詢字串、小寫）得到的標準形；沒有端點的站台層級問題
  用「站台」當資源。
- **穩定弱點類別**：`owasp_category`＋`cwe_id`（已由 `security/owasp_mapper.py` 對確定性 finding
  填值）。Agent finding 也要在落地時 tag OWASP／CWE（runner／findings 補），不再靠描述雜湊。

鍵形如 `bola|/api/users/#|A01|CWE-639`。**用途**：
- 跨掃描比較（`projects.compare_issues`、`compare_issues` 的 `keys_by_scan`）改用它，取代 `issue_key`
  的 `rule_id or title`。
- 同次掃描跨層去重（`cross_layer`）可用同一把鍵判「確定性與 agent 是不是同一筆」，減少現在靠
  bridge-concept 手列的特例。

**相容**：`issue_key` 保留給舊掃描（沒有 owasp/cwe 的資料）回退；新掃描寫入 `coverage` 時同時存
正典鍵，`versions` 升一版標記「身分模型 v2」，只有兩次都是 v2 才用正典鍵比較，否則回退舊鍵。

## 決策 B：resolved 只由「正向重探」認定

新增一個**收尾階段的輕量重探**（`stage_scoring` 之前或 `compare_issues` 時觸發，受同樣的全站＋
主動＋已授權閘）：對「前次有、本次的確定性檢查沒再產生」且**有端點**的問題，用無憑證／原請求
重打一次那個資源——

- 回 401／403／404（或敏感欄位消失、成批資料不再回傳）→ 標 `resolved`（正向驗證通過）。
- 回 200 且資料仍在 → 其實沒修好，**本次補一筆 finding**（修掉「漏報」）。
- 打不到／逾時／被 WAF 擋 → `not_observed`（維持現況的保守值，不冒稱修好）。

站台層級、無端點、或需登入態才能判的問題，維持 `absent_issue_status` 的現行邏輯（不退步）。
**鐵律**：任何情況下「沒再出現」本身都不足以標 resolved；resolved 一定對應一次成功的重探。

## 決策 C：headline 分數（確定性基準）與 agent 深測分離

- `category_scores`（headline、趨勢、`comparable` 比較用）**只由確定性層 finding 計算**。這組分數
  同站同碼每次一致。
- Agent finding 不進 headline 衰減，改成獨立呈現：報告與前端的「AI 深度測試」區塊照常列出（含
  嚴重度、證據、OWASP／CWE），並可給一個**獨立的** `agent_findings_summary`（筆數／最高嚴重度），
  但不混入可比較的主分數。
- 計分版本升一版（`SCORING_VERSION`）；`comparable` 的語意變成「確定性基準分可比較」，agent 區塊
  本就不宣稱可比較。

**理由**：使用者要的「趨勢」只有確定性層能誠實提供；agent 是非確定性的深測，當附錄最誠實。深度
agent 已是 opt-in（勾選才跑），所以「沒勾的掃描」headline 本來就穩，這條把「勾了也不污染趨勢」補齊。

---

## 非目標（不做、不退步）

- **不關閉或弱化 agent**：agent 照跑、照呈現，只是身分統一、分數隔離。不因為「確定性沒找到」就
  跳過 agent（那是 Codex #2 的限縮，本 ADR 不採，`coverage_summary` 的 revert 是前車之鑑）。
- **不改 OWASP／CWE 的對映邏輯**，只是把它當身分的一部分並要求 agent 也 tag。
- **不碰計費**：分數分離不影響扣點（計費看頁數×維度＋固定附加費，與分數無關）。
- **resolved 的重探受既有授權閘**（全站＋主動＋已授權），不對未授權目標發新請求。

---

## 落地順序（每刀完成回來更新本檔與 `apps/scans/CLAUDE.md`）

> **實作狀態（2026-10-18）：第 1～4 刀已全部落地並通過測試。** 落地中對決策 B 的「回 200 補一筆
> finding」採保守做法（見下）；其餘依本計劃實作。

1. ✅ **身分函式**：`finding_identity`＋兩層落地時都帶 owasp/cwe（agent 補 tag）；`coverage` 同時存
   正典鍵與舊 `issue_key`。單元測試鎖「同洞不同措辭／不同掛載前綴 → 同鍵」。
   （`finding_identity.py`、`owasp_mapper.tag` agent 退回、coverage v2、`tests_finding_identity`）
2. ✅ **比較改用正典鍵**（v2＋v2 才用，否則回退）；`compare_issues`／總覽 `changes.resolved` 接上。
   （`projects.compare_issues`、`absent_issue_status(by_identity)`、`tests_coverage.IdentityComparisonTests`；
   `issue_streaks` 仍以 issue_key 計算，未改。）
3. ✅ **正向重探 resolved**（決策 B）：把上次端點型確定性發現依層分流併入本次探測——authz 端點進
   無憑證 authz 探測、exposure 檔案端點進 `probe_paths(extra_paths=...)`——仍存在的由該層分析器
   重新找到（**漏報自癒，含仍可讀的 exposure 檔案**），回 401/403/404 且本次沒再被報才標 resolved。
   IDOR `#` 模板不直接重探（保守）；resolved 一律要有成功重探（回封鎖狀態），絕不靠「消失」推斷。
   （`tasks._previous_deterministic_endpoints`／`_mark_reverify_resolved`、`exposure_scanner.probe_paths`
   的 `extra_paths`、coverage `reverify_resolved`、`tests_coverage.ReverifyResolvedTests`）
4. ✅ **分數分離**（決策 C）：headline 只吃確定性 finding（`is_agent_observation` 濾掉 agent 觀察），
   agent 另出 `agent_findings_summary`（migration 0037）；`SCORING_VERSION` 5；報告導讀句與資安分析頁
   註明基準分不含 AI 深度測試；競賽 Word 內容 md 同步。**只分離 `agent-observed-security-*`**（使用者
   拍板）：agent UX（`AGENT_UX_*`）與 Kali（`kali-*`）仍計分。（`scanners.summarize_agent_security`、
   `tests_scoring_and_report_grouping.AgentScoreSeparationTests`）
5. ✅ 文件：`apps/scans/CLAUDE.md`、`RENDERER_VERSION` 35、競賽 Word 內容 md、各刀 log 同步完成。

## 風險與未決

- **正典鍵把兩個其實不同的洞併成一筆**（同端點同 CWE 但不同參數）：先保守——資源正規化不要剝過頭
  （`_canonical_resource` 已只剝開頭一段），必要時把「參數名」也納入鍵。先上線觀察，別一步到位。
- **分數分離後 headline 可能「變好看」**：因為 agent 的 high/critical 不再扣 headline。要在報告明講
  「資安基準分不含 AI 深度測試；深度測試另列」，避免使用者誤以為變安全——與既有 `SCORE_NOTE` 同處。
- **重探增加請求**：受授權閘＋只對「前次有、本次疑似消失」的少數端點重打，量可控；逾時要有上限。
- 本 ADR 未涵蓋 Codex #4（CDN scan profile）與 #6（管線可觀測性）——另案，優先序較低。
