# 想法與待實作項目

## 日/夜模式切換功能（2026-03-30）

### 重點決策
- 使用 Tailwind `darkMode: 'class'` 策略
- 預設跟隨系統 `prefers-color-scheme`
- 使用者手動切換後存入 localStorage，不再跟隨系統
- 亮色模式使用暖色品牌色（橘/金色 warm 色板），暗色模式維持原有品牌藍
- 切換按鈕在 Navbar 右側（太陽/月亮圖示）
- FOUC 防護：main.jsx 渲染前立即初始化 `<html>` class

### 涉及檔案
- ThemeContext.jsx（新增）
- main.jsx、App.jsx、tailwind.config.js、index.css（基礎建設）
- Navbar、Footer、FloatingCart（元件）
- Home、Product、Purchase、PurchaseResult、Team、Download、Project、Announcements（頁面）

## 多裝置架構（已實作）

### 已完成
- `start_multi_device.py`：同時啟動 4 個獨立 FastAPI 進程（port 8081~8084）
  - 啟動指令：`uv run python start_multi_device.py`
  - 只啟動 N 台：`uv run python start_multi_device.py --count 2`
  - Ctrl+C 一次關閉全部
- `nginx.conf`：新增 `/device/1/` ~ `/device/4/` 路由，各自代理至對應 FastAPI
- `nginx.conf`：新增 `/api/devices/N/status` 直通各裝置 `/api/debug_status`
- `nginx.conf`：修正 `/GlassesBackstage/` 改為 `proxy_pass`（避免 WebSocket redirect 斷線）
- `DeviceMonitor.jsx`：管理後台裝置監控面板（2x2 卡片，3 秒輪詢）
- `AdminApp.jsx` + `Sidebar.jsx`：後台加入「裝置監控」選單項目

### 路徑結構說明
| 路徑 | 用途 | 保護 |
|------|------|------|
| `https://aiglasses.qzz.io/admin/` | 管理員後台 (React) | JWT 保護 |
| `https://aiglasses.qzz.io/device/N/` | 眼鏡 APP 連線 URL | **公開**（WebSocket 需要） |
| `https://aiglasses.qzz.io/api/` | Django REST API | 部分有 JWT |
| `https://aiglasses.qzz.io/api/devices/N/status` | 裝置狀態查詢 | **公開**（無 JWT） |
| `https://aiglasses.qzz.io/GlassesBackstage/` | 舊路徑，相容至裝置 1 | **公開** |

---

## 公網部署已知問題與修復紀錄（2026-05-03）

### 症狀
APP 在本地測試正常，連公網（`aiglasses.qzz.io`）後開啟避障時畫面卡在「等待 YOLO 影像串流…」。

### 根因
`websocket_service.dart` 的 viewer WS（`/ws/viewer`）沒有重連機制：
```dart
onError: (_) {},  // 靜默吞掉錯誤
onDone:  () {},   // 斷線不重連
```
公網比本地更容易出現連線抖動、Cloudflare Tunnel timeout，viewer WS 斷一次就永遠不重連，畫面永遠沒有 frame。

**相比之下 camera WS（`/ws/camera`）有正確的重連邏輯，所以導航指令不受影響，只有畫面不顯示。**

### 修復（commit 含在此 push）
`Android/lib/services/websocket_service.dart`：
- 新增 `_viewerActive` flag（確保 `disconnectViewer` 後不再重連）
- 新增 `_viewerOnFrame` 儲存 callback（重連後繼續用）
- `onError` / `onDone` 改為 `_scheduleReconnect(_doConnectViewer)`（3 秒後自動重連）

### 公網部署注意事項（Cloudflare Tunnel）
| 項目 | 說明 |
|------|------|
| APP 伺服器位址 | `https://aiglasses.qzz.io/device/N/`，啟用 **secure = true**（使用 wss://） |
| WebSocket 路徑 | nginx 需設 `proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";` |
| viewer WS 重連 | 已修復，斷線 3 秒後自動重連 |
| camera WS 重連 | 原本即有，無問題 |
| 已知限制 | Cloudflare Tunnel 對長時間 idle WebSocket 可能 timeout（約 100 秒），建議心跳或重連機制 |

