# 交接文件：Session 2 工作進度（2026-05-26）

**操作者**：Claude  
**下次繼續從**：**Task 3.4 review → Phase 6（公告系統）→ Phase 2 → Phase 4 → Phase 5**

---

## 已完成的任務

| Task | 說明 | Commit |
|---|---|---|
| Phase 1 / Task 1.1 | robots.txt 封鎖 /admin/ 爬蟲 | `20a8bf0` |
| Phase 1 / Task 1.2 | Email 帳號註冊 + 登入端點 | `e4e9ece`, `9754a2c` |
| Phase 1 / Task 1.3 | GET/PATCH /api/auth/me/ + change-password | `5d5fffb`, `1ab0001` |
| Phase 1 / Task 1.4 | LoginPage 3-tab（Google/Email/新帳號）+ 移除後台按鈕 | `bab64aa` |
| Phase 3 / Task 3.1 | POST /api/estimate/ 預掃描費用估算後端 | `1e91e9f`, `d6fb911` |
| Phase 3 / Task 3.2 | 前端掃描表單加預估費用按鈕，移除頁數上限 | `fcdb207` |
| Phase 3 / Task 3.3 | 發票 UI 重構（個人/公司分開，加統一編號） | `22f1514` |
| Phase 3 / Task 3.4 | 移除 account-bar，NavActions 整合進 TopNav | （本次 commit） |

---

## 尚未完成的任務

### Phase 6（公告系統）← **下一個開始**

| Task | 說明 |
|---|---|
| **6.1** | Announcement model + migration + seed（台灣法律常駐公告） |
| **6.2** | POST/GET /api/admin/announcements/ API 端點 |
| **6.3** | Dashboard 公告 Modal（localStorage 記 dismiss） |
| **6.4** | 後台公告管理 UI（/admin/content 或新頁面） |

### Phase 2（公開頁面）

| Task | 說明 |
|---|---|
| 2.1 | 組員 seed data（4 人佔位符，組長第一，含 GitHub/email/大頭照 URL） |
| 2.2 | /download 頁 PWA 卡片可點擊優化 |
| 2.3 | TopNav 修正（首頁按鈕 ICON、移除下載按鈕） |

### Phase 4（設定與評論）

| Task | 說明 |
|---|---|
| 4.1 | /settings 頁重設計（用戶資料 + 改密碼 + 危險區） |
| 4.2 | /reviews 修正 is_admin 標籤（非 staff 不顯示「Argus 官方」）+ 圖片 lightbox |

### Phase 5（後台改造）

| Task | 說明 |
|---|---|
| 5.1 | 操作日誌合併（transactions + scans + audit-log 合成 3-tab，名稱改「操作日誌」） |
| 5.2 | Admin Overview 改為 AI API Key 用量顯示 |
| 5.3 | /admin/content 改善（刪 ProjectFeature、TeamMember 加 github/email/avatar、AppRelease 美化） |
| 5.4 | /admin/reviews + /admin/plans 美化 |

---

## 執行方式

計畫檔：`docs/superpowers/plans/2026-05-26-argus-26-fixes.md`  
使用 `subagent-driven-development` skill 繼續執行，從 Phase 6 Task 6.1 開始。

---

## 重要注意事項

1. **`.env` 需手動更新**（hook 保護，AI 無法寫入）：
   ```
   DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,argus6.qzz.io
   ```

2. **前端 build 一律用**：
   ```powershell
   cd frontend; .\build-node22.ps1
   ```
   或 Bash：
   ```bash
   cd /c/Users/puppy/OneDrive/Desktop/專題/Argus/frontend && D:/node22/node.exe D:/node22/node_modules/npm/bin/npm-cli.js run build
   ```

3. **store 名稱**：用 `useArgusStore` + `setToken`（非 `useStore`/`setAccessToken`）

4. **Task 3.4 已完成但尚未做 review**，下次繼續前可先快速確認 build 沒問題。
