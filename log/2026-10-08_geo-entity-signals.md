# GEO 實體與權威訊號：組織實體、sameAs、文章作者（roadmap §3 GEO 第 1 項）

**日期**：2026-10-08  
**操作者**：Claude

## 變更內容
- 新增 `backend/apps/scans/geo_entity.py`：讀爬蟲已保存的頁面（rendered_dom 優先），只看 2xx 且沒被阻擋的頁面，不發任何請求。
  - **組織實體**：JSON-LD 中 Organization、LocalBusiness（含常見子類型）、教育、政府、新聞媒體等節點。
    - 不含 Person：文章的 author 節點就是 Person，算進來會把每位作者當成網站的組織。
    - 名稱做 HTML 實體還原（實測 blog.gslin.org 在 JSON-LD 放了 `&#039;`）。
  - **sameAs**：辨識 Wikidata、維基百科、Facebook、Instagram、LinkedIn、X、YouTube、GitHub、Threads。
  - **文章頁**：
    - JSON-LD 標 Article／NewsArticle／BlogPosting 等，或 `og:type=article` 加上 `article:published_time`，且 `<article>` 區塊少於 3 個。
    - 標 CollectionPage／ItemList／SearchResultsPage 的不算。
  - **作者**：JSON-LD `author`、`<meta name="author">`、`article:author`、`rel="author"`。
- Finding（GEO，`impact_area=entity`）：
  - `geo-entity-organization-missing`（低）：有結構化資料但沒有任何組織實體。完全沒有 JSON-LD 的網站已由逐頁「可補充 JSON-LD」提醒，不重複。
  - `geo-entity-no-same-as`（資訊，不扣分）：組織實體沒有 sameAs。
  - `geo-article-author-missing`（低）：列出沒有作者的文章頁。
- `tasks.stage_geo_site` 呼叫；覆蓋檢查沿用 `geo_site`。
- `reports.RULE_BASIS` 三條規則的依據與限制。
- 文件：scans CLAUDE.md、roadmap、需求書 GEO 段落。

## 原因
AI 摘要與知識圖譜需要確認「網站是誰、文章是誰寫的」（E-E-A-T）。原本 GEO 只看有沒有 JSON-LD 與常見類型。

## 真實網站核對（首頁＋同網站 6 個連結）
- 正確辨識：
  - blog.cloudflare.com 只有 WebSite 標記：判為缺組織實體，與原始碼一致。
  - wordpress.org 組織 sameAs 有 Facebook、X、維基百科。
  - css-tricks 組織 sameAs 有 4 個；文章 4 篇都有作者。
  - blog.gslin.org 組織與文章作者都有。
- 修正兩次誤判：
  - WordPress 分類頁（css-tricks `/category/articles/`）標了 `og:type=article`，但 JSON-LD 是 CollectionPage。
  - Smashing Magazine `/articles/` 列表頁有 og:type=article 與發布時間、沒有 JSON-LD，但有 10 個 `<article>` 區塊。
  - 改為排除這兩種情況後，兩者都不再被當成「缺作者的文章」。
  - css-tricks 文章頁本身因為「相關文章」也有多個 `<article>`，所以 JSON-LD 明確標 Article 的不看區塊數。
- 沒有 JSON-LD 的網站（ntub.edu.tw、ithome、technews）不列組織缺少，交給逐頁提醒。

## 影響範圍
- 有結構化資料但缺組織、或文章缺作者的網站，GEO 多一到兩項低風險問題。
- `RULESET_VERSION` 今天已是 2026.10.08；不需要 migration。

## 驗證方式
- 新測試 `tests_geo_entity.py`（9 項）：
  - 完整組織不列問題、缺組織、完全沒有 JSON-LD 不重複列。
  - 沒有 sameAs 為資訊、HTML 實體還原。
  - 作者 Person 不算組織。
  - 文章缺作者（三種作者標記）。
  - 三種列表頁不算文章；標 Article 但有相關文章區塊仍算。
  - 錯誤與被阻擋頁面略過。
- 全套 `uv run python backend/manage.py test apps`：1694 項 OK（3 skipped）。
- `ruff check backend` 通過；`makemigrations --check` 無變更。
