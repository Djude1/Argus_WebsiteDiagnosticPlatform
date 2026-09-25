# 後台 UI 重構 S0（地基）＋ S1（接上斷點）

**日期**：2026-09-25  
**操作者**：Claude

## 變更內容

### S0 地基
- `styles.css`：`:root` 新增後台語意 token（`--admin-canvas` / `--admin-surface` / `--admin-surface-sunken` / `--admin-border` / `--admin-text*` / `--admin-accent` / `--admin-sidebar-*`），全部由既有品牌色衍生，未引入新色系。
- `.admin-sidebar` 背景由寫死的 `#0f172a → #1e293b`（Tailwind slate 預設值）改為 `--argus-navy-950 → --argus-navy-800`；右邊界改 cyan 微光。
- `.admin-main` 由三段漸層改為單一平色 `--admin-canvas`。
- 新增共用元件：
  - `shared/formatters.js`（`formatDateTime` / `formatDate` / `formatRelative` / `formatDuration` / `formatNumber` / `formatNtd`）
  - `components/admin/AdminStates.jsx`（`AdminSkeleton` / `AdminEmptyState` / `AdminErrorState`）
  - `components/admin/AdminModal.jsx`（`AdminModal` ＋ `AdminField`）
  - `components/admin/AdminPagination.jsx`（原本是 `AdminPages.jsx` 的內部函式，無法重用）
- 收斂後台的三套 modal（CMS 的 `.admin-modal` 手寫外殼、方案與公告的 `.ann-modal`）為單一 `AdminModal`；`.admin-add-btn` → `.admin-btn primary`；`.input` → `.admin-input`。
- 後台 11 處 `toLocaleString("zh-Hant")` 全數改走 formatters。
- 表格數字欄位加 `font-variant-numeric: tabular-nums`。

### S1 接上斷點（後端零改動）
- **新增 `/admin/orders`**（`features/admin/AdminOrdersPage.jsx` ＋ `App.jsx` 路由 ＋ 側欄導覽項）。後端 `orders_list` 早已實作 `q` / `status` / `invoice_type` 篩選，前端先前完全沒有 UI。含狀態分段切換、搜尋、發票類型篩選、明細 modal。
- **概覽補上 `recent_scans`**：`overview` API 一直有回傳，前端未使用。與「最近購買」並列，列可點進掃描詳情。
- **掃描詳情補上 `top_actions` 與 `warning_summary`**：兩者 `scan_detail` 一直回傳、前端未使用。新增 `AdminScanWarnings` 元件，依 `crawler.py` 的實際結構（`blocked_urls` / `failed_urls` / `screenshot_failures` / `tech_stack`）分組收合呈現。

## 原因
依 2026-09-25 的後台 UI/UX 重構規劃（使用者審閱通過後指示開工）執行路線圖的 S0 與 S1。

- 後台「像通用管理面板」的直接原因是品牌 token 就在 `:root` 裡卻沒被後台使用——sidebar 用的是 Tailwind slate 預設值。
- S1 三項皆為後端已完成、前端未接上的能力，後端零改動即可補齊功能缺口，投入產出比最高。發票／統編類客訴先前在後台完全無從查起。

## 影響範圍
- 只動後台（`/admin/*`）與新增的共用元件；前台與使用者端頁面未改動。
- **`.ann-*` CSS 保留未刪**：`shared/AppShared.jsx` 的全站確認對話框（`useConfirmDialogs`）也使用這組樣式，刪除會波及整站。僅把後台兩頁遷移走。
- `AdminPages.jsx` 產出 chunk 由 63.65 kB 降至 61.70 kB。
- 新增 `AdminOrdersPage` 獨立 chunk（8.04 kB），維持 route-level code splitting。

## 驗證方式
- `npx vite build` 通過（12.94s），無錯誤；`AdminOrdersPage` 正確獨立成 chunk。
- 殘留檢查全為 0：`ann-backdrop` / `ann-modal` / `ann-btn` / `admin-add-btn` / `className="input"` / `toLocaleString("zh-Hant")` / `useDialogFocus`（後台內）。
- 新 token 與新元件樣式確認進入產出 CSS；舊的 `#0f172a → #1e293b` 漸層在產出中已歸零。
- **對比度實測**（WCAG AA 內文門檻 4.5）：
  - `#64748b` on `#f4f7fb`（原 muted 於 sunken 底）＝ **4.43 FAIL** ← 規劃階段的推斷獲證實
  - `#5a6b80` on `#f4f7fb`（新增的 `--admin-text-muted-sunken`）＝ **5.08 PASS**
  - 正文 `#0f172a` on `#eef3f9` ＝ 16.00 PASS；warn 4.51 PASS；paid 狀態 4.95 PASS
- **待人工確認**：瀏覽器實際操作訂單頁的搜尋與篩選、掃描詳情的警告展開、各 modal 的 Esc 與遮罩關閉行為。

## 未做（依規劃刻意保留）
- **S4 掃描處置（取消／重排／退點）**：依賴 Q6「重排是否重複扣點」的計費決策，未獲回覆前不動。
- **系統健康頁**：依賴 Q1（是否新增 Celery／Redis 探測端點）。
- **`COIN_COST_NTD` 移到後端**：依賴 Q2。
- S2（URL 狀態與表格排序）、S3（待辦中心）、S5–S7 尚未開始。
- CMS modal 內部仍使用購買流程的 `.wizard-field` 類名，尚未收斂。
