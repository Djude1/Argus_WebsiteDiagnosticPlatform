<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-19 | Updated: 2026-05-19 -->

# Website（展示網站）

## 用途

專案對外展示網站：Django REST 後端 + React (Vite) 前端 + 管理後台，含產品介紹、團隊、公告、購買流程（綠界 ECPay）與裝置/語音監控。以 Docker Compose 編排。

## 關鍵檔案 / 目錄

| 路徑 | 用途 |
|------|------|
| `docker-compose.yml` | backend / frontend / nginx 服務編排 |
| `CLAUDE.md` | Website 子專案專屬規則 |
| `aiglass.glb` | 產品 3D 模型（前端 ModelViewer 使用） |
| `backend/` | Django REST 後端（見 `backend/AGENTS.md`） |
| `frontend/` | React + Vite 前端與管理後台（見 `frontend/AGENTS.md`） |
| `nginx/` | 反向代理設定 |
| `docs/superpowers/` | 規劃與規格文件 |

## For AI Agents

### 在本目錄工作

- 先讀 `Website/CLAUDE.md` 子專案規則；註釋繁體中文
- 機密（DB 密碼、ECPay 金鑰、Django SECRET_KEY）一律走環境變數，勿硬編碼

### 測試要求

- 完整測試清單見 `web-test` skill（含後端 API 驗證）
- 後端改動：直打 API 確認回應；前端改動：build + 畫面驗證

### 常見模式

- 前後端分離，前端經 `/api` 走 nginx 代理至 Django

## 相依

### 外部
- Django / DRF、React / Vite / TailwindCSS、Docker、nginx、綠界 ECPay

<!-- MANUAL: 此線以下手動註記在重新產生時會保留 -->
