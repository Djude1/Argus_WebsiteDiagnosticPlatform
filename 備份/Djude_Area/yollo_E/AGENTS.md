<!-- Generated: 2026-03-16 | Updated: 2026-03-16 -->

# yollo_E

## Purpose
YOLO 日常物品辨識系統 - 為視障人士設計的即時物體偵測系統。使用 ESP32 串流影像至筆電，透過 YOLOE-26 開放詞彙模型進行即時物品偵测，並透過語音回報偵測結果。

## Key Files

| File | Description |
|------|-------------|
| `README.md` | 項目說明文檔 |
| `CLAUDE.md` | AI 開發規範（語言規範、環境隔離、敏感資訊管理） |
| `pyproject.toml` | Python 專案配置，依賴套件管理 |
| `yoloe-26s-seg.pt` | YOLOE-26S 開放詞彙分割模型（約 29MB） |
| `.env.example` | 環境變數範本 |
| `使用說明.md` | 詳細使用指南（繁體中文） |
| `功能介紹與使用指南.md` | 功能介紹與使用指南 |
| `我的硬體配置.md` | 硬體配置說明 |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `src/` | Python 原始碼模組 |
| `data/` | 資料儲存目錄（資料庫、標註、圖片） |
| `models/` | 模型檔案存放處 |
| `scripts/` | 輔助腳本 |
| `yollo_E/` | ESP32 韌體程式碼（Arduino） |

## For AI Agents

### Working In This Directory
- 所有回覆使用 **繁體中文**
- 所有程式碼註釋使用 **繁體中文**
- Python 套件管理使用 `uv`（`uv add`、`uv run`）
- 敏感資訊（API Key、密碼、模型路徑）必須存放於 `.env`

### Project Architecture
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
                                                     │  │ 開放詞彙分割    │  │
                                                     │  └───────┬────────┘  │
                                                     │          │           │
                                                     │          ▼           │
                                                     │  ┌────────────────┐  │
                                                     │  │  SQLite 資料庫  │  │
                                                     │  └────────────────┘  │
                                                     └──────────────────────┘
```

### Common Patterns
- 使用 dataclasses 管理配置（`src/config.py`）
- 從 `.env` 讀取敏感資訊
- YOLOE 開放詞彙偵測：設定 `DETECTION_CLASSES` 環境變數
- mDNS 自動發現：`yollo.local` → ESP32 IP

## Dependencies

### External
- **ultralytics>=8.3.0** - YOLO 物件偵測框架
- **opencv-python>=4.9.0** - 影像處理
- **sqlalchemy>=2.0.0** - 資料庫 ORM
- **python-dotenv>=1.0.0** - 環境變數管理
- **requests>=2.31.0** - HTTP 請求
- **loguru>=0.7.0** - 日誌系統
- **pillow>=10.0.0** - 中文文字繪製

### Hardware
- XIAO ESP32-S3 Sense
- OV3660 攝影機
- NVIDIA RTX 3060 (6GB VRAM)

