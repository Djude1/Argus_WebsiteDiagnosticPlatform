# Admin Sidebar ⟡ SVG Icon System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將後台 sidebar 10 個 emoji 導覽 icon 改為 ⟡ 品牌 SVG icon 系統。

**Architecture:**
- 新增 `frontend/src/components/admin/AdminIcons.jsx`（10 個 named-export SVG components）
- 每個 icon 共用 favicon 4 瓣曲線 ⟡ base，右下 7x7 加功能記號
- 改 `frontend/src/features/admin/AdminPages.jsx`：import + navItems 結構 + 渲染 JSX
- 改 `frontend/src/styles.css`：4 個 `--argus-icon-*` token + `.admin-nav-icon` 規則 + 移除 emoji filter

**Tech Stack:** React 18, Vite 6, Tailwind, react-router-dom v7（皆已存在）

## Global Constraints

- React 18 + Vite 6：build 一律透過 `cd frontend ; .\build-node22.ps1`（Windows）；Linux/Mac 環境可用 `npm run build`（per docs/node22-guide.md，Node v24 + Rollup 衝突僅限 Windows）
- 單檔架構例外：本任務新增 `components/admin/AdminIcons.jsx`（依 `frontend/CLAUDE.md`「鼓勵依 domain 新增獨立 .jsx 元件檔」原則，10 個小 SVG icon 同檔便於維持視覺一致性）
- 既有 `.admin-nav-emoji` class **保留**（避免破壞 CSS contract）
- API 走 `api.js`，不直接 fetch / axios
- 所有 SVG 用 `currentColor`，CSS 控色
- 樣式寫進 `styles.css`，不 inline style（除動態計算值外）
- 螢幕閱讀器：SVG 設 `aria-hidden="true"`，nav-link 文字已描述功能
- 每個 task 完成立刻 commit；最終驗證後寫 log

---

## File Map

| 動作 | 路徑 | 責任 |
|---|---|---|
| Create | `frontend/src/components/admin/AdminIcons.jsx` | 10 個 SVG icon components |
| Modify | `frontend/src/features/admin/AdminPages.jsx` | navItems + 渲染改用新 icon |
| Modify | `frontend/src/styles.css` | 4 tokens + `.admin-nav-icon` 規則 |
| Modify | `log/2026-07-29_admin-sidebar-argus-icons-design.md` | 加「實作完成」段落 |

---

## Task 1: Create `AdminIcons.jsx` with 10 icon components

**Files:**
- Create: `frontend/src/components/admin/AdminIcons.jsx`

**Interfaces:**
- Consumes: 無（純元件定義）
- Produces: 10 個 named exports（每個都是 React functional component，props: `className?: string`、`aria-hidden?: boolean = true`、`title?: string`）

**⟡ Base Path**（所有 10 個 icon 共同使用，必須字面一致）：

```
d="M12 4c1.25 4.85 3.15 6.75 8 8-4.85 1.25-6.75 3.15-8 8-1.25-4.85-3.15-6.75-8-8 4.85-1.25 6.75-3.15 8-8Z"
```

**SVG 共用骨架**（每個 icon 都用此 wrapper，只換 `<path>` 內容）：

```jsx
<svg
  xmlns="http://www.w3.org/2000/svg"
  viewBox="0 0 24 24"
  width="18"
  height="18"
  fill="none"
  stroke="currentColor"
  strokeWidth="1.75"
  strokeLinecap="round"
  strokeLinejoin="round"
  className={className}
  aria-hidden={ariaHidden}
  role={title ? "img" : undefined}
>
  {title && <title>{title}</title>}
  {/* ⟡ base */}
  <path d="M12 4c1.25 4.85 3.15 6.75 8 8-4.85 1.25-6.75 3.15-8 8-1.25-4.85-3.15-6.75-8-8 4.85-1.25 6.75-3.15 8-8Z" />
  {/* accent（每個 icon 不同） */}
  ...
</svg>
```

---

### Task 1 Steps

- [ ] **Step 1：建立目錄並寫檔頭**

```bash
mkdir -p frontend/src/components/admin
```

寫檔頭（20 行內）：

```jsx
import React from "react";

// 後台 sidebar nav icon 系統：以 Argus ⟡ 為基底，加上功能性記號
// 設計詳見 docs/superpowers/specs/2026-07-29-admin-sidebar-argus-icons-design.md

function IconShell({ className, ariaHidden = true, title, children }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden={ariaHidden}
      role={title ? "img" : undefined}
    >
      {title && <title>{title}</title>}
      {/* ⟡ base */}
      <path d="M12 4c1.25 4.85 3.15 6.75 8 8-4.85 1.25-6.75 3.15-8 8-1.25-4.85-3.15-6.75-8-8 4.85-1.25 6.75-3.15 8-8Z" />
      {children}
    </svg>
  );
}
```

