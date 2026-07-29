# 後台 Sidebar ⟡ SVG Icon 系統設計

**日期**：2026-07-29
**狀態**：待 user review
**範疇**：純設計文件，無程式碼變更

---

## 背景與目標

使用者回饋：後台 sidebar 導覽目前使用 emoji（📊 👥 🔍 💳 💼 📝 ⭐ ⚙️ 📜 📢），
屬於典型 AI 生成範本，缺乏品牌辨識度與後台專業感。

Argus 既有品牌素材完整但未進入後台：

| 素材 | 內容 | 現況 |
|---|---|---|
| `frontend/src/assets/brand-logo.webp` | 單顆眼睛（藍虹膜 + 黑瞳孔 + 銀白輪廓 + 放射電路線） | 僅在 sidebar 當 logo 圖用 |
| `frontend/public/favicon.svg` | cyan→indigo 漸層 + 自訂 ⟡ path（4 瓣曲線眼睛） | production 上線 |
| `frontend/public/pwa-icon.svg` | 同上 + 中央 `⟡` glyph + "ARGUS" 字 | production 上線 |
| `frontend/src/App.jsx:64` | 註解「品牌 ⟡ icon 可呼叫 replayIntro 重播」 | 未實作 |

本設計目標：

- 10 個 sidebar nav icon 全部以 ⟡ 為基底，建立視覺系列感
- 跨平台一致（純 SVG path，不用 Unicode 字型）
- 沿用既有 cyan/indigo token，不發明新色
- 維持後台「冷靜高效」原則（無炫技 layout 動畫）
- 鍵盤 / 螢幕閱讀器可達性不退步

## 非目標

- 不重設計 sidebar layout、間距、字級
- 不為後台加品牌 hero / banner / 滿版 watermark
- 不改 AdminAuditLogPage 等子頁面內部 layout
- 不動 CMS schema emoji 欄位 hint（屬另一個改進範圍，本次不處理）
- 不改 brand-logo.webp / favicon.svg / pwa-icon.svg 本體

---

## 設計決策

### 決策 1：⟡ 基底形式

**選項 B：favicon 自訂 path**

```svg
<path d="M12 4 c1.25 4.85 3.15 6.75 8 8
         -4.85 1.25 -6.75 3.15 -8 8
         -1.25 -4.85 -3.15 -6.75 -8 -8
         4.85 -1.25 6.75 -3.15 8 -8 Z" />
```

（從 `frontend/public/favicon.svg` 抽出，重新縮放至 24x24 viewBox；4 瓣曲線眼睛形）

**理由**：

- 已是 production 上線設計，不另起爐灶
- 純 SVG path 跨平台一致（Unicode `⟡` 字型會跨 OS 變形）
- 改用 stroke 而非 fill 後，18px sidebar 尺寸仍可辨識
- 與 PWA icon 形式統一

**淘汰方案**：

- A. Unicode `⟡`：跨平台不一致、18px 辨識度差
- C. brand-logo 簡化眼睛：細節太多，小尺寸會糊
- D. 完全新設計：與既有品牌分裂，等於再發明一次品牌

### 決策 2：差異化策略

**選項 B：外部眼神記號**

⟡ 原形不動，在右下角 7x7 區域加小記號（線稿或填色）。

**理由**：

- 系列感最強：所有 icon 共用 ⟡ 主體，一看就是同一家族
- 設計風險最低：⟡ 已固定，變數只有記號
- 維持品牌識別：⟡ 永遠是主視覺，記號只表達功能

**淘汰方案**：

- A. 變形：8 個 icon 重設計 8 個 path，工程量與測試成本最高
- C. 內部嵌入：18px 內塞嵌入符號，視覺過度擁擠
- D. 混搭：系列感不一致

### 決策 3：10 個 icon 配置

