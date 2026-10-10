# AI 爬蟲清單擴充 + GEO 內容衰退 + RAG 分塊（借鑑 GeoReady）

**日期**：2026-10-10  
**操作者**：Claude

## 變更內容
延續「借鑑 GeoReady（MIT, auriti-labs）」,依使用者指定順序 A→B→C 加入三項,全為純解析、零額外請求、軟訊號:

- **A. AI 爬蟲清單 13 → 24（`ai_bots.py`）**：新增 Google-CloudVertexBot、cohere-ai、AI2Bot、PetalBot（訓練）、Applebot、Amazonbot、DuckAssistBot、YouBot、xAI-Bot（AI 搜尋）、Meta-ExternalFetcher（使用者觸發）。刻意不加 Googlebot／Bingbot（其 robots 已由 SEO 層涵蓋，避免重複）。
- **B. GEO 內容衰退預測（`geo_decay.py`，新檔）**：有篇幅正文頁同時出現過去年份、時效性措辭、軟體版本、定期價格 ≥2 類會變動的內容時 → `geo-content-decay`（資訊）。補 `geo_entity.freshness_findings`（只看日期標記）之外的「內容實質會不會過時」。footer 版權年份由正文擷取排除，當年／未來年份不算。
- **C. GEO RAG 分塊就緒（`geo_rag.py`，新檔）**：有 ≥2 小標題、但正文總字數 ÷ 小標題數的平均區段 > 280 字時 → `geo-rag-chunking`（資訊）。補 `geo_structure`「長文完全無小標題」之外的「有分段但分不夠細」。
- B、C 接在 `scanners.analyze_geo` 的 GEO 分支（structure／citability 之後）。
- 測試：`tests_geo_decay.py`（6）、`tests_geo_rag.py`（6）；A 沿用既有 `tests_ai_bots.py`（8，數量未硬編碼）。
- 文件：`backend/apps/scans/CLAUDE.md`（ai_bots 24、geo_decay、geo_rag）、`docs/scan-stage-checks.md`（GEO 表三列＋AI 爬蟲 24）、競賽需求書 ARGUS-F-012 同步。

## 原因
使用者審查 GeoReady 後，挑出對 Argus GEO 最有價值且零成本的三項補強：擴充 AI 爬蟲覆蓋、補內容時效性與 RAG 可分塊性兩個 Argus 原本沒有的內容訊號。

## 影響範圍
- 勾 GEO 的掃描，有篇幅正文頁可能多出最多 2 項資訊級建議（衰退、分塊），都不重扣分。
- 封鎖更多 AI 搜尋／使用者觸發爬蟲的網站，可能多出 `geo-ai-search-bots-blocked`（規則不變，只是涵蓋更多 bot）。
- 都是當天規則集變更，`RULESET_VERSION` 維持當日版本。覆蓋契約沿用既有 `page_geo`。

## 驗證方式
- 三項新測試 + ai_bots + pipeline/coverage/scoring/report 回歸共 88 項通過；`ruff check backend` 與 `manage.py check` 通過。
- 誤報防護已鎖測試：薄頁不出題、單一衰退訊號不報、當年／未來年份不算過時、無小標題不報分塊（屬 geo_structure）、分塊良好（多小標題）不報。
