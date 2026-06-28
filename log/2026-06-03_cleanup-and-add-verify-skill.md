# 專案清理：刪除多餘檔案與更新使用說明

**日期**：2026-06-03
**操作者**：Claude

## 變更內容

### 1. 移除 `backend/config/settings.py` 的 jazzmin dead code
- 刪除 `_JAZZMIN_SETTINGS_DEPRECATED` 與 `_JAZZMIN_UI_TWEAKS_DEPRECATED` 兩個變數（原 182-271 行，共 93 行）
- 套件 `django-jazzmin` 已於 W4 `uv remove`，這兩個常數已無任何引用
- 保留 3 行說明性註解解釋為何不用 jazzmin
- settings.py 從 272 行縮減為 179 行

### 2. 刪除根目錄殘留檔案（無任何引用）
- `admin-1440.png`（183 KB，與 admin-django-served.png md5 完全相同的副本）
- `admin-django-served.png`（183 KB）
- `admin-overview-after.png`（135 KB）
- `admin-transactions.png`（212 KB）
- `admin-users.png`（206 KB）
- `新網站報告.docx`（41 KB，疑似測試產出殘留）
- `log/.gitkeep`（log/ 已有大量檔案，.gitkeep 失去作用）

合計釋出約 870 KB。

### 3. 刪除過時的 superpowers plan / spec（已落地或孤立）
- `docs/superpowers/plans/2026-05-26-argus-26-fixes.md`（26 項修正計畫，log/ 已有 phase/task 執行紀錄）
- `docs/superpowers/specs/2026-05-26-argus-26-fixes-design.md`（對應上方計畫的 spec）
- `docs/superpowers/plans/2026-05-29-argus-system-manual-v3.md`（針對「專題文件生成」資料夾的計畫，該資料夾已於 commit `f19ad44` 刪除）
- `docs/superpowers/specs/2026-05-29-argus-system-manual-optimization-design.md`（對應上方計畫的 spec）

`docs/superpowers/plans/` 與 `docs/superpowers/specs/` 兩個子目錄已淨空，docs/ 整個目錄樹已隨之消失。

### 4. 更新 `使用說明.md` 到當前事實
- 移除過時敘述：「每月 20 次 UserScanQuota」（已被點數制度取代）、「Django Admin 是主介面」（已被 React `/admin/*` 取代）、`npm run build`（CLAUDE.md 已禁，改 `build-node22.ps1`）
- 重新定位為「中文使用者操作快速指南」，與 README.md（英技術介紹）、ONBOARDING.md（協作上手）三者區隔
- 補上：點數制度、`/free-tools` 公開頁、React `/admin/*` 後台、`rerun_scan` 命令、Docker 細節

## 原因

使用者要求先深入了解專案，列出多餘可刪除檔案；確認 A 級（無引用殘留）與 B 級（過時計畫）後執行清理；使用說明.md 因內容已與當前事實不符（仍寫舊配額制度與舊管理介面），改為更新而非刪除。

## 影響範圍

- 後端：settings.py 僅移除已禁用常數，無功能改動
- 文件：使用說明.md 完全重寫
- 無前端、無 API、無 migration 改動
- 無對外可見行為改變

## 驗證方式

### 靜態檢查（全綠）
- `uv run python backend/manage.py check` → System check identified no issues (0 silenced)
- `uv run python backend/manage.py makemigrations --check --dry-run` → No changes detected
- `uv run ruff check backend` → All checks passed!

### 全測試
- `uv run python backend/manage.py test apps` → **Ran 252 tests in 95.759s, OK**

### 跨檔一致性 grep（無殘留）
- grep `admin-*.png|新網站報告|_JAZZMIN_*_DEPRECATED` → No files found
- grep `UserScanQuota` 於 使用說明.md → No matches found
- grep `jazzmin` 於 backend → 只剩 settings.py + cms_views.py 的說明性註解（非 dead code）
