# 評論作者隱私與星等控制調整

**日期**：2026-07-30
**操作者**：Codex

## 變更內容

- 移除評論表單的公開顯示名稱輸入，改為「顯示部分 Email」勾選框
- 預設完全匿名；只有使用者主動勾選時，後端才輸出遮罩 Email
- 遮罩結果若可能等於原始 Email，或 Email 格式異常，強制退回完全匿名
- 新增 `show_partial_email` 模型欄位、migration 與 revision 稽核
- 移除星等按鈕的白色方塊，只保留星形、hover、focus 與選取回饋
- 管理後台改為顯示前台採「遮罩後的部分 Email」或「完全匿名」

## 原因

公開名稱不應由使用者任意填寫，且星等白色方塊破壞夜間評論頁的視覺一致性。新的流程讓作者只需選擇部分 Email 或完全匿名，並由後端統一處理公開身分。

## 影響範圍

- `/reviews` 新增與編輯評論表單
- 公開評論及本人評論 API 的作者顯示
- `PlatformReview`、`ReviewRevision` 與管理後台評論資訊
- 舊版 `display_name` 資料保留，但不再參與公開顯示
- 評論 API、模型圖、專案說明與模組交接文件

## 驗證方式

- `uv run python backend/manage.py test apps`：649 項通過，2 項略過
- Email 遮罩保護完成後再跑 `uv run python backend/manage.py test apps.reviews`：27 項通過
- push 前再跑 `uv run python backend/manage.py test apps.reviews apps.admin_api`：66 項通過
- `uv run ruff check backend`：通過
- `uv run python backend/manage.py check`：通過
- `uv run python backend/manage.py makemigrations --check --dry-run`：無遺漏 migration
- `frontend/build-node22.ps1` production build：通過
- 瀏覽器驗證桌機 1280px 與手機 390px 的星等、checkbox、匿名／遮罩 Email 新增與編輯流程，且無水平溢位與 console error