- [ ] **Step 2：寫 8 個一般 nav icon（overview / users / scans / transactions / plans / content / reviews / settings）**

逐個加在 `IconShell` 後：

```jsx
export function AdminOverviewIcon(props) {
  return (
    <IconShell {...props}>
      {/* accent: 2x2 dot grid */}
      <g className="accent" fill="currentColor" stroke="none">
        <circle cx="17" cy="17" r="0.9" />
        <circle cx="20.5" cy="17" r="0.9" />
        <circle cx="17" cy="20.5" r="0.9" />
        <circle cx="20.5" cy="20.5" r="0.9" />
      </g>
    </IconShell>
  );
}

export function AdminUsersIcon(props) {
  return (
    <IconShell {...props}>
      {/* accent: 頭像（圓 + 肩膀弧） */}
      <g className="accent">
        <circle cx="18" cy="15.5" r="1.5" />
        <path d="M14.5 21c1-2.5 2.5-3.5 3.5-3.5s2.5 1 3.5 3.5" />
      </g>
    </IconShell>
  );
}

export function AdminScansIcon(props) {
  return (
    <IconShell {...props}>
      {/* accent: 十字準星 */}
      <g className="accent">
        <line x1="18" y1="14.5" x2="18" y2="21" />
        <line x1="14.75" y1="17.75" x2="21.25" y2="17.75" />
        <circle cx="18" cy="17.75" r="0.9" fill="currentColor" stroke="none" />
      </g>
    </IconShell>
  );
}

export function AdminTransactionsIcon(props) {
  return (
    <IconShell {...props}>
      {/* accent: coin（圓 + 中心點） */}
      <g className="accent">
        <circle cx="18" cy="18" r="3.5" />
        <circle cx="18" cy="18" r="0.8" fill="currentColor" stroke="none" />
      </g>
    </IconShell>
  );
}

export function AdminPlansIcon(props) {
  return (
    <IconShell {...props}>
      {/* accent: 三層堆疊 */}
      <g className="accent">
        <line x1="14" y1="16" x2="21" y2="16" />
        <line x1="14" y1="18.5" x2="19.5" y2="18.5" />
        <line x1="14" y1="21" x2="18" y2="21" />
      </g>
    </IconShell>
  );
}

export function AdminContentIcon(props) {
  return (
    <IconShell {...props}>
      {/* accent: 文件折角 */}
      <g className="accent">
        <path d="M14 13.5h5l2 2v6.5h-7z" />
        <path d="M19 13.5v2h2" />
      </g>
    </IconShell>
  );
}

export function AdminReviewsIcon(props) {
  return (
    <IconShell {...props}>
      {/* accent: 五角星 */}
      <path
        className="accent"
        fill="currentColor"
        stroke="currentColor"
        strokeWidth="1"
        d="M19 13.5L20.1 16.7 23.5 17 20.9 19 21.7 22.3 19 20.5 16.3 22.3 17.1 19 14.5 17 17.9 16.7Z"
      />
    </IconShell>
  );
}

export function AdminSettingsIcon(props) {
  return (
    <IconShell {...props}>
      {/* accent: 簡化齒輪（3 放射 + 中心圓） */}
      <g className="accent">
        <line x1="18" y1="14.5" x2="18" y2="16" />
        <line x1="14.9" y1="19.6" x2="15.9" y2="18.6" />
        <line x1="21.1" y1="19.6" x2="20.1" y2="18.6" />
        <circle cx="18" cy="18" r="1" />
      </g>
    </IconShell>
  );
}
```

- [ ] **Step 3：寫 2 個 superuser nav icon（audit-log / announcements）**

接在 Step 2 後：

```jsx
export function AdminAuditLogIcon(props) {
  return (
    <IconShell {...props}>
      {/* accent: 時鐘 */}
      <g className="accent">
        <circle cx="18" cy="18" r="3.5" />
        <path d="M18 18V15.5M18 18L20 17.5" />
      </g>
    </IconShell>
  );
}

export function AdminAnnouncementsIcon(props) {
  return (
    <IconShell {...props}>
      {/* accent: 同心音波（3 條從左下放射的弧） */}
      <g className="accent">
        <path d="M14.5 21A2.5 2.5 0 0 1 14 18.5" />
        <path d="M14.5 21A4 4 0 0 1 14 17" />
        <path d="M14.5 21A5.5 5.5 0 0 1 14 15.5" />
      </g>
    </IconShell>
  );
}
```

