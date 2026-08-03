# 後台 sidebar icon 重新設計 + 內容區底色改為淺灰藍（去除純白感）

**日期**：2026-08-03
**操作者**：Claude

## 背景

使用者對 2026-08-02（icon 去 emoji 化）與同日稍早（stat card 配色重設）兩輪成果的回饋：「沒有很大變化，且 SVG 圖標醜、單調、沒有品牌特色，背景不要純白色」。

實際檢查發現兩個根因：

1. **上一版部署診斷**：前一輪 CSS/JSX 變更本機已建置成功，但 Docker `frontend` nginx 容器映像檔停留在 2026-07-04（近一個月前），使用者看到的其實是舊版畫面——已於本次任務前段修復（`docker compose build frontend && docker compose up -d --no-deps frontend`）。
2. **設計本身的問題**（本次修正對象）：
   - 舊版每顆 sidebar icon 都用**整顆 ⟡ 菱形**當底（佔滿 24x24 視覺主體），功能記號只是塞進右下角的極小線稿（多半 <2px 可視面積），18px 渲染下 10 顆 icon 幾乎都長得一樣，只看得到菱形，看不出差異——這正是「醜、單調」的根因。
   - `.admin-main` 背景是 `linear-gradient(135deg, #f8fafc 0%, #f1f5f9 50%, rgba(219,234,254,.4) 100%)`，色差極小接近純白，加上卡片本身也是 `#ffffff`，整體觀感等同「一片白」。

## 變更內容

- `frontend/src/components/admin/AdminIcons.jsx`：
  - 10 顆 sidebar nav icon（概覽／使用者／掃描／交易／方案／內容／評論／設定／操作日誌／公告管理）全部重畫：**功能圖形佔滿 24x24 主體**（儀表板格、人像、雷達準星、交疊雙硬幣、三層階梯、文件折角、實心星、8 向齒輪、時鐘、喇叭音波），**⟡ 品牌記號縮小為右上角固定小角標**（取代原本整顆菱形當底），比例反過來，讓每顆圖示在 18–19px 下仍可一眼分辨。
  - `GlyphShell`／`AdminMenuIcon`／`AdminStarIcon`（漢堡選單、評分星星，非 sidebar nav 用途）未變動。
- `frontend/src/styles.css`：
  - 新增 `:root` token `--argus-admin-bg-1/2/3`（`#e7eef8` / `#d9e6f3` / `#cce0f0`，navy/cyan 品牌延伸的淺灰藍階）。
  - `.admin-main` 背景改用這三個 token 的漸層（取代原本色差極小的近白漸層）。
  - `.argus-app.is-admin-mode` 底色同步改為 `--argus-admin-bg-2`。
  - `.admin-stat-card`／`.admin-panel` 卡片本身維持 `#ffffff` 不動——密集資料表格仍需高對比可讀性，改為讓「淺色非純白」的識別感來自頁面底色，白卡片在有色頁面上自然形成清楚的卡片邊界（常見 SaaS dashboard 模式），非全面重上色所有 admin class。

## 原因

同前次決策脈絡：後台維持亮色內容區（表格密集資料需要），只調整配色來源與圖形設計，不轉深色、不動版面結構。這次specifically解決「icon 比例失衡導致看起來單調」與「背景色差太小等同純白」兩個具體視覺問題。

## 影響範圍

- 全站 `/admin/*` sidebar 全部 10 顆 nav icon 外觀
- 全站 `/admin/*` 頁面 `.admin-main` 內容區底色（`.argus-app.is-admin-mode` 外層底色同步）
- 未觸及：`.admin-stat-card`／`.admin-panel` 卡片底色、後台版面結構、前台 UI、`GlyphShell` 系列元件（漢堡選單、評分星星）

## 驗證方式

- `cd frontend && npm run build`（WSL/Linux Node 20，非 Windows Node24+Rollup 情境）：✓ 2039 modules、4.33s、無錯誤
- `docker compose build frontend && docker compose up -d --no-deps frontend`：重建並重啟容器成功
- 部署後直接 curl 已 serve 的 bundle 驗證：
  - `admin-main` CSS 規則已引用新 `--argus-admin-bg-1/2/3` token（非舊的近白漸層）
  - `AdminPages-*.js` chunk 中舊版整顆 ⟡ 菱形 path（`M12 4c1.25 4.85...`）已完全移除（grep 命中 0 次）
  - 新版右上角品牌角標 path 與新版概覽格線圖示 rect 座標均已出現在部署的 bundle 中
- **無法完成**：此環境未安裝 Chrome/Chromium，無法用 chrome-devtools MCP 截圖做視覺自我檢查；改以獨立靜態 HTML（複製相同 SVG markup 與 CSS token，置於 session scratchpad，非程式庫一部分）做過人工比對邏輯，但未能實際渲染確認。
- **待使用者手動確認**（需登入 staff 帳號，且瀏覽器需強制重新整理避免快取舊資源）：`/admin/overview` 等所有 `/admin/*` 頁面的 sidebar icon 是否清楚可辨、內容區背景是否不再是純白、整體是否有明顯「品牌特色」的觀感改善。
