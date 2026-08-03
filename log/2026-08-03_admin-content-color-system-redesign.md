# 後台內容區配色系統重設：去除彩虹漸層樣板感，改用品牌 token

**日期**：2026-08-03
**操作者**：Claude

## 變更內容

- `frontend/src/styles.css`：
  - `.admin-stat-card` 的 `.tone-*` 頂條漸層改為引用既有 `:root` token（`--argus-cyan-dot`/`--argus-cyan-glow`、`--tone-good`/`--tone-good-bright`、`--tone-medium`/`--tone-medium-bright`、`--tone-bad`/`--tone-bad-bright`），取代原本 5 種互不相干的硬編碼色相（cyan/violet/amber/rose/good）；`tone-violet` 規則移除（無語意，改分類為 cyan）。
  - 新增 `.admin-stat-card::after` ⟡ 品牌浮水印：與 sidebar icon 同一 SVG path，以 `mask-image` 純 CSS 實作，右下角 6% 透明度、無動畫，克制的角落品牌識別。
  - `.admin-status.*`（completed/failed/crawling/scanning/agent_testing/queued）改用 `--tone-good`/`--tone-bad`/`--argus-cyan-dot` 的 rgba 淡底 + 對應實色文字，取代原本的 Tailwind 預設淺色徽章色（emerald-100/rose-100/cyan-100 風格）。
  - `.admin-btn.primary` 漸層第二色由 indigo `#6366f1` 改為 `#06b6d4`，與 `.admin-nav-link.active`（sidebar 主色 CTA）用同一組 cyan 漸層，讓「這是 Argus 主要動作」的視覺訊號在 sidebar 與內容區一致。
  - `.admin-staff-chip`/`.admin-super-chip` 由隨機 indigo/pink 改為 cyan（一般 staff）/amber（superuser，語意為「權限提升」）。
  - `.tx-pos`/`.tx-neg` 改引用 `--tone-good`/`--tone-bad`。
- `frontend/src/features/admin/AdminPages.jsx`：
  - `AdminOverviewPage` 6 張 stat card 的 `tone` prop 由隨機分配（violet/amber/rose 各用兩次、彼此無語意關聯）改為：中性數據一律 `cyan`，只有真正有狀態意義的「待回覆評論」用條件式 `warn`/`good`。
  - `AdminReviewsPage` 統計卡同步：修掉既有 bug（`tone="yellow"` 沒有對應任何 CSS 規則，頂條實際上不會顯示顏色），改為 `warn`（沿用新 token 命名）。

## 原因

使用者反映後台「很有 AI 味」，前一輪（2026-07-29 / 2026-08-02）已把 sidebar icon 與 UI chrome emoji 換成品牌 ⟡ glyph，但**後台內容區(stat card、status 徽章、按鈕、chip)從未被設計過**，仍是預設 Tailwind 亮色樣板：5 色彩虹漸層頂條（stat card 逐張隨機配色，其中 2 張還用同一個 violet，彼此毫無語意關聯）、淺色 Tailwind 徽章色、按鈕漸層混用 indigo——這正是 LLM 生成 admin dashboard 的典型長相，也是使用者感受到「沒有系統特色」的根因。與使用者確認方向為「保留亮色內容區（表格密集資料仍需亮色可讀性），只重設配色與細節」（非全面轉深色），故本次只換色彩來源（改引用 `:root` 既有 token）與新增 ⟡ 浮水印，不動版面結構。

## 影響範圍

- `/admin/overview`、`/admin/reviews` 的 stat card 顏色與角落浮水印
- 全站 `/admin/*` 頁面的狀態徽章（`.admin-status`）、主要按鈕（`.admin-btn.primary`）、staff/superuser chip、交易正負號顏色（`.tx-pos`/`.tx-neg`）
- 副作用：`tone="violet"`/`"amber"`/`"rose"`/`"yellow"` 不再是 `AdminStatCard` 的有效值（CSS 規則已移除，若未來新增 stat card 誤用舊值會沒有頂條顏色，需用 `cyan`/`good`/`warn`/`bad`）
- 未觸及：後台版面結構、間距、字級、sidebar（已於前兩輪完成）、前台 `AuthenticatedPages.jsx` 的 `StatTile`（獨立元件與 CSS class，未受影響）

## 驗證方式

- `npm run build`（WSL/Linux，Node 20，非 Windows Node24+Rollup 情境，與 2026-08-02 log 同一核准方式）：✓ 2039 modules、4.89s、無錯誤，最大 chunk 187.6 kB（未超過 500 kB 門檻）
- 全域 grep 確認 `AdminStatCard` 所有 `tone=` 呼叫（10 處）與新 CSS `.admin-stat-card.tone-*` 規則（cyan/good/warn/bad）一一對應，無孤兒值
- 確認 `AuthenticatedPages.jsx` 的 `StatTile`/`tone="violet"` 等用的是獨立 `.stat-grid`/`.stat-tile` class（非 `.admin-*`），未被本次改動影響
- 待使用者手動確認（需登入 staff 帳號）：`/admin/overview` 6 張 stat card 顏色與右下角 ⟡ 浮水印是否清晰可辨、`/admin/reviews` 待回覆/待審檢舉卡片顏色、`/admin/scans` 狀態徽章、任一頁面主要按鈕（primary）視覺
