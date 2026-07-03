# scans 家族 ViewSet 加分頁

## 變更內容

**修改檔案：**
- `backend/apps/scans/views.py` — 新增 `ScansPagination` 類別並套用到三個 ViewSet
- `backend/apps/scans/tests_list_dedup.py` — 3 個測試改用 `resp.json()["results"]` 解析分頁回應

**新增 `ScansPagination`：**
- `page_size = 100`（預設）
- `page_size_query_param = "page_size"`（前端可用 `?page_size=N` 覆蓋）
- `max_page_size = 500`（防惡意請求撐爆 memory）

**套用範圍：**
- `ScanJobViewSet`
- `PageViewSet`
- `FindingViewSet`

## 原因

三個 ViewSet 原本無分頁，一次全撈 queryset 序列化回傳：
- 一個掃描可能產生 200-500 個 Finding（50 頁 × 平均 4-10 findings/頁）
- 使用者累積 100 次掃描後，`/api/scans/` 一次撈幾千筆
- 記憶體與頻寬會隨資料量線性成長，無上限

未動 admin CMS ViewSet（`admin_api/cms_views.py` 5 個）與 admin function-based views（自帶 `_paginate` helper），避免破壞既有前端。

## 行為說明

**回應格式變化（僅 list action）：**
```json
// 原本
[{...}, {...}, ...]

// 改後
{
  "count": 234,
  "next": "http://.../findings/?page=2",
  "previous": null,
  "results": [{...}, {...}, ...]
}
```

**detail action（`/scans/{id}/` 等）不受影響**，仍回單一物件。

前端 `App.jsx` 已有 `response.data.results || response.data` 兼容寫法在三處（L1426、1427、1800），此變更不需要前端配合改動。

## 影響範圍

- 記憶體/頻寬：單次回應上限 500 筆（`max_page_size`）
- API 語意：list 端點改回分頁物件；直接消費者需用 `.results`
- 測試：`tests_list_dedup.py` 需同步改用 `["results"]` 解析
- 前端：兼容寫法已就位，無需修改

## 驗證方式

- AST 語法檢查 — 通過
- 全套 scans 測試（263 項）— 全部通過（含修正的 3 個 list 解析測試）
