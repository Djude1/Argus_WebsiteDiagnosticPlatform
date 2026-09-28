# Argus 品牌與介面規範（Night Watch）

> 程式碼的單一事實來源是 `frontend/src/styles/03-tokens.css`（token）與 `frontend/src/styles/05-brand.css`（品牌元件）。本文件說明「為什麼」與「怎麼用」。

> **適用範圍（2026-09-28 起）**：本規範適用於登入後的會員區、掃描報告與後台。公開頁（`.public-shell`：首頁、快速檢查、購買、下載、報告查驗、評論）維持改版前的視覺——系統字、深藍＋科技青——並以 `73-public-refine.css` 做克制整理，見 `frontend/CLAUDE.md` 樣式規範。

## 1. 品牌概念

**Argus Panoptes——百眼巨人，永不同時闔眼的守望者。**
Argus 替使用者「看見」網站在 SEO／AEO／GEO／資安／UX 上的所有問題，並直接給出可用的修正。

| 關鍵字 | 在介面上的表現 |
|---|---|
| 守望（Watch） | 深夜墨藍底、細網格「掃描面」底紋、觀景窗四角框 |
| 看見（Seeing） | 虹膜青主色、Argus 之眼標誌、虹膜環形分數 |
| 洞察（Insight） | 守望琥珀——只用在「值得注意」的地方：反光點、重點提示、次要 CTA |
| 可信（Trust） | 克制的動態、清楚的層級、等寬字呈現可驗證的技術資訊 |

語氣：專業、直接、不恐嚇。講「找到 3 個高風險問題，這是修法」，不講「你的網站危險了！」。

## 2. 標誌

一律使用專案原有的品牌圖，不使用向量重繪版（元件 `components/brand/ArgusMark.tsx`）：

- **Logo `ArgusLogo`**：`assets/brand-logo.webp`（之眼＋ARGUS 字標）——導覽列、頁尾、後台側欄、登入頁。
- **之眼圖示 `ArgusMark`**：`assets/argus-eye-still.webp`——登入頁、狀態圖示、空狀態等；`scanning` 屬性加呼吸光暈。
- **動態之眼**：`assets/argus-eye.webp`——專案介紹頁 hero（原版掃描動畫，樣式在 `34-classic-hero.css`）。
- 日間主題下 logo 以 filter 壓暗以便在淺底上辨識；後台側欄恆為深色，維持原色。
- 不要：拉伸、改色、加額外外框。

## 3. 色彩

全站只用 `--ag-*` 語意 token；深色值在 `:root`，日間值在 `:root[data-theme="light"]`。**規則不要寫兩套顏色。**

| Token | 用途 |
|---|---|
| `--ag-bg` / `--ag-bg-raised` | 頁面底色／略浮起的底（輸入框、抽屜） |
| `--ag-surface` / `-2` / `-3` | 卡片／卡片內區塊／軌道、停用 |
| `--ag-border` / `-strong` / `-accent` | 分隔線／輸入框邊／hover 與選取 |
| `--ag-text` / `-2` / `-3` | 主要／次要／輔助文字（皆通過 WCAG AA） |
| `--ag-primary`（虹膜青） | 主要動作、選取狀態、連結 |
| `--ag-accent`（守望琥珀） | 重點提示、次要強調；一個畫面最多一兩處 |
| `--ag-good / warn / bad / info` | 狀態 |
| `--ag-sev-critical … info` | 嚴重度（徽章、長條、圖表） |
| `--ag-cat-seo / aeo / geo / security / ux` | 五個掃描維度 |

主要按鈕在深色主題是「青底深字」（`--ag-on-primary`），在日間是「深青底白字」，兩者對比都 ≥ 4.5:1。
已淘汰：青→紫漸層、靛紫 `#6366f1` 按鈕、Tailwind `slate-*` / `blue-*` 硬編碼色。

## 4. 字體

| Token | 字體 | 用途 |
|---|---|---|
| `--ag-font-display` | Sora + Noto Sans TC | 標題、分數、大數字（`.ag-num` 開 tabular-nums） |
| `--ag-font-sans` | Noto Sans TC | 內文、介面 |
| `--ag-font-mono` | JetBrains Mono | URL、程式碼、眉標（`.ag-eyebrow`）、技術識別碼 |

字級節奏：12 / 14 / 16 / 20 / 24 / 32 / 48 / 64。內文行高 1.7，標題 1.15–1.3。

## 5. 形狀、陰影、動態

- 圓角：`--ag-r-sm` 8（小元件）、`-md` 12（按鈕、輸入）、`-lg` 16（卡片）、`-xl` 22（大區塊）。
- 陰影：`--ag-shadow-1/2/3` 三級；光暈 `--ag-glow` 只給「選取中／焦點」使用。
- 動態：`--ag-ease`，時長 120 / 200 / 360ms；所有動畫都受 `prefers-reduced-motion` 關閉。

## 6. 標誌性元件

| Class / 元件 | 說明 |
|---|---|
| `ArgusMark`, `ArgusLogo` | 品牌標誌 |
| `IrisScore` | 0–100 分數環（≥80 good、≥60 medium、其餘 bad），12 道刻度呼應標誌 |
| `.ag-eyebrow` | 等寬眉標，前導虹膜點 |
| `.ag-viewfinder` | 觀景窗四角框，包住重點區塊 |
| `.ag-surface-grid` | 掃描面細網格底紋 |
| `.panel`, `.primary-button`, `.secondary-button`, `.ghost-button`, `.input`, `.severity`, `.status-badge`, `.category-pill` | 核心元件，已全面 token 化 |

## 7. 無障礙底線

- 文字對比 ≥ 4.5:1（大字 ≥ 3:1）；不要只靠顏色傳達嚴重度，一律附文字標籤。
- 所有互動元素有 `:focus-visible` 樣式；觸控目標 ≥ 40×40px。
- 動畫尊重 `prefers-reduced-motion`；手機寬度（≤ 390px）不得出現水平捲動。
