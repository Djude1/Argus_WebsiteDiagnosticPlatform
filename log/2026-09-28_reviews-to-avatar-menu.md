# 會員導覽列移除「評論」，改放頭像選單

**日期**：2026-09-28  
**操作者**：Claude

## 變更內容
- `frontend/src/features/account/TopNav.jsx`：會員頂部導覽列移除「評論」，連帶移除「掃描頁隱藏評論」的特例判斷。
- `frontend/src/components/navigation/NavActions.jsx`：頭像選單新增「評論」（`/reviews`，星形圖示），位於購點與訂閱之後。
- `frontend/CLAUDE.md`：導覽列與頭像選單項目同步。

## 原因
使用者要求把評論從頂部導航欄移到頭像選單。

## 影響範圍
- 會員導覽列剩首頁／Dashboard／掃描／網域驗證／歷史／購點／MCP 接入中心。
- 會員從頭像選單進入 `/reviews` 仍留在會員區版型；公開頁導覽列的「評論」不變。

## 驗證方式
- Playwright（本機 runserver＋前端 build）：導覽列不含評論；頭像選單為帳號設定／購點與訂閱／評論／登出；點選單的評論 → `/reviews`、會員導覽列、無公開頁殼；1440／1180／390px 導覽列不換行、無水平捲動
- `npm run lint`、`npm run typecheck`、`npm test`（152 項）、`vite build` 通過
