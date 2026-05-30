# Yollo_E 快速部署指南

> 本指南說明如何在新電腦上快速部署 Yollo_E 辨識系統

---

## 目錄

- [環境準備](#環境準備)
- [快速安裝](#快速安裝)
- [啟動網頁伺服器](#啟動網頁伺服器)
- [使用 Tailscale VPN](#使用-tailscale-vpn)
- [行動裝置連線](#行動裝置連線)
- [故障排除](#故障排除)

---

## 環境準備

### 硬體需求

| 項目 | 最低需求 | 推薦配置 |
|------|----------|----------|
| CPU | 4核心 | 6核心以上 |
| RAM | 8GB | 16GB 以上 |
| GPU | 無 | NVIDIA RTX 3060 (6GB) |
| 儲存 | 10GB | 20GB 以上 |

### 軟體需求

- **Windows 10/11**
- **Python 3.10+**
- **Git**
- **uv** (Python 套件管理器，可選但推薦)

---

## 快速安裝

### 1. 安裝 uv (Python 套件管理器)

```powershell
# 使用 PowerShell 安裝 uv
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. 複製專案

```powershell
git clone <你的-repo-url> yollo_E
cd yollo_E
```

### 3. 安裝依賴

```powershell
# 使用 uv (推薦，快速)
uv sync

# 或使用傳統 pip
pip install -r requirements.txt
```

### 4. 設定環境變數

複製範例配置並修改：

```powershell
copy .env.example .env
notepad .env
```

必要設定：

```env
# 偵測類別 (用逗號分隔)
DETECTION_CLASSES=cell phone,bottle,cup,handbag,backpack,remote,mouse,keyboard,laptop,wallet,keys

# 模型路徑
MODEL_PATH=yoloe-26s-seg.pt

# 輕量模式 (低效能電腦)
USE_LIGHTWEIGHT_MODEL=false
FORCE_CPU=false

# ESP32 設定
ESP32_HOSTNAME=yollo
```

---

## 啟動網頁伺服器

### HTTP 模式 (區網內使用)

```powershell
# 基本模式
uv run python src/main.py --web

# 指定埠號
uv run python src/main.py --web --port 8080

# 輕量模式 (低效能電腦)
uv run python src/main.py --web --lightweight --cpu
```

### HTTPS 模式 (Cloudflare Tunnel / Dev Tunnel / 公網)

```powershell
# 啟用 HTTPS (自動生成自簽名證書)
uv run python src/main.py --web --ssl

# 指定埠號
uv run python src/main.py --web --ssl --port 8443
```

> **注意**: HTTPS 模式使用自簽名證書，瀏覽器會顯示安全警告，這是正常的。

### 可用參數

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `--web` | 啟動網頁伺服器 | - |
| `--ssl` | 啟用 HTTPS | false |
| `--host HOST` | 伺服器地址 | 0.0.0.0 |
| `--port PORT` | 連接埠 | 8080 |
| `--lightweight` | 使用輕量模型 (yolov8n.pt) | false |
| `--cpu` | 強制使用 CPU | false |
| `--confidence N` | 信心度門檻 (0-100) | 50 |

### 啟動成功訊息

伺服器啟動後會顯示：

```
============================================================
HTTPS 模式
============================================================
伺服器啟動中... 按 CTRL+C 停止

本地訪問: https://localhost:8080
區網訪問: https://192.168.x.x:8080
Tailscale: https://100.x.x.x:8080

API 端點:
  POST /api/detect/v2      - 物件檢測 API (推薦)
  WS   /ws/video            - 影像串流 (WS)
  WS   /ws/result           - 結果串流 (WS)
============================================================
```

---

## 使用 Tailscale VPN

### 為什麼使用 Tailscale？

- ✅ 無需複雜的端口轉發設定
- ✅ 端到端加密連線
- ✅ 支援所有裝置 (手機、平板、筆電)
- ✅ 穿透 NAT，無需路由器設定
- ✅ 免費方案支援 100 台裝置

### 安裝 Tailscale

1. **下載 Tailscale**:
   - Windows: https://tailscale.com/download/windows
   - Android: https://play.google.com/store/apps/details?id=com.tailscale.ipn
   - iOS: https://apps.apple.com/app/tailscale/id1475387342

2. **登入並啟動**:
   - 執行 Tailscale 應用程式
   - 使用 Google/Microsoft/GitHub 帳號登入
   - 確認狀態為「已連線」

3. **取得 Tailscale IP**:
   - Windows: 在 Tailscale 應用程式中查看
   - 格式類似: `100.x.x.x`

### 連線方式

1. **確保伺服器已啟動** (見上文啟動指令)

2. **在行動裝置上**:
   - 安裝 Tailscale 並登入同一帳號
   - 確認 Tailscale 狀態為「已連線」
   - 開啟瀏覽器訪問伺服器的 Tailscale IP

3. **輸入網址**:
   ```
   https://100.x.x.x:8080
   ```
   (將 `100.x.x.x` 替換為伺服器的 Tailscale IP)

> **重要**: 第一次訪問會有安全警告，點選「進階」→「繼續前往」

---

## 行動裝置連線

### 支援的連線方式

| 方式 | 適用場景 | 說明 |
|------|----------|------|
| 區網 IP | 同 WiFi 內 | `http://192.168.x.x:8080` |
| Tailscale | 異地連線 | `https://100.x.x.x:8080` |
| Cloudflare Tunnel | 公網部署 | `https://xxx.trycloudflare.com` |
| Dev Tunnel | 開發測試 | `https://xxx.devtunnels.ms` |

### 操作步驟

1. **開啟網頁**:
   - 輸入伺服器 URL
   - 允許相機權限

2. **開始偵測**:
   - 點選「開啟攝像頭」
   - 將物品對準鏡頭
   - 系統自動偵測並顯示結果

3. **查看日誌**:
   - 頁面底部有即時除錯面板
   - 顯示連線狀態和錯誤訊息

---

## 故障排除

### 無法連線到伺服器

**症狀**: 「網路連線失敗」或「Failed to fetch」

**檢查清單**:

1. **確認伺服器正在運行**:
   ```powershell
   # 檢查埠號是否被佔用
   netstat -an | findstr "8080"
   ```

2. **檢查防火牆**:
   ```powershell
   # Windows 防火牆 - 允許連接埠
   New-NetFirewallRule -DisplayName "Yollo Web Server" -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow
   ```

3. **確認伺服器監聽地址**:
   - 必須是 `0.0.0.0` 不是 `127.0.0.1`
   - 預設已設定為 `0.0.0.0`

4. **測試本地連線**:
   ```
   在伺服器電腦開啟: http://localhost:8080
   ```

### HTTPS 安全警告

**症狀**: 瀏覽器顯示「不安全的連線」

**解決方案**:
- 這是正常的！使用自簽名證書會有此警告
- 點選「進階」→「繼續前往」即可

### WebSocket 連線失敗

**症狀**: 頁面載入但偵測不工作，控制台顯示 WebSocket 錯誤

**可能原因**:
1. Dev Tunnel 不支援 WebSocket → 使用 Cloudflare Tunnel 或 Tailscale
2. 防火牆阻止 WebSocket 連接 → 檢查防火牆設定
3. 代理伺服器干擾 → 關閉代理測試

### 相機權限被拒絕

**症狀**: 「無法存取相機」

**解決方案**:
1. 檢查瀏覽器權限設定
2. 確保使用 HTTPS 或 localhost
3. 重新整理頁面並重新授權

### 模型載入失敗

**症狀**: 「模型載入失敗」或 CUDA 錯誤

**解決方案**:
```powershell
# 使用輕量模型
uv run python src/main.py --web --lightweight

# 強制使用 CPU
uv run python src/main.py --web --cpu
```

### 伺服器埠號被佔用

**症狀**: `[Errno 10048] error while attempting to bind on address`

**解決方案**:
```powershell
# 查找佔用進程
netstat -ano | findstr "8080"

# 終止進程 (替換 PID)
taskkill /F /PID <PID>

# 或使用不同埠號
uv run python src/main.py --web --port 9090
```

---

## 日誌位置

伺服器日誌儲存在 `logs/` 目錄：

```
logs/
├── web_server_20260317.log    # 今日日誌
├── web_server_20260316.log    # 昨日日誌
└── ...
```

日誌自動輪替，單檔最大 10MB，保留 7 天。

---

## 進階設定

### 自動啟動服務

使用 Windows Task Scheduler 開機自動啟動：

1. 開啟「工作排程器」
2. 建立「基本工作」
3. 觸發程序: 電腦啟動時
4. 動作: 啟動程式
   - 程式: `python.exe`
   - 引數: `src/main.py --web --ssl`
   - 起始目錄: `<專案路徑>`

### 自動重啟

使用批次檔自動重啟：

```batch
@echo off
:restart
uv run python src/main.py --web --ssl
goto restart
```

---

## 技術支援

遇到問題？檢查以下資源：

1. **查看日誌**: `logs/web_server_YYYYMMDD.log`
2. **檢查伺服器狀態**: 訪問 `/health` 端點
3. **測試 API**: 使用 Postman 或 curl 測試 `/api/detect/v2`
