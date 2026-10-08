# GEO 內容新鮮度：文章日期缺少、不合理、標記不一致（roadmap §3 GEO 第 2 項）

**日期**：2026-10-08  
**操作者**：Claude

## 變更內容
- `geo_entity.py` 擴充：沿用同一套文章頁判斷（排除列表頁）。
  - 收集每篇文章的 JSON-LD `datePublished`／`dateModified`，以及 `article:published_time`／`article:modified_time`。
- `parse_date`：取日期部分，支援 ISO 8601 與「2026-10-06 10:00:00 +0000 UTC」這類寫法。
- `freshness_findings(summary, today)`（GEO，`impact_area=freshness`，低風險）：
  - `geo-article-date-missing`：兩種來源都沒有日期。
  - `geo-article-date-invalid`：更新日期早於發布日期，或日期在未來；容許 1 天，避免時區造成的跨日。
  - `geo-article-date-inconsistent`：JSON-LD 與 meta 的發布或更新日期相差超過 1 天。
- `tasks.stage_geo_site`：以 `timezone.localdate()` 呼叫。
- `reports.RULE_BASIS`：三條規則的依據與限制。
- 文件：scans CLAUDE.md、roadmap、需求書 GEO 段落。

## 刻意不做
- 不判斷內容「舊不舊」：長青內容（教學、介紹）不需要常更新，以年份判過時會誤導。
- 不比對 HTTP `Last-Modified`：動態網站每次回應都是當下時間，比對沒有意義。

## 真實網站核對（首頁＋同網站 10 個連結）
- css-tricks.com 5 篇文章、blog.gslin.org 1 篇：JSON-LD 與 meta 的發布與更新日期一致，沒有誤報。
- smashingmagazine、wordpress.org/news、blog.cloudflare.com、technews 的取樣頁沒有被判為文章（列表頁或沒有文章標記）。

## 影響範圍
- 文章日期有缺漏或矛盾的網站，GEO 多一到三項低風險問題。
- `RULESET_VERSION` 今天已是 2026.10.08；不需要 migration。

## 驗證方式
- `tests_geo_entity.py` 新增 5 項，共 14 項：
  - 一致的日期（含時區跨日）不列問題。
  - 缺日期。
  - 更新早於發布與未來日期。
  - JSON-LD 與 meta 不一致。
  - 日期解析格式。
- 全套 `uv run python backend/manage.py test apps`：1699 項 OK（3 skipped）。
- `ruff check backend` 通過；`makemigrations --check` 無變更。
