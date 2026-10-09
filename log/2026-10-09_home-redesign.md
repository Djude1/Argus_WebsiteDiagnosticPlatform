# 首頁（/project）重新編排與配色

**日期**：2026-10-09
**操作者**：Claude

## 背景
使用者認為首頁內容太多、太亂，配色不夠成熟。要求參考 https://www.tradinggoose.ai/zh 首頁重做編排與配色。

## 參考站的設計語言
用 Playwright 實際截圖對照，歸納出以下幾點：
- 近黑底加淡網格，只用一個強調色，邊框是 1px 細線。
- hero 置中：上方小徽章、大標題（關鍵詞加底線）、標籤列、主要與次要按鈕，下面是中心節點連線圖。
- 段落開頭用小字距眉標，接大標題；版面多為左文右卡。
- 清單項目前面放強調色的短橫線。
- 頁尾前有一塊網格底的 CTA。

## 變更內容
- **新增 `features/public/ProjectPage.jsx`**（獨立 lazy chunk），`App.jsx` 改從這裡載入首頁。
- 新首頁的段落：
  1. hero：徽章、標題「看見網站的每一個問題」、五個面向、開始掃描與免登入快速檢查，下方是中心節點圖（Argus 之眼連到六個節點）。
  2. 運作方式：四個步驟。
  3. 即時進度：掃描示意畫面。
  4. 你會拿到什麼：互動報告、PDF 報告與查驗、頁面優化，各配一張示意卡。
  5. 安全邊界：四項。
  6. 技術：品牌 logo 牆，沿用 `brandMarks.jsx`。
  7. 常見問題。
  8. 結尾 CTA。
- **修正舊內容與現況不符的地方**：
  - 舊版寫「四維」，現在是五個面向。
  - 舊版的 AEO 說明寫「FAQPage／HowTo」，現在是可回答性檢測。
  - UX 不只檢查破版。
  - 頁面優化已取代修正產出分頁。
  - 舊版沒寫第一次完整掃描免費。
  - 計費、贈點、首次免費依 `ARGUS_COIN_PER_CATEGORY`、`ARGUS_MONTHLY_BONUS_COINS`、`ARGUS_FREE_TRIAL_SCAN_ENABLED` 核對。
- **不再讀 CMS「專案特色」**（`/content/features/`）。後台「網站內容 → 專案特色」分頁仍可編輯，但首頁已不顯示。
- **樣式**：`73-public-refine.css` 新增 `.home2-*`。
  - 顏色用 `.home2` 上的 `--h-*` 變數，日間與夜間各一組。
  - 整頁背景由 `.public-shell:has(.home2)` 換成平底。
  - 沒有彩色左邊條；嚴重度用徽章加文字。
  - 手機版的節點圖改成一排圖示。
- **移除只有舊首頁使用的程式與樣式**：
  - 元件：`ScanPipeline.jsx`、`PipelineDiagram.jsx`、`TechMarquee.jsx`。
  - 整個 `71-scan-pipeline.css`。
  - `70-home.css` 的產品預覽、品牌 hero、統一面板樣式。
  - `21-public.css` 的技術棧面板與 marquee。
  - `35-public-legacy.css` 的 `public-hero--console` 系列。
  - `73` 的檢測面向、交付物、證據說明、面板覆寫。
  - `01`、`02` 的 marquee 字級與動畫。
  - 商業合作頁仍在用的 `home-evidence-sample` 系列保留。
- **文件**：`frontend/CLAUDE.md`（公開頁樣式、路由表、核心檔案、動態之眼用途）、`docs/brand-guidelines.md`。

## 驗證方式
- `npm run lint`：0 error，1 個既有 warning（AdminPages）。
- `npm run typecheck` 通過。
- `npx vitest run`：39 個檔案、256 項全過。
- `vite build` 通過。
- `vite preview` 加 Playwright 截圖：
  - 夜間與日間各兩種寬度：1440px、390px。
  - 4 種組合都沒有頁面錯誤，也沒有水平捲動（scrollWidth 等於視窗寬）。
  - 依截圖修正：清單短橫線粗細、副標換行、日間背景被舊漸層蓋過、手機標題斷字。

## 尚未做／觀察
- 後台「專案特色」分頁不再影響首頁，要不要移除留待使用者決定。
- 其他公開頁（購買、快速檢查、下載、查驗、商業合作）仍是舊配色，頂部導覽列與頁尾也沒改。

## 追加修正：最上面的品牌 hero 還原（同日）
- 使用者指出：要改的是 hero 以下的區塊（從「argus.example.com 示意」的掃描畫面開始），最上面的 hero 不在範圍內，卻被改成新的置中 hero 加節點圖。這是我的錯，擴大了修改範圍。
- 已還原原本的品牌 hero，內容如下：
  - 會動的之眼、ARGUS 藝術字、「掃描 · 洞察 · 證據」。
  - 標題「一鍵看見網站的所有問題」與兩行副標。
  - 「登入進行詳細檢查」「免登入先試單頁檢查」兩個按鈕。
- 還原方式：
  - JSX 照原樣放回 `ProjectPage.jsx`。
  - `35-public-legacy.css` 的 `.public-hero--console` 系列，以及 `70-home.css` 的品牌 hero、藝術字、副標強調樣式，都從原檔取回。
  - 刪掉新 hero 用到的 `.home2-hero`、徽章、節點圖等樣式。
- 驗證：
  - 改版前的 commit（ab5543f）用 git worktree 另外 build 一份，與目前版本並排截圖：日間與夜間 1440px、夜間 390px。
  - hero 內容與排版一致，只有動畫進行到的時間點不同。
  - lint、typecheck、build 通過。
- `frontend/CLAUDE.md` 已註明「最上面的品牌 hero 維持原樣，不要再動」。

## 最終結果：整頁還原（同日）
- 使用者決定整個首頁先還原。
- 以 `git revert` 撤回 38a4587（改版）與 5adad8c（hero 還原）。`frontend/` 與 `docs/` 已和改版前的 ab5543f 完全相同（`git diff ab5543f -- frontend docs` 無差異）。
- 恢復原狀的項目：
  - 舊的 `ProjectPage`（在 `PublicPages.jsx`）。
  - CMS「專案特色」再次顯示在首頁。
  - 掃描鏈路圖、技術 marquee 等元件與樣式。
- 本 log 保留，作為這次改版與撤回的紀錄。
- 驗證：lint、typecheck、vite build 通過。
