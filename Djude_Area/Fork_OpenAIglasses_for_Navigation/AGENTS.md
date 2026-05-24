<!-- Generated: 2026-05-19 | Updated: 2026-05-19 -->

# Fork_OpenAIglasses_for_Navigation

## 用途

面向視障人士的智能導航與輔助系統。專案根目錄是 **Python AI 服務後端**（FastAPI），負責盲道導航、過馬路輔助、物品查找、即時語音互動。完整系統說明見 `README.md`，現況與決策記錄見 `MD/`。

> 詳細架構、模組職責、Port 對照、TTS 地雷請優先查閱 `arch` skill 與 `MD/系統介紹.md`、`MD/現況快照.md`。

## 核心模組（根目錄 Python）

| 檔案 | 功能 |
|------|------|
| `app_main.py` | FastAPI 主服務、WebSocket 路由、音視訊流分發、狀態協調（預設 `0.0.0.0:8081`） |
| `navigation_master.py` | 導航統領狀態機（IDLE/CHAT/BLINDPATH_NAV/CROSSING/TRAFFIC_LIGHT/ITEM_SEARCH）、模式切換、語音節流 |
| `workflow_blindpath.py` | 盲道偵測、避障、轉彎引導、Lucas-Kanade 光流穩定 |
| `workflow_crossstreet.py` | 斑馬線偵測、紅綠燈識別、對齊引導 |
| `yolomedia.py` | 物品偵測、手部引導、抓取確認（YOLO-E + ByteTrack + MediaPipe） |
| `asr_core.py` | 即時 ASR、VAD、指令解析（DashScope Paraformer） |
| `omni_client.py` | Qwen-Omni 串流語音生成 |
| `audio_player.py` / `audio_stream.py` / `audio_compressor.py` | 多路混音、TTS 播放、音量控制、串流 |
| `sync_recorder.py` | 音視訊同步錄製 |
| `bridge_io.py` | 執行緒安全的影格緩衝與分發 |
| `gemini_scene_describer.py` / `qwen_extractor.py` / `model_client.py` / `model_server.py` | 場景描述、標籤提取、模型推理服務 |
| `trafficlight_detection.py` / `crosswalk_awareness.py` / `obstacle_detector_client.py` | 紅綠燈/斑馬線/障礙物偵測 |
| `speaker_verifier.py` | 聲紋驗證 |
| `config.py` / `utils.py` | 全域設定與工具函式 |
| `esp32_simulator.py` / `local_device.py` / `start_multi_device.py` | 裝置模擬與多裝置啟動 |
| `generate_voice.py` / `prepare_voice_assets.py` / `compute_walk_embeddings.py` | 離線語音資產與嵌入產生 |
| `test_*.py` | ASR/語音指令/壓力測試 |

## 子系統

| 目錄 | 用途 |
|------|------|
| `Android/` | Flutter App，取代 ESP32 硬體的視障友善導航介面（見 `Android/AGENTS.md`） |
| `Website/` | 展示網站 Django 後端 + React 前端 + 管理後台（見 `Website/AGENTS.md`） |
| `MD/` | 專案規劃、現況快照、使用說明、規則導覽（見 `MD/AGENTS.md`） |
| `model/` | YOLO/YOLO-E/紅綠燈/手部偵測模型權重（未進 Git，從 ModelScope 下載） |
| `static/` / `templates/` | Web 監控介面靜態資源與模板（含 Three.js IMU 3D） |
| `voice/` / `voice_missing_log/` | 預生成語音檔與缺失語音 log |
| `compile/` | ESP32 韌體（`compile.ino`） |

## For AI Agents

### 在本目錄工作

- 所有回覆與程式碼註釋一律 **繁體中文**；嚴禁洩漏使用者個資
- Python 套件管理統一用 `uv`（`uv add` / `uv run`），禁止污染全域環境
- API Key / Token / 模型路徑一律放 `.env`，用 `python-dotenv` 讀取，禁止硬編碼
- 修改前先讀 `MD/現況快照.md` 確認專案現況；遵守 `CLAUDE.md` 行為準則（簡潔優先、精準修改）
- 大型 git/test/build 輸出用 RTK 包裝（見 `CLAUDE.md` RTK 規則）

### 測試要求

| 情境 | 驗證方式 |
|------|----------|
| Python 修改 | `uv run python -c "import 模組"` 或跑對應 `test_*.py` |
| API 端點 | 直打 API 確認回應；可用 `api-check` skill |
| TTS / Vertex AI | 用 `check` skill 的專屬測試 |
| 無法自動測試（實機/硬體） | 明確告知使用者需手動驗證項目清單 |

### 常見模式

- 狀態切換集中在 `navigation_master.py`；新增語音指令在 `app_main.py` 的指令解析處
- WebSocket 端點：`/ws/camera`、`/ws/viewer`、`/ws_audio`、`/ws_ui`、`/ws`、`/stream.wav`

## 相依

### 外部
- FastAPI / Uvicorn、Ultralytics YOLO、MediaPipe、OpenCV
- 阿里雲 DashScope（Paraformer ASR、Qwen-Omni-Turbo、Qwen-Turbo）
- Google Vertex AI / Gemini（場景描述、TTS，視設定）

<!-- MANUAL: 此線以下手動註記在重新產生時會保留 -->
