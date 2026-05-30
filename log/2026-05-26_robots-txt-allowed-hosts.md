# 加入 robots.txt 封鎖爬蟲索引 + 更新 ALLOWED_HOSTS

**日期**：2026-05-26
**操作者**：Claude Sonnet 4.6

## 變更內容
- `backend/config/urls.py`：新增 `from django.http import HttpResponse` import
- `backend/config/urls.py`：新增 `robots_txt(request)` 函式，回傳純文字封鎖 `/admin/` 與 `/django-admin/`
- `backend/config/urls.py`：在 `urlpatterns` 最前面加入 `path("robots.txt", robots_txt)`
- `.env`：`DJANGO_ALLOWED_HOSTS` 加入 `argus6.qzz.io`（**未納入 git**，因 `.env` 是機密設定）

## 原因
Phase 1 Task 1.1：部署前安全強化。robots.txt 防止搜尋引擎爬取後台路徑；ALLOWED_HOSTS 加入外部域名以允許正式環境請求。

## 影響範圍
- `GET /robots.txt` 現在回傳正確的 robots 規則（不再 fallback 到 SPA）
- `SPA fallback` 正則 `^(?!django-admin/|api/|static/|media/).*$` 仍會匹配 `robots.txt`，但由於 `path("robots.txt", ...)` 排在前面，Django URL dispatcher 會先命中它（Django URL 按順序匹配，第一個 match 優先）
- `DJANGO_ALLOWED_HOSTS` 增加 `argus6.qzz.io`，不影響本機開發

## 驗證方式
- `uv run python backend/manage.py check` → `System check identified no issues (0 silenced).` ✅
- `.env` 異動需手動更新（hook 保護禁止程式自動寫入機密檔案）
