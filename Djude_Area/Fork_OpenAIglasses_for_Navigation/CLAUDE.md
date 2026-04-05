# CLAUDE.md

本文件用於指引 Claude Code（claude.ai/code）在本倉庫中進行程式開發時的行為規範。

## 工作規則（必須遵守）

* **語言**：所有回覆與程式碼註解一律使用繁體中文
* **環境隔離**：任何會影響套件或環境變數的操作（pip install、uv add 等），必須在虛擬環境（`.venv`）或 Docker 容器內執行，禁止污染系統環境
* **重點整理**：請每次都將討論出來的重點或是想法，放置到idea.md當中，來為了保證使用者不會忘記他當初的想法，或是需要修改的東西

## 專案概覽

本專案為 AI 智慧眼鏡系統，主要服務視障輔助導航。系統提供即時盲道導航、斑馬線過馬路輔助、物品尋找與語音互動功能。系統架構為 Python FastAPI 伺服器，並透過 WebSocket 與基於 ESP32 的穿戴裝置進行通訊。

**重要**：模型檔案未包含在倉庫中。請從以下網址下載模型並放置於 `model/` 目錄：

https://www.modelscope.cn/models/archifancy/AIGlasses_for_navigation

## 系統運行方式

```bash
# 啟動主應用程式（FastAPI，埠號 8081）
python app_main.py

# 存取監控頁面
# http://localhost:8081
```

## 開發環境設定 這裡記得都要用uv


```bash
# 使用 uv 安裝依賴（推薦，會使用 pyproject.toml 中的 CUDA index）
uv sync

# 或使用 pip
pip install -r requirements.txt

# 若需要 GPU 支援（CUDA 11.8），請先單獨安裝 PyTorch：
pip install torch==2.0.1+cu118 torchvision==0.15.2+cu118 --index-url https://download.pytorch.org/whl/cu118
```

**必須使用 Python 3.11**（pyproject.toml 已限制 `>=3.11`）

## 環境變數設定

請在專案根目錄建立 `.env`：

```env
DASHSCOPE_API_KEY=sk-xxxxx   # 必填：阿里雲 DashScope，用於 ASR 與 Qwen-Omni

# 可選覆寫參數（下方為預設值）
BLIND_PATH_MODEL=model/yolo-seg.pt
OBSTACLE_MODEL=model/yoloe-11l-seg.pt
YOLOE_MODEL_PATH=model/yoloe-11l-seg.pt
AIGLASS_MASK_MIN_AREA=1500
TTS_INTERVAL_SEC=1.0
ENABLE_TTS=true
```

## 單元模組測試方式

```bash
python test_cross_street_blindpath.py  # 盲道導航測試
python test_traffic_light.py           # 紅綠燈偵測測試
python test_recorder.py                # 錄音功能測試
python test_crosswalk_awareness.py     # 斑馬線偵測測試
```

## Docker 使用方式

```bash
docker compose up --build
```

## 系統架構

### 分層概覽

```
ESP32 裝置（韌體：compile/compile.ino）
    |-- 視訊：WebSocket /ws/camera -> JPEG影格
    |-- 音訊上行：WebSocket /ws_audio -> PCM16
    |-- IMU：UDP port 12345 -> JSON
    |-- 音訊下行：HTTP GET /stream.wav -> WAV

Python 伺服器（app_main.py - FastAPI）
    |-- NavigationMaster（navigation_master.py）- 狀態機核心
    |   |-- BlindPathNavigator（workflow_blindpath.py）
    |   |-- CrossStreetNavigator（workflow_crossstreet.py）
    |   |-- TrafficLightDetection（trafficlight_detection.py）
    |-- YoloMedia（yolomedia.py）- 物品搜尋模組
    |-- ASR（asr_core.py）-> DashScope Paraformer
    |-- OmniClient（omni_client.py）-> Qwen-Omni-Turbo
    |-- AudioPlayer（audio_player.py）- TTS 與混音控制
    |-- BridgeIO（bridge_io.py）- 執行緒安全影格緩衝區
```

### 狀態機（NavigationMaster）

`IDLE` -> `CHAT` | `BLINDPATH_NAV` | `CROSSING` | `ITEM_SEARCH` | `TRAFFIC_LIGHT_DETECTION`

`BLINDPATH_NAV` 子狀態：
`ONBOARDING`（旋轉／平移校正） ->
`NAVIGATING` ->
`MANEUVERING_TURN` / `AVOIDING_OBSTACLE`

`CROSSING` 子狀態：
`SEEKING_CROSSWALK` ->
`WAIT_TRAFFIC_LIGHT` ->
`CROSSING` ->
`SEEKING_NEXT_BLINDPATH`

### 主要資料流

**影像流程**：
`bridge_io.push_raw_jpeg()` → 導航處理 →
`bridge_io.send_vis_bgr()` → WebSocket 廣播給監控端

**語音上行流程**：
ESP32 麥克風 → `/ws_audio` →
`asr_core.py` → DashScope ASR →
`start_ai_with_text_custom()`（位於 app_main.py）

**語音下行流程**：
Qwen-Omni / TTS →
`audio_player.py` →
`audio_stream.py` →
`/stream.wav` → ESP32 喇叭

### 核心模組職責

| 檔案                        | 功能                                           |
| ------------------------- | -------------------------------------------- |
| `app_main.py`             | FastAPI 進入點、WebSocket 路由、模型初始化與協調控制          |
| `navigation_master.py`    | 全域狀態機；負責 `process_frame()` 任務派發              |
| `workflow_blindpath.py`   | YOLO分割 + Lucas-Kanade 光流導航                   |
| `workflow_crossstreet.py` | 斑馬線幾何與紅綠燈狀態判斷                                |
| `yolomedia.py`            | YOLO-E 開放詞彙偵測 + MediaPipe 手部追蹤               |
| `bridge_io.py`            | WebSocket 收發與 AI 推理之間的執行緒安全緩衝                |
| `nemotron_vision.py`      | 使用 OpenRouter 呼叫 NVIDIA Nemotron VLM（場景描述備援） |
| `qwen_extractor.py`       | 將中文語音指令轉換為 YOLO 英文標籤                         |

### ESP32 韌體（compile/compile.ino）

目標為 **Seeed Studio XIAO ESP32S3**。主要硬體介面：

* 攝影機：DVP（XCLK=10，SIOD=40，SIOC=39）
* 麥克風：PDM（CLK=42，DAT=41）
* 喇叭：I2S → MAX98357A（BCLK=7，LRCK=8，DIN=9）
* IMU：SPI → ICM42688（SCK=D0，MOSI=D1，MISO=D2，CS=D3）

若使用其他 ESP32 開發板，腳位對應請參考 `compile/camera_pins.h`。

### 新增語音指令方式

語音指令由 `start_ai_with_text_custom()`（位於 app_main.py）處理。
若要新增指令，請在 Qwen-Omni 後備流程之前加入關鍵字判斷。

狀態切換透過 `NavigationMaster` 方法觸發，例如：

* `start_blind_path_navigation()`
* `start_crossing()`

### 模型檔案需求

請將下列模型放入 `model/` 目錄：

* `yolo-seg.pt` — 盲道分割模型
* `yoloe-11l-seg.pt` — 開放詞彙物件偵測模型
* `shoppingbest5.pt` — 物品識別模型
* `trafficlight.pt` — 紅綠燈偵測模型
* `hand_landmarker.task` — Google MediaPipe 手部偵測模型
