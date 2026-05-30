# 新增 Cloudflare challenge 頁面偵測

**日期**：2026-05-27
**操作者**：Claude

## 變更內容

- `backend/apps/scans/crawler.py`
  - 新增常數 `CF_TURNSTILE_MARKERS`（4 個 Turnstile / Managed Challenge 特徵字串）
  - 新增常數 `CF_JS_CHALLENGE_MARKERS`（3 個 JS challenge 特徵字串）
  - 新增 helper `classify_cf_challenge(html)` → 回傳中文原因或空字串
  - `crawl_site()` 內判斷 `blocked_reason` 處：先看 body 是否為 CF challenge，沒中再 fallback 到既有的 `classify_blocked(status_code)`
- `backend/apps/scans/tests.py`
  - import 加入 `classify_cf_challenge`
  - `CrawlerHelperTests` 新增 7 個測試（JS challenge、browser verification、Turnstile、優先順序、正常頁、空輸入、避免「Just a moment」短語誤判）

## 原因

ARGUS 的 `crawler.py` 既有的 `classify_blocked()` 只看 HTTP status code 401/403/429。但 Cloudflare challenge 經常回 HTTP 200 加上一個假內容頁（內含 `challenge-platform` JS 載入器等特徵字串），原本邏輯偵測不到，會把這頁交給 `scanners.py` 全套 SEO/AEO/GEO 分析，產生「H1 缺失」「meta description 缺失」等假 finding。**使用者看到報告會誤以為自己網站 SEO 很爛**，實際原因是 ARGUS 根本沒抓到真內容。

特徵字串設計參考使用者另一個專案 Shinsekai 的 `cf_webview_service.dart` 與 `metadata_scraper.dart`。**僅做偵測與回報**，不繞過——符合 ARGUS「合規檢查工具」的產品定位。

## 影響範圍

- `tasks.py` 不需要修改：第 108-109 行既有的 `if not page_data["blocked_reason"]` 守護會自動跳過 CF challenge 頁的四維分析
- `crawler.py` 既有的 `links = [] if blocked_reason else await extract_links(...)`（第 213 行）會自動避免在 challenge 頁上繼續往下爬
- `crawler.py` 既有的 `warnings["blocked_urls"].append(...)`（第 235-236 行）會自動把 CF challenge 加進警告列表
- 既有 status code 為 401/403/429 的行為不變——CF 偵測失敗才會 fallback 到 status code 判斷
- 若 CF challenge 同時回 403 + body 含 CF 特徵：blocked_reason 會從原本的「伺服器拒絕存取」改為「Cloudflare JavaScript 驗證...」，給使用者更精準訊息

## 設計取捨

- **不收錄「Just a moment」短語**：該短語在正常文章正文可能出現，false positive 風險高。CF challenge 頁面實務上必然會有 `challenge-platform` 等結構性標記，不會單獨只出現該短語
- **Turnstile 優先於 JS challenge**：兩者特徵並存時，Turnstile 較嚴重（必擋、需人工點擊），回報前者更精準
- **以 body 內容為主、status code 為輔**：CF challenge 常回 200，純看 status code 漏判，body 內容才是真實狀況

## 驗證方式

```powershell
uv run python backend/manage.py test apps.scans.tests.CrawlerHelperTests -v 2
```

結果：**11 tests passed**（4 個既有 + 7 個新增），耗時 0.004s。

執行 `uv run python backend/manage.py test apps.scans`（100 tests）有 1 個 fail：`test_analyze_page_returns_seo_geo_and_security_findings` 斷言「缺少 JSON-LD 結構化資料」但 scanners.py 已把該 finding title 改為「可補充 JSON-LD 結構化資料」。經 stash 比對確認此 fail **pre-existing**，與本次修改無關。