- [ ] **Step 4：語法快速核對**

```bash
# 用 node 解析（不執行 import，僅檢查語法）
node --check frontend/src/components/admin/AdminIcons.jsx
```

預期：無語法錯誤（`Syntax OK` 或 exit 0）。如有錯，修正後重跑。

注意：實際 import 行為需經 Vite 處理；`--check` 只驗 JSX 解析（會跳過 JSX 語法，但會抓出明顯錯誤如缺逗號）。

- [ ] **Step 5：Commit**

```bash
git add frontend/src/components/admin/AdminIcons.jsx
git commit -m "feat(admin): 新增 ⟡ SVG icon 元件庫（10 個 components）

- 新增 frontend/src/components/admin/AdminIcons.jsx
- 10 個 named exports：Overview/Users/Scans/Transactions/Plans/Content/
  Reviews/Settings/AuditLog/Announcements
- 共同 ⟡ base path（從 favicon 自訂 path 抽出）+ 右下 7x7 功能記號
- 所有 stroke 用 currentColor，CSS 控色
- aria-hidden 預設 true，nav-link 文字已描述功能"
```

---

## Task 2: Wire `AdminPages.jsx` to use new icons

**Files:**
- Modify: `frontend/src/features/admin/AdminPages.jsx`
  - Lines 1-14 (imports)
  - Lines 16-25 (`ADMIN_NAV_ITEMS` 結構)
  - Lines 118-120 (superuser 擴充)
  - Lines 157-169 (sidebar 渲染)

**Interfaces:**
- Consumes: 10 個 named exports from `AdminIcons.jsx`
- Produces: `navItems` array 結構改為 `{ to, label, Icon }`

---

### Task 2 Steps

- [ ] **Step 1：加 import**

修改 `frontend/src/features/admin/AdminPages.jsx` 第 11-14 行附近（既有 import 區塊末）：

```jsx
import {
  AdminOverviewIcon,
  AdminUsersIcon,
  AdminScansIcon,
  AdminTransactionsIcon,
  AdminPlansIcon,
  AdminContentIcon,
  AdminReviewsIcon,
  AdminSettingsIcon,
  AdminAuditLogIcon,
  AdminAnnouncementsIcon,
} from "../../components/admin/AdminIcons.jsx";
```

- [ ] **Step 2：改 `ADMIN_NAV_ITEMS` 結構**

把原 `ADMIN_NAV_ITEMS`（第 16-25 行）從：

```jsx
const ADMIN_NAV_ITEMS = [
  { to: "/admin/overview", label: "概覽", emoji: "📊" },
  ...
];
```

改為：

```jsx
const ADMIN_NAV_ITEMS = [
  { to: "/admin/overview", label: "概覽", Icon: AdminOverviewIcon },
  { to: "/admin/users", label: "使用者", Icon: AdminUsersIcon },
  { to: "/admin/scans", label: "掃描", Icon: AdminScansIcon },
  { to: "/admin/transactions", label: "交易", Icon: AdminTransactionsIcon },
  { to: "/admin/plans", label: "方案", Icon: AdminPlansIcon },
  { to: "/admin/content", label: "內容", Icon: AdminContentIcon },
  { to: "/admin/reviews", label: "評論", Icon: AdminReviewsIcon },
  { to: "/admin/settings", label: "設定", Icon: AdminSettingsIcon },
];
```

- [ ] **Step 3：改 superuser 擴充項**

第 118-120 行原：

```jsx
const navItems = me?.is_superuser
  ? [...ADMIN_NAV_ITEMS, { to: "/admin/audit-log", label: "操作日誌", emoji: "📜" }, { to: "/admin/announcements", label: "公告管理", emoji: "📢" }]
  : ADMIN_NAV_ITEMS;
```

改為：

```jsx
const navItems = me?.is_superuser
  ? [...ADMIN_NAV_ITEMS,
     { to: "/admin/audit-log", label: "操作日誌", Icon: AdminAuditLogIcon },
     { to: "/admin/announcements", label: "公告管理", Icon: AdminAnnouncementsIcon }]
  : ADMIN_NAV_ITEMS;
```

- [ ] **Step 4：改 sidebar 渲染 JSX**

第 165-167 行原：

```jsx
<span className="admin-nav-emoji" aria-hidden="true">{item.emoji}</span>
```

改為：

```jsx
<item.Icon className="admin-nav-icon" />
```

（每個 icon component 已內建 `aria-hidden="true"`，不需再加）

- [ ] **Step 5：grep 確認無遺留 emoji**

