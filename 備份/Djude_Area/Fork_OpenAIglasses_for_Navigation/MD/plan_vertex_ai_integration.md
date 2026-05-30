# 計畫：切換至 Google Cloud 試用金方案

## 背景

目前 Gemini 走 AI Studio（GEMINI_API_KEY），不吃試用金。
測試結果顯示 Vertex AI 速度相當，可改走試用金節省 API Key 費用。

測試結論（2026-04-05）：

| 服務 | 現有方案 | 新方案 | 速度對比 |
|------|---------|--------|---------|
| STT | v1 串流（0.53s 暖機） | v2 Chirp_2（5.55s） | **維持 v1，不換** |
| Gemini 文字 | AI Studio Flash（8.68s） | Vertex AI Flash（8.16s） | 相當，換 |
| Gemini 場景描述 | AI Studio Flash+圖（10.12s） | Vertex AI Flash+圖（6.52s） | Vertex 更快，換 |
| TTS（導航提示） | Gemini TTS（4.81s） | Cloud TTS WaveNet（1.36s） | WaveNet 快 3.5x，換 |
| TTS（AI 對話） | Gemini TTS（4.81s） | — | 音質更自然，**保留** |

---

## 修改計畫

### 1. `omni_client.py` — Gemini Flash 改走 Vertex AI

**目前**：用 `urllib` 直接打 AI Studio HTTP API（`generativelanguage.googleapis.com`）

**改後**：改用 `google.genai.Client(vertexai=True)` SDK

需改動：
- 移除 `_GEMINI_KEYS` 輪換池（Vertex AI 用服務帳號，不需 API Key）
- 移除 `_gemini_request()` urllib 函式
- `_call_flash()` 改用 `client.models.generate_content()`
- `_call_flash_stream()` 改用 `client.models.generate_content_stream()`
- `_call_tts()` 保留 AI Studio（音質更自然，走 API Key）

注意：
- Vertex AI client 初始化需要 `GOOGLE_APPLICATION_CREDENTIALS` 環境變數
- 串流 TTS 並行邏輯不動，只換底層呼叫方式
- 備援機制維持

---

### 2. `gemini_scene_describer.py` — 場景描述改走 Vertex AI

**目前**：呼叫 `omni_client._call_flash()`，間接走 AI Studio

**改後**：改用 `google.genai.Client(vertexai=True)`，直接傳圖片 + 文字

需改動：
- `_worker()` 裡的 Gemini 呼叫改用 `genai.Client`
- 圖片傳法改為 `types.Part.from_bytes()`
- 移除對 `omni_client._call_flash` 的依賴

---

### 3. `audio_player.py` — 導航 TTS 改用 Cloud TTS WaveNet

**目前**：所有 TTS 都走 Gemini TTS（`omni_client._call_tts`）

**改後**：
- **導航提示**（短句，如「前方有斑馬線」）→ Cloud TTS WaveNet（1.36s，快）
- **AI 對話回覆**（由 omni_client 產生）→ 保留 Gemini TTS（音質更自然）

判斷依據：呼叫方是否來自 `omni_client`
- `omni_client.py` 內部的 `_call_tts()` 維持 Gemini TTS
- `audio_player.py` 的獨立 TTS（導航提示、系統訊息）改用 WaveNet

需改動：
- `audio_player.py` 新增 `_wavenet_tts(text)` 函式
- 判斷呼叫來源，導航提示走 WaveNet，對話回覆走原流程

WaveNet 參數：
- `language_code = "cmn-TW"`
- `name = "cmn-TW-Wavenet-A"`
- `sample_rate_hertz = 24000`（與現有 TTS 輸出格式一致）

---

## 相依套件確認

已確認安裝：
- `google-genai`（pyproject.toml 已有）
- `google-cloud-texttospeech`（pyproject.toml 已有）

新增環境變數（`.env`）：
```
GOOGLE_CREDENTIALS_PATH=./google_Speech_to_Text.json
GCP_PROJECT_ID=project-efbb5958-c7d2-47e8-86e
GCP_LOCATION=us-central1
```
（`GOOGLE_CREDENTIALS_PATH` 已有，`GCP_PROJECT_ID` / `GCP_LOCATION` 需確認是否已存在）

---

## 執行順序

1. 確認 `.env` 有 `GCP_PROJECT_ID` 與 `GCP_LOCATION`
2. 改 `omni_client.py`
3. 改 `gemini_scene_describer.py`
4. 改 `audio_player.py`
5. 執行 `uv run python app_main.py` 確認啟動無誤
6. 用 ESP32 模擬器測試語音對話與導航流程

---

## 回退方式

若 Vertex AI 出現問題，只需在 `.env` 加一行：
```
USE_VERTEX_AI=false
```
並在各模組加判斷切回 AI Studio（可在實作時加入此開關）。
