# 可上線收斂與響應式優化

**日期**：2026-05-28  
**操作者**：Codex

## 變更內容
- 移除 `/api/auth/dev-login/`、`/api/billing/dev-cheat/` 與前端結帳頁測試 coin 面板。
- 將購點方案 API 改為公開可讀，避免 `/purchase` 公開頁被 401 攔截導回登入。
- 統一整站掃描上限為 50 頁，前端預扣、送出 payload 與後端 serializer 上限一致。
- 補強手機版響應式樣式：公開導覽列、公開頁 hero/card、掃描頁、結帳 wizard、評論頁在窄螢幕改為更緊湊的單欄與滿寬操作。
- 將 `/reviews` 納入公開頁 layout，讓導覽與 footer 一致。
- 修正 `manifest.webmanifest` 的 nginx MIME type。
- 修正少量既有 ruff 格式問題，讓後端 lint 全綠。

## 原因
使用者要求把展示級功能收斂成可上線產品，重點包含公開流程不可斷、測試後門拆除、合規限制一致、手機與響應式排版優化。

## 影響範圍
- 前端公開頁、登入頁、掃描建立頁、購點頁、評論頁。
- 後端 accounts、billing、scans API。
- Docker frontend nginx PWA 檔案服務。

## 驗證方式
- `UV_CACHE_DIR=/tmp/argus-uv-cache uv run python backend/manage.py test apps.accounts apps.billing apps.scans`：139 tests pass。
- `UV_CACHE_DIR=/tmp/argus-uv-cache uv run ruff check backend`：pass。
- `docker compose up -d --build web worker frontend`：完成並重啟容器。
- `docker compose build frontend`：Vite production build pass。
- HTTP smoke：
  - `GET /api/billing/plans/` 回 200。
  - `POST /api/auth/dev-login/` 回 404。
  - `POST /api/billing/dev-cheat/` 回 404。
  - `HEAD /manifest.webmanifest` 回 `application/manifest+json`。
- Playwright 手機截圖檢查 `/project`、`/purchase`、`/reviews`、`/download`。

## 注意
- 曾嘗試完整 `uv run python backend/manage.py test apps`，但該完整套件在無輸出狀態停住；本輪採用最接近改動面的 accounts/billing/scans 測試作為主要驗證。