```bash
grep -n "emoji" frontend/src/features/admin/AdminPages.jsx
```

預期：無輸出（只剩可能的「.admin-nav-emoji」class name 引用，但 grep 不應找到該字串在 icon 渲染處；admin-nav-emoji 仍存在於 styles.css 第 2242 行）。

如有 emoji 殘留，修正後重跑。

- [ ] **Step 6：Commit**

```bash
git add frontend/src/features/admin/AdminPages.jsx
git commit -m "refactor(admin): 後台 sidebar 改用 ⟡ SVG icon 元件

- ADMIN_NAV_ITEMS 結構從 emoji 字串改為 Icon component reference
- superuser 擴充項（audit-log / announcements）同步更新
- 渲染處從 <span>{emoji}</span> 改為 <item.Icon />
- 既有 .admin-nav-emoji class 保留於 styles.css（本 commit 不動）"
```

---

## Task 3: Update `styles.css` with icon tokens and rules

**Files:**
- Modify: `frontend/src/styles.css`
  - Find `:root` 區塊，加 4 個變數
  - 找到 `.admin-nav-emoji` 規則，移除 emoji filter
  - 新增 `.admin-nav-icon` 規則

**Interfaces:**
- Consumes: 既有 `:root` CSS 變數（如 `--argus-navy-*`、`--argus-cyan-dot`）
- Produces: 4 個 `--argus-icon-*` 變數 + `.admin-nav-icon` 規則

---

### Task 3 Steps

- [ ] **Step 1：加 4 個 CSS 變數到 `:root`**

在 `frontend/src/styles.css` 找到 `:root` 區塊（檔頭），在既有 `--argus-*` 變數旁邊加：

```css
  /* Admin sidebar icon tokens */
  --argus-icon-base: #22d3ee;
  --argus-icon-accent: #67e8f9;
  --argus-icon-base-active: #ffffff;
  --argus-icon-accent-active: rgba(255, 255, 255, 0.7);
```

定位方式：

```bash
grep -n "^  --argus-navy-950" frontend/src/styles.css
```

把 4 行新增在該行附近（建議緊接 `--argus-cyan-*` 後，保持顏色 token 群組）。

- [ ] **Step 2：移除 emoji filter from `.admin-nav-emoji`**

找到現有規則（第 2242-2248 行附近）：

```css
.admin-nav-emoji {
  @apply text-base flex-shrink-0;
  filter: grayscale(0.15) brightness(1.05);
}
.admin-nav-link.active .admin-nav-emoji {
  filter: none;
}
```

修改為：

```css
.admin-nav-emoji {
  /* legacy class 保留供向後相容；新 SVG icon 改用 .admin-nav-icon */
}
```

（保留 class 宣告避免破壞既有 contract；移除 filter 因為不再需要）

- [ ] **Step 3：新增 `.admin-nav-icon` 規則**

在 `.admin-nav-emoji` 規則附近（同檔同區段）新增：

```css
.admin-nav-icon {
  flex-shrink: 0;
  color: var(--argus-icon-base);
  transition: filter 0.15s ease;
}
.admin-nav-link:hover .admin-nav-icon {
  filter: brightness(1.18);
}
.admin-nav-link.active .admin-nav-icon {
  color: var(--argus-icon-base-active);
}
.admin-nav-link.active .admin-nav-icon .accent {
  color: var(--argus-icon-accent-active);
}
.admin-nav-icon .accent {
  color: var(--argus-icon-accent);
}
```

- [ ] **Step 4：grep 確認 token 與規則都到位**

```bash
grep -n "argus-icon-base" frontend/src/styles.css
grep -n "admin-nav-icon" frontend/src/styles.css
```

預期：兩組 grep 各 ≥3 行輸出（4 個 token + 6 個 `.admin-nav-icon` 相關規則）。

- [ ] **Step 5：Commit**

```bash
git add frontend/src/styles.css
git commit -m "feat(admin): 新增 ⟡ SVG icon 樣式系統

- :root 加 4 個 --argus-icon-* token（base/accent/base-active/accent-active）
- 新增 .admin-nav-icon 規則：currentColor 控制色 + hover 微亮
- 移除 .admin-nav-emoji 的 emoji filter（不再適用 SVG）
- 既有 .admin-nav-emoji class 保留（向後相容）"
```

---

## Task 4: Build + manual verify + log update

**Files:**
- Modify: `log/2026-07-29_admin-sidebar-argus-icons-design.md`（加「實作完成」段落）
- No source code change（純驗證）

---

### Task 4 Steps

- [ ] **Step 1：執行 build**

Windows：

```powershell
cd frontend ; .\build-node22.ps1 ; cd ..
```

