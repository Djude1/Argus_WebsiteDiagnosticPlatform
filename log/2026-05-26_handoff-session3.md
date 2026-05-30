# 交接文件：Session 3 工作進度（2026-05-26）

**操作者**：Claude（Session 3 / Opus 4.7 max effort）
**下次繼續從**：**Phase 6 Task 6.3 → 6.4 → Phase 2 → Phase 4 → Phase 5**

---

## 本 Session 已完成

| Task | 說明 | Commit |
|---|---|---|
| Phase 6 / Task 6.1 | Announcement model + migration 0002 + data migration 0003（seed 台灣刑法 358/359/360 條法律公告，type=permanent） | `b7bf9cd` |
| Phase 6 / Task 6.2 | 公告 API：active_announcements / announcements_admin / announcement_detail + AnnouncementSerializer + 3 條 URL | `d628292` |

公告系統「後端」已 100% 完成，可被前端呼叫。

---

## 已存在的 API 端點

| Method | Path | Permission | 功能 |
|---|---|---|---|
| GET | `/api/admin/announcements/active/` | IsAuthenticated | 取得目前有效公告（已過濾 is_currently_active） |
| GET | `/api/admin/announcements/` | IsAdminUser | 列出全部公告（含停用/過期） |
| POST | `/api/admin/announcements/` | IsAdminUser | 建立公告 |
| GET | `/api/admin/announcements/<pk>/` | IsAdminUser | 取得單一公告 |
| PATCH | `/api/admin/announcements/<pk>/` | IsAdminUser | 部分更新公告 |
| DELETE | `/api/admin/announcements/<pk>/` | IsAdminUser | 刪除公告 |

回應格式：list 端點 `{"announcements": [...]}`；detail 端點直接 announcement object。

---

## 尚未完成的任務

### Phase 6（公告系統） — 還剩前端

| Task | 說明 | 預估工作量 |
|---|---|---|
| **6.3** | Dashboard 公告 Modal（localStorage 記 dismiss 臨時 / confirm 常駐 24h suppress） | 中 |
| **6.4** | 後台 `/admin/announcements` 管理 UI（superuser 專屬，新增/編輯/刪除） | 中 |

### Phase 2（公開頁面）

| Task | 說明 |
|---|---|
| 2.1 | 組員 seed data（4 人佔位符，已寫好 seed_team.py 在計畫中） |
| 2.2 | /download 頁 PWA 卡片可點擊優化 |
| 2.3 | TopNav 修正（首頁按鈕 ICON、移除下載按鈕） |

### Phase 4（設定與評論）

| Task | 說明 |
|---|---|
| 4.1 | /settings 頁重設計 |
| 4.2 | /reviews 修正 is_admin + 圖片 lightbox |

### Phase 5（後台改造）

| Task | 說明 |
|---|---|
| 5.1 | 操作日誌合併（3-tab，名稱「操作日誌」） |
| 5.2 | Admin Overview 改 AI API Key 用量 |
| 5.3 | /admin/content 改善 |
| 5.4 | /admin/reviews + /admin/plans 美化 |

---

## 執行方式

計畫檔：`docs/superpowers/plans/2026-05-26-argus-26-fixes.md`（Task 6.3 在 line 2337 起，Task 6.4 在 line 2509 起）

使用 `subagent-driven-development` 風格繼續執行：
1. 每個 Task 拆成 step
2. 每 step 後驗證再進入下一個
3. Task 結尾必 commit + log

---

## 重要注意事項

### 1. PowerShell heredoc 中文編碼地雷

計畫 Task 6.1 Step 3 原本要用 `manage.py shell -c @'...'@` heredoc 來 seed 中文公告，但 PowerShell 在 Windows cp950 console 下會把繁體中文編碼壞掉（實測會回 `unrecognized arguments` 錯誤）。

**更穩定的替代方案**：寫 **data migration**（`migrations.RunPython`），檔頭加 `# -*- coding: utf-8 -*-`，內容直接寫繁中字串。範例：`backend/apps/admin_api/migrations/0003_seed_legal_announcement.py`。

未來如果還要 seed 中文資料（例如 Task 2.1 組員資料），可參考此 pattern；或如計畫所述用 management command（也是 .py 檔，沒 shell 編碼問題）。

### 2. 既有 view 風格

`backend/apps/admin_api/views.py` 慣用：
- `@permission_classes([permissions.IsAdminUser])`（不是直接 `[IsAdminUser]`）
- `get_object_or_404`（不是 try/except DoesNotExist）

請遵循風格，不要混。

### 3. 前端 build

`cd frontend; .\build-node22.ps1`（system Node v24 + Rollup 4.x 會 crash）

### 4. App.jsx 巨型單檔

4500+ 行，**必須先 grep 定位再讀**，不要從頭瀏覽。Task 6.3 要找 `DashboardPage`（約 line 2303），Task 6.4 要找 `ADMIN_NAV_ITEMS` 與路由區。

### 5. store 名稱

用 `useArgusStore` + `setToken`（非 `useStore` / `setAccessToken`，計畫文件部分早期段落仍用舊名）。實際看 `frontend/src/store.js`。

### 6. APIClient + ALLOWED_HOSTS

如果要在 script 內直接呼叫 DRF APIClient（測試環境外），它會用 `testserver` 作 HOST，本專案 `ALLOWED_HOSTS` 不含 `testserver`，會撞 DisallowedHost。改用 `APIRequestFactory + force_authenticate + 直接呼叫 view function`（不走 middleware）即可繞過。

---

## 驗證指令備忘

```powershell
# Django check
uv run python backend/manage.py check

# admin_api 測試（34 個）
uv run python backend/manage.py test apps.admin_api

# 全部測試
uv run python backend/manage.py test apps

# 啟動（前端要先 build）
uv run python backend/manage.py runserver 127.0.0.1:8000

# 前端 build
cd frontend; .\build-node22.ps1; cd ..
```
