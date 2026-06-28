---
name: argus-ui-design
description: Argus 前端 UI/UX 設計與實作準則（科技風 / 前台動效 / 前後台對應 / affordance / 返回導覽）。當你要新增或修改 Argus 任何前端介面時必讀——包含 frontend/src/App.jsx 的頁面與元件、styles.css 樣式、前台公開頁（public-shell）、React 後台（/admin/*）、新頁面或新元件、按鈕 / 導覽列 / 分頁 / 動畫 / 特效 / 配色 / 版面 / 互動、或任何「美化、調整版面、做動畫、改視覺」的需求時，先讀本 skill 再動手。
---

# Argus 前端 UI/UX 準則

本 skill 是 Argus 前端的**唯一視覺與互動規範**。動手改任何畫面前先讀完「鐵則摘要」，再翻對應章節。本檔只談「設計怎麼做」；技術硬限制（單檔架構、build 工具等）以 [`frontend/CLAUDE.md`](../../../frontend/CLAUDE.md) 為準，兩者衝突時硬限制優先。

---

## 何時用這份 skill

任一條成立就先讀本檔：

- 在 `App.jsx` 新增 / 修改任何**頁面**或**元件**
- 改 `styles.css`（配色、版面、動畫、按鈕、卡片、導覽）
- 碰前台公開頁（`.public-shell`）或 React 後台（`/admin/*`）
- 使用者說「美化 / 做動畫 / 加特效 / 調版面 / 改視覺 / 不好看 / 不知道怎麼點」

---

## 鐵則摘要（TL;DR，違反就重做）

1. **科技風固定**：沿用既有 navy + cyan + glassmorphism token，不要每次換風格、不要亮白底紫漸層。
2. **動畫分層**：複雜動效**只給前台** `.public-shell`；**後台保持冷靜高效**，只留狀態回饋。
3. **只做必要按鈕**：每個按鈕都要對應一個真實使用者任務，做不出對應就不要加。
4. **一眼可點**：每個可互動元素都要一看就知道能點、且知道按了會發生什麼（affordance + signifier）。
5. **前後台同功能同分頁**：同一功能在前台與後台用同名分頁，使用者一套心智模型走到底，用 bar 切換。
6. **每頁都有返回**：所有詳情頁 / 子頁都要有明確「返回上一層」，使用者永遠不會卡死。

---

## 1. 視覺語言：固定科技風（延伸現有 token，別發明新風格）

專案 `styles.css` 的 `:root` 已建立科技風語言，**一律沿用、只擴充、不另起爐灶**：

| 角色 | 既有 token / 值 | 用途 |
|---|---|---|
| 深空底 | `--argus-navy-950 #050a1c` / `-900 #060b1f` / `-800 #0a1535` | 頁面與卡片底色 |
| 主色（科技藍） | `--argus-cyan-dot #0ea5e9`、cyan glow rgba(56,189,248,…) | 主要 CTA、focus、強調、連結 |
| 玻璃 / 邊光 | `rgba(103,232,249,.45)` border + `0 0 14px rgba(34,211,238,.45)` glow | glassmorphism 卡片、hover 光暈 |
| 危險 | red / magenta `rgba(239,68,68,…)` | 刪除、取消掃描、失敗狀態 |
| 成功 | green | 完成、通過 |
| 警告 | amber | 注意、待處理 |

做法：

- **暗色科技底為主**：深 navy 漸層 + 浮動 ambient 光暈（cyan / indigo orbs），靠「深底 × 亮光洩漏」做出層次與氛圍，不要平塗純色。
- **玻璃擬態**：卡片用 `backdrop-filter: blur()` + 半透明底 + 1px 內光邊（沿用既有 box-shadow inset 寫法）。
- **霓虹點綴克制**：neon glow、scanline、glitch 只當點綴，不能蓋過內容；文字一律維持高對比（接近白）以保可讀。
- **字體**：標題用具科技感的 display 字體、內文用清晰易讀字體；前台公開頁字級已刻意放大（評審老花），延續 `.public-shell` 的放大規則，不要縮小。
- **禁止 AI slop**：不要亮白底 + 紫漸層、不要 Inter/Arial 當招牌字、不要每次生成都換一套配色。Argus 的識別＝深藍 × 科技藍 × 玻璃光。

> 樣式一律寫進 `styles.css`、用 CSS 變數、BEM-like 命名（`.頁面-元素`），**禁止 inline style**（動態計算值除外）。詳見 `frontend/CLAUDE.md`。

---

## 2. 動畫與特效：前台重、後台輕

**前台公開頁（`.public-shell`：`/project` `/team` `/purchase` `/reviews` 等行銷頁）— 放手做複雜動效：**

- 進場用一次精心編排的 **staggered reveal**（`animation-delay` 階梯式淡入上移，沿用既有 `fade-up`），一次高衝擊的 page-load 勝過一堆散亂微互動。
- hover glow、scroll-triggered 顯現、ambient 漸層光暈緩慢飄移、scanline / glitch 點綴。
- 一律走 **GPU 友善屬性**（`transform` / `opacity` / `backdrop-filter`），不要動會觸發 reflow 的 layout 屬性，維持 60fps。

**後台（`/admin/*`）— 動效克制：**

- 後台重效率，**不放炫技動畫**。只保留功能性回饋：hover、focus、loading、狀態切換、資料更新的輕量過場。
- 表格 / 表單 / 圖表不要進場特效干擾閱讀。

**無障礙（兩邊都要）：**

- 一律尊重 `@media (prefers-reduced-motion: reduce)`：關閉動畫時顯示靜態版，不可只有動態版。

---

## 3. 只做必要按鈕（克制 UI）

- **每個按鈕都要能直接追溯到一個真實使用者任務**。寫不出「使用者為什麼需要按它」就不要加。
- 不加推測性 / 「未來可能用到」的按鈕，不加重複入口，不為單一情境硬造彈性。
- **一個畫面最多一個主要 CTA（primary 實心）**，其餘降為次要（ghost / outline）。視覺權重要分明，別讓使用者在五顆同等顯眼的按鈕前猶豫。
- 破壞性操作（取消掃描、刪除評論、調整點數）：二次確認 + 紅色視覺區隔，且文案講清楚後果。

---

## 4. Affordance：一眼看出怎麼觸發功能

目標：使用者**不用試**就知道哪裡能點、按了會發生什麼。

- **可點＝看起來可點**：主要動作用實心 neon fill；次要用 ghost outline；都要有明確 `:hover` / `:active` / `:focus-visible` 狀態 + `cursor: pointer` + 足夠對比。
- **signifier 要配 label**：按鈕文字用**動詞**（「開始掃描」「下載報告」「取消任務」），不要只丟一個 icon 讓人猜；icon 要搭文字或 tooltip。
- **連結 vs 按鈕可區分**：兩者外觀不要混淆。
- **狀態可見**：loading（spinner / 骨架）、disabled（降透明 + 不可點）、成功 / 失敗都要有明確視覺回饋，不要「按了沒反應」。
- **鍵盤可達**：所有互動元素要有 `:focus-visible` 樣式，可 Tab 到、可 Enter 觸發。

---

## 5. 前後台對應：同功能同分頁，用 bar 切換

**原則**：同一個業務功能，在前台與後台用**同名分頁**，使用者建立一套心智模型即可兩邊通用。

| 功能 | 前台（使用者） | 後台（staff `/admin/*`） |
|---|---|---|
| 掃描 | `/scans`、`/scans/:id`、`/scans/:id/topology` | `/admin/scans`、`/admin/scans/:id` |
| 評論 | `/reviews` | `/admin/reviews` |
| 內容 / CMS | `/project`、`/team`（公開呈現） | `/admin/content` |
| 方案 / 購買 | `/purchase` | `/admin/plans` |
| 交易 / 錢包 | 使用者錢包 | `/admin/transactions` |
| 使用者 | （個人資料） | `/admin/users`、`/admin/users/:id` |

**導覽 bar：**

- 前台：頂部 `PublicNav` 橫向導覽列。
- 後台：左側固定**深色 sidebar**（沿用既有 admin sidebar CSS 變數）。
- **同網域子頁用 segmented tab bar 切換**（例：scan detail 的「總覽 / Findings / 拓樸」），切換時不離開當前情境。
- tab 數量克制：同一層超過約 5–7 個就重整資訊架構，不要硬塞。

---

## 6. 每頁都有返回（不讓使用者卡死）

- **所有詳情頁 / 子頁**（`/scans/:id`、`/admin/users/:id`、`/admin/scans/:id` 等）一律放明確「← 返回上一層」+ breadcrumb。
- 對齊瀏覽器 **Back 心智模型**：Back 要回到「使用者認知的上一頁」。overlay / lightbox / 篩選 / 排序**不要污染 history stack**（這是業界最常見的 Back 破壞點）。
- 後台是複雜 app → 一定要有 **in-app Back（Up）**，不要依賴瀏覽器 Back 把人帶出 App 邊界。
- Modal：`Esc` 可關 + 點遮罩可關，且不留在 history 裡。

---

## 實作硬限制（來自 `frontend/CLAUDE.md`，不可違反）

- `App.jsx` 是 6500+ 行單檔：改前**先 grep 定位**，禁止從頭瀏覽；路由在底部 `<Routes>` 區（約第 6460 行）。
- **禁止新增獨立 `.jsx` / `.tsx` 元件檔**（單檔架構）。
- 樣式只寫 `styles.css`，BEM-like 命名，**禁止 inline style**（動態值除外）。
- build 一律 `cd frontend ; .\build-node22.ps1`，**禁止 `npm run build`**（Node 24 + Rollup crash）。
- API 走 `api.js` 的 axios instance，**禁止元件內直接 `fetch` / `axios`**。

---

## 業界依據（rationale 出處，需要深究時查）

- 共用 design system + tab 切換、一致性：Pencil&Paper、Eleken — https://www.pencilandpaper.io/articles/ux-pattern-analysis-data-dashboards ／ https://www.eleken.co/blog-posts/ux-navigation-design
- Affordance / signifier、讓按鈕看起來可點：NN/g「Beyond Blue Links」、UXPin — https://www.nngroup.com/articles/clickable-elements/ ／ https://www.uxpin.com/studio/blog/affordances-user-interaction/
- Back button 期待與常見破壞點：Baymard、Smashing Magazine — https://baymard.com/blog/back-button-expectations ／ https://www.smashingmagazine.com/2022/08/back-button-ux-design/
- 暗色玻璃擬態 / 科技風配色與 60fps 實作：CYBERCORE CSS、Dark Glassmorphism 2026 — https://dev.to/sebyx07/introducing-cybercore-css-a-cyberpunk-design-framework-for-futuristic-uis-2e6c ／ https://medium.com/@developer_89726/dark-glassmorphism-the-aesthetic-that-will-define-ui-in-2026-93aa4153088f
