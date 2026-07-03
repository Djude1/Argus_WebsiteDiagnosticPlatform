# scans/views.py 查詢優化（Cartesian product + 冗餘 aggregate）

## 變更內容

**修改檔案：** `backend/apps/scans/views.py`

**修 1：`ScanJobViewSet.get_queryset()` 改用 `Subquery`**

原本：
```python
.annotate(
    findings_count=Count("findings", distinct=True),
    pages_count=Count("pages", distinct=True),
)
```

改為：獨立 `Subquery` 各算 `findings_count` 與 `pages_count`，用 `Coalesce(..., 0)` 補零。

**修 2：`dashboard_summary` 合併 4 次查詢為 1 次 aggregate**

原本：`scans.count()` + `.filter(COMPLETED).count()` + `.filter(FAILED).count()` + `.aggregate(Avg("overall_score"))` → 4 個獨立 SQL round-trip。

改為單一 `.aggregate()` 內含 `Count(id)`、`Count(id, filter=Q(...))` ×2、`Avg("overall_score", filter=Q(...))` → 1 個 round-trip。

## 原因

**問題 1：Cartesian product**
`Count("findings", distinct=True) + Count("pages", distinct=True)` 在單一 SQL 內同時對兩個反向 FK 做 count，PostgreSQL 底層會 JOIN 兩張表產生笛卡兒積後才 DISTINCT。範例：
- 1 筆 scan 有 300 findings + 50 pages → 中間結果 15,000 rows
- 100 筆 scan 的 list 端點 → 1.5M rows 全部要 sort & distinct

`Subquery` 各自獨立計算，每個 subquery 只掃自己的表，總掃描數與資料量成線性關係。

**問題 2：dashboard 冗餘 round-trip**
Dashboard 是首頁載入時最早呼叫的 API，4 個 SQL round-trip 全部串行等待，額外增加 3 × network latency。合併後只需 1 次。

## 行為說明

- 回應資料完全相同（`findings_count` / `pages_count` 為整數、dashboard 結構不變）
- 執行計畫改變：
  - ScanJob list：兩個獨立 aggregated subquery 取代 double JOIN + DISTINCT
  - Dashboard：一次 `SELECT COUNT(*) FILTER (WHERE ...) ...` 取代 4 次獨立查詢

## 影響範圍

- 效能：資料量越大差距越明顯（100 筆 scan × 300 findings 這種規模改善顯著）
- API 語意：完全兼容，無需前端配合
- SQL 用到 PostgreSQL 的 `FILTER (WHERE ...)` 語法，Django ORM 會自動用等效寫法處理其他 DB backend

## 驗證方式

- AST 語法檢查 — 通過
- 全套 scans 測試（263 項）— 全部通過
