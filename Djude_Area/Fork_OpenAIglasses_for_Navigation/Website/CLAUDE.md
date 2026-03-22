# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概述

AI 導航智慧眼鏡展示與購買網站，基於 [OpenAIglasses_for_Navigation](https://github.com/AI-FanGe/OpenAIglasses_for_Navigation) 開源專案製作。**所有服務均透過 Docker Compose 執行，禁止直接在本機安裝 Python/Node 套件。**

## 常用指令

```bash
# 首次啟動（需先建立 .env）
cp .env.example .env
docker compose up --build

# 日常啟動 / 停止
docker compose up -d
docker compose down

# 查看即時 log
docker compose logs -f backend
docker compose logs -f frontend

# 重新建置（修改 Dockerfile 或 requirements.txt 後）
docker compose up --build

# 進入 Django shell
docker compose exec backend python manage.py shell

# 手動執行 migrate
docker compose exec backend python manage.py migrate

# 手動建立遷移檔案
docker compose exec backend python manage.py makemigrations
```

## 架構概覽

```
Nginx (:80)
 ├── /api/, /admin/  →  Django (backend:8000, Gunicorn)
 ├── /media/         →  Volume 靜態服務（GLB 模型、圖片）
 ├── /static/        →  Volume 靜態服務（Django collectstatic）
 └── /              →  React (frontend:3000, Vite dev server)
```

**請求流向：** 瀏覽器 → Nginx → backend 或 frontend 容器。前端的 `vite.config.js` 也設有同樣的 proxy 規則（供容器內部開發模式使用）。

## 後端（Django）

- **進入點**：`backend/entrypoint.sh` — 啟動時自動 wait for db、makemigrations、migrate、collectstatic、建立 superuser、載入初始資料，最後啟動 Gunicorn。
- **設定檔**：`backend/config/settings.py`，全部敏感值從環境變數讀取。
- **API 路由**：
  - `POST /api/token/` — 取得 JWT
  - `POST /api/token/refresh/` — 刷新 JWT
  - `/api/accounts/` — 使用者（CustomUser，role: admin/editor/viewer）
  - `/api/products/` — 商品、功能、規格
  - `/api/orders/` — 訂單（訪客可購買，不需登入）
  - `/api/team/` — 團隊成員（`?type=developer` 或 `?type=reference`）
- **媒體檔案**：`aiglass.glb` 從專案根目錄以 read-only volume 掛載至容器 `/app/media/models/aiglass.glb`，前端透過 `/media/models/aiglass.glb` 存取。

## 前端（React）

- **API 集中管理**：`frontend/src/api/client.js` — 所有 API 呼叫從這裡發出，`baseURL` 為 `/api`。
- **路由**（react-router-dom）：
  - `/` — Home（首頁）
  - `/product` — Product（商品詳情 + 3D 模型檢視器）
  - `/purchase` — Purchase（購買表單）
  - `/team` — Team（團隊成員）
- **3D 模型**：`frontend/src/components/ModelViewer/ModelViewer.jsx`，使用 `@react-three/fiber` 渲染 `aiglass.glb`。

## 環境變數（.env）

`.env` 不納入 Git，需從 `.env.example` 複製後修改。關鍵變數：

| 變數 | 說明 |
|------|------|
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | PostgreSQL 連線，backend 與 db 容器必須一致 |
| `SECRET_KEY` | Django secret key |
| `DJANGO_SUPERUSER_USERNAME` / `DJANGO_SUPERUSER_PASSWORD` | 首次啟動自動建立的後台帳號 |

## 注意事項

- `aiglass.glb` 為二進位格式，勿用文字編輯器開啟；預覽請用 [glTF Viewer](https://gltf-viewer.donmccurdy.com/) 或 Blender。
- 新增 Django App 後需在 `entrypoint.sh` 的 `makemigrations` 指令中加入 app 名稱。
- 後台管理員資料（TeamMember 組員姓名、介紹）需至 `http://localhost/admin/team/teammember/` 手動修改。
