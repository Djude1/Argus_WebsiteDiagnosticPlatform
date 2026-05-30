<!-- Generated: 2026-03-14 | Updated: 2026-03-14 -->

# OpenAIDevice_For_VisualImpairment

## Purpose
An open-source IoT device project that integrates AI models (YOLO, Qwen-Omni, ASR) with ESP32 hardware (camera, microphone, IMU) to assist visually impaired people with navigation, obstacle detection, and object finding.

這是一個搭載開源人工智慧模型的IoT裝置（ESP32、麥克風、攝影機等），專為視障人士設計的開源專案。

## Key Files

| File | Description |
|------|-------------|
| `app_main.py` | FastAPI 主服務入口，處理所有 WebSocket 連接與狀態協調 |
| `navigation_master.py` | 導航統領器，管理整個系統的狀態機 (IDLE/CHAT/BLINDPATH_NAV/CROSSING/ITEM_SEARCH) |
| `workflow_blindpath.py` | 盲道導航工作流 (上盲道/導航中/轉彎/避障) |
| `workflow_crossstreet.py` | 過馬路導航工作流 (斑馬線偵測/方向對齊) |
| `yolomedia.py` | 物品查找工作流 (YOLO-E 檢測/MediaPipe 手部追蹤/光流追蹤) |
| `yoloe_backend.py` | YOLO-E 開放詞彙檢測後端 |
| `trafficlight_detection.py` | 紅綠燈檢測模組 (YOLO + HSV 備用) |
| `obstacle_detector_client.py` | 障礙物檢測客戶端 (白名單過濾/路徑掩碼檢測) |
| `asr_core.py` | 阿里雲 Paraformer ASR 實時語音識別 |
| `omni_client.py` | Qwen-Omni-Turbo 多模態對話客戶端 |
| `audio_player.py` | 統一的音頻播放管理 (TTS/多路混音/音量控制) |
| `audio_stream.py` | 音頻流管理 |
| `audio_compressor.py` | 音頻壓縮處理 |
| `bridge_io.py` | 線程安全的幀緩衝與分發 (生產者-消費者模式) |
| `sync_recorder.py` | 音視頻同步錄製 |
| `crosswalk_awareness.py` | 斑馬線感知模組 |
| `models.py` | 模型定義與數據結構 |
| `Dockerfile` | Docker 映像定義 |
| `docker-compose.yml` | Docker Compose 配置 |
| `hand_landmarker.task` | MediaPipe 手部追蹤模型 |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `.github/` | GitHub 配置 (Issue 模板、PR 模板) |
| `Djude_Area/` | 硬體與軟體開發區域 (ESP32 韌體、Camera Server、OCR) |
| `SmallLo's_Testing_Area/` | SmallLo 的測試區域 (FastAPI + YOLO + Dify Server) |
| `static/` | Web 前端靜態資源 (JS、CSS、3D 模型) |
| `templates/` | HTML 模板 |
| `music/` | 系統提示音 (導航方向語音) |
| `voice/` | 預錄語音檔案 |
| `YOLO_Module/` | YOLO 訓練模型與數據集 |
| `compile/` | ESP32 Arduino 編譯檔案 (IMU 驅動、Camera 配置) |
| `Zeng's_Testing_Area/` | Zeng 的測試區域 |

## For AI Agents

### Working In This Directory
- 主入口點: `python app_main.py` 啟動 FastAPI 服務 (port 8081)
- Docker 部署: `docker-compose up -d`
- 環境變數: 複製 `.env.example` 為 `.env` 並配置 API keys
- Python 依賴: 參考 `requirements.txt` 或各子目錄的 `pyproject.toml`

### Testing Requirements
- 單元測試位於各模組的 `tests/` 目錄
- YOLO 模型測試: 確保 `model/` 目錄下有必要模型檔案
- ESP32 連接測試: 驗證 WebSocket `/ws/camera` 和 `/ws_audio`

### Common Patterns
- 狀態機模式: `navigation_master.py` 管理系統狀態轉換
- 生產者-消費者模式: `bridge_io.py` 解耦視頻接收與處理
- 策略模式: 各 `workflow_*.py` 實現不同導航策略
- 觀察者模式: WebSocket 通信實現多客戶端訂閱

### Data Flow

**視頻流:**
```
ESP32-CAM → [JPEG] WebSocket /ws/camera → bridge_io → navigation_master → /ws/viewer → Browser
```

**音頻流 (上行):**
```
ESP32-MIC → [PCM16] /ws_audio → asr_core → DashScope ASR → AI 處理
```

**音頻流 (下行):**
```
Qwen-Omni/TTS → audio_player → audio_stream → HTTP /stream.wav → ESP32-Speaker
```

**IMU 數據流:**
```
ESP32-IMU → [JSON] UDP 12345 → WebSocket /ws → visualizer.js (Three.js)
```

## Dependencies

### Internal
- `navigation_master.py` → `workflow_blindpath.py`, `workflow_crossstreet.py`, `trafficlight_detection.py`
- `yolomedia.py` → `yoloe_backend.py`
- `app_main.py` → 所有模組

### External
- **FastAPI** - Web 框架
- **Uvicorn** - ASGI 伺服器
- **OpenCV** - 影像處理
- **Ultralytics** - YOLO 模型
- **MediaPipe** - 手部追蹤
- **DashScope SDK** - 阿里雲 ASR/TTS
- **NumPy** - 數值計算
- **Three.js** - 前端 3D 可視化

## Model Files Required

| Model | Path | Purpose |
|-------|------|---------|
| 盲道分割 | `model/yolo-seg.pt` | 盲道檢測 |
| YOLO-E 開放詞彙 | `model/yoloe-11l-seg.pt` | 開放詞彙檢測 |
| 物品識別 | `model/shoppingbest5.pt` | 物品識別 |
| 紅綠燈檢測 | `model/trafficlight.pt` | 紅綠燈狀態檢測 |
| 手部追蹤 | `hand_landmarker.task` | MediaPipe 手部模型 |

<!-- MANUAL: -->
