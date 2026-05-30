# AI 智慧眼鏡 (AI Glasses for Visual Impairment)

這是一個開源專案，將開源人工智慧模型整合到 IoT 裝置中，專為視障人士設計。

## 功能特點

| 功能 | 說明 |
|------|------|
| 盲道導航 | 即時偵測盲道並語音引導方向 |
| 過馬路輔助 | 斑馬線偵測 + 紅綠燈識別 |
| 紅綠燈偵測 | 持續偵測燈號狀態並語音播報 |
| 物品搜尋 | 開放詞彙視覺搜尋物品位置 |
| 語音對話 | ASR 語音轉文字 + LLM 智能回應 |
| 緊急聯絡人 | 語音指令快速撥打電話 |

## 硬體需求

### 選項一：ESP32 開發板
- Seeed Studio XIAO ESP32S3 Sense
- 攝影機模組
- 麥克風模組

### 選項二：Android 手機（不需要 ESP32）
- Android 8.0+ 手機
- 安裝 Flutter App（見下文）

## 軟體需求

- Python 3.10+
- 8GB+ RAM
- （可選）NVIDIA GPU with CUDA

---

## 快速開始

### 1. 複製專案

```bash
git clone https://github.com/Djude1/OpenAIDevice_For_VisualImpairment.git
cd OpenAIDevice_For_VisualImpairment
```

### 2. 建立虛擬環境

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. 安裝依賴

```bash
pip install -r requirements.txt
```

### 4. 下載模型

從 ModelScope 下載模型檔案並放入 `model/` 目錄：

| 檔案 | 大小 | 用途 |
|------|------|------|
| `yolo-seg.pt` | 144MB | 盲道分割 |
| `yoloe-11l-seg.pt` | 71MB | 障礙物檢測 |
| `trafficlight.pt` | 175MB | 紅綠燈偵測 |
| `shoppingbest5.pt` | 144MB | 物品識別 |
| `hand_landmarker.task` | 7.8MB | 手部檢測 |

下載指令：
```bash
# 使用 modelscope 下載
python -c "
from modelscope.hub.snapshot_download import snapshot_download
snapshot_download('archifancy/AIGlasses_for_navigation', cache_dir='model/')
"
```

### 5. 設定環境變數

複製 `.env.example` 為 `.env` 並填入 API 金鑰：

```env
# API 金鑰（至少需要一個）
DASHSCOPE_API_KEY=your_dashscope_key
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key

# 選填：模型路徑（使用預設值可不設）
# BLIND_PATH_MODEL=model/yolo-seg.pt
# OBSTACLE_MODEL=model/yoloe-11l-seg.pt
# TRAFFICLIGHT_MODEL=model/trafficlight.pt
# SHOPPING_MODEL=model/shoppingbest5.pt
# HAND_LANDMARKER_PATH=model/hand_landmarker.task

# 伺服器設定
SERVER_HOST=0.0.0.0
SERVER_PORT=8081
```

取得 API 金鑰：
- **DashScope**: https://dashscope.console.aliyun.com/
- **Gemini**: https://aistudio.google.com/app/apikey
- **GroQ**: https://console.groq.com/keys

### 6. 啟動伺服器

```bash
python app_main.py
```

伺服器啟動後，訪問 http://localhost:8081/ 查看監控頁面。

---

## 使用方式

### 方式一：使用 Flutter App（推薦）

1. 建置或下載 APK：
   ```bash
   cd Djude_Area/Android
   flutter pub get
   flutter build apk --debug
   ```

2. 將 `app-debug.apk` 安裝到手機

3. 確保手機與伺服器在同一 WiFi 網路

4. App 會自動發現伺服器，或手動輸入 IP

### 方式二：使用網頁介面

1. 啟動伺服器後訪問 http://localhost:8081/

2. 允許瀏覽器存取攝影機和麥克風

3. 點擊功能按鈕或使用語音指令

### 方式三：ESP32 硬體

請參考 [XIAO ESP32-S3 Sense 筆記](https://www.notion.so/XIAO-ESP32-S3-Sense-2f9cd2f379818066a8aedc41570dab27) 燒錄韌體。

---

## 語音指令

| 指令 | 功能 |
|------|------|
| 開始導航 / 盲道導航 | 啟動盲道偵測 |
| 開始過馬路 | 啟動斑馬線 + 紅綠燈偵測 |
| 檢測紅綠燈 | 啟動紅綠燈偵測 |
| 幫我找 [物品] | 搜尋特定物品 |
| 停止導航 | 停止所有功能 |
| 打給 [姓名] | 拨打紧急联系人 |

---

## 常見問題

### Q: 伺服器無法啟動
A: 檢查是否已安裝所有依賴 `pip install -r requirements.txt`

### Q: 模型載入失敗
A: 確認 `model/` 目錄中已有所有模型檔案

### Q: CUDA 記憶體不足
A: 環境變數設 `AIGLASS_DEVICE=cpu` 強制使用 CPU

### Q: Flutter App 找不到伺服器
A: 確認手機與電腦在同一 WiFi，手動輸入伺服器 IP

### Q: 語音辨識沒有反應
A: 檢查麥克風權限，確認已說出喚醒詞

---

## 專案結構

```
OpenAIDevice_For_VisualImpairment/
├── app_main.py              # 主程式入口
├── requirements.txt          # Python 依賴
├── model/                   # AI 模型目錄（需下載）
├── voice/                   # 語音提示音效
├── music/                   # 背景音效
├── static/                  # 前端網頁
├── Djude_Area/              # 擴充模組
│   ├── Android/             # Flutter App
│   ├── config.py           # 設定模組
│   └── ...
└── recordings/             # 錄製的影片
```

---

## API 端點

### HTTP
| 端點 | 方法 | 說明 |
|------|------|------|
| `/` | GET | 監控網頁 |
| `/api/nav/state` | GET | 取得導航狀態 |
| `/api/nav/blindpath` | POST | 啟動盲道導航 |
| `/api/nav/crossing` | POST | 啟動過馬路 |
| `/api/nav/traffic_light` | POST | 啟動紅綠燈偵測 |
| `/api/nav/item_search` | POST | 啟動物品搜尋 |
| `/api/nav/stop` | POST | 停止導航 |

### WebSocket
| 端點 | 方向 | 說明 |
|------|------|------|
| `/ws/camera` | 上行 | 傳送 JPEG 影像 |
| `/ws_audio` | 上行 | 傳送 PCM16 音訊 |
| `/ws` | 雙向 | IMU 感測器 / 一般訊息 |
| `/ws_ui` | 下行 | 狀態推播 |
| `/ws/viewer` | 下行 | YOLO 處理後影像 |

---

## 授權

MIT License

## 參考來源

- https://github.com/AI-FanGe/OpenAIglasses_for_Navigation
- [XIAO ESP32-S3 Sense 開發筆記](https://www.notion.so/XIAO-ESP32-S3-Sense-2f9cd2f379818066a8aedc41570dab27)
