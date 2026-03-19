# 工作日誌 (Work Log)

本文件記錄每次 AI 助手完成的工作內容，方便下一個使用者快速了解專案狀態。

---

## 2026-03-19 (第三次更新)

### 任務摘要
修正 VS Code Dev Tunnel 連線時的 FPS 顯示問題，新增詳細除錯日誌。

### 解決的問題

1. **FPS 顯示與實際不符**
   - 問題：伺服器顯示 30fps，但實際端到端只有 5fps
   - 原因：FPS 計算只基於伺服器推論時間，未包含網路延遲
   - 修正：改為計算「收到結果的時間差」作為真實 FPS

2. **超時後 FPS 異常下降**
   - 問題：請求超時後 FPS 從 5fps 掉到 0.1fps
   - 原因：超時期間的時間差被計入 FPS
   - 修正：新增 `_hadTimeoutSinceLastResult` 標記，超時後跳過下一次 FPS 計算

3. **HTTP 請求超時處理**
   - 新增 10 秒請求超時機制
   - 連續 3 次超時自動重新連線
   - 新增詳細除錯日誌（請求 ID、時間戳）

4. **更正功能類別列表載入逾時**
   - `/api/classes` 請求新增 5 秒超時
   - 超時後顯示「載入逾時，請手動輸入」

### 修改的檔案

| 檔案 | 修改內容 |
|------|----------|
| `src/static/app.js` | 真實 FPS 計算、超時標記、詳細日誌 |

### Git 提交記錄

```
bfa5db9 - fix: correct FPS calculation after timeout periods
f880430 - feat: 更正流程改為類別選擇器，支援中文輸入自動轉換英文
```

### 注意事項

1. **真實 FPS vs 伺服器 FPS**：Tunnel 連線時網路延遲約 200ms，實際 FPS 約 5fps
2. **超時標記**：超時後收到第一個結果會顯示伺服器 FPS，之後恢復真實 FPS 計算

---

## 2026-03-19 (第二次更新)

### 任務摘要
提升 YOLOE 偵測準確率，新增時序穩定化、用戶反饋系統、自適應信心度門檻，改善前端 UI。

### 新增功能

1. **偵測參數調優**
   - 信心度門檻從 0.5 降至 0.3（CLIP 開放詞彙模型特性）
   - 雙路輸出：顯示門檻 0.3（寬鬆避免漏報）+ 記錄門檻 0.55（嚴格減少誤報）
   - `imgsz` 可透過 `.env` 配置
   - 預設偵測類別從 30 個精簡為 10 個高頻測試物品

2. **DetectionStabilizer 時序穩定化**
   - 滑動視窗過濾閃爍偵測（window=3, min_hits=2）
   - 假正例過濾：極小框、佔滿畫面框、異常長寬比
   - 確認延遲約 0.2-0.4 秒，對視障輔助可接受

3. **FeedbackManager 用戶反饋系統**
   - 三種反饋類型：確認正確 / 更正類別 / 標記誤報
   - 反饋時自動裁剪偵測區域截圖（base64 → JPEG）
   - 自適應門檻：累積 10+ 筆反饋後自動計算最佳信心度
   - 執行緒安全（threading.Lock）

4. **YOLODetector 修正**
   - `update_classes()` 修正使用 `get_text_pe()` + `set_classes()` 兩步驟
   - FP16 ↔ FP32 切換保護（CLIP 嵌入需要 FP32）

5. **前端 UI 改善**
   - 除錯面板改為預設隱藏、可收合（🔧 按鈕切換）
   - 右下角新增標註狀態面板（顯示各類別反饋次數）
   - 點擊偵測框彈出反饋 modal（正確/更正/誤報）
   - 反饋 API：`POST /api/feedback`、`GET /api/feedback/stats`

### 修改的檔案

| 檔案 | 修改內容 |
|------|----------|
| `.env` | 精簡偵測類別、降低信心度、新增參數 |
| `src/config.py` | ModelConfig 新增 4 個欄位 |
| `src/detection/stabilizer.py` | **新增** DetectionStabilizer + filter_false_positives |
| `src/detection/feedback.py` | **新增** FeedbackManager 反饋收集與自適應門檻 |
| `src/detection/yolo_detector.py` | imgsz 可配置、修正 update_classes |
| `src/web_server.py` | 整合 stabilizer/feedback、新增反饋 API、雙路輸出 |
| `src/static/index.html` | 除錯面板收合、標註狀態面板 |
| `src/static/style.css` | 新 UI 元件樣式 |
| `src/static/app.js` | 反饋 modal、截圖裁剪、標註面板輪詢 |

### Git 提交記錄

