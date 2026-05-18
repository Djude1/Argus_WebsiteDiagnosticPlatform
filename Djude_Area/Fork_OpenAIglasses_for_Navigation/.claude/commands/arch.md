---
allowed-tools: Read
description: 系統架構、模組職責、Port 對照、TTS 地雷速查
---

## 啟動方式

```bash
uv run python start_multi_device.py         # 正式啟動（4 台，port 8081～8084）
uv run python start_multi_device.py --count 2  # 指定台數
cd Website && docker compose up --build     # 網站 port 8888
```

> ⚠️ **禁止**用 `app_main.py` 當正式啟動指令，那是單機開發用途。

## YOLO 模型分工（model/ALL.pt）

| 功能 | PT 檔案 | 用到的 class |
|------|---------|-------------|
| 盲道分割 | `model/ALL.pt` | 8=guide_bricks, 9=crossing_crosswalk |
| 障礙物偵測 | `model/ALL.pt` | 0~7（person/bicycle/car 等）|
| 紅綠燈偵測 | `model/ALL.pt` | 10=crossing_green_light, 11=crossing_red_light |
| 物品尋找 | `model/shoppingbest5.pt` | 獨立（yolomedia.py 按需載入）|

所有模型由 `model_server.py`（port 9099）集中載入一次，4 台 app_main 共用。
相同路徑的 .pt 只載入一次（共用 VRAM + 共用推論鎖）。

## Port 分工

| Port | 用途 |
|------|------|
| 8888 | nginx 網站入口（Docker）|
| 8081～8084 | FastAPI 各裝置 instance |
| 12345 UDP | ESP32 IMU 資料 |

## 核心模組

| 檔案 | 職責 |
|------|------|
| `app_main.py` | FastAPI 入口、WebSocket 路由、模型初始化 |
| `navigation_master.py` | 全域狀態機、process_frame() 派發 |
| `omni_client.py` | Gemini Flash 串流 + TTS（Vertex AI 優先，AI Studio 備援）|
| `audio_player.py` | 音訊播放、WaveNet TTS fallback |
| `asr_core.py` | Google STT 串流（待機/主動雙模式）|
| `bridge_io.py` | WebSocket ↔ AI 推理執行緒安全緩衝 |

## AI 服務分工

| 功能 | 服務 |
|------|------|
| ASR | Google Speech-to-Text 串流 |
| 語音對話 + 場景描述 | Gemini 2.5 Flash（Vertex AI 優先）|
| 導航 TTS | WaveNet（cmn-TW-Wavenet-A）|
| 對話 TTS | Gemini TTS（gemini-2.5-flash-preview-tts）|
| 盲道/障礙/紅綠燈 | 本地 YOLO 模型（model/ALL.pt）|

## Android APP 語音架構（三層優先順序）

```
Layer 1：LocalVoiceService（assets/audio/ + voice_map.json）
  ├── 儲存位置：APK 內部（不會被清除）
  ├── 預錄 WAV 打包進 APK，命中即播，零延遲
  └── 未命中 ↓

Layer 2：VoiceCacheService（flutter_tts 合成 → 手機暫存目錄）
  ├── 儲存位置：手機的 getTemporaryDirectory()（系統清快取時消失，下次啟動重新合成）
  ├── 首次啟動預合成固定語句（14 句），後續直接播 WAV，零延遲
  └── 未命中 ↓

Layer 3：/stream.wav HTTP 串流（伺服器端 Gemini TTS / WaveNet 合成）
  ├── AudioService.playStreamWav() 持續連線，中斷自動重連（0.8s）
  └── suppressStreamFor(ms)：本地語音播放時靜音串流，避免重疊
```

> Layer 1/2 的「本機」= **手機本身**，不是伺服器。

**重點**：APP 端優先走本地語音，盡量不依賴網路 TTS 延遲。

## TTS 地雷

- Gemini TTS ≤4 字短句/問句 → 400
- Gemini TTS 不支援 systemInstruction → 500
- **短句播報必須走 WaveNet**
- APP 新增固定語句 → 必須同步加進 `VoiceCacheService._phrases` 或錄 WAV 加進 `assets/audio/`

## Vertex AI 備援

`USE_VERTEX_AI=true` → 先走 Vertex，配額耗盡自動切回 AI Studio 16-Key 輪換