| # | 路由 | 標籤 | 右下記號 | 識別原理 |
|---|---|---|---|---|
| 1 | `/admin/overview` | 概覽 | 2x2 dot grid | 儀表板 tile 暗示 |
| 2 | `/admin/users` | 使用者 | 頭像（圓 + 肩膀弧） | avatar 標準 |
| 3 | `/admin/scans` | 掃描 | 十字準星 | 對焦 / 掃描 |
| 4 | `/admin/transactions` | 交易 | coin（圓 + 點） | 金流 |
| 5 | `/admin/plans` | 方案 | 三層堆疊 | 套餐層次 |
| 6 | `/admin/content` | 內容 | 文件折角 | CMS |
| 7 | `/admin/reviews` | 評論 | 五角星 | 評分 |
| 8 | `/admin/settings` | 設定 | 簡化齒輪 | 設定 |
| 9 | `/admin/audit-log` | 操作日誌 | 時鐘 | 時間軸 / 紀錄 |
| 10 | `/admin/announcements` | 公告管理 | 同心音波 | 廣播 |

### 決策 4：尺寸 / stroke / 配色

**尺寸**

- 容器：`width: 18px; height: 18px;`
- viewBox：`0 0 24 24`（標準 SVG 規格；實際渲染時縮至 18px）
- ⟡ 主體：14x14 居中
- 右下記號：7x7 落在右下角 `(15,15)` 至 `(22,22)`

**stroke / fill 規則**

| 元素 | stroke | fill | stroke-width |
|---|---|---|---|
| ⟡ 4 瓣曲線 | `currentColor` | `none`（透明） | `1.75` |
| 右下記號（線性：十字、弧線、堆疊線） | `currentColor` | `none` | `1.5` |
| 右下記號（點狀：圓點、星角、coin） | `none` | `currentColor` | — |

⟡ 用 stroke 而非 fill 的理由：favicon 在 64px 是實心，縮至 18px 會糊；改 stroke 1.75px 反而更像「科技線稿」，呼應 brand-logo.webp 的電路 motif。

**新增 CSS 變數**（加到 `frontend/src/styles.css :root`）

```css
:root {
  /* existing tokens 保留 */
  --argus-icon-base: #22d3ee;             /* ⟡ cyan */
  --argus-icon-accent: #67e8f9;           /* 記號 cyan-light */
  --argus-icon-base-active: #ffffff;      /* active 反白 */
  --argus-icon-accent-active: rgba(255, 255, 255, 0.7);
}
```

### 決策 5：狀態對應

| 狀態 | ⟡ color | 記號 color | filter |
|---|---|---|---|
| 預設（inactive） | `--argus-icon-base` | `--argus-icon-accent` | `none` |
| Hover | `--argus-icon-base` | `--argus-icon-accent` | `brightness(1.18)` |
| Active | `--argus-icon-base-active` | `--argus-icon-accent-active` | `none` |
| Active + Hover | `--argus-icon-base-active` | `--argus-icon-accent-active` | `none` |

```css
.admin-nav-icon {
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
```

transition 只動 `filter`，不動 `color`（瀏覽器 compositing 最佳化，符合後台冷靜原則）。

### 決策 6：檔案結構

**新增檔案**：`frontend/src/components/admin/AdminIcons.jsx`

10 個 named exports：

```
AdminOverviewIcon
AdminUsersIcon
AdminScansIcon
AdminTransactionsIcon
AdminPlansIcon
AdminContentIcon
AdminReviewsIcon
AdminSettingsIcon
AdminAuditLogIcon
AdminAnnouncementsIcon
```

每個 component 的 props：

| prop | 型別 | 預設 | 說明 |
|---|---|---|---|
| `className` | string | — | 外部 CSS hook |
| `aria-hidden` | boolean | `true` | 螢幕閱讀器跳過 |
| `title` | string | `undefined` | 設定時變 `role="img"` |

**理由**：和現有 `components/scans/ScanBadges.jsx` 等小元件同 pattern；單一檔案 10 個 export 比重複 10 檔更易維持視覺一致性；不需 lazy loading（總量小）。

**修改檔案**：

1. `frontend/src/features/admin/AdminPages.jsx`
   - import 10 個 icon components
   - `ADMIN_NAV_ITEMS` 結構：`emoji` 欄位改為 `Icon`（component reference）
   - superuser 擴充項同樣改 `Icon`
   - 渲染處：
     ```jsx
     // 改前
     <span className="admin-nav-emoji" aria-hidden="true">{item.emoji}</span>
     // 改後
     <item.Icon className="admin-nav-icon" />
     ```
   - **保留** `.admin-nav-emoji` class 名（避免破壞既有 CSS contract；新 class `.admin-nav-icon` 為 SVG 專用）

