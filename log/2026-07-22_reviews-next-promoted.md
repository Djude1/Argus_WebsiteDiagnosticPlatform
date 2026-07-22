# 新版評論頁切換正式入口

**日期**：2026-07-22
**操作者**：Codex

## 變更內容

- 將夜間科技評論介面改為正式 `ReviewsPage`，由 `/reviews` 直接呈現
- 將 `/reviews` 掛回共用 `PublicLayout`，沿用全站 top bar 與 footer，並移除評論頁重複頁首
- 移除舊版評論元件與 967 行舊版專用 CSS
- 將 `/reviews-next` 改為相容轉址至 `/reviews`，移除頁首版本比較導覽與舊回跳網址
- 尚未具備發表資格的已登入使用者，在留言入口顯示「評論前先完成一次掃描」並連往 `/scans`

## 原因

比較階段已完成，使用者決定以新版取代原本評論頁，並保留簡潔且可直接操作的掃描資格提示

## 影響範圍

- 前台公開評論路由、登入後回跳位置與評論頁首排版
- 評論 API、管理後台與既有評論資料不變
- 舊 `/reviews-next` 書籤仍可使用，但會直接轉到正式 `/reviews`

## 驗證方式

- `frontend/build-node22.ps1`：Vite 6.4.2 production build 成功，2,038 個模組，輸出正式 `ReviewsPage` chunk
- `uv run python backend/manage.py check`：通過，0 個問題
- HTTP：`/reviews` 與 `/reviews-next` 均回傳 200；瀏覽器確認 `/reviews-next` 最終轉址到 `/reviews`
- 瀏覽器：1280px 與 320px 都無水平溢位；共用公開頁首／頁尾各出現一次、評論頁無重複頁首，掃描資格提示在 320px 維持單行，主控台 0 錯誤
