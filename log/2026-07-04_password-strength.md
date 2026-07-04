# 密碼強度加強（min 10 + 複雜度 + view 層真正呼叫 validate_password）

## 變更內容

**新增檔案：** `backend/apps/accounts/validators.py`
- `ComplexityValidator`：密碼需同時包含英文字母與數字（可選參數 `require_letter`、`require_digit`）

**修改檔案：**
- `backend/config/settings.py`：`AUTH_PASSWORD_VALIDATORS` 加強
  - `MinimumLengthValidator`：min_length 8 → 10
  - 新增 `apps.accounts.validators.ComplexityValidator`
- `backend/apps/accounts/views.py`：3 個 view 改用 `django.contrib.auth.password_validation.validate_password`
  - `EmailRegisterView`：註冊時驗證密碼強度
  - `PasswordResetConfirmView`：重設密碼時驗證（token 驗證通過後才驗）
  - `ChangePasswordView`：變更密碼時驗證

## 原因

原本 `AUTH_PASSWORD_VALIDATORS` 雖有 4 個 validator 設定，但**三個 view 全部硬編碼 `len(password) < 8`**，完全繞過 Django 的 validator 機制。這代表：
1. 加什麼 validator 到 settings 都無效
2. 密碼只需要 8 字元就過關，可以是純數字、可以是 `12345678`、也可以與 email 完全一樣
3. `CommonPasswordValidator`（擋 20,000 個最常見的弱密碼）從未被呼叫過

新規則：
- **長度 ≥ 10**（原 8）
- **必須同時含字母與數字**（Django 內建無此規則）
- **UserAttributeSimilarityValidator 生效**：密碼不能與 email 過度相似
- **CommonPasswordValidator 生效**：擋 20K 個弱密碼
- **NumericPasswordValidator 生效**：擋純數字密碼

## 行為說明

**Register**（`POST /api/auth/register/`）：
```
輸入 password="StrongPass123"
  → 傳入 unsaved user_model(username=email, email=email) 給 similarity validator
  → 通過 → 建立 user
輸入 password="short"（< 10）
  → 400 {"password": ["密碼長度不能少於 10 個字元。"]}
輸入 password="1234567890"（純數字）
  → 400 {"password": ["這組密碼全都是數字。", "密碼需至少包含一個英文字母。"]}
輸入 password="password"（廣為人知弱密碼）
  → 400 {"password": ["密碼長度不能少於 10 個字元。", "這組密碼過於常見。"]}
```

**Password Reset Confirm**：驗證 token 通過**之後**才檢查密碼強度（避免透過此端點爆破密碼複雜度規則獲取有效 token 存在的資訊）。

**Change Password**：`request.user` 作為 similarity 檢查基準。

## 影響範圍

- **既有使用者**：不影響（既有密碼哈希不重新驗證）
- **新註冊**：必須符合新規則
- **測試**：無 regression。既有測試用 `create_user()` 直接建立（不走 validators）；透過 API 的 register/login 測試已使用強密碼（`StrongPass123!` 等）
- **前端**：可讀 400 回應的 `password` / `new_password` 欄位陣列顯示所有失敗原因

## 驗證方式

- AST 語法檢查（3 個檔案）— 通過
- accounts 測試（11 項）— 通過
- 全套後端測試（398 項）— 全部通過，無 regression
