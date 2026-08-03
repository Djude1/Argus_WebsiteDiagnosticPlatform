# 後台 Card 視覺語言重新設計：移除頂部色條，改採 Linear × Stripe 式材質語言

**日期**：2026-08-03
**操作者**：Claude
**呼叫者**：無檔案 import 此變更涉及的內部函式（`App.jsx` 只 lazy import 整個 `AdminPages.jsx` 模組）；純 UI 呈現層，無資料檔案異動。

## 背景

使用者對前一輪「面板加頂部 cyan 色條 + 角落浮水印」的方向直接否決：這正是幾乎所有 AI Dashboard Template（shadcn/TailAdmin/Flowbite/Magic UI/Aceternity）的招牌手法，一眼就能認出是模板。使用者明確要求：不要頂部色條、不要每張卡都長一樣、不要靠顏色分辨卡片（大小/佈局也可以設計）、參考 Stripe/Linear/Vercel/Notion/Raycast/Arc/Apple HIG 的材質質感，且**必須是 redesign 而非 refine**。

## 變更內容

- **移除全部頂部色條與角落浮水印**：`.admin-stat-card::before/::after`、`.admin-panel::before/::after`(連同對應的 `.admin-panel-danger::before/::after` 覆寫)全數刪除,改回 `--argus-brand-mark` token 只保留給 sidebar icon 本身使用,不再重複貼到每張卡片上。
- **卡片材質語言重寫**:`border-radius: 18px`(原 16px)、邊框改為極淡的 `rgba(15,23,42,.07)`(原實色 `#e2e8f0`)、陰影改為兩層柔和堆疊(貼近 hairline + 大範圍暈染,取代單層 `0 1px 3px`)、hover 改為更明顯但依然克制的浮起(`translateY(-2px)` + 陰影加深 + 邊框變深,取代原本幾乎無感的 `-1px`)。
- **Icon 自帶背景色塊**:新增 `.admin-stat-icon-chip`/`.admin-panel-icon-chip`——圓角方形淡色底(依 tone 換色:cyan/good/warn/bad),取代原本裸色 SVG 浮貼在卡片右上角。這是「用顏色只服務單一元素(icon chip),不再用顏色橫掃整張卡片」的核心手法。
- **數字為視覺焦點**:`.admin-stat-value` 加 `letter-spacing: -0.015em` + `font-variant-numeric: tabular-nums`(緊排數字,Stripe/Linear 大數字典型手法);`.admin-stat-label` 改為更淡的 `#94a3b8`(原 `#64748b`),拉開數字與標籤的視覺權重差。
- **Bento 式版面差異化(不靠顏色分卡片)**:Overview 頁新增 `.admin-stat-grid--bento` 4 欄版面,「累計營收」卡改為 `hero` 變體——跨 2 欄、字級加大(`text-4xl`)、底部內嵌一條迷你營收趨勢 sparkline(新元件 `AdminSparkline`,重用既有 14 天 `dash.series` 資料,漸層區域填色,無座標軸/圖例,Stripe 風格極簡走勢圖)。營收作為業務北極星指標領銜,其餘 5 張卡維持一般尺寸,靠**版面結構**而非顏色建立主次層級。

## 檔案

- `frontend/src/features/admin/AdminPages.jsx`:`AdminStatCard` 加 `hero`/`spark` prop,內部 icon 改包 `.admin-stat-icon-chip`;新增 `AdminSparkline` 元件;`AdminOverviewPage` 重排 stat card 順序(營收移到第一張並設為 hero)、grid 加 `--bento` class、4 個面板標頭圖示改包 `.admin-panel-icon-chip`。
- `frontend/src/styles.css`:`.admin-stat-card`/`.admin-panel` 整段重寫(陰影/邊框/圓角/hover),移除 `::before`/`::after` 頂條與浮水印,新增 `.admin-stat-icon-chip`/`.admin-panel-icon-chip`/`.admin-stat-grid--bento`/`.admin-stat-card.hero`/`.admin-stat-spark` 系列 class。

## 影響範圍

- 全站所有使用 `AdminStatCard`/`.admin-panel` 的頁面(含 `/admin/reviews` 的 4 張統計卡)都套用新材質語言,非僅 Overview 頁;bento/hero/spark 版面差異化僅作用於 Overview 頁(透過額外 modifier class 加註,未動全域 `.admin-stat-grid` 基礎規則,其他頁面版面不受影響)。

## 驗證方式

- `npm run build`(WSL/Linux Node 20):✓ 2039 modules、4.21s、無錯誤
- `docker compose build frontend && docker compose up -d --no-deps frontend`:成功(沿用 `DOCKER_CONFIG` 暫存空設定繞過 credsStore 問題)
- curl 已部署 bundle 逐項確認:舊版頂部色條 CSS 規則(`tone-cyan::before` 等)已完全消失;新版 `admin-stat-grid--bento`/`admin-stat-card.hero`/`admin-stat-icon-chip`/`admin-panel-icon-chip`/`admin-stat-spark` 均已出現在部署的 CSS 與 JS bundle 中
- **視覺自我檢查(事後補做)**:環境本無 Chrome,已用 `sudo apt-get install google-chrome-stable`(官方 apt repo,單機 WSL,非共用/正式環境)+ `fonts-noto-cjk` 補齊後,以 chrome-devtools MCP 實際登入 `/admin/overview` 截圖確認:頂部色條與浮水印已完全移除、6 張 stat card(含 hero 跨欄營收卡)、icon chip、面板標頭圖示、狀態徽章均正確渲染,無版面破圖。已知限制:目前測試資料庫營收為 0,hero 卡內嵌的 sparkline 因全期間數值皆為 0 而呈現為貼底平線,並非設計瑕疵,待有真實營收波動資料後才能看出漸層曲線效果。
