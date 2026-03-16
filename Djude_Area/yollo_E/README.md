# YOLO 日常物品辨識系統

> **硬體需求**: XIAO ESP32-S3 Sense + OV3660 攝影機 + NVIDIA RTX 3060 筆電

## 目錄

- [功能特色](#功能特色)
- [系統架構](#系統架構)
- [快速開始](#快速開始)
- [使用流程](#使用流程)
- [開放詞彙偵測](#開放詞彙偵測)
- [資料庫結構](#資料庫結構)
- [常見問題](#常見問題)
- [專案結構](#專案結構)

---

## 功能特色

### 核心功能

- **開放詞彙偵測**：使用 YOLOE-26 模型，可偵測任何物品，不限於預訓練類別
- **mDNS 自動發現**：ESP32 啟動後自動廣播 `yollo.local`，無需手動查 IP
- **即時物件辨識**：每秒 15-25 幀的即時偵測效能
- **ESP32 串流**：HTTP MJPEG 協議，低延遲影像傳輸
- **資料庫記錄**：SQLite 記錄辨識結果，支援查詢和統計
- **中英文標籤**：自動對應物品中文名稱

### YOLOE-26 模型特點

| 特性 | 說明 |
|------|------|
| 開放詞彙 | 可偵測任何物品，不限於 COCO 80 類 |
| 文字提示 | 透過環境變數設定要偵測的物品名稱 |
| 實例分割 | 同時輸出邊界框和分割遮罩 |
| 模型大小 | YOLOE-26S 約 29MB，適合 RTX 3060 |

---

## 系統架構

```
┌─────────────────────┐         HTTP MJPEG          ┌──────────────────────┐
│  XIAO ESP32-S3      │ ───────────────────────────>│    筆電 (Python)      │
│  + OV3660 攝影機     │    http://yollo.local/      │                      │
│                     │         /stream              │  ┌────────────────┐  │
│  - HTTP MJPEG 串流   │     (mDNS 自動發現)          │  │ ESP32 接收器    │  │
│  - WiFi 連線        │                              │  └───────┬────────┘  │
│  - mDNS 廣播        │                              │          │           │
└─────────────────────┘                              │          ▼           │
                                                     │  ┌────────────────┐  │
                                                     │  │ YOLOE-26 偵測器 │  │
                                                     │  │ (RTX 3060)     │  │
                                                     │  │ 開放詞彙分割    │  │
                                                     │  └───────┬────────┘  │
                                                     │          │           │
                                                     │          ▼           │
                                                     │  ┌────────────────┐  │
                                                     │  │  SQLite 資料庫  │  │
                                                     │  └────────────────┘  │
                                                     └──────────────────────┘
```

---

## 快速開始

### 環境需求

| 項目 | 規格 |
|------|------|
| Python | 3.10+ |
| GPU | NVIDIA RTX 3060 (6GB VRAM 以上) |
| ESP32 | XIAO ESP32-S3 Sense |
| 攝影機 | OV3660 |

### 安裝步驟

#### Step 1: 建立 Python 虛擬環境

```powershell
# 進入專案目錄
cd D:\GitHub_Project\yollo_E

# 建立虛擬環境
uv venv

# 啟動虛擬環境
.\.venv\Scripts\activate

# 安裝套件
uv sync
```

#### Step 2: 設定環境變數

在專案根目錄建立 `.env` 檔案：

```env
# WiFi 設定
WIFI_SSID=你的WiFi名稱
WIFI_PASSWORD=你的WiFi密碼

# ESP32 設定 (使用 mDNS 自動發現)
ESP32_HOSTNAME=yollo
# ESP32_IP=               # 可選，若 mDNS 失敗時可手動填入 IP

# 模型設定 - YOLOE-26 開放詞彙模型
MODEL_PATH=yoloe-26s-seg.pt

# 開放詞彙偵測類別（用逗號分隔，可自訂任何物品）
DETECTION_CLASSES=cell phone,bottle,cup,handbag,backpack,remote,mouse,keyboard,laptop,wallet,keys
```

#### Step 3: 下載 YOLOE-26 模型

首次執行時會自動下載模型，或手動下載：

```powershell
# 模型會在首次執行時自動下載到快取目錄
# YOLOE-26S 模型大小約 29MB
```

#### Step 4: 燒錄 ESP32

> **注意：** ESP32 程式已移至獨立專案目錄：`D:\ArduinoProjects\yollo_E\`

1. 開啟 Arduino IDE
2. 安裝 ESP32 開發板 (版本 3.3.6+)
3. 開啟 `D:\ArduinoProjects\yollo_E\yollo_E.ino`
4. 設定開發板：
   - Board: XIAO_ESP32S3
   - PSRAM: OPI PSRAM (必須開啟)
   - Flash Size: 8MB
5. 上傳程式
6. 開啟序列監視器 (115200 baud) 確認連線

**mDNS 自動發現：**

ESP32 啟動後會自動廣播 `yollo.local`，序列監視器會顯示：

```
WiFi connected!
mDNS responder started
Hostname: yollo.local
Stream URL: http://yollo.local/stream
```

---

## 使用流程

### 啟動辨識系統

```powershell
# 確保虛擬環境已啟動
.\.venv\Scripts\activate

# 使用 ESP32 串流（自動透過 mDNS 連接）
uv run python src/main.py --source esp32

# 使用本地 Webcam 測試
uv run python src/main.py --source webcam
```

### 命令列參數

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `--source` | 影像來源 (esp32/webcam) | esp32 |
| `--model` | 模型路徑 | yoloe-26s-seg.pt |
| `--custom` | 使用自定義模型 | False |
| `--confidence` | 信心度門檻 (0.0-1.0) | 0.5 |
| `--no-db` | 不儲存到資料庫 | False |
| `--save-images` | 儲存辨識圖片 | False |
| `--no-display` | 不顯示視窗 | False |

### 操作說明

| 按鍵 | 功能 |
|------|------|
| `q` | 結束程式 |
| `s` | 儲存當前畫面 |

---

## 開放詞彙偵測

### 功能說明

YOLOE-26 是 Ultralytics 的開放詞彙實例分割模型，可以偵測任何物品，不限於預訓練類別。

**傳統 YOLO 模型 vs YOLOE-26：**

| 傳統 YOLO 模型 | YOLOE-26 開放詞彙模型 |
|----------------|----------------------|
| 只能偵測 80 種 COCO 類別 | 可偵測任何物品 |
| 需要自定義訓練才能偵測新類別 | 直接輸入物品名稱即可 |
| 訓練需要大量標註資料 | 無需訓練，即開即用 |

### 使用方式

在 `.env` 檔案中設定 `DETECTION_CLASSES`：

```env
# 設定要偵測的物品（用逗號分隔）
DETECTION_CLASSES=cell phone,bottle,cup,handbag,backpack,remote,mouse,keyboard,laptop,wallet,keys
```

### 常用偵測類別

| 物品 | 英文名稱 |
|------|----------|
| 手機 | cell phone |
| 水瓶 | bottle |
| 杯子 | cup |
| 手提包/錢包 | handbag |
| 背包 | backpack |
| 遙控器 | remote |
| 滑鼠 | mouse |
| 鍵盤 | keyboard |
| 筆電 | laptop |
| 錢包 | wallet |
| 鑰匙 | keys |

> **提示：** YOLOE-26 的開放詞彙功能讓您無需進行自定義訓練即可偵測各種物品。只需將物品名稱加入 `DETECTION_CLASSES` 即可。

---

## 資料庫結構

### items 表 (物品記錄)

| 欄位 | 類型 | 說明 |
|------|------|------|
| id | INTEGER | 主鍵 |
| name | TEXT | 物品名稱（中文）|
| name_en | TEXT | 英文名稱 |
| category | TEXT | 分類 |
| confidence | REAL | 信心度 |
| class_id | INTEGER | YOLO 類別 ID |
| first_seen | DATETIME | 首次辨識時間 |
| last_seen | DATETIME | 最後辨識時間 |
| detection_count | INTEGER | 辨識次數 |

### 查詢範例

```python
from src.database.db_manager import DatabaseManager

db = DatabaseManager("data/database/items.db")

# 取得最近 50 筆記錄
recent = db.get_recent_items(50)

# 取得最常出現的物品
frequent = db.get_frequent_items(20)

# 取得統計資訊
stats = db.get_statistics()
```

---

## 常見問題

### Q1: ESP32 無法連接 WiFi

**解決方案：**
1. 確認 WiFi SSID 和密碼正確
2. 確認 ESP32 和筆電在同一網段
3. 檢查 WiFi 訊號強度

### Q2: mDNS 無法解析 yollo.local

**解決方案：**
1. 確認 Windows 已啟用 mDNS 功能
2. 檢查防火牆是否阻擋 mDNS 封包
3. 若仍無法使用，手動在 `.env` 填入 ESP32 IP：
   ```env
   ESP32_IP=192.168.1.xxx
   ```

### Q3: 串流延遲過高

**解決方案：**
1. 降低 ESP32 的影像解析度
2. 降低 JPEG 品質
3. 確保 WiFi 訊號良好

### Q4: YOLO 辨識速度慢

**解決方案：**
1. 確認使用 GPU (CUDA)
2. 確認 NVIDIA 驅動程式為最新版本
3. 降低影像解析度

### Q5: 無法辨識特定物品

**解決方案：**
1. 將物品名稱加入 `DETECTION_CLASSES`
2. 嘗試使用不同的英文描述詞
3. 若效果仍不佳，可考慮自定義訓練

---

## 專案結構

```
yollo_E/
├── .env                    # 環境配置
├── pyproject.toml          # Python 套件配置
├── README.md               # 本文檔
├── 功能介紹與使用指南.md    # 詳細使用指南
│
├── src/                    # Python 原始碼
│   ├── main.py            # 主程式入口
│   ├── config.py          # 配置管理
│   ├── camera/            # 攝影機模組
│   ├── detection/         # YOLO 辨識模組
│   ├── database/          # 資料庫模組
│   ├── training/          # 訓練模組
│   └── utils/             # 工具函式
│
├── data/                   # 資料目錄
│   ├── database/          # SQLite 資料庫
│   ├── saved_images/      # 儲存的截圖
│   └── datasets/          # 訓練資料集
│
└── models/                 # 模型檔案
    ├── pretrained/        # 預訓練模型
    └── custom/            # 自定義模型
```

**ESP32 程式位置：**
```
D:\ArduinoProjects\yollo_E\
├── yollo_E.ino            # ESP32 主程式
├── camera_pins.h          # GPIO 定義
└── config.h               # 配置
```

---

## 效能參考

| 指標 | RTX 3060 + YOLOE-26S |
|------|----------------------|
| FPS | 15-25 |
| 延遲 | 150-300ms |
| 辨識準確率 | 開放詞彙類別 > 80% |
| 記憶體使用 | < 4GB VRAM |
| 模型大小 | 約 29MB |

---

## 授權

MIT License

---

## 致謝

- [Ultralytics YOLO](https://github.com/ultralytics/ultralytics)
- [ESP32 Camera](https://github.com/espressif/esp32-camera)
- [OpenCV](https://opencv.org/)
