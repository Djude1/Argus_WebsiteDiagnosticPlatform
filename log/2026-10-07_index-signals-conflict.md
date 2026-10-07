# sitemap／robots.txt／noindex／canonical 一致性交叉檢查（roadmap §1 SEO 第 3 項）

**日期**：2026-10-07  
**操作者**：Claude

## 變更內容
- 先確認現況：roadmap 標「待驗證」。
  - 原本 `site_checks` 只檢查 robots.txt 與 sitemap 是否存在。
  - `seo-primary-url-inconsistent` 只比對宣告的主機。
  - 沒有「sitemap 列出的網址」與「頁面實際狀態」的交叉檢查。
- 新增 `seo/site_findings.index_signal_conflicts`，產生 `seo-index-signals-conflict`（低）。矛盾分六類，逐類列網址：
  - sitemap 列出設為 noindex 的頁面。
  - sitemap 列出 canonical 指向其他網址的頁面。
  - sitemap 列出回應錯誤的網址。
  - sitemap 列出會轉址的網址。
  - sitemap 列出 robots.txt 禁止 Googlebot 抓取的網址。
  - noindex 頁面被 robots.txt 擋住：Google 讀不到 noindex，網址仍可能出現在搜尋結果。
- 判斷範圍：
  - 只比對本次爬到的頁面，與 crawler 讀到的 sitemap 網址（最多掃描頁數上限個）。
  - 被 WAF 等攔截的頁面不判斷。
  - robots.txt 依 Googlebot 群組判斷，沒有點名才用 `*`；Allow／Disallow 取最長路徑。
- 改動的檔案：
  - `ai_bots.robots_allows()`：新公開函式，共用 RFC 9309 解析。
  - `crawler.probe_site_signals`：保留 robots.txt 原文（`site_signals.robots_text`，上限 512 KB）。
  - crawler 主流程：保留 sitemap 網址清單（`site_signals.sitemap_urls`）。
  - `tasks.stage_seo_links`：把這兩項資料傳給 `seo_site_findings`。
- `reports.py`：判斷依據與限制、驗證方式（sitemap.xml＋Search Console 網址檢查）。
- 文件：scans CLAUDE.md、roadmap、需求書 SEO 段落。

## 原因
sitemap 應只列希望被收錄的正式網址；與 noindex、canonical、robots.txt 互相矛盾時，搜尋引擎可能忽略 sitemap、浪費爬取額度，或收錄不想被收錄的頁面。

## 影響範圍
- 有矛盾的網站多一項低風險 SEO 問題。
- 單頁掃描不讀 sitemap，只會判斷「noindex 頁被 robots.txt 擋住」。
- 不需要 migration；`RULESET_VERSION` 今天已是 2026.10.07。

## 驗證方式
- 新測試 `tests_index_signals.py`（8 項）：
  - 一致的網站不列問題。
  - sitemap 列出四種不可索引頁面，含 noindex、canonical 指他頁、HTTP 404、轉址。
  - 不在 sitemap 的頁面不判斷。
  - Googlebot 點名群組優先於 `*`，含查詢字串。
  - noindex 頁被 robots.txt 擋住。
  - WAF 攔截頁略過。
  - finding 形狀。
  - `robots_allows` 的 `$`、最長比對與 Allow 規則。
- `tests_seo_analysis.py`：
  - 階段測試的假 ctx 補上 `site_signals`。原本是 Mock，會讓 site findings 轉換靜默失敗。
  - 新增「階段把 sitemap／robots 傳給檢查」測試。
- 真實網站（抓 robots.txt、sitemap 前 15 個網址與各頁 HTML），逐筆以 curl 核對屬實：
  - wordpress.org：5 個 sitemap 頁面設 `noindex,follow`。
  - docs.djangoproject.com：舊版文件 canonical 指向新版 7 頁；`/index/` 302 轉址 2 頁。
  - smashingmagazine.com：sitemap 列 `/category/`，canonical 是 `/categories/`，3 頁。
  - ntub.edu.tw、blog.cloudflare.com 沒有問題；ntubimdbirc.tw、python.org、gov.tw 拿不到 sitemap 網址。
- 全套 `uv run python backend/manage.py test apps`：1670 項 OK（3 skipped）。
- `ruff check backend` 通過；`makemigrations --check` 無變更。
