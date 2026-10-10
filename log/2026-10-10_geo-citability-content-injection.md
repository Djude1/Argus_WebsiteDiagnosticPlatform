# GEO 可引用性 + 頁面 AI 提示詞注入偵測（借鑑 GeoReady）

**日期**：2026-10-10  
**操作者**：Claude

## 變更內容
借鑑開源 GeoReady / geo-optimizer-skill（MIT, auriti-labs）的兩個檢查，改寫成 Argus 風格（stdlib、無 BeautifulSoup、接覆蓋契約與 make_finding）：

- **GEO 可引用性 `apps/scans/geo_citability.py`**（新檔）：依 Princeton「GEO: Generative Engine Optimization」(KDD 2024) 的內容訊號，對有篇幅的正文頁（`content_size` 換算 ≥ `MIN_PROSE_WORDS`＝200）檢查三項——`geo-citability-no-sources`（低）、`geo-citability-no-statistics`（資訊）、`geo-citability-no-quotations`（資訊）。軟訊號、刻意壓低嚴重度，短頁／導覽頁不出題。由 `scanners.analyze_geo` 的 GEO 分支呼叫（接在 structure_findings 之後）。
- **AI 提示詞注入 `apps/scans/security/content_injection.py`**（新檔）：`detect_content_injection(html)`（stdlib `html.parser`）＋`build_injection_finding`。只有命中明確 LLM 操縱指令字樣（可見文字／HTML 註解／隱藏區塊）或 AI 專用 `data-*` 屬性才判定——`security-ai-prompt-injection`（高；隱藏或註解＝刻意隱藏；只在可見文字且頁面有留言區＝可能第三方 UGC 降中）、`security-ai-suspicious-markup`（低，只有 data-ai-* 或異常不可見字元）。一般 `display:none`／摺疊選單不成立（刻意保守避免誤報）。由 `tasks._analyze_one_page` 資安分支被動呼叫（同 secret_scanner，零額外請求）。
- 登記：`owasp_mapper`（`security-ai-prompt-injection`→A03/CWE-74、`security-ai-suspicious-markup`→A05/CWE-451）、`finding_kind`（prompt-injection＝suspected、suspicious-markup＝exposure）。
- 測試：`tests_geo_citability.py`（8 項）、`security/tests_content_injection.py`（10 項）。
- 文件：`backend/apps/scans/CLAUDE.md`、`security/CLAUDE.md`、`docs/scan-stage-checks.md`（GEO 表＋資安表）、競賽需求書 ARGUS-F-012／資安段同步。

## 原因
使用者審查 GeoReady 專案後，挑「可引用性」與「內容注入偵測」兩項對 Argus 最有價值、且純解析零額外請求的檢查引入：前者補 Argus GEO 偏結構面、缺內容訊號的空白（且有論文依據）；後者是 Argus 原本完全沒有、橫跨資安與 GEO 的新檢查。

## 影響範圍
- 勾 GEO 的掃描，有篇幅的正文頁可能多出最多 3 項可引用性建議（多為資訊、一項低風險）。
- 勾資安的掃描，逐頁多一道注入偵測；正常網站不應命中（保守規則）。命中明確指令時列高風險。
- 覆蓋契約：citability 併入既有 `page_geo`、injection 併入 `page_security`，不需新檢查登記。
- 兩者都是當天的規則集變更，`RULESET_VERSION` 維持當日版本 `2026.10.10.4`。

## 驗證方式
- `tests_geo_citability`＋`tests_content_injection`：18 項通過。
- 回歸：`tests_pipeline_stages`／`tests_coverage`／`tests_project_security`／`tests_report_evidence_quality`／`tests_accuracy_review` 共 57 項通過。`ruff check backend` 通過。
- 誤報防護已鎖測試：摺疊選單（display:none＋aria-hidden 導覽）不觸發；`<script>` 內字串不當頁面文字；薄頁不評可引用性。
