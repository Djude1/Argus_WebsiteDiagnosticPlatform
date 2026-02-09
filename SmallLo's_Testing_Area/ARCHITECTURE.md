# SmallLo's Testing Area - ESP32 + YOLO + Dify Server

## Context

本專案在 `SmallLo's_Testing_Area/` 中建構視障輔助系統。目標是建立一個 FastAPI 伺服器：
1. 從 ESP32 (XIAO ESP32S3) 接收攝影機畫面
2. 使用 YOLO (yolo11n.pt) 進行即時障礙物/導航偵測
3. 將偵測結果傳送至 Dify 進行自動化工作流程處理
4. 將多個模型串聯成完整的 Pipeline

架構參考 `OpenAIglasses_for_Navigation`，但經過簡化並新增 Dify 整合。

---

## System Architecture

```
┌─────────────────┐     MJPEG/HTTP      ┌──────────────────────────────────┐
│   ESP32-CAM     │ ──────────────────→  │     FastAPI Server (port 8081)   │
│  XIAO ESP32S3   │                      │                                  │
│  OV2640 Camera  │                      │  frame_capture.py                │
└─────────────────┘                      │    ↓ cv2.VideoCapture            │
                                         │  bridge_io.py                    │
                                         │    ↓ push_raw_jpeg → deque       │
                                         │  yolo_detector.py                │
                                         │    ↓ YOLO inference (yolo11n.pt) │
                                         │  pipeline.py                     │
                                         │    ↓ Context Analysis            │
                                         │  dify_client.py                  │
                                         │    ↓ Dify Workflow API            │
                                         │  Response Dispatch               │
                                         └───────────┬────────────────┬─────┘
                                                     │                │
                                              WS /ws/viewer    WS /ws/detections
                                                     │                │
                                              ┌──────▼────────────────▼─────┐
                                              │   Browser Dashboard         │
                                              │   (index.html + main.js)    │
                                              │   - Live video with boxes   │
                                              │   - Detection results       │
                                              │   - FPS & latency           │
                                              └────────────────────────────┘
```

---

## Directory Structure

```
SmallLo's_Testing_Area/
├── ARCHITECTURE.md          # This file
├── server/
│   ├── app_main.py          # FastAPI entry point, WebSocket handlers, lifecycle
│   ├── config.py            # Centralized settings (env vars)
│   ├── bridge_io.py         # Thread-safe frame buffer (producer-consumer)
│   ├── frame_capture.py     # MJPEG HTTP pull from ESP32
│   ├── yolo_detector.py     # YOLO inference wrapper
│   ├── dify_client.py       # Dify API integration (Phase 2)
│   ├── pipeline.py          # Model chaining orchestrator (Phase 3)
│   ├── models.py            # Data models (Detection, DetectionResult, etc.)
│   ├── requirements.txt     # Python dependencies
│   ├── .env.example         # Environment variable template
│   └── static/
│       ├── index.html       # Monitoring dashboard
│       └── main.js          # WebSocket viewer client
└── tests/
    ├── test_yolo_inference.py
    └── test_image.jpg
```

---

## Implementation Phases

### Phase 1: Core Server (優先)

#### Step 1.1 - 專案骨架
- 建立目錄結構
- `requirements.txt`: fastapi, uvicorn[standard], opencv-python, numpy, ultralytics, python-dotenv, httpx
- `.env.example` 環境變數模板
- `config.py` 集中設定管理

#### Step 1.2 - bridge_io.py (幀緩衝)
改編自參考專案的 bridge_io.py (93行)：
- `deque(maxlen=4)` + `threading.Condition` 實現執行緒安全的幀緩衝
- `push_raw_jpeg(jpeg_bytes)` - 擷取執行緒推送幀
- `wait_raw_bgr(timeout_sec)` - 推理執行緒拉取並解碼為 BGR
- `send_vis_bgr(bgr, quality)` - 將標註後的幀推送給 Viewer
- `set_sender(cb)` - 註冊 WebSocket 廣播回呼

#### Step 1.3 - frame_capture.py (ESP32 擷取)
基於現有的 Yolo_Server/main.py 模式：
- 背景執行緒使用 `cv2.VideoCapture(url)` 從 ESP32 拉取 MJPEG
- 串流失敗時自動重連
- 每一幀 → `bridge_io.push_raw_jpeg()`