---

## 待實作：後台管理裝置 API URL

### 背景
- 目前 4 台裝置的 FastAPI URL（`/device/N/`）是固定在 nginx 設定中
- 希望管理員能在後台動態設定每台裝置的 APP 連線網址
- APP 啟動時從網站 API 取得對應的 server_url

### 計劃步驟

#### 1. Django：新增 DeviceConfig 模型
- 檔案：`Website/backend/content/models.py`
- 欄位：`device_id`（1~4）、`server_url`、`label`（裝置名稱）、`note`、`updated_at`
- 初始資料：4 筆，server_url 預設為 `/device/1/` ~ `/device/4/`

#### 2. Django API：新增端點
- 管理員讀寫：`GET/PUT /api/content/device-config/`（需 JWT）
- APP 讀取：`GET /api/content/device-config/<device_id>/`（公開，APP 啟動時呼叫）
- 檔案需修改：`content/serializers.py`、`content/views.py`、`content/urls.py`

#### 3. Admin UI：新增 DeviceConfig 管理頁面
- 新增檔案：`Website/frontend/src/admin/sections/DeviceConfig.jsx`
- 功能：顯示 4 台裝置的 URL，允許管理員修改
- 整合至 `AdminApp.jsx` 與 `Sidebar.jsx`

#### 4. Android APP：支援裝置編號
- 在 APP 設定中加入「裝置編號」欄位（1~4）
- `fetchServerConfigFromWebsite()` 改為帶入裝置編號，fetch 對應 URL
- 檔案：`Android/lib/providers/app_provider.dart`、`Android/lib/screens/home_screen.dart`

---

## Bug 修復記錄

### 多裝置連線：音訊 WS 踢出 / 切換裝置後避障失效（已修復）

**症狀 1**：裝置2 APP 連上後，裝置1 的音訊連線被踢出
**症狀 2**：APP 重連（不重啟伺服器）後，避障語音指令失效，需重啟 APP 才正常
**症狀 3**：裝置2 (`/device/2/`) 的 APP 連上，避障完全打不開

**根本原因 1：音訊 WS 未拒絕重複連線（app_main.py）**
- 相機 WS 有入口防護（`if esp32_camera_ws is not None: close 1013`）
- 但 `ws_audio` 直接 `esp32_audio_ws = ws`，不檢查是否已有連線
- 結果：新裝置連線 → 舊連線的 handler 仍在跑 → 舊 handler 的 `stop_rec()` 呼叫 `set_current_recognition(None)` → 清掉新連線剛建立的 ASR → 語音指令完全失效

**修復**：`app_main.py` 的 `ws_audio` 加入與相機 WS 相同的拒絕邏輯：
```python
if esp32_audio_ws is not None:
    await ws.close(code=1013)
    return
```

**根本原因 2：start_multi_device.py 兩台間只等 2 秒，YOLO 模型載入需 30-60 秒**
- 裝置1 和裝置2 的 YOLO 模型幾乎同時載入 GPU，VRAM 不足導致裝置2 模型載入失敗
- `orchestrator = None` → 避障按下顯示「导航系统未就绪」

**修復（方案B）**：新增共用模型推論伺服器架構：
- `model_server.py`：獨立 process，載入所有 YOLO 模型一次，透過 TCP port 9099 提供推論
- `model_client.py`：`RemoteYOLO` / `RemoteObstacleDetector` proxy，介面與原 YOLO 相同
- `app_main.py`：偵測到 `MODEL_SERVER_PORT` env var 時使用 proxy，不載入本機模型
- `start_multi_device.py`：預設先啟動 `model_server.py` 並等待就緒，再同時啟動 4 個 instance

啟動方式不變：`uv run python start_multi_device.py`

