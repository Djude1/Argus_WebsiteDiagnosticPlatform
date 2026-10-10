# Trust Stack 五層信任分（借鑑 GeoReady）

**日期**：2026-10-10  
**操作者**：Claude

## 變更內容
借鑑 GeoReady / geo-optimizer-skill（MIT, auriti-labs）的 trust_stack，做成 Argus 的資訊參考（像 observatory，不產生問題、不改分數、不發請求）：

- **`apps/scans/trust_stack.py`（新檔）**：`evaluate(findings_rules, observatory, categories)` 把**既有訊號**聚合成五層信任分，每層 0–100＋等第，總分為已評估各層平均：
  - 技術信任＝直接沿用 observatory 分數（勾資安時）。
  - 身分／社群／學術／一致性＝依本次 findings 的規則代號有無扣分（如 `geo-entity-organization-missing`、`geo-entity-no-same-as`、`geo-citability-no-sources`、`geo-article-date-*`／`geo-content-decay`／`seo-index-signals-conflict`／`seo-duplicate-titles`）。只在對應維度有掃到時評分，否則「未評估」。
  - `summary_line` 給報告「網站架構」一行；不重新偵測、不計入分數。
- **`site_profile.py`**：`build_site_profile` 計算並存 `site_profile["trust_stack"]`；`VERSION` 2→3。
- **`reports.py`**：報告「網站架構」事實表加「信任輪廓（五層）」一列（與 observatory 同結構，schema 不變）；`RENDERER_VERSION` 20→21。
- **序列化**：`site_profile` 本就在 `ScanJobSerializer`，前端「網站架構」分頁已自動收到 `trust_stack` 資料（UI 卡片留待後續）。
- 測試：`tests_trust_stack.py`（7）；修 `tests_site_profile.py` 的 version 斷言 2→3。
- 文件：`backend/apps/scans/CLAUDE.md`（site_profile 階段、RENDERER_VERSION 21）、`docs/scan-stage-checks.md`（網站概況）、競賽需求書 ARGUS-F-013 同步。

## 原因
使用者要在 GeoReady 借鑑清單中加入 Trust Stack。它把 Argus 已經分散算出的訊號換角度聚合成「AI／搜尋引擎眼中的可信度輪廓」，讓使用者一眼看出哪一層強弱，呼應平台定位；零額外成本（純聚合）。

## 影響範圍
- 掃描完成後 `site_profile.trust_stack` 多一塊資料；報告「網站架構」多一行；都不影響分數與問題清單。
- 未掃到的維度對應層標「未評估」，不硬湊分數。
- 報告版面版本 +1，舊掃描重新下載會重產（既有機制）。

## 驗證方式
- `tests_trust_stack`（7）＋ site_profile／report_payload／report_layout／report_compactness／report_verification／pipeline_stages／project_security 回歸通過；`ruff check backend` 與 `manage.py check` 通過。
- 邏輯鎖定：無負面規則→各層滿分；技術層取 observatory 分數；citability／一致性規則正確扣分；未掃維度不列入總分。
