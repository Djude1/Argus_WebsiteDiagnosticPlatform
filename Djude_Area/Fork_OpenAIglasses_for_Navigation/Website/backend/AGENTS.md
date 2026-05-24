<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-19 | Updated: 2026-05-19 -->

# Website/backend（Django REST 後端）

## 用途

提供展示網站的 REST API 與管理後台 API。標準 Django 多 app 結構，每個 app 內含 `models / serializers / views / urls / admin`，管理後台另有 `admin_views.py`。

## 關鍵檔案

| 檔案 | 用途 |
|------|------|
| `manage.py` | Django 管理進入點 |
| `requirements.txt` | Python 相依 |
| `config/settings.py` | 全域設定（DB、CORS、第三方金鑰等，走環境變數） |
| `config/urls.py` | 根路由 |
| `config/wsgi.py` | WSGI 進入點 |
| `fixtures/` | 初始資料 |

## 子應用（Django apps）

| App | 職責 |
|-----|------|
| `accounts/` | 使用者帳號、權限（`permissions.py`）、認證 |
| `products/` | 產品資料與管理 |
| `orders/` | 訂單與綠界金流（`ecpay.py`） |
| `content/` | 頁面內容 / 公告 |
| `team/` | 團隊成員 |
| `analytics/` | 流量/事件分析（`utils.py` 統計工具，無 serializers） |

各 app 的 `migrations/` 為 Django 自動產生的資料庫遷移，請勿手改。

## For AI Agents

### 在本目錄工作

- 註釋繁體中文；遵守 `Website/CLAUDE.md`
- model 變更必須產生 migration（`uv run python manage.py makemigrations`）
- 金鑰/密碼走環境變數，禁止寫入 `settings.py`

### 測試要求

- 改動後直打對應 API 確認回應；參考 `web-test` skill 後端章節
- migration 變更先在本地 `migrate` 驗證

### 常見模式

- 公開 API 在各 app `views.py` + `urls.py`；管理後台在 `admin_views.py`

## 相依

### 內部
- 前端 `Website/frontend` 消費本 API

### 外部
- Django / DRF、綠界 ECPay SDK

<!-- MANUAL: 此線以下手動註記在重新產生時會保留 -->