---


### APP 導航無法啟動（已修復）

**症狀**：
- Debug 面板：攝影機 WS 未連線、音訊 WS 未連線、狀態機未初始化
- 按下避障導航按鈕：伺服器回「导航系统未就绪」，偶發 405 錯誤

**根本原因 1：WebSocket scheme 錯誤（constants.dart）**
- `_wsBase()` 在 `baseUrl = "https://..."` 且 `secure = false`（預設）時
- 產生 `ws://trycloudflare.com`（port 80），Cloudflare Tunnel 只接受 port 443（WSS）
- → 攝影機、音訊 WebSocket 全部連線失敗

**修復**：`Android/lib/core/constants.dart` `_wsBase()` 改為根據 `baseUrl` 本身的 scheme 決定 WS scheme
```dart
final wsSchemeToUse = cleanBase.startsWith('https://') ? 'wss' : 'ws';
return cleanBase.replaceFirst(RegExp(r'^https?://'), '$wsSchemeToUse://') + path;
```

**根本原因 2：Orchestrator 只在攝影機連線後才初始化（app_main.py）**
- NavigationMaster 只在第一幀攝影機畫面到來時初始化
- 攝影機 WS 斷線 → orchestrator 永遠是 None → 導航 API 無法使用

**修復**：`app_main.py` 新增 `_startup_init_navigators()`，在啟動時背景等待 YOLO 模型載入後直接初始化 orchestrator，不需等待攝影機連線。

---

### Docker Port 設定整理（已修復）

**最終設定**：`Website/docker-compose.yml` nginx 只保留 `- "8888:80"`

**歷史**：曾有 9999（Hyper-V 保留，無法綁定）、8080、6666 等不同設定，統一改為 8888

**Port 分工**：
- `8888` → nginx（網站入口，Docker 容器）
- `8081～8084` → FastAPI 各裝置 instance（直接跑在主機）

---

## 後台管理 APP 伺服器設定（已實作）

管理員可在後台動態設定 AI 伺服器 URL，APP 啟動時自動讀取，不需手動填寫。

### 運作流程
1. 管理員登入 `https://aiglasses.qzz.io/admin/` → 左側「APP 伺服器設定」
2. 填入當次 Cloudflare Tunnel URL（例如 `https://xxxx.trycloudflare.com/GlassesBackstage/`）
3. APP 設定頁「網站 URL」填 `https://aiglasses.qzz.io`（只需設定一次）
4. APP 每次啟動自動呼叫 `GET /api/content/app-config/` 取得伺服器位址

### 相關檔案
- Django 模型：`Website/backend/content/models.py` `AppServerConfig`
- Django API：`Website/backend/content/admin_views.py` `AdminContentSectionView`（`app-config` section）
- React UI：`Website/frontend/src/admin/sections/ServerConfig.jsx`（新增）
- Flutter 讀取：`Android/lib/screens/splash_screen.dart` `fetchServerConfigFromWebsite()`

---

## 專案清理紀錄（2026-04-02）

### 已刪除的冗餘檔案
| 檔案/目錄 | 原因 |
|-----------|------|
| `朋友更新/` | 朋友貢獻的程式碼快照，已被主分支吸收 |
| `Website/原專案的CODE/` | 原始 HTML/JS，已被 React 取代 |
| `compile/自己用` | 舊版韌體，硬編碼 IP，已被 compile.ino 取代 |
| `compile/輩分節` | 同上 |
| `mobileclip2_b.ts`（243MB） | 主專案未使用（ultralytics 遺留），已刪除 |
| `mobileclip_blt.ts`（572MB） | 同上，共釋放 815MB |
| `download_models.py` | 模型已就位，腳本用途已達成 |
| `music/歡迎使用AI智慧眼鏡.wav.bak` | .bak 備份，原始 .wav 保留 |
| `yollo_E/`（1.3GB） | 已被 yolomedia.py 整合取代的舊子專案 |

