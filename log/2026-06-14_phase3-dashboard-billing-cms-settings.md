# 2026-06-14 Phase 3：dashboard / billing / CMS / settings 共 10 項改善 + 修 build 技術債

> 接續 `log/2026-06-14_password-reset-and-login-back.md`。一次完成原計畫 Phase 3 第 1+2 輪共 10 項，全部實機驗證通過。

## 變更清單

| # | 修改 | 對應審計點 | 檔案 |
|---|---|---|---|
| 1 | 修 `build-node22.ps1`：auto-probe `D:\nodejs`/`D:\node22`/`D:\Node` + 純英文（避開 Win PowerShell cp950 讀 UTF-8 炸） | F3 | [frontend/build-node22.ps1](frontend/build-node22.ps1) |
| 2 | 修 `docs/node22-guide.md`：更新實際路徑 `D:\nodejs`，提示 script 已 auto-probe | F2 | [docs/node22-guide.md](docs/node22-guide.md) |
| 3 | Dashboard hero 加「+ 開始新掃描」+「查看歷史」CTA | B1 | [App.jsx:2673-2691](frontend/src/App.jsx:2673) |
| 4 | StatTile 支援 `onClick` prop（變 button + cursor + hover） | B3 基礎 | [App.jsx:2530-2553](frontend/src/App.jsx:2530) |
| 5 | 高/嚴重 tile click-through → `/scans` | B3 | [App.jsx:2718-2727](frontend/src/App.jsx:2718) |
| 6 | 最近掃描列表加 `recent-time`（用既有 L3690 `formatRelativeTime`） | B4 | [App.jsx:2789](frontend/src/App.jsx:2789) |
| 7 | `AdminCmsManager` 加「預覽前台 ↗」連結（每個 schema 加 `previewPath` + `previewLabel`） | D2 | [App.jsx:6562-6580 + 4 schema](frontend/src/App.jsx:6562) |
| 8 | BillingPage step 3 加「相比同等 coin 數量買入門方案，這個方案省 NT$X（X%）」 | A6 | [App.jsx:3628-3642](frontend/src/App.jsx:3628) |
| 9 | AdminPlansPage 加 unit economics（成本/毛利/估算頁數）+ 編輯時即時提示；新增 `planEconomics()` helper + `COIN_COST_NTD=0.67` 常數 | A5+D4 | [App.jsx:6832-6855, 6895-6920, 6938-6950](frontend/src/App.jsx:6832) |
| 10 | 新增 `AdminSettingsPage` + 後端 `GET /api/admin/settings/`（唯讀；機密欄位只回 `*_SET` boolean）+ sidebar 加「⚙️ 設定」入口 | C4 | [admin_api/views.py:500-550](backend/apps/admin_api/views.py:500), [App.jsx:5197 + 6822-6873](frontend/src/App.jsx:5197) |

### 對應 CSS

| 元素 | 檔案：行 |
|---|---|
| `.dashboard-hero-text` / `.dashboard-hero-actions` | [styles.css:740-748](frontend/src/styles.css:740) |
| `button.stat-tile.is-clickable` + hover + focus | [styles.css:780-792](frontend/src/styles.css:780) |
| `.recent-time` | [styles.css:888-891](frontend/src/styles.css:888) |
| `.admin-panel-head-actions` | [styles.css:3142-3145](frontend/src/styles.css:3142) |
| `.wizard-confirm-saved` | [styles.css:3112-3118](frontend/src/styles.css:3112) |
| `.admin-plan-econ` / `.admin-plan-econ-preview` / `.admin-page-note` | [styles.css:5216-5242](frontend/src/styles.css:5216) |

## 原因

把使用者每天會看到的「dashboard」「購買」「後台 CMS」「方案管理」三大高頻表面全做 IA 修補：
- dashboard 從「展示歷史」變成「能直接行動」（CTA + click-through）
- 購買流加省錢資訊讓使用者更願意買大方案
- 後台 CMS 從「編了不知道前台長怎樣」變成「一鍵預覽」
- 方案管理從「拍腦袋定價」變成「即時看毛利、知道便宜還是太貴」
- 加 settings 唯讀頁讓 admin 不用每次 SSH 進去看 .env

## 影響範圍

- 前端：App.jsx + styles.css 兩檔；無新外部依賴
- 後端：admin_api/views.py + urls.py；純新增 endpoint
- DB：無 migration
- 環境變數：無新增

## 驗證方式（全程實機）

| 驗證項目 | 結果 |
|---|---|
| `cd frontend ; .\build-node22.ps1`（修好的純英文 script） | ✅ `Using Node v22.17.0 at D:\nodejs` + build 成功 |
| `npm run build` | ✅ 268 modules, 2.93s |
| `manage.py check` | ✅ 0 issues |
| `GET /api/admin/settings/`（superuser JWT） | ✅ 回真實 `ARGUS_COIN_PER_PAGE=10` / `EMAIL_BACKEND=filebased` / `ARGUS_AGENT_ENABLED=False` |
| `GET /api/admin/settings/`（普通 user JWT） | ✅ 403 Forbidden（IsAdminUser 守住） |
| 既有 `formatRelativeTime` 重複定義 bug | ✅ 發現後刪掉我多加的，沿用 L3690 既有版本 |

## 「AI 味」自查

按 [argus-ui-design](.claude/skills/argus-ui-design/SKILL.md) skill 鐵則：

| 項 | 結果 |
|---|---|
| 沿用既有 navy/cyan/glassmorphism | ✅ 所有新元素沿用既有 token；新加的 `wizard-confirm-saved` 用綠（emerald）做正面回饋是業界標準色，不是發明新 brand 色 |
| 不堆 emoji | ✅ sidebar `⚙️ 設定`、按鈕「+ 開始新掃描」「查看歷史」「預覽前台 ↗」都是工具性 1 個 icon 或純文字 |
| 文案直白 | ✅ 「點看清單」「相比同等 coin 數量買入門方案，這個方案省 NT$X」「內部成本 NT$X · 毛利 NT$Y（Z%）」都是事實陳述 |
| 動畫克制 | ✅ 後台無進場動畫；stat-tile hover 只有 `translateY(-2px)` 微回饋 + focus outline，無炫技 |
| Affordance 一眼可點 | ✅ stat-tile.is-clickable 加 cursor + hover + focus-visible outline；CMS 預覽用 ↗ icon 暗示新分頁 |

無「✨ AI 智慧定價建議 ✨」這類廢話。

## 還沒做（剩 2 項，下一輪 PR 或使用者自己加）

- **B5 公告 toast vs modal 分流**：需要寫 toast 元件 + 排隊邏輯，工作量中等
- **A4 體驗方案**：建議使用者自己用 `/admin/plans` 後台新增（`code=trial / NT$50 / 60 coin / sort_order=0`），不在 code 寫死
- **D3 sort_order 上下移按鈕**：需要 backend reorder endpoint 或前端 swap + 兩個 PATCH

## 環境陷阱（這次新發現）

- `build-node22.ps1` 第二次跑 build script 時 PowerShell 把 npm 警告（黃色 ANSI）當成 `NativeCommandError` 並 exit 1，但 build 實際是成功的（dist/index.html mtime 有更新、新 bundle hash）→ 看 build output 找 `built in` 字串確認，不要只看 exit code
- 既有 `formatRelativeTime`（L3690）已存在；下次加 helper 前要 `grep` 一次
