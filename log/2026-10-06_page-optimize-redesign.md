# 頁面優化重新設計：兩層優化、成果頁、Notion 式分享、側邊欄固定

**日期**：2026-10-06
**操作者**：Claude

## 變更內容

### 側邊欄上下跳動
- 實測原因：會員導覽列高度由內容撐出（75.4px），側邊欄 sticky `top` 是 92px、自然位置 99.4px，捲動時在兩者間位移約 7px；內容長短切換時捲軸出現／消失也讓版面左右跳。
- `64-project-switcher.css`：≥921px 會員導覽列內層固定 `height: 75px`；`:root:has(.public-nav.is-member)` 設 `scrollbar-gutter: stable`。
- `legacy-member/93-projects.css`：`.project-sidebar` sticky `top: calc(76px + 1.5rem)`，`max-height` 限制在視窗內並自行捲動（`overscroll-behavior: contain`）。

### 後端（`apps/rebuild`）
- `models.py`：`SiteRebuild.share_access`（private／link／login）、`outcome`（JSON）；`share_is_active` 改依存取層級判斷，`share_expires_at` 為空＝不過期。
- migration `0007_rebuild_share_access_outcome`：新增兩欄，既有分享連結回填為 `link`（保留原到期時間）。
- `metrics.py`（新）：以同一套規則量測原始與優化後 HTML，只回有變化的指標，不呼叫模型。
- `services.py`：解析 `summary`／`edits[layer, category, why, impact]`／`not_handled`；成功時把摘要、未處理與指標寫入 `outcome`；`apply_edits` 另拒絕 CSS 的 `@import`、外部 `url()`、`expression()`、`-moz-binding`、`behavior:`。
- `prompts.py`：每次請求的指令改為兩層（技術修正＋視覺與 UX 改善），附格式範例。
- `serializers.py`：`page_findings`（不含證據）、`public_edits`（不含 `find` 原文）、列表的 `share_path`／`share_access`／`share_active`／`result_summary`，詳細的 `outcome`／`findings`。
- `views.py`：`share` POST `{access}` 開啟或切換（token 第一次產生後固定），DELETE 改回僅限本人；公開端點 `login` 模式未登入回 401；`html/` 只接受 `Sec-Fetch-Dest` 為 empty／iframe／frame，直接整頁開啟回 403。
- `docs/opencode-agents/argus-rebuild.md`：agent 定義檔全文改寫（工程師兼 UI/UX 設計師、兩個層次、避免 AI 模板感、回覆格式與範例、安全規則）。

### 前端
- 新成果頁 `features/optimize/OptimizationResultPage.jsx`（`/scans/:scanId/rebuild/:rebuildId`，側邊欄選中「頁面」）：原始頁面 → 發現的問題 → Argus 的修改 → 優化後頁面 → 可量測的改善；前後對照（並排／原始／優化後 × 桌面／手機）、修改清單依視覺／SEO／無障礙／效能分組、改善指標、未處理項目；動作只留分享、下載優化版 HTML、重新優化；AI 說明與追問收合在最下方。
- 新分享頁 `features/optimize/SharedOptimizationPage.jsx`（`/optimized/:token`）：精簡頁首、唯讀、無會員導覽與管理動作；需登入模式顯示登入提示；舊 `/share/rebuilds/:token` 轉址。
- `components/optimize/`：`OptimizationReport`、`ComparisonViewer`、`ShareDialog`、`optimizeLabels`；樣式 `legacy-member/96-optimize.css`。
- `PageRebuildPanel.jsx` 改寫：開始優化／進行中／完成摘要（視覺、技術、可量測改善數）＋查看前後對照、分享、重新優化；**移除原樣複刻與下載原樣複刻**。
- 刪除 `RebuildWorkspace.jsx`、`SharedRebuildPage.jsx`、`13-page-rebuild.css`（兩份）與 `73-public-refine.css` 的 `share-*`；重新產生 `openapi.json`／`apiTypes.ts`。

### 文件
- `backend/apps/rebuild/CLAUDE.md`、`backend/CLAUDE.md`、`frontend/CLAUDE.md`、`docs/opencode-site-rebuild.md`、需求書 F-029。

## 原因
使用者回饋：桌面全螢幕時側邊欄會上下移動；「優化此頁」只修技術問題，畫面看起來一模一樣，看不出 Argus 做了什麼；原樣複刻沒有價值；分享要像 Notion／Figma／Google Docs 一樣有固定連結與存取層級，可以隨時關閉。

## 影響範圍
- 部署需套用 migration `rebuild/0007`（只新增欄位與回填，無破壞性）。
- **agent 主機的定義檔要同步更新**：把 `docs/opencode-agents/argus-rebuild.md` 複製到 agent 主機的 `~/.config/opencode/agent/argus-rebuild.md` 並 `sudo systemctl restart opencode`，否則舊定義只會回技術修正。
- 既有分享連結仍可用（回填為「知道連結的任何人」，保留原到期時間）；新的分享不會過期。
- 舊成果（沒有 `outcome`）仍能顯示修改清單，只是沒有摘要與指標。

## 驗證方式
- `uv run python backend/manage.py test apps.rebuild`：91 項 OK（含兩層記錄、分享唯讀不洩漏帳號、HTML sandbox 與直接開啟 403、連結關閉再開不變、需登入模式、非擁有者不能改、舊連結到期、CSS 外部資源拒絕、指標計算）。
- `uv run python backend/manage.py test apps`：1478 項 OK（skipped=1）。
- `uv run ruff check backend`：通過。
- 前端 `npm run lint`（0 errors）、`npm run typecheck`、`npm test`（218 項通過）、build 成功。
- 本機瀏覽器端對端（模擬 agent 走真實 `run_rebuild` 路徑，產出 2 筆技術＋4 筆視覺修改）：頁面列面板、成果頁版面、手機對照、分享對話框與 `/optimized/<token>`、Esc 關閉、未登入看不到會員導覽與側邊欄、舊連結轉址、390px 無水平捲動、需登入導向 `/login?next=`、關閉後顯示「這個分享連結無法使用」、無 JS 錯誤；側邊欄捲動與切換分頁時固定在 100px（修正前 99.4→92）。
- **需人工確認**：正式環境以真實 agent（新定義檔）優化一頁，確認視覺改善實際看得出差別且沒有改變品牌與內容。