### .gitignore 新增項目
- `Website/downloads/` — 防止 APK 誤 commit
- `*.apk`
- `mobileclip2_b.ts`

---

## Vertex AI 整合（已實作，2026-04-09）

### 策略：Vertex AI 優先，試用金耗盡自動切回 AI Studio 16-Key 輪換

**已完成**：
- `config.py`：新增 `GCP_PROJECT_ID`、`GCP_LOCATION`、`USE_VERTEX_AI` 三個設定項
- `omni_client.py`：
  - 新增 Vertex AI 客戶端 lazy init（`_get_vertex_client()`）
  - 新增自動切換旗標 `_VERTEX_EXHAUSTED`，配額耗盡時自動切回 AI Studio
  - `_call_flash()` / `_call_flash_long()` / `_stream_flash_sync()`：全部 Vertex 優先
  - **`_call_tts()` 完全不動**，繼續走 AI Studio（保留 Gemini TTS 音質）
- `audio_player.py`：WaveNet TTS 備援（`_wavenet_tts` / `_play_tts_fallback`）早已實作完畢
- `gemini_scene_describer.py`：不需改動，自動受惠於 `_call_flash()` 的切換邏輯

**需使用者補充 `.env`**：
```
GCP_PROJECT_ID=你的 GCP 專案 ID
GCP_LOCATION=us-central1
USE_VERTEX_AI=true
```
> 注意：若 `GCP_PROJECT_ID` 留空，系統自動走 AI Studio，不報錯

**自動切換條件**：
- Vertex AI 遇 `resource_exhausted` / `quota` / `billing` / 429 相關錯誤 → 切回 AI Studio
- 切換後印出：`[Gemini] Vertex AI 試用金耗盡，自動切換回 AI Studio（16-Key 輪換）`

---

## 預錄語音升級：Chirp3-HD 重新生成（待實作）

### 背景（2026-04-08）
- `voice/` 資料夾約 80 個預錄 WAV，來自原大陸專案，簡體中文、品質不一
- 即時 TTS fallback 已改用 `cmn-TW-Wavenet-A`（速度快，台灣口音）
- Google Cloud TTS 的台灣中文最高只有 WaveNet，**Chirp3-HD 只支援 `cmn-CN`（大陸口音）**

### 決策
- 預錄檔可用 `cmn-CN-Chirp3-HD-Aoede`（女聲）離線批次重新生成，品質最佳
- 即時 fallback 維持 `cmn-TW-Wavenet-A`（台灣口音 + 速度快）

### 待確認（實作前需與使用者確認）
- 文字是否同步轉繁體中文（簡→繁）？
- 口音是大陸腔可以接受嗎？

### 實作方式
讀取 `voice/map.zh-CN.json` 的所有 key，逐一呼叫 Google Cloud TTS Chirp3-HD 生成，
直接覆蓋 `voice/` 對應的 WAV 檔，並更新 `duration_ms`。

```python
# 關鍵參數
voice = texttospeech.VoiceSelectionParams(
    language_code="cmn-CN",
    name="cmn-CN-Chirp3-HD-Aoede",  # 女聲，最高品質
)
audio_config = texttospeech.AudioConfig(
    audio_encoding=texttospeech.AudioEncoding.LINEAR16,
    sample_rate_hertz=24000,
)
```

---

## 已知限制與地雷（必讀，避免重蹈）

### Gemini TTS（`gemini-2.5-flash-preview-tts`）已知限制

**查明日期**：2026-04-09

| 輸入類型 | 結果 | 原因 |
|---------|------|------|
| 導航陳述句（≥5字，如「前方有斑馬線，請注意。」） | 正常 | 模型判定為「需朗讀的文字」 |
| 極短打招呼（如「你好。」，≤4字） | 400 錯誤 | 模型誤判為對話，想生成文字回應而非音訊 |
| 問句（如「請問有什麼需要幫助？」） | 400 錯誤 | 同上 |
| 加 `systemInstruction` 欄位 | 500 錯誤 | TTS preview 模型不支援此欄位 |

