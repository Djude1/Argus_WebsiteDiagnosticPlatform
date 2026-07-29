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
