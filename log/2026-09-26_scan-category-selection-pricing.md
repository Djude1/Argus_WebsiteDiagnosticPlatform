# 掃描維度多選計費：使用者可只勾 SEO/GEO 等維度，費用按勾選數計

日期：2026-09-26

## 變更內容

**計費模型**：掃描費用從「頁數 × 10 coin」改為「**頁數 × 勾選維度數 × ARGUS_COIN_PER_CATEGORY（預設 2）**」。五維全選＝每頁 10 coin，與舊定價等價；只勾 SEO+GEO＝每頁 4 coin。`ARGUS_COIN_PER_PAGE` 設定移除，wallet API 以 `coin_per_category` 取代 `coin_per_page`。

- `backend/apps/scans/models.py`：`ScanJob.categories`（JSONField，migration 0017 讓既有資料預設五維全選）；`ALL_CATEGORIES` 事實來源；`effective_categories` property（過濾未知值、空集合退回全開）；`clean()` 新增「主動模式必須勾資安」
- `backend/apps/billing/services.py`：`estimate_scan_cost(max_pages, categories=None)` 三計費點（serializer 預檢／`hold_for_scan`／`settle_scan_actual`）統一改維度公式；hold 與 settle 用同一組維度，退差對稱
- `backend/apps/scans/serializers.py`：`categories` ListField（至少一項、去重、白名單驗證）；active＋未勾資安回 400；`ScanJobSerializer` 回傳 `categories`
- `backend/apps/scans/scanners.py`：`analyze_page(page_input, categories=None)` 逐維度過濾子分析（管理頁／二進位資源的 security 檢查也受資安維度控制）
- `backend/apps/scans/tasks.py`：秘鑰偵測、站台層級資安（`analyze_security_site_level`）、站台訊號 GEO（`analyze_site_signals`）按維度跳過；`tested_categories &= effective_categories` 作計分最後防線（UX layout_metrics 爬蟲仍一律收集，但未勾不計分）
- `backend/apps/scans/management/commands/rerun_scan.py`：replay 沿用 `effective_categories`；資安未勾不產站台層級資安 findings；`calculate_scores` 依實際 findings 推導 tested_categories
- `backend/apps/scans/views.py`：`/api/scans/estimate/` 接受 `categories` 並回傳
- `backend/apps/billing/serializers.py`：`coin_per_page` → `coin_per_category`
- `backend/apps/admin_api/views.py`：系統設定頁改暴露 `ARGUS_COIN_PER_CATEGORY`
- 前端 `ScanExperience.jsx`：維度五選多卡片（預設全選、至少一項）、每頁費用與餘額檢查連動、取消資安自動關閉主動模式（checkbox disabled＋提示）、estimate/create 帶 `categories`、草稿保存維度；`styles.css` 新增 `.category-grid`；購點／公開頁／admin 文案同步維度計費
- 文件同步：`scans/CLAUDE.md`（維度選擇節＋扣點流程圖）、`billing/CLAUDE.md`（函式表＋維度計費節）、`backend/CLAUDE.md`（ScanJob 欄位）、`ONBOARDING.md`（wallet 回應欄位）、需求書 md（F-005/F-006/NF-004／功能總覽）

## 原因

使用者回饋：多數人只想做 SEO/GEO 掃描，不需要滲透測試，卻負擔相同費用。設計經使用者選定「維度多選計費」：關閉資安維度即不執行任何資安掃描、費用對應減少；主動測試屬資安維度深入檢查，未勾資安即不可開啟（與既有網域驗證閘門相互獨立、並存不變）。

## 影響範圍

- 定價：五維全選價格不變；部分維度便宜（2/頁/維）。既有掃描資料（migration 補滿五維）行為與費用完全不變
- 未勾維度＝不掃描、`category_scores` 缺鍵（報告顯示未評估）——沿用既有「未評估分類」契約，報告／詳情頁零改動
- wallet API 回應欄位更名（`coin_per_page` → `coin_per_category`）；前端全數同步，無其他消費端
- k8s ConfigMap 未新增 `ARGUS_COIN_PER_CATEGORY`（預設值即 2，與現行定價一致；要調價時再加）

## 驗證方式

- `apps.billing`：78 tests OK（新增：全選等價舊價、部分維度估價、去重／未知值／空集合、部分維度 hold＋settle 退差、wallet `coin_per_category`）
- `apps.scans`：742 tests，errors=72 全為本機缺 CJK 字型之 report 測試（與本次無關的既有環境限制；非 report 類別 errors=0）。新增案例：預設全選、部分維度計費（50×2×2=200 預扣）、空 categories 400、active 未勾資安 400（serializer＋model.clean）
- `apps.admin_api`：86 tests OK（系統設定鍵更名）
- `uv run ruff check backend` 通過；`manage.py check` 無 issue；前端 `build-node22.ps1` 成功
- 殘留掃描：`rg ARGUS_COIN_PER_PAGE` 僅剩歷史 log 與刻意保留的「與舊定價等價」註解
