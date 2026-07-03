# JWT Refresh Token Rotation + Blacklist

## 變更內容

**修改檔案：**
- `backend/config/settings.py` — `INSTALLED_APPS` 加入 `token_blacklist`；`SIMPLE_JWT` 擴充配置
- `backend/apps/accounts/urls.py` — 新增 `refresh/` 端點對應 `TokenRefreshView`

**新增 SIMPLE_JWT 設定：**
| 設定 | 值 | 說明 |
|---|---|---|
| `REFRESH_TOKEN_LIFETIME` | 7 天（`.env` 可覆寫 `JWT_REFRESH_TOKEN_LIFETIME_DAYS`）| 明確設定，覆寫 SimpleJWT 預設 1 天 |
| `ROTATE_REFRESH_TOKENS` | `True` | 每次 refresh 換發新 refresh |
| `BLACKLIST_AFTER_ROTATION` | `True` | 舊 refresh 立即加入黑名單 |

**新增端點：**
- `POST /api/auth/refresh/` — SimpleJWT 內建 `TokenRefreshView`

## 原因

原本 `SIMPLE_JWT` 只設定 `ACCESS_TOKEN_LIFETIME`（60 分），未配置 refresh token 相關：
1. 沒有 `TokenRefresh` 端點，login 拿到的 refresh token 完全用不到
2. 沒有 rotation，refresh token 被竊後可持續換 access（等於長期存取）
3. 沒有 blacklist 機制，撤銷 token 無從實作

使用者實際體驗：60 分鐘後 access 過期 → 401 → 靜默登出 → 需重新登入。加上 refresh 端點後可實作無感續期。

## 行為說明

**Rotation + blacklist 流程：**
```
POST /api/auth/refresh/  {"refresh": "OLD_REFRESH"}
  ↓
{"access": "NEW_ACCESS", "refresh": "NEW_REFRESH"}
  ↓
OLD_REFRESH 立即進 blacklist（BlacklistedToken 記錄）
再用 OLD_REFRESH → 401
```

**Token 生命週期：**
- Access：60 分（短，被竊影響時效有限）
- Refresh：7 天（`.env` 可調整）
- Blacklist：SimpleJWT 提供 `flushexpiredtokens` management command 週期清理

## 影響範圍

- **DB migration**：新增 `token_blacklist` 兩張表（`OutstandingToken`、`BlacklistedToken`）
- **API**：新增 `POST /api/auth/refresh/`（既有端點行為不變）
- **前端**：可選擇實作 refresh 攔截器（axios interceptor 於 401 時呼叫 refresh 續期）；不改也不會壞
- **既有 refresh token**（舊使用者已持有的 refresh JWT）：仍可 refresh 一次，用畢即入黑名單

## 驗證方式

- Migration：`python manage.py migrate token_blacklist` — 13 個 migration 全通過
- accounts 測試（11 項）— 全部通過
- 全套後端測試（398 項）— 全部通過，無 regression