**為什麼目前系統不受影響**：
- AI 對話回覆由 `_merge_short_sentences()` 確保 ≥5 字才送 TTS
- 導航提示走 WaveNet（`audio_player._wavenet_tts`），完全不走 Gemini TTS

**未來注意**：
- 若要新增系統短句播報（如「好的」、「收到」），**必須走 WaveNet**，不能走 Gemini TTS
- 任何修改 `_call_tts` 的方案都要先直接打 API 驗證，不能只測周邊邏輯

---

## Claude Skills 系統建立（已實作，2026-04-09）

### 決策重點
- 將所有工作規範拆成獨立 skill 檔，用 `/名稱` 叫出，避免 CLAUDE.md 過長
- 全域 `~/.claude/commands/`：通用規範（check / delete / pre-commit）
- 專案 `.claude/commands/`：專案特有規範（check / arch / update-md / app-check / web-test）
- `.gitignore` 改為只忽略 `.claude/memory/`，讓 `commands/` 可以 push 到 GitHub

### 涉及檔案
- `.claude/commands/check.md`：TTS / Vertex AI / model_server 專屬驗證
- `.claude/commands/arch.md`：系統架構速查
- `.claude/commands/update-md.md`：MD 維護規範（含步驟與格式）
- `.claude/commands/app-check.md`：Android APP 視障者可用性檢查
- `.claude/commands/web-test.md`：Website Django+React 完整測試清單（含後端 API 權限驗證）
- `CLAUDE.md`：精簡為 skill 索引表

---

## 專案清理（已完成，2026-04-09）

### 刪除的檔案
| 檔案 | 原因 |
|------|------|
| `idea.md`（根目錄） | 與 `MD/idea.md` 重複，MD 版本是主版本 |
| `models.py`（根目錄） | 引用不存在的 `app.cloud.*`，無任何模組使用 |
| `setup.bat` / `setup.sh` | 使用舊版 `pip install`，專案已改用 `uv` |
| `yoloe-26l-seg.pt`（根目錄） | `model/` 內已有相同檔案 |
| `mobileclip_blt.ts` | 72MB，gitignored，不使用 |
| `Chirp3-HD/`、`docs/` | 空資料夾 |
| `test_tts_*.py` | 臨時測試腳本，測試已完成 |
| `MD/tts_test_output.wav` | 測試輸出 |

---

## 安全性待改善（選擇性）

### `/device/N/` 攝影機畫面仍然公開
- 問題：知道 URL 的人可直接看到即時攝影機畫面（如 `/device/1/speaker`）
- 根本原因：WebSocket 無法跟隨 HTTP redirect，路徑必須公開
- 解法（後續）：在 FastAPI 端的 viewer 頁面加入 token 驗證
  - APP 連線時附帶 token（query param）
  - nginx 對 `/device/N/speaker`、`/device/N/viewer` 等頁面要求 token

### `/api/devices/N/status` 無需登入即可查詢
- 問題：任何人可查詢裝置狀態（uptime、導航狀態等）
- 解法（後續）：在 nginx 或 Django 加一層 proxy 驗證

---

## ASR 語音辨識改善（已完成，2026-04-29~30）

### 問題
APP 使用者反映「語音方面效果沒有很好」「語音轉文字收音聽不太到」。

### 已完成改善

#### 1. AGC 自動增益控制
- **問題**：固定增益 5.0x 無法適應不同麥克風（ESP32 vs 手機）和環境
- **方案**：AGC 根據最近 10 幀中位數 RMS 動態調整增益（0.5x~15.0x）
- **參數**：目標 RMS 800~3000、平滑係數 0.5、靜音門檻從 150 降到 80
- **檔案**：`asr_core.py`

