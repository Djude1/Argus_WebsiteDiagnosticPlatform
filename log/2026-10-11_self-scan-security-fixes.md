# Argus 自掃資安問題修正：登入 CSRF、網頁安全標頭

**日期**：2026-10-11  
**操作者**：Claude

## 變更內容
- `accounts/views.py`：`EmailLoginView`、`GoogleLoginView` 加 `csrf_protect`；`TurnstileConfigView` 加 `ensure_csrf_cookie`（登入頁一進來就設定 csrftoken cookie）
- 前端新增 `shared/CsrfField.jsx`：送出登入前確保有 cookie、登入表單加隱藏 `csrfmiddlewaretoken` 欄位
- `k8s/05-frontend.yaml`（revision 3）與 `frontend/nginx.conf`：SPA 頁面（`location /`）加 HSTS（1 年、includeSubDomains）、X-Frame-Options DENY、X-Content-Type-Options nosniff、Referrer-Policy；`/api/` 仍由 Django 自己送
- 測試 `LoginCsrfTests`；既有 refresh CSRF 測試改為先取 cookie 再登入
- 文件：accounts／frontend CLAUDE.md

## 原因
使用者對 argus.clouda.dpdns.org 自掃，報告列出：
- 登入表單缺 CSRF token：登入端點原本不驗 CSRF，確實有 login CSRF 風險
- 缺 HSTS／X-Frame-Options／nosniff：網頁是前端 nginx 直接送出，沒有任何安全標頭；Django 的 HSTS 因 Cloudflare Tunnel 進來是 http（`X-Forwarded-Proto: http`）也不會送

## 影響範圍
- 登入與 Google 登入必須帶 CSRF token（前端已處理）；其他直接呼叫這兩個 API 的客戶端會收到 403
- HSTS 一經瀏覽器記住 1 年內只能走 HTTPS（Cloudflare 一律提供 HTTPS，無影響）
- 需人工處理（不在 repo）：Cloudflare「Always Use HTTPS」、clouda.dpdns.org 的 SPF／DMARC DNS 紀錄
- 尚未處理：CSP、頁面標題重複、JavaScript 渲染（GEO）

## 驗證方式
- `manage.py test apps`：1913 項 OK（skipped 10）；`ruff check backend` 通過
- 前端 lint（0 error）、typecheck、`npm test` 280 項通過
- root `tests/`：唯一錯誤是本機沒有 kustomize，改動前即如此
- 部署後需重新掃描確認
