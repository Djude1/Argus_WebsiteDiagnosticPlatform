# 已驗證評論區與治理流程重構

**日期**：2026-07-21
**操作者**：Codex

## 變更內容

- 重構 reviews models、serializers、views、urls 與 migration，新增官方單一回覆、修訂歷史、檢舉與公開狀態。
- 將發表資格綁定完成掃描；公開列表只顯示具驗證時間的評論，且不從帳號姓名或 Email 推導公開名稱。
- 讓使用者建立、編修、刪除自己的評論；保留一人一則，新增 helpful、星等篩選、排序、統計與分頁。
- 重構 admin_api 評論端點與 React 管理頁，提供待回覆/待審檢舉/隱藏篩選、官方回覆 upsert/delete、隱藏/重新公開及 audit。
- 新增獨立 lazy-loaded `ReviewsPage`，重做桌機、深淺色與 320px 手機版視覺和完整互動；移除舊 thread/圖片公開流程。
- 同步 backend/frontend 模組文件、ONBOARDING、專案說明、資料圖、開發歷史與 memory 索引。

## 原因

原評論區缺乏可驗證體驗、隱私邊界與清楚治理流程，評分建立後又無法由本人修正；thread/圖片互動增加複雜度，卻沒有提高公開評論的可信度。

## 影響範圍

- 後端 `reviews` 與 `admin_api`、兩筆 migration、公開/管理 API。
- 前端 `/reviews`、`/admin/reviews`、路由 lazy chunk 與全域評論樣式。
- 舊 `ReviewMessage` 資料保留；migration 只將最後一則舊管理員訊息轉成官方回覆，舊公開訊息/圖片不再展示。
- 部署時必須先套用 migration，再重新建置前端映像或 dist。

## 驗證方式

- `uv run python backend/manage.py test apps`：465 項全部通過。
- `uv run ruff check backend`：通過。
- `uv run python backend/manage.py check`：通過。
- `uv run python backend/manage.py makemigrations --check --dry-run`：無漂移。
- `frontend/build-node22.ps1`：Vite production build 成功，共 279 modules，ReviewsPage 維持獨立 chunk。
- 實際瀏覽器 QA：公開頁桌機/320px、深淺色、評分篩選/排序、登入後表單、官方回覆；管理後台確認評分零輸入欄位、單一回覆與治理操作，console 無錯誤。
