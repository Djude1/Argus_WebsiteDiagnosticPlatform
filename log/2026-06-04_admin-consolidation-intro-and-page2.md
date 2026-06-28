# 後台整併（只剩 React /admin）＋ 首次進站粒子過場動畫 ＋ page2 風格首頁 ＋ 下載頁/分權/CMS 補強

**日期**：2026-06-04  
**操作者**：Claude

## 變更內容

### 後端
- **新增** `apps/accounts/management/commands/seed_admin.py`：建立/更新「種子管理員」，密碼由 `--password` 或環境變數 `SEED_ADMIN_PASSWORD` 提供（**零硬編碼**、冪等）。已建立 `115401@gmail.com` 為 superuser。
- **完全移除 django-admin**：`config/urls.py` 移除 `admin.site.urls` 路由與 `from django.contrib import admin`、SPA fallback regex 去掉 `django-admin/` 排除、`robots.txt` 去掉該 Disallow；`config/settings.py` 註解更新（`django.contrib.admin` 仍留 INSTALLED_APPS 作為 LogEntry 等基礎設施，但無對外 URL）。
- **移除** `apps/scans/tests.py` 的 `ScanAdminTests`（測 `/django-admin/` 行為，已隨後台移除而失效）。
- **分權收緊**：`apps/admin_api/views.py` 的 `announcements_admin`、`announcement_detail` 由 `IsAdminUser` 改為 `IsSuperuser`（對齊前端 nav 只給 superuser 顯示「公告管理」）。
- **milestone CMS parity**：`apps/admin_api/cms_views.py` 新增 `ProjectMilestoneWriteSerializer` + `ProjectMilestoneViewSet`；`urls.py` 註冊 `cms/milestones/`。讓 ProjectMilestone 可在 React `/admin` 編輯（先前僅 django-admin 可改）。

### 前端（`frontend/src/App.jsx` + `styles.css`，維持單檔架構、樣式只進 styles.css）
- **首次進站粒子過場動畫**：新增 `IntroSequence` 元件（移植自 `過場動畫和網站設計範本/index.html`：STORM→ASSEMBLE→DISPLAY→EXPLODE→WARP），`AppShell` 加 `introSeen` gate（localStorage `argus_intro_seen`），播完導向首頁（`/login` 不覆寫）。尊重 `prefers-reduced-motion`、有「略過」鈕、`finish` setTimeout 在 unmount 清除。資產 `frontend/src/assets/intro-logo.png`（= 範本的「請使用該照片做.png」），以 import 方式進 `/assets`。
- **首頁 page2 化**：`ProjectPage` hero 加 `public-hero--console` + 裝飾元素（`hero-grid`/`hero-scan`/`hero-corner`），`styles.css` 新增對應 console CSS（網格漂移/掃描線/HUD 邊角/發光標題；reduced-motion 關動畫）。
- **下載頁修正**：`DownloadPage` 主 CTA 改為永遠可見可動作（可安裝→原生安裝；否則→捲到 `#install-guide` 安裝教學；另在有 AppRelease 下載連結時顯示下載鈕）。
- **milestone CMS tab**：`CONTENT_TABS` 新增 `MILESTONE_SCHEMA` 分頁（date 用 text + hint，配合 CMS 表單僅支援 text/number/datetime）。
- **分權一致性**：`AdminAnnouncementsPage` 補 `is_superuser` 前端守門並 gate 資料載入（與 `AdminAuditLogPage` 一致）。

### 文件
- `backend/apps/admin_api/CLAUDE.md`：新增超管/一般管理員權限矩陣。
- `backend/apps/accounts/CLAUDE.md`、`CLAUDE.md`：把「管理員走 /django-admin」改為「前台 email 登入 + seed_admin」、route map 移除 django-admin 列、「三種管理介面」→「管理介面（React /admin 唯一後台）」。

## 原因
使用者需求：(1) 兩個後台只留 React `/admin`、所有功能集中於此；(2) 管理員帳號 `115401@gmail.com` 前台登入即可進 `/admin`；(3) 參考 `網站範例` 的分權/下載/配色；(4) 融合 `過場動畫和網站設計範本` 的粒子過場與 page2 設計（內容放大）；(5) 首次進站播動畫、回訪不重播。

## 影響範圍
- **登入流程**：管理員不再有 django-admin；改用前台 email 登入（`/api/auth/email-login/`）。授予 staff/superuser 只能用 `manage.py seed_admin` 或 shell。
- **路由**：`/django-admin/*` 現在落入 SPA fallback（回 index.html），不再是 Django Admin。
- **前端**：首次進站行為改變（播動畫）；首頁 hero、下載頁 CTA、後台內容管理多一個里程碑分頁。
- **相依**：本機原無 `frontend/node_modules`、`frontend/dist`，本次已 `npm install` + `npm run build`（系統 Node v22.17，安全）。

## 驗證方式
- 後端：`manage.py check` 0 issues；`apps.scans` 118 tests OK、`apps.admin_api` 34 tests OK；種子帳號 `authenticate()`=True、is_staff/is_superuser=True；milestone CMS 端點 CREATE 201/LIST 200（測試資料已清）。
- 整合 smoke：`/`=200、`/django-admin/`=200（已成 SPA）、intro 資產=200。
- 前端：`npm run build` EXIT=0（多次）。
- fresh-eyes 子代理 QA：無 Critical；已修 🟡 公告前端守門、🔵 intro timeout 清除、🟡 /login 不覆寫；🟠 ProjectFeature 無 admin 編輯（既有狀態，待產品決策）留待後續。
- **待人眼驗證（無法自動化）**：動畫實際播放、略過鈕、回訪不重播、reduced-motion；React 後台 milestone 分頁與下載頁 UI。

## 未完成 / 後續（詳見 `.sisyphus/argus-handoff.local.md`）
- **#7 雙色主題切換**：評估後**不硬做**。App 用固定品牌色 token + 大量硬編碼深色，無語意主題變數；真 light/dark 需大重構，且抵觸 `argus-ui-design` skill「科技風固定」鐵則。待使用者決策（保持固定深色識別／或另立重構專案）。
- **#6 後台視覺**：後台原已是「深色 cyan sidebar + 白卡片 + cyan 發光 active」（符合網站範例 + UIUX「後台克制」鐵則），本次再加 sidebar 頂部靜態 cyan 微光。深度動畫化會違反該鐵則，故不做。
- **#11 staff 授權 UI**：暫不做（授予 staff/superuser 用 `seed_admin` 命令即可，且屬高敏感、非明確需求）。
- **ProjectFeature**：QA 發現 `cms/features/` 端點存在但 React admin 無分頁、`ProjectPage` features 為硬編碼 → 待產品決策（上 admin 分頁並接 DB／或移除孤兒端點）。
- **文件殘留**：living docs 已全數對齊（CLAUDE.md／accounts·admin_api CLAUDE.md／ONBOARDING／使用說明／README／Project_說明／開發計畫 + GoogleLoginView docstring）。僅 `ONBOARDING.md:115` 的 nginx 部署描述提到 `/django-admin`（harmless）、log 檔屬歷史，皆不動。
- **全套件驗證**：`manage.py test apps` 251 passed、`check` 0 issues、前端 `npm run build` EXIT=0。
