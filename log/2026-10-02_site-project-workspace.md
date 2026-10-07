# 會員區改為以網站專案為核心的工作區（第二版）

**日期**：2026-10-02  
**操作者**：Claude

## 背景
第一版（`f477fca`）完成後由使用者回退。本次以回退後的 `main`（`5cd88ce`）為基礎重新實作，沿用第一版的資料關係與頁面架構，並依第一版實測經驗補強。

## 變更內容

### 規劃
- `docs/adr/0003-site-project-workspace.md`：專案與掃描的資料關係、頁面資訊架構、使用流程、API、考慮過的選項；新增「第二版修訂」一節。`CONTEXT.md` 新增「網站專案」「問題」詞條。

### 後端
- `SiteProject`（user、name、origin、start_url、**default_scope、default_categories**、archived_at；`UniqueConstraint(user, origin)`）與 `ScanJob.project`；migration `0019_site_projects` 依 (使用者, origin) 回填既有掃描。
- `ScanJob.save()` 新建時未指定專案就依 origin 歸入，已封存的自動恢復（MCP、後台重排不用改）。
- 建立掃描可帶 `project`（須本人、同網站）；`/api/scans/?project=<id>` 回該專案全部掃描。
- `/api/projects/`：清單（**`?archived=true` 列已封存**）、新增（同網站 409、封存的自動恢復）、PATCH（名稱、起始網址、**預設掃描設定**）、封存、`restore`、`overview`、`issues`。
- `apps/scans/projects.py`：總覽、跨掃描問題比較、清單摘要；**`issue_streaks`（連續 N 次、自哪天起）**；**問題與總覽優先建議只收本次有勾的維度**。
- 測試 `tests_site_projects.py`（18 項）。

### 前端
- 頂部切換器 `ProjectSwitcher.jsx`：切換時停留同分頁、**每列顯示最新分數與設定齒輪、專案多時可搜尋、↑／↓ 選擇**、所有專案、新增專案。
- 工作區 `features/projects/`：側邊欄（**圖示、目前分數、「＋新掃描」**）＋總覽（**進行中掃描的階段與進度條**）、掃描、問題分析（**連續 N 次、受影響頁面**）、歷史報告、專案設定（**預設掃描設定**）；所有專案（**跨網站總覽、已封存專案可恢復**）、新增專案。
- `ScanJobForm`：專案內以專案預設起始，**草稿按專案分開**；`scanProgress()` 抽出供總覽與掃描詳情共用同一進度公式。
- `/dashboard`、`/scans`、`/history` 轉到目前專案的對應分頁；Dashboard／History 頁移除（分數環與公告 toast 移到 `components/projects/OverviewWidgets.jsx`）。
- 樣式：`legacy-member/93-projects.css`、`styles/64-project-switcher.css`。
- 測試：`ProjectSwitcher.test.tsx`（7 項）、`ScanJobForm.test.tsx`（2 項）。

### 沿用第一版實測修正
- `/projects` 被 `startsWith("/project")` 當成公開頁 → 路徑段比對。
- 網域驗證頁呼叫 `/api/scans/domains/`（被解析成掃描 id）→ 改為實際端點 `/api/domains/`（網域驗證頁先前無法運作）。
- 工作區側邊欄 sticky 避開導覽列、表格不撐出水平捲動、歷史表格操作欄底線對齊。

### 文件
- `frontend/CLAUDE.md`、`backend/CLAUDE.md`、`backend/apps/scans/CLAUDE.md`、`.claude/skills/argus-ui-design/SKILL.md`、`專題文件/本機資料/歷史需求書/需求書_複賽版完整內容.md`（ARGUS-F-022）。

## 原因
使用者要求參考 Sitechecker 把會員區改為以網站專案為核心；第一版回退後，要求以回退版本為基礎、以第一版經驗做出更好的版本。

## 影響範圍
- **部署需要跑 migration 0019**（Argo PreSync migrate Job 自動執行）。
- 舊連結 `/dashboard`、`/scans`、`/history` 轉址；`/scans/:id` 不變；`/api/dashboard/`、`/api/history/` 保留相容。
- 已知既有行為（未在本次修改）：沒勾「資安」時，掃描流程的深度資安階段仍會寫入 DNS 郵件紀錄等 finding、`top_actions` 也可能含未勾維度；分數不受影響，問題分析與總覽已在彙整層過濾。

## 驗證方式
- `manage.py test apps` 全數通過；`ruff check backend` 通過；`makemigrations --check` 無遺漏。
- 前端 lint、typecheck、vitest、vite build 通過。
- 本機 eager 端對端（Playwright）：所有專案總覽列；專案設定存預設（單頁＋SEO／AEO／GEO）→ 掃描分頁表單套用 → 建立掃描 → 總覽顯示進行中橫幅、完成後自動更新；問題分析顯示「連續 4 次」與提醒、已排除未勾維度；封存 → 已封存區 → 恢復；切換器分數與方向鍵；日／夜主題截圖；390px 寬五個頁面無水平捲動。
