# 結構化資料驗證：Google 複合式搜尋結果必填欄位（roadmap §1 SEO 第 2 項）

**日期**：2026-10-07  
**操作者**：Claude

## 變更內容
- 新增 `backend/apps/scans/seo/structured_data.py`：檢查頁面已有的 JSON-LD 是否缺少 Google 複合式搜尋結果的必填欄位。
  - **欄位規格**：逐項核對 Google Search Central 各類型說明頁（2026-09 版）：
    - 產品：name，以及 review／aggregateRating／offers 其中之一。Offer 要 price 或 priceSpecification.price；AggregateOffer 要 lowPrice、priceCurrency。
    - 軟體應用程式：name、offers.price、aggregateRating／review。
    - 職缺：datePosted、description、hiringOrganization、title、jobLocation／jobLocationType。
    - 食譜：name、image。
    - 影片：name、thumbnailUrl、uploadDate。
    - 導覽路徑：itemListElement；每個 ListItem 要 position、name（item 帶 name 時可省略）、item（最後一項可省略）。
    - 活動：name、startDate、location；實體地點要 address，線上活動不用。
    - 在地商家（含常見子類型）：name、address。
    - 評論：author、reviewRating.ratingValue。
    - 評分彙總：ratingValue，以及 ratingCount／reviewCount 其中之一。
  - **避免誤報**：
    - 類型規則只套頂層節點（區塊根、陣列、`@graph`、`mainEntity`），例如 Offer.itemOffered 裡被引用的 Product 不檢查。
    - 純 `@id` 參照不檢查；`@type` 接受 schema.org 網址形式。
    - 空字串或空陣列視為缺少。
    - 語法錯誤略過，已由 AEO `aeo-markup-syntax` 回報。
  - **刻意不檢查**：
    - FAQPage、HowTo：已不在 Google 支援的複合式搜尋結果清單。
    - Article、Organization：沒有必填欄位。
    - 建議欄位，以及值是否正確。
- `scanners.SEO_PAGE_CHECKS` 加兩項逐頁檢查：
  - `seo-structured-data-required`（低）：列出每個項目缺少的欄位，`evidence_json.issues` 含說明頁連結。
  - `seo-structured-data-self-serving-reviews`（資訊）：LocalBusiness／Organization 標了自己的評分時，提醒 Google 不會顯示星等。
- `reports.py`：兩條規則的判斷依據與限制；必填欄位規則另附驗證方式（Rich Results Test）。
- 文件：scans CLAUDE.md、roadmap、需求書 SEO 段落。

## 原因
roadmap §1 SEO 第 2 項。網站常放了結構化資料，卻因為缺少一兩個必填欄位而拿不到價格、星等、活動日期等複合式搜尋結果，自己又不知道。

## 影響範圍
- 有不完整結構化資料的頁面會多一項低風險 SEO 問題，同一規則全站只扣一次分。
- 沒有結構化資料的頁面不受影響。
- `RULESET_VERSION` 今天已是 2026.10.07，同版本內新增規則，尚未部署；不需要 migration。

## 驗證方式
- 新測試 `tests_structured_data.py`（17 項）：
  - 各類型的必填與「其中之一」條件。
  - Offer／AggregateOffer、巢狀評論與評分。
  - 實體活動地點要地址、線上活動不用。
  - 網址形式的 `@type`、職缺遠端條件。
  - 導覽路徑項目的例外規則。
  - `@graph` 節點只檢查一次。
  - Article／Organization／FAQPage 不檢查；被引用的 Product 不檢查。
  - 空值算缺少、語法錯誤略過。
  - 自評星等。
  - SEO finding 的嚴重度與證據。
- 真實網站核對：
  - 完整的標記全部通過，沒有誤報：BBC Good Food 食譜（含影片、導覽路徑）、Apple 產品頁、WooCommerce 產品頁、Google Play 與 App Store 應用程式頁、CakeResume 導覽路徑。
  - 多數大型網站會擋 curl，沒有取得標記。
- 全套 `uv run python backend/manage.py test apps`：1661 項 OK（3 skipped）。
- `ruff check backend` 通過；`makemigrations --check` 無變更。
- `scanners.py` 維持 CRLF。