#### Step 1.4 - models.py (資料模型)
- `Detection`: class_name, confidence, bbox, center_x, center_y, area_ratio
- `DetectionResult`: timestamp, frame_size, detections list, inference_time_ms

#### Step 1.5 - yolo_detector.py (YOLO 推理)
- 載入 `yolo11n.pt`，GPU 加速 (CUDA) 或 CPU 降級
- 啟動時暖機推理
- `detect(bgr, conf=0.25) -> DetectionResult`
- 繪製偵測框和標籤

#### Step 1.6 - app_main.py (FastAPI 伺服器)

**API Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | 監控儀表板 |
| GET | `/api/health` | 健康檢查 |
| GET | `/api/detections` | 最新偵測結果 (JSON) |
| WS | `/ws/viewer` | 瀏覽器接收標註後的 JPEG 幀 |
| WS | `/ws/detections` | 即時偵測結果 JSON 串流 |

**啟動流程:**
1. 設定 Windows 事件迴圈策略 (`WindowsSelectorEventLoopPolicy`)
2. 載入 YOLO 模型
3. 啟動 MJPEG 擷取背景執行緒
4. 啟動推理背景執行緒 (frame → YOLO → 標註 → 廣播)
5. 註冊 bridge_io sender callback

**推理迴圈** (背景執行緒):
```python
while running:
    bgr = bridge_io.wait_raw_bgr()
    detections = yolo_detector.detect(bgr)
    annotated = draw_detections(bgr, detections)
    bridge_io.send_vis_bgr(annotated)
    publish_detections(detections)  # → /ws/detections
```

#### Step 1.7 - static/index.html + main.js
- 連接 `ws://host:8081/ws/viewer`，將 JPEG 幀渲染在 Canvas 上
- 連接 `ws://host:8081/ws/detections`，顯示偵測清單
- 顯示 FPS 和推理延遲

---

### Phase 2: Dify Integration (Dify 整合)

#### Step 2.1 - dify_client.py
- `DifyClient` 類別，`run_workflow(detections, image_b64)` 方法
- 呼叫 Dify Workflow API: `POST {base_url}/workflows/run`
- `DifyThrottler`: 每 N 秒或偵測結果有顯著變化時才呼叫 Dify

#### Step 2.2 - 整合至 app_main.py
- 新增 async Dify 任務：從偵測佇列讀取，節流後呼叫 Dify
- 透過 `/ws/detections` 發布 Dify 回應

---

### Phase 3: Model Chaining (模型串聯)

#### Step 3.1 - pipeline.py
Pipeline 階段:
```
Frame → YOLO Detection → Context Analysis (本地規則) → Dify Workflow (LLM) → Response
```

- `ContextAnalyzer`: 本地規則引擎，將偵測結果分類為導航情境 (obstacle_ahead, clear_path, crosswalk_detected, danger levels)
- `Pipeline`: 編排器，連接所有階段，管理模型間的資料流

---

## Key Reference Files

| 參考檔案 | 用途 |
|---------|------|
| `OpenAIglasses_for_Navigation/bridge_io.py` | 執行緒安全幀緩衝模式 (deque + Condition) |
| `OpenAIglasses_for_Navigation/app_main.py` | FastAPI WebSocket、YOLO 載入、Viewer 廣播 |
| `Hardware/34/CameraWebServer_34/Yolo_Server/main.py` | MJPEG HTTP 拉取模式 |
| `YOLO_Module/YOLO_Traine_Model/yolo11n.pt` | YOLO 模型檔案 |

---

## Verification (驗證)

1. 載入 yolo11n.pt，對測試圖片推理，確認偵測結果
2. 驗證 `cv2.VideoCapture(esp32_url)` 可開啟並讀取幀
3. 啟動 `uvicorn app_main:app --port 8081`，檢查 `/api/health` 回應 OK
4. 開啟瀏覽器至 `http://localhost:8081`，確認即時影像含 YOLO 偵測框
5. (Phase 2) 傳送偵測結果至 Dify，驗證工作流程回應
6. (Phase 3) 驗證 Frame → YOLO → Context → Dify → Response 完整流程

---

## Quick Start

```bash
cd SmallLo's_Testing_Area/server
pip install -r requirements.txt
cp .env.example .env  # Edit with your ESP32 IP and Dify settings
python -m uvicorn app_main:app --host 0.0.0.0 --port 8081
```