2. `frontend/src/styles.css`
   - `:root` 新增 4 個 icon 變數
   - 移除 `.admin-nav-emoji { filter: grayscale(0.15) ... }` 與 `.admin-nav-link.active .admin-nav-emoji { filter: none }`（emoji filter 不適用 SVG）
   - 新增 `.admin-nav-icon` 規則（如上）
   - 驗證 NavLink `aria-current="page"` 行為（react-router 預設已加；必要時補 `end` prop）

**不修改**：

- 其他後台頁面
- 其他 feature（auth / scans / account / public / reviews）
- `App.jsx` route 結構
- brand-logo / favicon / pwa-icon 圖檔

---

## Component API 範例

```jsx
// frontend/src/components/admin/AdminIcons.jsx
export function AdminOverviewIcon({ className, "aria-hidden": ariaHidden = true, title }) {
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
      {/* ⟡ base（4 瓣曲線） */}
      <path d="M12 4c1.25 4.85 3.15 6.75 8 8-4.85 1.25-6.75 3.15-8 8-1.25-4.85-3.15-6.75-8-8 4.85-1.25 6.75-3.15 8-8Z" />
      {/* accent: 2x2 dot grid */}
      <g className="accent" fill="currentColor" stroke="none">
        <circle cx="17" cy="17" r="0.9" />
        <circle cx="20.5" cy="17" r="0.9" />
        <circle cx="17" cy="20.5" r="0.9" />
        <circle cx="20.5" cy="20.5" r="0.9" />
      </g>
    </svg>
  );
}
```

（其餘 9 個 icon 採相同 pattern；⟡ path 文字一致，accent 改變）

---

## 實作計畫（單次 commit）

1. 新增 `frontend/src/components/admin/AdminIcons.jsx`（10 個 icon components）
2. 改 `frontend/src/features/admin/AdminPages.jsx`：import + 改 navItems 結構 + 改渲染
3. 改 `frontend/src/styles.css`：新增 :root 變數、新增 .admin-nav-icon 規則、移除 emoji filter
4. 驗證：build 後手動確認 sidebar 顯示、active 切換、hover 微亮、鍵盤 Tab、螢幕閱讀器
5. 同次 commit 附 `log/2026-07-29_admin-sidebar-argus-icons-design.md`

---

## 驗證方式

- **視覺**：到 `/admin/overview` 確認 10 個 icon 顯示、active 切換反白、hover 微亮
- **a11y**：鍵盤 Tab 可達；螢幕閱讀器只讀 nav-link 文字（不讀 SVG）
- **跨瀏覽器**：Chrome / Safari / Firefox 視覺一致（viewBox + stroke-linecap round）
- **自動化**：無新增 unit test（純視覺改變）
- **Regression**：`.admin-nav-emoji` class 保留、其他後台頁面無破壞

---

## 風險

| 風險 | 緩解 |
|---|---|
| 18px 太小 ⟡ 看不清楚 | stroke 1.75px 比 emoji 粗；改 stroke 後實際視覺更明顯 |
| 不同瀏覽器 SVG 渲染差異 | viewBox 標準化、`stroke-linecap="round"`、`stroke-linejoin="round"` |
| 螢幕閱讀器把 SVG 當圖讀出 | `aria-hidden="true"`；nav-link 文字已描述功能 |
| 既有 `.admin-nav-emoji` CSS contract 破壞 | class 保留；新 `.admin-nav-icon` 為 SVG 專用 |
| 建置後 icon 沒出現 | build 採 `build-node22.ps1`；產出後 manual smoke test |

---

## Out of Scope（後續可考慮）

- CMS schema emoji 欄位 hint 改用品牌語彙（⟡ ◈ ◎⋯）
- AdminAnnouncementsPage 標題移除 📢
- Sidebar 加 ⟡ watermark（保留「克制」原則下的小品牌識別）
- Dashboard / Scans 前台頁面 nav 也跟進改 ⟡ 系列
