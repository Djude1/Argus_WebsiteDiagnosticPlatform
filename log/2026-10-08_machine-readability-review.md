# 內容可機讀性與錨文字品質核對（roadmap §10 第 2 項、§11 第 4 項）

**日期**：2026-10-08  
**操作者**：Claude

## 變更內容
- 只改文件：`docs/scan-upgrade-roadmap.md` 兩項標註核對結果。沒有程式變更。

### §10 第 2 項：內容可機讀性
- 既有檢查已涵蓋：
  - 缺 `<main>`：`analyze_geo`「缺少語意化主內容區塊」。
  - 正文擷取排除 nav／header／aside／footer：`aeo/content.py`。
  - 核心內容依賴 JavaScript。
  - 段落與小標題結構：`geo_structure.py`。
- 評估過兩項新規則：
  - 多個可見 `<main>`。
  - `<main>` 只包含少部分正文（<30%）。
- 實測 8 個網站約 40 頁：ntubimdbirc.tw、ntub.edu.tw、wordpress.org、blog.gslin.org、cna.com.tw、setn.com、law.moj.gov.tw、docs.djangoproject.com。
  - 沒有任何頁面有多個 `<main>`。
  - `<main>` 正文占比：除 wordpress.org/showcase（0.31，正文僅約 67 詞）外，都在 0.68 以上。
  - 沒有 `<main>` 的頁面（cna 首頁等、law.moj）已由既有規則列出。
- 結論：新規則不會觸發，不做。「語意 HTML 比例」沒有公認門檻，也不做。

### §11 第 4 項：錨文字品質
- 已具備：
  - `seo/page_audit.GENERIC_ANCHORS` 涵蓋點此、這裡、更多、read more、click here 等字面。
  - 空錨文字由 `seo/report.py` 列在 SEO 分析頁：空錨文字為警告，無意義文字為提示。
  - 沒有可讀名稱的連結由 axe-core `link-name` 列為無障礙問題。
- 「連結目的是否清楚」屬 WCAG 2.4.4，需要看上下文，不以字面規則擴充。

## 影響範圍
- 無程式變更。

## 驗證方式
- 以 `aeo/content.extract_page_content` 與 `seo/page_audit.content_size` 量測上述頁面的 `<main>` 數量與正文占比。
- `grep` 確認 `GENERIC_ANCHORS`、`seo/report.py` 的嚴重度，以及 axe 沒有停用 `link-name`。
