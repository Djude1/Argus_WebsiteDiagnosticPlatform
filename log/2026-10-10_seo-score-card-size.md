# SEO 分數卡恢復一般尺寸

**日期**：2026-10-10  
**操作者**：Claude

## 變更內容
- `legacy-member/95-seo.css`：移除 SEO 分數卡在寬螢幕佔左側兩列（`grid-row: span 2`）與放大字級（`text-4xl`）的規則；分數卡與其他數字卡同尺寸，寬螢幕固定 4 欄（7 張卡排成 4＋3）。
- `ProjectSeoPage.jsx`：拿掉不再使用的 `seo-kpi-score` class。
- `frontend/CLAUDE.md` SEO 分析頁說明同步。

## 原因
使用者回饋 SEO 分析總覽頁的 SEO 分數面板太大、看起來不正常（`0d716f4` 讓它佔兩列）。

## 影響範圍
只影響 SEO 分析頁概覽的數字卡排版；資料與其他頁面不變。

## 驗證方式
- `npm run lint`（0 error）、`npx vitest run src/features/projects`（30 項通過）、`vite build` 成功。
- 沙箱 scratch DB＋runserver 實際登入截圖（深／淺主題，1440 寬）：分數卡與其他卡等高同寬。
