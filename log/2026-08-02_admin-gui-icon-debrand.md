# 後台 GUI icon 去 AI 化：emoji 全面替換為品牌 glyph

**日期**：2026-08-02
**操作者**：Claude

## 變更內容

- `frontend/src/shared/AppShared.jsx`：新增 `StatusGlyphShell`（15px、stroke 1.75、currentColor）與 7 個掃描狀態 glyph（`StatusQueuedGlyph` 時鐘、`StatusCrawlGlyph` 拓樸、`StatusScanGlyph` 準星、`StatusAgentGlyph` 晶片、`StatusDoneGlyph` 勾號、`StatusFailedGlyph` 叉號、`StatusCancelledGlyph` 禁止）；`STATUS_LABELS` 資料形狀由 `emoji: "🕷️"` 改為 `Icon: ComponentRef`（label / tone 不變）。
- `frontend/src/components/scans/ScanBadges.jsx`：`ScanStatusBadge` 改渲染 `<meta.Icon className="status-badge-icon" />`，未知狀態 fallback `Icon: null`。
- `frontend/src/features/scans/ScanExperience.jsx`：`CRAWL_PHASES` emoji→Icon；爬蟲動畫主圖與階段清單改渲染 glyph（已完成階段顯示 `StatusDoneGlyph`）。`.crawl-phase-emoji` class 名保留以維持 CSS contract。
- `frontend/src/components/admin/AdminIcons.jsx`：新增 `GlyphShell`（16px、無 ⟡ 底、同 stroke 語言）、`AdminMenuIcon`（三橫線）、`AdminStarIcon`（`filled` prop 控制實心/空心）。
- `frontend/src/features/admin/AdminPages.jsx`：☰ 按鈕→`AdminMenuIcon`；總覽/評論統計卡與逐則星等→`AdminStarIcon`；官方回覆標記與 `is_active`/`is_latest` 布林欄→`StatusDoneGlyph`；CONTENT_TABS 標籤去 emoji；公告管理標題移除 📢。
- `frontend/src/styles.css`：新增 `.status-badge-icon`、`.crawl-anim-glyph`（含 compact 24px 變體）、`.crawl-phase-emoji svg`、`.admin-star-icon`（amber）、`.admin-bool-glyph` / `.admin-inline-glyph`（green）尺寸與顏色規則；`.admin-menu-button` 補 flex 置中。
- `docs/superpowers/specs/2026-07-29-admin-sidebar-argus-icons-design.md`：Out of Scope 清單標註完成狀態。

## 原因

使用者反映後台 GUI 使用「AI 喜歡的 icon / emoji」，一眼看出是 AI 生成、沒有系統特色。本次延續 2026-07-29 sidebar ⟡ 品牌 icon 系統的視覺語言（stroke-based、1.75px、currentColor、viewBox 0 0 24 24），把剩餘的 UI chrome emoji 全面替換為手工設計的品牌 glyph。使用者確認「前後台一起改」：掃描狀態徽章為前台 `/scans` 與後台 `/admin/scans` 共用，故 glyph 放在 `shared/AppShared.jsx` 避免循環 import。

## 影響範圍

- 前台：`/scans` 列表與詳情的狀態徽章、掃描進行中的爬蟲動畫與階段清單。
- 後台：`/admin/*` 全部頁面的 ☰ 選單鈕、統計卡星等、評論星等列、布林勾號、內容分頁標籤、公告管理標題。
- **刻意保留**：CMS 欄位提示文字中的 emoji（例：🕷️ 🔍 🤖）屬資料層範例內容；`AuthenticatedPages.jsx` 前台導覽 `NAV_ITEMS` emoji 不在本次範圍（列為後續建議）。
- `docker-compose.yml` 的 `ars.clouda.dpdns.org` 網域改動為使用者既有工作，與本任務無關、未納入。

## 驗證方式

- WSL（OhMyOpencode）內 `npm install` + `npm run build`：✓ 2039 modules、3.54s、無錯誤（Linux 不受 Windows Node24+Rollup crash 影響，此為使用者核准的 build 方式）。
- code-reviewer agent 審查：無 CRITICAL；唯一 HIGH 為 `NAV_ITEMS` emoji（刻意排除範圍）；確認 `STATUS_LABELS` / `CRAWL_PHASES` 無殘留 `.emoji` 讀取者、fallback 正確、CSS 命名合規、無 inline style。
- 待使用者手動確認（需登入 staff 帳號）：`/admin/overview` 統計卡星等、`/admin/reviews` 星等列與官方回覆標記、`/admin/content` 分頁標籤與布林勾號、☰ 收合鈕、公告管理標題；前台 `/scans` 狀態徽章與掃描進行中動畫回歸檢查。
