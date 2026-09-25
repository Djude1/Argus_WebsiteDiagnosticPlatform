# 後台 UI 重構 S7：深色主題

**日期**：2026-09-25  
**操作者**：Claude

## 變更內容
- `:root` 補齊語意 token：`--admin-border-solid`、`--admin-text-secondary`、`--admin-accent-strong`、`--admin-accent-soft-bg`、`--admin-tone-{good,warn,bad}-{text,bg}`、`--admin-shadow-card`。
- **以程式化方式把 101 個 admin 規則塊內的硬編碼色值換成 token**（`#ffffff`／`#f8fafc`／`#e2e8f0`／`#0f172a`／`#64748b`／`#475569`／`#0e7490` 等），側欄相關 29 個規則塊刻意略過。
- 新增 `:root[data-theme="dark"]` 區塊：覆寫上述 token，並為 17 處仍寫死亮色的個案（狀態藥丸、輸入框、表格 hover、modal、分段切換、登入方式徽章等）逐一補上深色規則。共 45 條 dark 規則。
- `AdminLayout` 側欄底部新增主題切換按鈕。

## 原因
規劃 §1-2 問題 B：站台有 dark／light 切換（`store.js` 的 `toggleTheme`），但 `styles.css` 所有 `[data-theme="light"]` 規則只作用於 `.public-shell`——後台永遠是淺色，使用者的心智模型在跨進後台時斷裂。

**為何先做 token 轉換再做深色**：396 個 admin 選擇器逐條寫深色版本不可維護。把硬編碼色值收斂成語意 token 之後，深色只需覆寫 token 值；這也是 S0 當初建立 token 的目的。

**為何側欄不跟隨主題**：它本來就是深色的品牌元素，兩種主題下保持一致才有錨點；若跟著變淺，深色模式下反而失去層次。

**為何要在後台加切換按鈕**：切換開關原本只在前台導覽列。若後台只跟隨 `data-theme` 而沒有入口，使用者得先跑回前台才能改，等於半個功能。

## 重要行為改變
`store.js` 的預設主題是 **dark**（`argus_theme` 未設定時回 `"dark"`）。因此本次改動之後，**後台預設為深色**，而非先前的永遠淺色。使用者可在側欄底部或前台導覽列切換，兩處共用同一個開關與 localStorage 鍵。

若希望後台維持預設淺色，作法是把深色選擇器改為 `:root[data-theme="dark"]` 之外再加一層 opt-in 類名，或調整 `store.js` 的預設值——但後者會連帶改變前台預設，需另行決定。

## 影響範圍
- 只影響 `.admin-*` 樣式與後台側欄；前台、使用者端與 `.ann-*`（全站確認對話框）未改動。
- 側欄 29 個規則塊保持原樣。

## 驗證方式
- `npx vite build` 通過（13.32s）。
- **深色對比度實測 12 項全數通過 AA（4.5）**：正文 14.50、次要 12.04、弱化 6.97、accent 8.34、good 7.29、warn 8.24、bad 5.74、error 標題 8.74 等。
- 以程式掃描「admin 規則塊內仍為亮色（平均值 > 200）的硬編碼」，17 處全部補上深色覆寫後重掃。
- 以 Pillow 模擬明暗兩版版面比對，確認側欄一致、內容區翻轉、狀態色在兩種底色下都可讀。
- **待人工確認**：瀏覽器實際切換主題，檢查 modal、下拉選單、圖表 SVG（`AdminMiniChart` 的格線色 `#e2e8f0` 與文字 `#94a3b8` 寫在 JSX 裡，非 CSS，深色下可能偏暗）。

## 已知未處理
- `AdminMiniChart` 與 `AdminSparkline` 的座標軸顏色寫在 JSX 的 SVG 屬性中，不受 CSS token 控制。深色下格線可能過暗，需另外處理（可改用 `currentColor` 或 CSS 變數）。
