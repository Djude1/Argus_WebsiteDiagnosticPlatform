# yollo_E 本地伺服器部署指南

## 系統架構

```
┌─────────────────────┐         HTTP MJPEG          ┌──────────────────────┐
│  XIAO ESP32-S3      │ ──────────────────────────▶│    本地伺服器         │
│  + OV3660 攝影機     │    http://[伺服器IP]/      │                      │
│                     │         stream              │  ┌────────────────┐  │
│  - WiFi 連線        │                              │  │ YOLOE-26 偵測器 │  │
│  - mDNS 廣播        │                              │  │ (RTX 3060)     │  │
└─────────────────────┘                              │  └───────┬────────┘  │
                                                      │          │           │
                                                      │          ▼           │
                                                      │  ┌────────────────┐  │
                                                      │  │  SQLite 資料庫  │  │
                                                      │  └────────────────┘  │
                                                      └──────────────────────┘
```

## 部署步驟

### 1. 伺服器端設定（運行 YOLO 的電腦）

#### 1.1 環境準備

```powershell
# 確保安裝 Python 3.10+
python --version

# 安裝 uv (如果還沒安裝)
# Windows:
irm https://astral.sh/uv/install.ps1 | iex

# 或者使用 winget
winget install astral-sh.uv
```

#### 1.2 複製專案

```powershell
# 複製或拷貝 yollo_E 資料夾到伺服器
# 假設複製到 D:\GitHub_Project\yollo_E

cd D:\GitHub_Project\yollo_E

# 建立虛擬環境
uv venv

# 啟動虛擬環境
.\.venv\Scripts\activate

# 安裝依賴
uv sync
```

#### 1.3 配置環境變數

建立 `.env` 檔案：

```env
# WiFi 設定（ESP32 連線的 WiFi）
WIFI_SSID=你的WiFi名稱
WIFI_PASSWORD=你的WiFi密碼

# ESP32 設定
# 如果 ESP32 和伺服器在同一網段，可以留空
# 如果需要從外部訪問，可能需要設定固定 IP
ESP32_HOSTNAME=yollo
# ESP32_IP=               # 可選，若 mDNS 失敗時可手動填入 IP

# 模型設定
MODEL_PATH=yoloe-26s-seg.pt

# 開放詞彙偵測類別
DETECTION_CLASSES=cell phone,bottle,cup,handbag,backpack,remote,mouse,keyboard,laptop,wallet,keys

# 伺服器網路設定（可選）
# SERVER_HOST=0.0.0.0
# SERVER_PORT=8000
```

#### 1.4 測試執行

```powershell
# 測試 webcam 來源
uv run python src/main.py --source webcam

# 測試 ESP32 來源
uv run python src/main.py --source esp32
```

---

### 2. ESP32 端設定

#### 2.1 更新 WiFi 設定

編輯 `yollo_E/config.h`，確保 WiFi 設定與伺服器所在的網路一致：

```cpp
// yollo_E/config.h
#define WIFI_SSID "你的WiFi名稱"
#define WIFI_PASSWORD "你的WiFi密碼"
```

#### 2.2 重新燒錄 ESP32

使用 Arduino IDE 重新上傳程式到 ESP32。

---

### 3. 網路配置（重要）

#### 選項 A：同一網段（推薦）

確保 ESP32 和伺服器連接到**同一個 WiFi 路由器**：

```
[WiFi 路由器]
    ├── [ESP32] ──192.168.1.100
    └── [伺服器 PC] ──192.168.1.200
```

在 `.env` 中設定：
```env
ESP32_HOSTNAME=yollo
```

#### 選項 B：不同網段（需要端口轉發）

如果 ESP32 在另一個網段，需要在路由器上設定端口轉發：

```
[路由器 A] ──網際網路── [路由器 B]
  │                              │
[ESP32]                    [伺服器 PC]
```

---

### 4. 防火牆設定

如果伺服器無法連接 ESP32，檢查 Windows 防火牆：

```powershell
# 允許 Python 通過防火牆
netsh advfirewall firewall add rule name="yollo_E" dir=in action=allow program="C:\Python\python.exe"

# 或者直接關閉防火牆（不推薦）
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False
```

---

### 5. 執行腳本（可選：建立開機啟動）

#### Windows

建立批次檔 `start_yollo.bat`：

```batch
@echo off
cd /d D:\GitHub_Project\yollo_E
call .venv\Scripts\activate.bat
uv run python src/main.py --source esp32
pause
```

然後放到啟動資料夾：
```powershell
shell:startup
```

---

## 常見問題

### Q1: ESP32 無法連接到伺服器

**解決方案：**
1. 確認 ESP32 和伺服器在同一 WiFi 網段
2. 確認伺服器 IP：`ipconfig`（CMD）
3. 在瀏覽器測試：`http://[ESP32_IP]/stream`

### Q2: 伺服器上的 YOLO 偵測速度慢

**解決方案：**
1. 確認使用 GPU：`uv run python -c "import torch; print(torch.cuda.is_available())"`
2. 降低解析度：修改 `config.py` 中的 `FRAME_WIDTH`/`FRAME_HEIGHT`
3. 使用更小的模型：如 YOLOE-8S

### Q3: 需要從外部網路訪問

**解決方案：**
1. 使用 VPN 連線到家中網路
2. 使用 DDNS 服務（如 no-ip）
3. 設定路由器端口轉發

---

## 效能優化

| 設定 | 建議值 |
|------|--------|
| 伺服器 GPU | RTX 3060 或更高 |
| WiFi 頻段 | 5GHz（减少延遲） |
| 解析度 | 640x480 |
| JPEG 品質 | 10-15 |
| 目標 FPS | 15-25 |
