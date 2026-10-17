# 跨層去重擴充：Agent↔Agent 同後端資源（跨掛載路徑）合併

**日期**：2026-10-17
**操作者**：Claude
**來源**：使用者對一次實機重掃報告（代號 17AF）逐項審查後，指出資安發現有「同一件事報兩筆、
嚴重度還一高一低」的系統性重複，要求「開這刀」修報告引擎的去重缺口。

## 問題
`cross_layer.consolidate_cross_layer` 原本只處理「確定性層 exposure ↔ Agent 層打同一端點」一種重複。
審查發現第二種重複沒被攔到：

- Next.js rewrite `/api_proxy/:path* → 後端`，直連路徑是 `/backend/*`，兩者打到的是**同一個後端資源**。
- Agent 可能各打一次、各報一筆：某授權目標同一個 `visits` 端點的錯誤訊息洩內網 IP，
  `/svc/visits`（代理路徑）報「高」、`/alt/visits`（後端路徑）報「低」。
- 兩筆 rule_id 不同（`agent-observed-security-<雜湊>` 的錨點是端點路徑），`consolidate_security_findings`
  （agent runner 內、以 rule_id／標題相似度比對）看不出是同一件事 → 計分扣兩次、報告列兩次、嚴重度打架。

另有兩對重複經審查**判定不是 bug**，不動：
- 代理 vs 後端的 `members/all`（成員個資）：一筆歸「外洩」類、一筆歸「未授權」類，且後者還涵蓋多個
  端點（industry／campus／pastProjects），不是純重複——不同弱點類型不併（修法不同）。
- `v2/api-docs`（確定性 exposure）vs `v3/api-docs`（Agent）：版本路徑不同、確定性那筆可重現，各自獨立。

## 修法
`cross_layer.py` 改成兩個 pass：
1. **確定性 exposure ↔ Agent 同端點**（原行為不變）：丟 Agent 那筆。
2. **Agent ↔ Agent 同後端資源**（新增）：`_canonical_resource` 剝掉反向代理／BFF 的掛載前綴
   （`_MOUNT_SEGMENTS`＝api／api_proxy／apiproxy／backend／bff／gateway／proxy／rest，**通用命名慣例、
   非任何目標特定路徑**，與 `katana_scanner._API_ENDPOINT_HINT` 同精神；只剝開頭一段且後面要還有資源，
   裸 `/api` 不剝、非掛載詞 `/shop/...` 不剝），`/api_proxy/x` 與 `/backend/x` 正規化成同一鍵。
   **同資源＋同弱點類型**（`findings.vuln_class`）的 Agent 發現只留最嚴重那筆（`findings.rank`：
   嚴重度優先、已用工具驗證者優先）。只併 Agent 層，確定性層身分不動；不同弱點類型不併。

被丟的那筆同樣由 `tasks.stage_scoring` 連 DB 列一起刪（沿用既有機制，以 rule_id 刪）。

## 刻意不做（§跨類別同源收斂）
原本向使用者提議「同 URL＋同 selector 跨類別收斂」修密碼欄位明碼同時進資安＋UX 的重複。實作前讀
`form_scanner.py` 發現確定性的 `form-password-unmasked` **不存 CSS selector**（只有 url＋fields），
提議的 key 根本對不上該案例；且明碼密碼欄位本就是資安（CWE-549）與可用性兩個面向，分別扣各自分類
的分數可辯護，硬併反而抹掉一個合理訊號。模糊措辭比對有誤殺真發現的風險，不值得——不做。
（細節與未來備案見 ADR-0005 補遺。）

## 驗證
- 新增測試 `tests_cross_layer.AgentCrossPathMergeTests`（7）：同資源跨掛載取最嚴重、順序無關、
  不同弱點類型不併、不同資源不併、非掛載前綴不剝、裸掛載詞不併、確定性那筆不被 Agent 合併波及。
- `apps.scans` 全套 1450 通過（skipped 12）；`ruff check` 乾淨。
- `RULESET_VERSION` 已是今日（2026.10.17，同日其他刀更新過），同日變更共用日期，不再加碼。

## 殘餘（已知、未做）
- Agent 跨掃描「持續 vs 新出現」仍可能因鍵漂移錯分（更早的 log 已記；需動 `issue_groups` 熱路徑）。
- 要降 Agent 對確定性已知問題的重覆回報，較穩做法是把確定性發現餵給 UX agent（第 2 刀對資安
  orchestrator 的延伸），屬建議性、無法保證，另案再議。

## 備註（安全）
本 log 的端點一律用虛構值（`/svc`、`/alt`、`members/all` 等一般字詞），不含真實站名、真實內部路徑或
內網 IP；對應真實目標的 API 文件外洩與內網 IP 仍未修補，相關報告不得在修補前對外流通。
