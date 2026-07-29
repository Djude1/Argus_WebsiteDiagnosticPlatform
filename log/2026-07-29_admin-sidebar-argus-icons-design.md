# 後台 Sidebar ⟡ SVG Icon 系統設計文件

**日期**：2026-07-29
**操作者**：Claude (Sisyphus)

## 變更內容
- 新增 `docs/superpowers/specs/2026-07-29-admin-sidebar-argus-icons-design.md`：後台 sidebar nav 改用 ⟡ 自訂 SVG icon 系統（10 個 icon）取代 emoji 的設計文件
- 新增本 log 記錄

## 原因
- 使用者回饋：後台 sidebar 大量 emoji（📊 👥 🔍 💳 💼 📝 ⭐ ⚙️ 📜 📢）是典型 AI 生成範本，缺乏品牌辨識度與後台專業感
- Argus 品牌素材已存在（brand-logo.webp 眼睛、favicon 自訂 ⟡ path、PWA `⟡` glyph），但未進入後台
- 透過 brainstorm 決定用 ⟡ 為基底的 SVG icon 系列，保留品牌識別、跨平台一致、視覺系列感強

## 影響範圍
- **本次 commit 僅含設計文件，無程式碼變動**
- 程式碼改動計畫在 writing-plans 後實作：
  - 新增 `frontend/src/components/admin/AdminIcons.jsx`（10 個 named exports）
  - 改 `frontend/src/features/admin/AdminPages.jsx`：import + navItems 結構 + 渲染
  - 改 `frontend/src/styles.css`：4 個 CSS 變數 + `.admin-nav-icon` 規則 + 移除 emoji filter
- 既有 `.admin-nav-emoji` class 保留，避免破壞 CSS contract
- 其他後台頁面、其他 feature 皆不受影響

## 驗證方式
- 本次為設計階段，無程式碼可驗證
- 程式碼實作後驗證：
  - `cd frontend ; .\build-node22.ps1` 通過
  - 手動到 `/admin/overview` 確認 10 個 icon 顯示、active 反白、hover 微亮
  - 螢幕閱讀器測試 NavLink 文字正確讀出
  - Tab 鍵盤可達
  - Chrome / Safari / Firefox 視覺一致

## 實作進度（2026-07-29）

- [x] Task 1：新增 AdminIcons.jsx（10 個 components + IconShell helper）
- [x] Task 2：AdminPages.jsx navItems 改用 Icon component（4 個區域 + 修 useEffect 缺 `}` bug）
- [x] Task 3：styles.css 加 4 tokens + `.admin-nav-icon` 規則 + 移除 emoji filter
- [x] Task 4：build 通過 + dist 內含 ⟡ icon code + CSS class

## 驗證結果

- `npm run build` 成功（2039 modules, 5.15s）
- dist 內含 ⟡ base path（grep `M12 4c1.25 4.85` 命中 AdminPages chunk）
- dist 內含 `.admin-nav-icon` CSS class

## 修正過程備註

Task 2 實作中 subagent 誤刪 `useEffect` 中 `handleKeyDown` 函數的 closing `}`，
經 build 發現後由 controller 修復（原 subagent 自審與 review 都沒抓到
此語法錯誤，因 JS 缺少 `}` 會自動往後尋找匹配，導致靜默解析為不同結構）。
