# 修正前端統計失真，並在報告加入分類佔比圖

**日期**：2026-09-03
**操作者**：Claude
**觸發**：使用者回報「前端各類別 finding 佔比在掃描完成後 AEO 就不見了」，以及「報告沒有前端那張分類佔比圖」。

## ① 前端的分類佔比與嚴重度分佈是錯的

### 根因

前端抓 findings 時**沒有帶 `page_size`**：

```js
api.get(`/findings/?scan_id=${scan.id}`)          // 預設 page_size = 100
setFindings(findingsResponse.data.results || ...)  // 只有第一頁
```

而 `categoryTotals` 與 `severityTotals` 都是用這 100 筆算的。排序是 `priority_score desc`，NTUB 有 37 頁、每頁都有 H1／meta 問題，前 100 筆幾乎被高 priority 的 SEO 佔滿：

- **掃描中**：總數 < 100，全部拿得到 → SEO、GEO、AEO 都看得到
- **掃描完成**：總數遠超 100 → AEO 掉出第一頁 → **從圖上消失**

顯示的百分比其實是「前 100 筆的佔比」而非全體，會讓人誤判問題分佈（以為 AEO 完全沒問題）。

`ScansPagination` 的 docstring 自己寫著假設「單次 50 頁 × 平均 findings/頁 < 2」，NTUB 直接打破這個前提。

### 實測對照（SEO 120 / AEO 3 / GEO 2，共 125 筆）

| 分類 | 舊算法（前 100 筆） | 新算法（DB 計數） |
|---|---:|---:|
| SEO | 100 (100%) | 120 (96.0%) |
| AEO | **0 → 圖上消失** | 3 (2.4%) |
| GEO | **0 → 圖上消失** | 2 (1.6%) |

舊算法只看到 100 筆，少算 25 筆，兩個分類直接消失。

### 變更

- 新增 `GET /api/scans/{id}/finding-stats/`：由 DB 聚合回傳 `total` / `by_category` / `by_severity`。`values().annotate()` 前先 `order_by()` 清掉 `Meta.ordering`，避免排序欄位被帶進 GROUP BY。
- 前端改用這個端點；計數尚未載回時退回本地計算，讓圖表第一次 render 就有東西、不閃空白。
- 圖表顯示條件由「抓回來的清單非空」改為「有計數或有清單」。

**沒有選擇「撈更多筆」**：`max_page_size` 是 500，NTUB 可能就超過，那只是把上限往後推；而且為了數數量把整份 finding 送到前端本來就浪費。

### 新增 `tests_finding_stats.py`（6 項）
超過一頁的完整計數（**這就是事故本身**）、低 priority 分類不被高 priority 蓋掉、嚴重度計數、空掃描回零、他人無法讀取、匿名拒絕。

## ② 報告加入「問題集中在哪些分類」

- `theme.py`：新增 `CATEGORY_COLOR` 與 `category_color()`，**沿用前端 `AppShared.jsx` 的配色**，讓同一份掃描在畫面與報告上顏色一致。用前綴比對而非完全比對，日後改顯示名稱不會整組失效；未知分類退回中性灰而不是炸掉。
- `charts.py`：新增 `category_share()` 堆疊圖。佔比 < 8% 的分段塞不下數字就留白，數量由圖下方文字圖例補齊。
- `report.py`：放在「發現項目分佈」之後，與「各分類分數」呼應——**一個看體質、一個看問題分佈**。

**沒有改 schema 也沒有改 payload**：`build_all` 本來就從 `data["findings"]` 推導嚴重度計數，分類用同一個方式即可。初版曾把計數塞進圖表路徑 dict，後改為在 `report.py` 重算，與 module 處理嚴重度的既有慣例一致。

### 一個刻意的取捨（待使用者確認）

**報告的佔比是「去重後」的數字，前端是「原始筆數」。** 以 NTUB 為例：報告第 4 章寫「共 16 項」，佔比圖就是這 16 項的分佈；前端顯示的是 125 筆原始 finding 的分佈（同一問題出現在 37 頁算 37 筆）。

選去重是為了**與報告自己列出的內容一致**——寫「共 16 項」卻畫一張 125 筆的圖，讀者會對不起來。若認為報告該呈現「問題的擴散廣度」，改用原始筆數即可。

## 驗證方式

- `uv run ruff check backend` → All checks passed
- `uv run python backend/manage.py test apps` → **Ran 798 tests，OK（skipped=1）**（前次 790，+6 統計 +2 佔比圖）
- 前端 `npm run build` 通過
- **實際產生報告並抽出圖片目視**：分類佔比圖配色與前端一致，窄分段（AEO 1 項）自動不塞數字，文字圖例正確列出四個分類。

## 未處理／待決事項

- **finding 列表本身仍只顯示 100 筆**：同一個分頁限制造成的另一個問題，NTUB 那種掃描看不到第 101 筆之後的 finding。修法不同（需要分頁 UI 或無限捲動），未做。
- 報告佔比用去重或原始筆數，待使用者決定（如上）。
- 早期稽核的兩個 P0 仍未修：**worker 重啟砍掉進行中掃描且 coin 不退**（無 `acks_late`／reaper／beat，已實測確認）、**`settings.py` 完全沒有 LOGGING 設定**（0 處）。
- 報告快取沒有版本概念：已產生過報告的掃描永遠拿到舊版面。
- 「0 個 finding = 100 分」；`cleanup_reports` / `cleanup_screenshots` 未接排程；`argus_report_module/` 未納入版控。
- `.docx` 視覺與頁數仍需人工用 Word 確認。
