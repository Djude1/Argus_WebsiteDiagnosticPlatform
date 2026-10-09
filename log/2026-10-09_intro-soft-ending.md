# 進站動畫收尾改為柔和飄散

**日期**：2026-10-09
**操作者**：Claude

## 變更內容
- `frontend/src/components/brand/IntroSequence.jsx`：前段（字元風暴 → 聚合成 logo → 停留）不變；最後的 WARP 階段由「白色／青色錐形光束高速放射＋長殘影」改為柔和收尾：
  - logo 緩慢淡出、畫面輕微放大（最多 5%）。
  - 粒子從 logo 位置以 ease-out 往外飄 30～170px，並錯開時間逐一淡出（不再回收、不再拉長成光束）。
  - 中央一圈淡青色光暈先亮後淡（最高透明度 0.16），不用白色。
  - 時長 2200ms → 1600ms；HUD 狀態文字 HYPERSPACE → RELEASING。
- 移除不再使用的 `INTRO_WARP_COLORS` 與 `randomizeWarp`。

## 原因
使用者回饋：動畫前段可以，後段「一大串白色條」太刺眼，要改成更柔和的方式。

## 影響範圍
- 只影響首次進站品牌動畫的最後 1.6 秒；跳過（點擊、Esc／Enter／空白鍵）、`prefers-reduced-motion` 直接略過、結束後 650ms 淡出到首頁的行為不變。

## 驗證方式
- `npx eslint`、`npm run lint`、`npm test`：通過。
- `npx vite build` 後以本機 runserver＋Playwright 在 4.3／5.0／5.5／6.0／6.4／6.9 秒截圖：logo 散成字元後逐漸淡出、無白色光束，接著淡入首頁 hero。
