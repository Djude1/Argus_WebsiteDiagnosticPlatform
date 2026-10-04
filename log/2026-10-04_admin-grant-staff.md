# 超級管理員在後台設定／取消一般管理員

**日期**：2026-10-04  
**操作者**：Claude

## 變更內容
- `admin_api/views.py`：新增 `set_staff`（`POST /api/admin/users/<id>/staff/`，body `{is_staff}`），`IsSuperuser`；`select_for_update` 內檢查：不能改自己、不能改 superuser、停用或已刪除帳號不能設為管理員；有變更才寫 `AdminAuditLog`（`user_toggle_staff`，payload before／after，寫在 transaction 外）。
- `admin_api/serializers.py`：`SetStaffSerializer`；`urls.py` 新增路由 `admin-user-set-staff`。
- 前端 `AdminUsersPages.tsx`：使用者詳情新增「管理權限」區塊（只有超級管理員看得到）：顯示目前身分、設為／取消管理員按鈕與確認對話框；自己或超級管理員帳號只顯示說明。`api.ts` 新增 `adminSetStaff`，`apiContracts.ts` 新增型別；重新產生 `openapi.json`／`apiTypes.ts`（同時補上先前未重新產生的端點型別）。
- 樣式：`18-admin.css` 的 `.admin-role-row`。
- 文件：`admin_api`／`accounts`／`frontend` CLAUDE.md、ONBOARDING.md、使用說明.md、需求書 F-027、設計文件權限段落。

## 原因
使用者要求管理員可以在後台把用戶帳號變成管理帳號。決策（使用者選擇）：只有超級管理員能操作；後台只能授予一般管理員（staff），superuser 仍只能用 `seed_admin` 設定。

## 影響範圍
- 權限判斷每次請求都讀資料庫，取消管理員後立即失去後台權限。
- 一般管理員呼叫此端點回 403；auth 端點仍不簽發任何管理權限。

## 驗證方式
- `manage.py test apps.admin_api`（113 項 OK，含新 `SetStaffTests`）、`ruff check backend`。
- 前端 `npm run lint`、`npm run typecheck`、`npm test`、build；`AdminUsersPages.test.tsx` 新增 3 項。
- 本機瀏覽器：超級管理員把用戶設為管理員（確認對話框 → 成功訊息）；該用戶登入後可進後台使用者列表，且看不到管理權限區塊；無 JS 錯誤。
