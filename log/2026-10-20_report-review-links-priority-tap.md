# 報告審查修正：連結無法確認說明、站外檢查額度、優先清單排序、觸控目標門檻

**日期**：2026-10-20  
**操作者**：Claude

## 變更內容
- C-7 `seo/link_trend.unconfirmed_caveat`：站內已嘗試檢查的連結 ≥10 個且 ≥50% 為 restricted／timeout／error 時，產生「比較可能是 WAF 或速率限制擋下檢查，不代表失效」說明（附主要 HTTP 狀態）。`seo/report.py` links 區塊回 `caveat`（`CACHE_VERSION` 4）；報告 `report_site_metrics._links` 帶出、`report_render` 連結檢查段顯示（schema 加 `caveat`，`RENDERER_VERSION` 37）；SEO 頁 `LinkCoverageNote` 先顯示。
- C-8 `seo/collect._reserve_outbound`：25% 保留額度在子網域與站外之間對半分、互補不足。
- C-11 `scanners.calculate_scores` 的 `top_actions`：排序改「嚴重度 → 出現頁數 → priority_score」，項目附 `pages`。
- C-12 `crawler.collect_ux_signals`：觸控目標改「短邊 < 24px，或寬高都 < 40px」才列（`_WCAG_AA_TAP_TARGET_PX`）；`scanners._ux_tap_targets` 描述同步。
- 測試：`tests_seo_reuse`（額度對半、caveat 門檻）、`tests_scoring_and_report_grouping`（排序）、`tests_tap_targets`（300×39 不列、30×30 列，真實 Chromium）。
- 文件：`apps/scans/CLAUDE.md`、`frontend/CLAUDE.md`。

## 原因
2026-10-19 cs.ntust.edu.tw 實掃報告審查：站內 242 個連結 113 個「無法確認」、範圍表寫「無法連線 138」卻沒說是 WAF 406；站外 6 個有 4 個未檢查（子網域 35 個吃光額度）；優先清單第 1 名是只影響 2 頁的 JS 渲染、47 頁的 ARIA／CLS 排後面；「國立臺灣科技大學資訊管理系（345×39px）」因高度差 1px 被列為觸控目標過小。

## 影響範圍
- 觸控目標判定變寬鬆：橫條型連結不再列；`RULESET_VERSION` 未改（同一版規則集內的門檻微調，分數差異極小），下次改規則集時一併升。
- `top_actions` 順序改變會影響總覽「優先改善建議」與報告第 2 章；既有掃描的保存值不變，重算（`renormalize_findings`）才會更新。
- 報告版面升 37，既有報告重新下載會重產。

## 驗證方式
- `uv run ruff check backend` 通過；`manage.py test apps.scans`（`ARGUS_TEST_CHROMIUM_PATH` 指向 /opt/pw-browsers）1523 項通過（skipped 3）。
- 前端 `npm run lint` 0 error、`npm run typecheck`、`npx vitest run` 304 項通過。
