# 2026-06-14 UI/UX 重構 Phase 2 — 5 個高 ROI 結構修補

> 接續 `log/2026-06-14_ui-ux-billing-cms-audit.md`。複查後動手修。

## 變更內容（5 個修改 + 1 個刪除）

| # | 修法 | 檔案：行 | 對應審計點 |
|---|---|---|---|
| 1 | 後台 sidebar 補回隱藏路由入口（🔍 掃描 / 💳 交易） | [App.jsx:5194](frontend/src/App.jsx:5194) | C1+C2 |
| 2 | PurchasePage 方案卡可點 + 加 navigate(`/billing?plan=X`) + 加「≈ N 個小型網站」等價說明 + 刪掉「※ 想結帳請點下方…」廢話 | [App.jsx:4598-4628](frontend/src/App.jsx:4598) | A1+A3 |
| 3 | BillingPage 讀 URL `?plan=` 並自動 setStep(2) + 清空 URL param | [App.jsx:2965+, 2978+](frontend/src/App.jsx:2965) | A1 |
| 4 | Dashboard「點數餘額」hint 改為「≈ 還能掃 N 頁 · 累積花費 NT$」 | [App.jsx:2690-2695](frontend/src/App.jsx:2690) | B2 |
| 5 | features 接通：ProjectPage 改用 `/api/content/features/`（fallback 保留） + 新增 FEATURE_SCHEMA + CONTENT_TABS 加 features tab + AdminContentPage 預設 tab 改 features | [App.jsx:4203, 6367, 6466+](frontend/src/App.jsx:4203) | D1 |
| 6 | 刪除殭屍 `PLAN_SCHEMA`（定義 24 行、無人引用） | [App.jsx:6483](frontend/src/App.jsx:6483) | D5 |

CSS 新增：[styles.css:3741+](frontend/src/styles.css:3741) 加 `.public-plan-equivalents`。

## 原因

複查時發現 D1（features tab）真實本質不是「後台缺 tab」、是「整條 features stack 是殭屍」——後端 model/serializer/admin write API 都做了，前端 ProjectPage 用 hardcoded array 完全沒接，admin 永遠改不到。同時 D5（兩份重複）也是錯的，PLAN_SCHEMA 是定義了沒人用的殭屍代碼。把這些都修了等於同時減少了「假以為可以改、實際改不到」的心智誤導。

A1（購買流斷裂）+ C1/C2（後台死路）+ B2（dashboard 餘額顯示混淆）是使用者直接接觸的痛點，優先做。

## 影響範圍

- 前端：`App.jsx` + `styles.css`（兩個檔案）
- 後端：**無修改**（既存 API 都已支援，本次純前端利用）
- DB：**無 migration**（既存 4 個 features seed 就會跑出來）
- 部署：build 通過、`manage.py check` 通過

## 驗證方式

| 項目 | 結果 |
|---|---|
| `D:\nodejs\npm.cmd run build` | ✅ 268 modules 3.09s, exit 0 |
| `uv run python backend/manage.py check` | ✅ System check identified no issues |
| GET `/api/billing/plans/` | ✅ 200, 4 plans |
| GET `/api/content/features/` | ✅ 200, 6 features（DB 有真實 seed） |
| GET `/purchase`（SPA fallback） | ✅ 200 |

## 待做（下一輪 PR / 等使用者看畫面後微調）

- A2 收斂 `/purchase` 與 `/billing`（先不動，保留 marketing page）
- A4 新增體驗方案（NT$50 / 60 coin）
- A5 + D4 admin 方案卡顯示成本 / 毛利 / 估算可掃頁數
- A6 BillingPage step 3 顯示「相比入門省 NT$X」
- B1 dashboard hero 加「+ 新掃描」CTA
- B3 高/嚴重 tile 包成 button + click-through
- B4 「最近掃描」加相對時間
- B5 公告 modal 對 temporary 改用 toast
- C3 + D5 plans tab 整併進 `/admin/content`（先觀察使用者使用感）
- C4 admin settings 頁
- D2 CMS 加「預覽前台」link
- D3 sort_order 加「上下移」按鈕
- F2 修 CLAUDE.md「D:\node22」漂移 → 改成 `D:\nodejs`
- F3 修 `build-node22.ps1` 編碼（加 BOM 或改純英文）
- F5 TeamMember `skill_levels` / `contributions` JSON 物件陣列在 AdminCmsManager 編不了

## 已知小坑（這次發現但沒修）

1. `frontend/src/App.jsx:2965` 新增的 `setSearchParams` 變數 lint 可能警告未使用——其實在 useEffect 內用了 `setSearchParams({}, { replace: true })`，不會 warning。
2. `PurchasePage` 我刪了「※ 想結帳請點下方『前往結帳』進入 3 步驟結帳流程」這行 hint，因為現在每張卡都有「選此方案」按鈕了，那行 hint 變成謊話。
3. `BillingPage` 進場時 plans 還沒 ready，URL `?plan=` 邏輯要等 plans 載完才能執行——已用 useEffect 依賴 `[plans, searchParams, selectedPlan, setSearchParams]` 處理。