```
bd1f4ea - feat: 新增偵測參數設定（信心度分離、stabilizer、imgsz）
066e68d - feat: 新增 DetectionStabilizer 時序穩定化與假正例過濾
1267df1 - feat: 新增 FeedbackManager 用戶反饋收集與自適應門檻
95c06c9 - feat: YOLODetector 支援 imgsz 設定，修正 update_classes 使用文字嵌入
c387196 - feat: 整合 stabilizer/feedback 至 web_server，新增反饋 API
24f2f12 - feat: 除錯面板改為可收合，新增標註狀態面板與反饋 modal 樣式
f6b05a6 - feat: 前端反饋 modal、截圖裁剪與標註狀態面板
```

### 注意事項

1. **信心度門檻**：現在預設 0.3（顯示）/ 0.55（記錄），可在 `.env` 調整
2. **反饋資料目錄**：`data/feedback/`（feedback.jsonl + images/）
3. **自適應門檻**：每 20 筆反饋自動重新計算，存於 `data/feedback/class_thresholds.json`
4. **CLI 參數**：`--confidence` 現在預設從 `.env` 讀取，不再硬編碼 0.5

### 待處理/已知問題

- 端對端測試需手動啟動伺服器驗證（需要攝影機）

---

## 2026-03-19

### 任務摘要
修正 YOLOE 網頁偵測系統的多個問題，包括延遲、GPU 加速、中文顯示和準確率。

### 解決的問題

1. **伺服器連接問題**
   - 關閉佔用 8080 端口的舊伺服器進程
   - 使用正確的虛擬環境路徑啟動伺服器

2. **GPU 加速問題**
   - 發現 PyTorch 安裝的是 CPU 版本
   - 重新安裝 CUDA 12.8 版 PyTorch：`uv pip install torch torchvision --extra-index-url https://download.pytorch.org/whl/cu128`
   - 偵測時間從 ~270ms 降到 ~25-50ms

3. **FP16 與 CLIP 模型衝突**
   - 錯誤：`mat1 and mat2 must have the same dtype, but got Float and Half`
   - 修正：調整程式碼順序，先執行 `set_classes()` 再啟用 FP16

4. **中文標籤顯示 "???"**
   - 原因：OpenCV 的 `cv2.putText` 無法顯示中文
   - 解決：改用 PIL (Pillow) 繪製中文標籤
   - 使用 Windows 系統字體 `C:/Windows/Fonts/msyh.ttc`

5. **偵測準確率提升**
   - 使用正確的 `get_text_pe()` 生成文字嵌入
   - 將嵌入傳入 `set_classes(names, embeddings)`
   - 新增 `imgsz` 和 `augment` 參數支援

### 修改的檔案

| 檔案 | 修改內容 |
|------|----------|
| `src/detection/yolo_detector.py` | 1. 修正 FP16 順序 2. 使用 PIL 繪製中文 3. 使用 get_text_pe() |
| `src/static/app.js` | 點擊偵測框更正功能、HTTP 超時保護 |
| `src/static/index.html` | 新增提示文字、版本更新 |
| `src/static/style.css` | Canvas 點擊事件支援 |
| `功能介紹與使用指南.md` | 新增 CUDA PyTorch 安裝說明 |
| `pyproject.toml` | 新增 CUDA 安裝說明註解 |
| `CLAUDE.md` | 新增工作日誌規範 |

### Git 提交記錄

```
dcc2a11 - fix: 修正 FP16 與 CLIP 模型資料類型衝突
4de8077 - fix: 修正 FP16 與 CLIP 模型衝突，新增 CUDA PyTorch 安裝說明
29421ff - feat: 新增雙畫面佈局、點擊更正功能與 GPU 加速說明
65e7373 - feat: 提升 YOLOE 開放詞彙偵測準確率
```

### 啟動指令

```powershell
# 使用虛擬環境中的 Python
.\.venv\Scripts\python.exe src/web_server.py --port 8080

# 或使用 uv（需先安裝 CUDA 版 PyTorch）
uv pip install torch torchvision --extra-index-url https://download.pytorch.org/whl/cu128
uv run python src/web_server.py --port 8080
```

### 注意事項

1. **uv 與 CUDA PyTorch**：使用 `uv sync` 會安裝 CPU 版 PyTorch，需要手動安裝 CUDA 版
2. **GPU 檢查指令**：`.\.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"`
3. **信心度門檻**：預設 0.5，可在 `.env` 中調整 `CONFIDENCE_THRESHOLD`
4. **FP16 加速**：僅在 CUDA 可用時啟用，CLIP 模型需要 FP32

### 待處理/已知問題

- 無

---
