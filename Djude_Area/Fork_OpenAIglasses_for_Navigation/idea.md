# 想法與待實作項目

## 多裝置架構（已實作）

### 已完成
- `start_multi_device.py`：同時啟動 4 個獨立 FastAPI 進程（port 8081~8084）
  - 啟動指令：`uv run python start_multi_device.py`
  - 只啟動 N 台：`uv run python start_multi_device.py --count 2`
  - Ctrl+C 一次關閉全部
- `nginx.conf`：新增 `/device/1/` ~ `/device/4/` 路由，各自代理至對應 FastAPI
- `nginx.conf`：新增 `/api/devices/N/status` 直通各裝置 `/api/debug_status`
- `nginx.conf`：修正 `/GlassesBackstage/` 改為 `proxy_pass`（避免 WebSocket redirect 斷線）
- `DeviceMonitor.jsx`：管理後台裝置監控面板（2x2 卡片，3 秒輪詢）
- `AdminApp.jsx` + `Sidebar.jsx`：後台加入「裝置監控」選單項目

### 路徑結構說明
| 路徑 | 用途 | 保護 |
|------|------|------|
| `https://aiglasses.qzz.io/admin/` | 管理員後台 (React) | JWT 保護 |
| `https://aiglasses.qzz.io/device/N/` | 眼鏡 APP 連線 URL | **公開**（WebSocket 需要） |
| `https://aiglasses.qzz.io/api/` | Django REST API | 部分有 JWT |
| `https://aiglasses.qzz.io/api/devices/N/status` | 裝置狀態查詢 | **公開**（無 JWT） |
| `https://aiglasses.qzz.io/GlassesBackstage/` | 舊路徑，相容至裝置 1 | **公開** |

---

## 待實作：後台管理裝置 API URL

### 背景
- 目前 4 台裝置的 FastAPI URL（`/device/N/`）是固定在 nginx 設定中
- 希望管理員能在後台動態設定每台裝置的 APP 連線網址
- APP 啟動時從網站 API 取得對應的 server_url

### 計劃步驟

#### 1. Django：新增 DeviceConfig 模型
- 檔案：`Website/backend/content/models.py`
- 欄位：`device_id`（1~4）、`server_url`、`label`（裝置名稱）、`note`、`updated_at`
- 初始資料：4 筆，server_url 預設為 `/device/1/` ~ `/device/4/`

#### 2. Django API：新增端點
- 管理員讀寫：`GET/PUT /api/content/device-config/`（需 JWT）
- APP 讀取：`GET /api/content/device-config/<device_id>/`（公開，APP 啟動時呼叫）
- 檔案需修改：`content/serializers.py`、`content/views.py`、`content/urls.py`

#### 3. Admin UI：新增 DeviceConfig 管理頁面
- 新增檔案：`Website/frontend/src/admin/sections/DeviceConfig.jsx`
- 功能：顯示 4 台裝置的 URL，允許管理員修改
- 整合至 `AdminApp.jsx` 與 `Sidebar.jsx`

#### 4. Android APP：支援裝置編號
- 在 APP 設定中加入「裝置編號」欄位（1~4）
- `fetchServerConfigFromWebsite()` 改為帶入裝置編號，fetch 對應 URL
- 檔案：`Android/lib/providers/app_provider.dart`、`Android/lib/screens/home_screen.dart`

---

## Bug 修復記錄

### APP 導航無法啟動（已修復）

**症狀**：
- Debug 面板：攝影機 WS 未連線、音訊 WS 未連線、狀態機未初始化
- 按下避障導航按鈕：伺服器回「导航系统未就绪」，偶發 405 錯誤

**根本原因 1：WebSocket scheme 錯誤（constants.dart）**
- `_wsBase()` 在 `baseUrl = "https://..."` 且 `secure = false`（預設）時
- 產生 `ws://trycloudflare.com`（port 80），Cloudflare Tunnel 只接受 port 443（WSS）
- → 攝影機、音訊 WebSocket 全部連線失敗

**修復**：`Android/lib/core/constants.dart` `_wsBase()` 改為根據 `baseUrl` 本身的 scheme 決定 WS scheme
```dart
final wsSchemeToUse = cleanBase.startsWith('https://') ? 'wss' : 'ws';
return cleanBase.replaceFirst(RegExp(r'^https?://'), '$wsSchemeToUse://') + path;
```

**根本原因 2：Orchestrator 只在攝影機連線後才初始化（app_main.py）**
- NavigationMaster 只在第一幀攝影機畫面到來時初始化
- 攝影機 WS 斷線 → orchestrator 永遠是 None → 導航 API 無法使用

**修復**：`app_main.py` 新增 `_startup_init_navigators()`，在啟動時背景等待 YOLO 模型載入後直接初始化 orchestrator，不需等待攝影機連線。

---

### Docker Port 9999 無法綁定（已修復）

**症狀**：`docker compose up` 失敗，`Ports are not available: exposing port TCP 0.0.0.0:9999`

**原因**：Windows Hyper-V 保留了 9999 port，且 `docker-compose.yml` 重複 mapping（8080:80 和 9999:80 都指向 nginx:80）

**修復**：`Website/docker-compose.yml` 移除多餘的 `- "9999:80"` 行，只保留 `- "8080:80"`

---

## 後台管理 APP 伺服器設定（已實作）

管理員可在後台動態設定 AI 伺服器 URL，APP 啟動時自動讀取，不需手動填寫。

### 運作流程
1. 管理員登入 `https://aiglasses.qzz.io/admin/` → 左側「APP 伺服器設定」
2. 填入當次 Cloudflare Tunnel URL（例如 `https://xxxx.trycloudflare.com/GlassesBackstage/`）
3. APP 設定頁「網站 URL」填 `https://aiglasses.qzz.io`（只需設定一次）
4. APP 每次啟動自動呼叫 `GET /api/content/app-config/` 取得伺服器位址

### 相關檔案
- Django 模型：`Website/backend/content/models.py` `AppServerConfig`
- Django API：`Website/backend/content/admin_views.py` `AdminContentSectionView`（`app-config` section）
- React UI：`Website/frontend/src/admin/sections/ServerConfig.jsx`（新增）
- Flutter 讀取：`Android/lib/screens/splash_screen.dart` `fetchServerConfigFromWebsite()`

---

## 安全性待改善（選擇性）

### `/device/N/` 攝影機畫面仍然公開
- 問題：知道 URL 的人可直接看到即時攝影機畫面（如 `/device/1/speaker`）
- 根本原因：WebSocket 無法跟隨 HTTP redirect，路徑必須公開
- 解法（後續）：在 FastAPI 端的 viewer 頁面加入 token 驗證
  - APP 連線時附帶 token（query param）
  - nginx 對 `/device/N/speaker`、`/device/N/viewer` 等頁面要求 token

### `/api/devices/N/status` 無需登入即可查詢
- 問題：任何人可查詢裝置狀態（uptime、導航狀態等）
- 解法（後續）：在 nginx 或 Django 加一層 proxy 驗證