#### 2. 繁簡字元轉換
- **問題**：Google STT cmn-Hant-TW 偶爾輸出簡體字，繁簡混合無法匹配指令
- **方案**：`_s2t()` 使用 `str.maketrans` + `str.translate`，150+ 字元對應表
- **檔案**：`asr_core.py`（`_SIMP_TO_TRAD`、`_s2t()`、`_normalize_cn()`）

#### 3. 喚醒詞根本性重構
- **問題**：原喚醒詞需「哈囉曼波」組合，「哈囉世界」也會誤觸發
- **方案**：關鍵字改為「曼波」本身，7 個 ASR 誤辨變體（曼波/漫波/漫播/慢播/慢波/滿波/們波）
- **行為變更**：「曼波」→觸發、「哈囉世界」→不觸發、「哈囉」→不觸發
- **檔案**：`asr_core.py`（`_MAMBO_VARIANTS`、`_check_wake_word()`）

#### 4. 口語化指令擴充
- **問題**：台灣國語口語化指令成功率僅 14%
- **方案**：新增「我要導航」「不要導航」「開導航」「停導航」「我要過馬路」等
- **匹配順序修正**：「過馬路結束」判斷移到「過馬路開始」之前
- **檔案**：`app_main.py`（`start_ai_with_text_custom()`）

#### 5. 熱詞（speech_contexts）擴充
- 喚醒詞 10→18、結束詞 6→11、熱詞 11→19
- `boost=20.0` 提高曼波變體辨識優先權

### 測試驗證
- `test_mambo_keyword.py`：106/106 通過（喚醒/結束/熱詞/誤觸發/s2t）
- `test_voice_commands.py`：91/91 通過（全部語音指令端到端）
- `test_asr_agc.py`：21/21 通過（AGC + 噪音環境）
- `test_traditional_chinese_user.py`：繁簡混合 100%、cmn-Hant-TW 100%
- `test_comprehensive_stress.py`：117/117 通過（生命週期+邊界+壓力）
- **總計 435+ 條測試全部通過**

### 關鍵決策記錄
- 喚醒詞從「哈囉曼波」改為「曼波」：使用者明確指示「主要的關鍵字是曼波」
- cmn-Hant-TW 維持為主 language_code：對比測試 100% vs zh-CN 87.5%
- 只保留繁體中文測試：「使用者只會說繁體中文而已」
- `_s2t()` 用 str.translate：零外部依賴，效能最佳
- 詳細流程圖見 `MD/關鍵字語音流程圖.md`

---

## APP Debug ASR Dashboard（已完成，2026-04-30）

### 問題
使用者反映「APP 看不出來語音有沒有收到」，需要即時監控語音辨識狀態。

### 方案
在 APP 的 Debug 懸浮球面板（`debug_panel.dart`）加入分頁切換（總覽 / ASR 語音）。

### ASR Dashboard 顯示內容
1. **收音狀態指示燈**：🟢 聆聽中 / 🟠 處理中 / ⚪ 待機 + 麥克風狀態
2. **即時辨識文字**：ASR partial text 即時顯示（語音輸入時 cyan 顏色更新）
3. **伺服器 ASR 數據**：Partial 字數、Final 紀錄數、最新辨識結果（3 秒輪詢）
4. **辨識歷史列表**：最近 30 筆 final 辨識結果（最新在上）

### 技術架構
- **資料流**：伺服器 WS `/ws_ui` 推送 `PARTIAL:text`、`FINAL:text`、`INIT:{partial, finals}`
- **Provider**：`app_provider.dart` 新增 `asrPartialText` + `asrFinals`，即時更新
- **UI**：`debug_panel.dart` 分頁切換，Consumer\<AppProvider\> reactive 更新
- **伺服器 API**：`/api/debug_status` 新增 `current_partial` + `recent_finals` 欄位

### 涉及檔案
- `app_main.py`：debug API 新增欄位
- `Android/lib/providers/app_provider.dart`：ASR 文字追蹤 + INIT 解析
- `Android/lib/widgets/debug_panel.dart`：分頁 UI + ASR Dashboard
