# 地址改走共用證據（roadmap §2 第 3 項）

**日期**：2026-10-08  
**操作者**：Claude

## 變更內容
- **`evidence/contacts.py`**：
  - 新增地址：`ADDRESS_PATTERN`（由 `aeo/answers.py` 搬來，AEO 答案格式改用這一份）、`normalize_address`（去空白標點、臺→台、全形數字轉半形）、`find_addresses`。
  - 新增 `structured_addresses`：讀 JSON-LD 的 `address`，字串直接用，PostalAddress 只取 `streetAddress`。
  - `collect_contacts` 多一種位置 `structured_data`。JSON-LD 裡的地址不算頁面內容；Email／電話照舊。
- **`aeo/evaluate.reconcile_contact`**：地址題也用共用證據核對。
  - 頁面任何可讀段落含結構化資料的街道 → 判可回答，附該段原文。
  - 地址只在 JSON-LD → 判定不變，理由寫「只寫在結構化資料裡，搜尋引擎讀得到，但頁面上沒有顯示」，並註明和結構化資料檢查情境不同、不矛盾。
  - `aeo_report.shared_contacts` 多記地址筆數。
- **日期不共用**：AEO 的日期是正文中的截止日、活動日；GEO 的日期是文章發布／更新標記。兩者描述不同的事，不會互相矛盾，所以不做。
- **文件**：roadmap §2 第 3 項、scans CLAUDE.md、`evidence/__init__.py`。

## 驗證方式
- `tests_shared_evidence.py` 新增 6 項：
  - 地址三種位置。
  - PostalAddress 取街道、壞掉的 JSON-LD 略過。
  - AEO 與共用模組用同一個 pattern。
  - 只有 JSON-LD 時的理由。
  - 地址寫在短標題時以街道比對找回答案。
  - 摘要筆數。
- `aeo_benchmark`：改前改後結果相同（accuracy 0.975、precision 1.0、recall 0.977、FPR 0）。
- 真實網站（原始 HTML，未經瀏覽器渲染）：
  - yamatoya.com.tw 首頁地址只在 JSON-LD（崇德十二路431號），擷取為 `structured_data`。
  - 分店頁同時有頁面地址與 JSON-LD，AEO 判可回答。
  - nccu.edu.tw、sogo.com.tw 頁面地址擷取為 `content`。
- 全套後端測試、`ruff check backend`。

## 尚未做／觀察
- yamatoya 首頁沒有「地址、門市、交通」等字樣，AEO 不會出地址題。結構化資料有地址時要不要因此出題會改變 AEO 分數，這次沒做。
