# API Rate Limiting（DRF throttle + 敏感端點專屬限速）

## 變更內容

**修改檔案：**
- `backend/config/settings.py` — 新增 `CACHES` 與擴充 `REST_FRAMEWORK` 加入 throttle 配置
- `backend/apps/accounts/views.py` — 5 個公開 view 加 `ScopedRateThrottle` + `throttle_scope`
- `backend/apps/insights/views.py` — 新增 `InsightsAnonThrottle` 並套用到 4 個公開端點
- `backend/apps/scans/views.py` — 新增 `ScanCreateThrottle`，`ScanJobViewSet.get_throttles()` 只在 create action 套用

## 新增 Cache 配置

```python
CACHES = {
    "default": {
        "BACKEND": os.getenv("DJANGO_CACHE_BACKEND", "django.core.cache.backends.locmem.LocMemCache"),
        "LOCATION": os.getenv("DJANGO_CACHE_LOCATION", "argus-default"),
    }
}
```

- **dev / test**：LocMemCache（per-process 記憶體）
- **production**：透過 `.env` 設 `DJANGO_CACHE_BACKEND=django.core.cache.backends.redis.RedisCache` + `DJANGO_CACHE_LOCATION=redis://...`（Django 5 內建 RedisCache，不需另裝 django-redis）

## Throttle 設定表

| Scope | Rate | 對象 | 保護目的 |
|---|---|---|---|
| `anon` | 200/min | 所有未登入請求（by IP） | 一般公開頁 + 前端輪詢 |
| `user` | 3000/hour | 所有登入請求（by user.id） | 一般 API 使用 |
| `login` | 10/min | GoogleLogin / EmailLogin（by IP） | 防暴力破解密碼 |
| `register` | 10/hour | EmailRegister（by IP） | 防垃圾註冊 |
| `password_reset` | 5/hour | PasswordResetRequest / Confirm（by IP） | 防 Email 洪水、防 token brute force |
| `insights` | 30/hour | 4 個 insights 端點（by IP） | 防 SSRF 探測 / 免費工具濫用 |
| `scan_create` | 30/hour | `POST /api/scans/`（by user.id） | 掃描是最貴的操作（Playwright + Celery + LLM），限速防止 script 誤觸發 |

所有 rate 都可透過 `.env` 覆寫（`THROTTLE_LOGIN=20/min` 等）。

## 原因

原本後端**完全沒有 throttle**：
1. 5 個 auth `AllowAny` 端點無限制暴力破解
2. Insights 免費工具無限制濫用 → 每次呼叫都會對外部 URL 發 request（SSRF-adjacent）
3. `POST /api/scans/` 無限制 → 惡意 script 可讓 Celery 積滿無效任務

## 影響範圍

- 超過 rate 回 `HTTP 429 Too Many Requests` + `Retry-After` header
- Cache 後端要求：production 應改用 Redis（多 worker 需要共用 counter）
- 前端可解讀 429 顯示「操作過於頻繁，請稍後再試」；未改也不會壞
- 測試環境：LocMemCache per-process 已足夠，test suite 未觸發任何 throttle

## 驗證方式

- AST 語法檢查（4 個檔案）— 全部通過
- 全套後端測試（398 項）— 全部通過，無 regression
