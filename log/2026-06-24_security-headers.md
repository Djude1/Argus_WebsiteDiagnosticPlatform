# 安全 HTTP 頭部設定

## 變更內容

**修改檔案：** `backend/config/settings.py`

在 `CSRF_TRUSTED_ORIGINS` 之後新增安全頭部設定區塊：

| 設定 | 值 | 注入的 HTTP 頭部 |
|---|---|---|
| `SECURE_PROXY_SSL_HEADER` | `("HTTP_X_FORWARDED_PROTO", "https")` | — （讓 Django 信任 upstream proxy） |
| `SESSION_COOKIE_SECURE` | `not DEBUG` | `Set-Cookie: Secure` |
| `CSRF_COOKIE_SECURE` | `not DEBUG` | `Set-Cookie: Secure` |
| `SECURE_HSTS_SECONDS` | `0`（DEBUG）/ env 預設 `60` | `Strict-Transport-Security` |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `not DEBUG` | HSTS `includeSubDomains` |
| `SECURE_HSTS_PRELOAD` | `False` | — |
| `SECURE_CONTENT_TYPE_NOSNIFF` | `True` | `X-Content-Type-Options: nosniff` |
| `SECURE_REFERRER_POLICY` | `"strict-origin-when-cross-origin"` | `Referrer-Policy` |
| `X_FRAME_OPTIONS` | `"DENY"` | `X-Frame-Options: DENY` |

## 原因

`SecurityMiddleware` 和 `XFrameOptionsMiddleware` 雖已在 MIDDLEWARE 清單中，但未設定對應 settings 變數時，這些保護頭部不會被注入。缺少這些頭部使應用程式容易受 Clickjacking、MIME sniffing、Referrer 洩漏等攻擊。

## 行為說明

- **不設 `SECURE_SSL_REDIRECT`**：nginx/Cloudflare 負責 HTTP→HTTPS，Django 設此值會導致 nginx→Django 的內部 HTTP 請求觸發無限 redirect 迴圈。
- **`SECURE_PROXY_SSL_HEADER`**：使 `request.is_secure()` 在 proxy 後方正確回傳 True，前提是 nginx 需設 `proxy_set_header X-Forwarded-Proto $scheme`。
- **HSTS 初始 60 秒**：安全可逆測試。確認全程 HTTPS 穩定後，透過 `.env` 設 `SECURE_HSTS_SECONDS=31536000` 再搭配 `SECURE_HSTS_PRELOAD=True`。
- **DEBUG 環境豁免**：`not DEBUG` 確保本機開發不需 HTTPS 即可正常運作。

## 影響範圍

- 正式環境（`DEBUG=False`）：所有上述頭部生效
- 本機開發（`DEBUG=True`）：Cookie Secure 旗標和 HSTS 不啟用，不影響開發
- nginx 需確認已加 `proxy_set_header X-Forwarded-Proto $scheme`（Docker compose 配置應已有此設定）

## 驗證方式

語法驗證：`python -c "import ast; ast.parse(open('backend/config/settings.py', encoding='utf-8').read())"` — 通過

整合測試：部署至 Docker 後，用 `curl -I https://domain` 確認回應含 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: strict-origin-when-cross-origin`。