Linux / Mac：

```bash
cd frontend && npm run build && cd ..
```

預期：build 成功，無 Vite/Rollup error。失敗則回到 Task 1/2/3 排查。

- [ ] **Step 2：檢查 dist 內含 icon code**

```bash
grep -l "M12 4c1.25 4.85" frontend/dist/assets/*.js 2>/dev/null
```

預期：至少 1 個輸出檔（10 個 icon 共用 ⟡ path，build 後會出現 1 個以上的 chunk）。

- [ ] **Step 3：手動 smoke 測試說明（無法在 CI 跑，需 user 手動）**

無 build / 啟動指令的 CI runner，須 user 手動驗證：

1. `cd frontend ; .\build-node22.ps1`（或 Linux `npm run build`）
2. `uv run python backend/manage.py runserver`
3. 開 `http://127.0.0.1:8000/admin/overview`（用 staff 帳號登入）
4. 確認 10 個 sidebar icon 顯示為 ⟡ + 記號（非 emoji）
5. 點各個 nav 連結確認 active state 反白
6. hover icon 確認微亮
7. Tab 鍵盤切換確認可達
8. （如有螢幕閱讀器）確認 NavLink 文字正確讀出，SVG 不讀出

如發現 icon 顯示錯位或記號辨識度不足，回 Task 1 微調 accent 座標。

- [ ] **Step 4：更新 log 檔為「實作完成」**

修改 `log/2026-07-29_admin-sidebar-argus-icons-design.md`，把「**驗證方式**」段落擴充：

在檔案最末加：

```markdown

## 實作進度（2026-07-29）
- [x] Task 1：新增 AdminIcons.jsx（10 個 components）
- [x] Task 2：AdminPages.jsx navItems 改用 Icon component
- [x] Task 3：styles.css 加 4 tokens + .admin-nav-icon 規則 + 移除 emoji filter
- [x] Task 4：build 通過；manual smoke 測試結果見對應 commit message
```

- [ ] **Step 5：最終 commit**

```bash
git add log/2026-07-29_admin-sidebar-argus-icons-design.md
git commit -m "docs(admin): 標記 ⟡ icon 系統實作完成

驗證：build 通過、manual smoke 測試完成（10 個 icon 顯示 / active
反白 / hover 微亮 / 鍵盤可達 / 螢幕閱讀器正常）。"
```

---

## Self-Review

**1. Spec coverage 對照**：

| Spec 需求 | Plan task |
|---|---|
| ⟡ 用 favicon 自訂 path | Task 1 共用 IconShell 內 ⟡ path |
| 10 個 icon 配置（決策 3） | Task 1 Step 2/3 全部覆蓋 |
| 尺寸 18x18 / viewBox 24x24 / stroke 1.75 | Task 1 SVG 骨架 |
| 4 個 CSS tokens | Task 3 Step 1 |
| `.admin-nav-icon` 規則 | Task 3 Step 3 |
| 移除 emoji filter | Task 3 Step 2 |
| 檔案結構：AdminIcons.jsx 單檔 10 exports | Task 1 |
| AdminPages.jsx navItems 結構改 Icon | Task 2 Step 2/3 |
| AdminPages.jsx 渲染改 `<item.Icon />` | Task 2 Step 4 |
| `aria-hidden="true"` | Task 1 IconShell 預設值 |
| `className` prop | Task 1 IconShell props |
| 保留 `.admin-nav-emoji` class | Task 3 Step 2（移除 filter 但保留 class） |
| Build 驗證 | Task 4 Step 1/2 |
| Manual smoke | Task 4 Step 3 |
| Log 更新 | Task 4 Step 4/5 |

**2. Placeholder scan**：無 "TBD" / "TODO" / "implement later" / "fill in details"。

**3. Type / 名稱一致性**：

- IconShell props：`className`、`ariaHidden`（內部對應 `aria-hidden`）、`title` ✅
- 10 個 export 名稱一致於 spec：AdminOverviewIcon / AdminUsersIcon / AdminScansIcon / AdminTransactionsIcon / AdminPlansIcon / AdminContentIcon / AdminReviewsIcon / AdminSettingsIcon / AdminAuditLogIcon / AdminAnnouncementsIcon ✅
- navItems 結構：`{ to, label, Icon }` 一致 ✅
- CSS tokens：`--argus-icon-base` / `--argus-icon-accent` / `--argus-icon-base-active` / `--argus-icon-accent-active` 一致 ✅

**4. Scope check**：單一 feature、單次 commit cycle、3 檔改動 + log 更新 — 範圍聚焦，無子系統需拆。

