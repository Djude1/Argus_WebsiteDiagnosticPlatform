# 工作日誌 (Work Log)

本文件記錄每次 AI 助手完成的工作內容，方便下一個使用者快速了解專案狀態。

---

## 2026-03-25 (第十三次更新)

### 任務摘要
永久修復 PyTorch GPU 問題：透過 `pyproject.toml` 設定 `[tool.uv]` 讓所有未來的虛擬環境自動安裝 CUDA 版 PyTorch，並重新生成 `uv.lock` 確保鎖定版本為 CUDA build。

### 問題根因
`uv run` 強制遵守 `uv.lock`，而舊版 lockfile 中 torch 指向 PyPI（CPU 版）。
即使手動 `uv pip install` 安裝了 CUDA 版，下次 `uv run` 仍會回退到 CPU 版。
初次 `uv lock` 失敗原因：預設 index-strategy 只用第一個含有該套件的 index（PyPI 有 CPU torch → CUDA index 被忽略）。

### 修改的檔案
- `pyproject.toml` — 新增 `torch>=2.0.0`、`torchvision>=0.15.0` 至 dependencies；`[tool.uv]` 新增 `index-strategy = "unsafe-best-match"`
- `uv.lock` — 重新生成：torch `2.10.0` (CPU) → `2.11.0+cu128`，torchvision `0.25.0` → `0.26.0+cu128`

### 驗證結果
```
PyTorch: 2.11.0+cu128
CUDA available: True
Device: NVIDIA GeForce RTX 3050 Laptop GPU
```

### 重啟指令
```bash
# Webcam 版本
cd Djude_Area/yollo_E
uv run python src/main.py --source webcam

# Web 版本
cd Djude_Area/yollo_E
uv run python src/main.py --web
```

---

## 2026-03-25 (第十二次更新)

### 任務摘要
版本同步：回朔至 `b37a72b` 還原 DetectionEngine 整合，修復多個 CRITICAL/HIGH 問題，確保 webcam 與 web 版本均能正常偵測。

### 執行操作
1. `git reset --hard origin/main` 更新至遠端最新版本
2. `git checkout b37a72b -- 4 files` 還原 DetectionEngine 整合
3. 並行程式碼審查（webcam + web 兩條線同時）

### 修復的問題（共 10 項）

| 嚴重度 | 檔案 | 問題 |
|--------|------|------|
| CRITICAL | `detection_engine.py` | import 無 sys.path 防護，加入 `_src_path` 防護 |
| CRITICAL | `web_server.py:1275` | `draw_detections()` 前缺 None check |
| HIGH | `detection_engine.py` | `YOLODetector()` 位置引數錯誤（device 被當 confidence），改用具名參數 |
| HIGH | `detection_engine.py` | 未載入 `.env` 的 `DETECTION_CLASSES`，新增 `detection_classes` 欄位 |
| HIGH | `main.py:266` | 主迴圈內重複 import FrameDetectionResult，已移除 |
| HIGH | `main.py:267` | `FrameDetectionResult` 缺 `frame_shape=frame.shape` |
| HIGH | `main.py:288` | `result.count` 為 int，改為 `str(result.count)` |
| HIGH | `yolo_detector.py` | `draw_detections()` 空 detections 時 `text_height` NameError |
| MEDIUM | `data_manager.py` | `detection.class_name` 無 None 防護 |
| LOW | `web_server.py:101` | 移除未使用的 `ExtensionOID` import |

### 修改的檔案
- `src/core/detection_engine.py` — sys.path 防護、正確 YOLODetector 參數、DETECTION_CLASSES 載入
- `src/main.py` — 移除迴圈 import、加 frame_shape、修正 count 型別
- `src/web_server.py` — draw_detections None check、bbox warning、移除 ExtensionOID
- `src/detection/yolo_detector.py` — text_height 預設值防 NameError
- `src/core/data_manager.py` — class_name None 防護

### 提交記錄
- `ddd0550` revert: restore DetectionEngine integration from b37a72b
- `8c1b733` fix: detection_engine.py sys.path + OrderedDict
- `09f107d` fix: yolo_detector text_height + data_manager None guard
- `fd15fe9` fix: web_server None check + bbox warning + ExtensionOID
- `e548cc3` fix: main.py loop import + frame_shape + count type

### 重啟指令
```bash
# Webcam 版本
cd Djude_Area/yollo_E
uv run python src/main.py --source webcam

# Web 版本
cd Djude_Area/yollo_E
uv run python src/main.py --web
```

---

## 2026-03-24 (第十一次更新)

### 任務摘要
在 DetectionEngine.detect() 加入精確計時日誌，找出效能瓶頸。

### 修改的檔案
- `src/core/detection_engine.py` — 新增 `import time`、每個步驟計時點（t0~t4）、`[PROFILE]` 日誌

### 計時日誌格式
```
[PROFILE] detector.detect: X.XXms | filter_false_positives: X.XXms | stabilizer.update: X.XXms | label_mapping: X.XXms | total: X.XXms
```

### 重啟指令
```bash
cd Djude_Area/yollo_E
uv run python src/main.py --source webcam
# 或
uv run python src/main.py --web
```

---

## 2026-03-24 (第十次更新)

### 任務摘要
建立 DetectionEngine 類別，封裝 YOLODetector、DetectionStabilizer、PromptEnhancer、LabelMapper，提供 Webcam 和 Web 版本共用的偵測邏輯。

### 新建的檔案
- `src/core/detection_engine.py` — 完整偵測引擎，包含：
  - DetectionConfig 資料類別（model_path, device, confidence, max_active_classes, custom_classes_path）
  - DetectionEngine 類別（整合所有偵測元件）
  - detect() 方法（完整偵測流程：raw detection → stabilizer → alias resolution → Chinese label mapping）
  - _resolve_alias() 方法（使用 ALIAS_MAPPING 解析類別別名）
  - _load_custom_classes() 方法（從 JSON 載入自訂類別）
  - reset_session() 方法（重置偵測狀態）

### 修改的檔案
- `src/core/detection_engine.py`（新建）

### 注意事項
- DetectionEngine 目前參考的 LabelMapper.get_cn_label() 方法名稱需確認（可能應為 get_chinese_name_from_en）
- 詳細請參閱 `docs/INTEGRATION_PLAN.md`

### 重啟指令
```bash
# Webcam 版本
cd Djude_Area/yollo_E
uv run python src/main.py --source webcam
```

---

## 2026-03-24 (第九次更新)

### 任務摘要
完成 Webcam 版本 (main.py) 與 Web 版本 (web_server.py) 的功能比較分析，並建立詳細的版本整合計畫文件。

### 分析結果

**Web 版本已有但 Webcam 版本缺少的功能：**
- DetectionStabilizer（時序穩定過濾）
- FeedbackManager（用戶回饋系統）
- 類別槽位管理（max 10 active + LRU 替換）
- 別名系統（35+ 映射 + 自動合併）
- CLIP 變體擴展（variant expansion）
- PromptEnhancer（CLIP 提示優化）
- DetectionLogger（每日 JSONL 日誌）

**Webcam 版本獨有但 Web 版本缺少的功能：**
- AnnotationManager（Tkinter 手動標註 + annotations.json）
- DatabaseManager + ItemLogger（SQLite 自動記錄）

**資料格式差異：**
- annotations.json：bbox 為 `{x1,y1,x2,y2}` 物件，37 筆，2026-03-12~03-15
- feedback.jsonl：bbox 為 `[x1,y1,x2,y2]` 陣列，20 筆，2026-03-19

### 新建的檔案
- `docs/INTEGRATION_PLAN.md` — 版本整合計畫，包含：
  - 功能對照表與資料格式差異
  - 共用偵測引擎 (DetectionEngine) 架構設計
  - 統一資料格式 (unified_record.jsonl) 設計
  - 五階段詳細整合流程
  - 檔案變更清單與優先順序
  - 資料遷移策略與去重規則
  - 驗證清單

### 注意事項
- 整合工作尚未開始實作，僅完成計畫文件
- 建議從 P0（建立共用 DetectionEngine）開始實作
- 歷史資料遷移需先備份再執行

### 重啟指令
```bash
# Webcam 版本
cd Djude_Area/yollo_E
uv run python src/main.py --source webcam

# Web 版本
cd Djude_Area/yollo_E
uv run python src/main.py --web
```

---

## 2026-03-24 (第八次更新)

### 任務摘要
實作類別別名系統 + CLIP 提示變體擴展機制，讓使用者能擴展物品辨識範圍。

### 新增功能

1. **類別別名系統**
   - 預設 35+ 組常見別名（如 mug → cup、smartphone → cell phone）
   - 偵測結果自動歸併：偵測到 "mug" 時顯示為 "cup"
   - 新增類別時檢查別名衝突，提示合併而非重複新增
   - API：`GET/POST/DELETE /api/aliases`、`GET /api/aliases/check`

2. **CLIP 提示變體擴展**
   - 使用者可為任何類別新增變體描述（如 mouse → gaming mouse、wireless mouse）
   - 變體會附加到 CLIP 提示，擴展嵌入涵蓋範圍
   - 更新變體後自動重新生成 CLIP 嵌入
   - API：`GET /api/variants`、`PUT /api/variants`、`POST /api/variants/add`

3. **前端 UI**
   - 類別標籤新增 ⊕ 變體按鈕，點擊打開變體管理對話框
   - 新增類別發現別名時，彈出「發現類似物品」對話框，可選擇合併為變體
   - 變體管理對話框支援新增/移除變體描述

### 技術原理
- YOLOE 使用 CLIP 文字嵌入做開放詞彙偵測
- 增加變體描述（如 "computer mouse device, gaming mouse, wireless mouse"）讓嵌入涵蓋更多視覺變體
- 別名歸併減少 CLIP 嵌入空間中的類別競爭

### 修改的檔案
- `src/detection/prompt_enhancer.py` — 新增 `_variants` 支援、`add_variants()`、`set_variants()`、`load_all_variants()`
- `src/detection/label_mapper.py` — 新增 `DEFAULT_ALIASES`、`resolve_alias()`、`is_alias()`、`get_aliases_for()` 等方法
- `src/detection/yolo_detector.py` — 新增 `update_variants()`、`load_all_variants()`
- `src/web_server.py` — 別名 API、變體 API、偵測結果別名歸併、新增類別別名檢查
- `src/static/app.js` — 變體對話框、別名提示對話框、⊕ 按鈕
- `src/static/style.css` — 變體對話框樣式

### 資料結構變更
`custom_classes.json` 新增欄位：
```json
{
  "aliases": { "mug": "cup", "smartphone": "cell phone" },
  "variants": { "mouse": ["gaming mouse", "wireless mouse"] }
}
```

### 重啟指令
```bash
cd Djude_Area/yollo_E
uv run python src/main.py
```

---

## 2026-03-24 (第七次更新)

### 任務摘要
實作類別槽位管理機制：限制同時啟用的偵測類別最多 10 個，支援啟用/停用切換，並以 LRU 策略建議替換。

### 解決的問題

1. **YOLOE 多類別準確度下降**
   - 問題：YOLOE 使用 CLIP 嵌入做開放詞彙偵測，同時偵測太多類別會導致嵌入空間擁擠、類別混淆
   - 方案：限制同時啟用的類別數量（預設上限 10 個），超出時建議替換最久未偵測到的類別

2. **類別管理機制**
   - 區分「已註冊」和「啟用中」兩種狀態
   - 所有類別（預設 + 自訂）都可以啟用/停用
   - 停用的類別不會被刪除，隨時可重新啟用
   - LRU（最近最少使用）策略自動建議替換對象

### 新增功能

1. **後端 API**
   - `PUT /api/classes/toggle` — 啟用/停用類別
   - `GET /api/classes` — 新增 `active`、`last_detected`、`active_count`、`max_active` 欄位
   - `POST /api/classes` — 槽位已滿時回傳 `slots_full` + LRU 建議
   - 偵測時每 30 幀自動更新 `last_detected` 時間戳

2. **前端 UI**
   - 類別標籤顯示啟用/停用狀態（●/○ 切換按鈕）
   - 停用類別以虛線框 + 刪除線 + 半透明顯示
   - 槽位計數器「啟用中 N/10」
   - 槽位已滿時彈出替換對話框，顯示 LRU 建議

3. **設定**
   - `.env` 新增 `MAX_ACTIVE_CLASSES=10`
   - `config.py` 新增 `max_active_classes` 設定欄位

### 修改的檔案
- `src/web_server.py` — 類別管理 API 全面改造（toggle、LRU、槽位上限）
- `src/static/app.js` — 前端類別列表、toggleClass()、槽位替換對話框
- `src/static/style.css` — 停用狀態樣式、modal overlay、對話框樣式
- `src/config.py` — 新增 max_active_classes 設定
- `.env` — 新增 MAX_ACTIVE_CLASSES
- `data/custom_classes.json` — 新增 active、deactivated_defaults、last_detected 欄位

### 資料結構變更
`custom_classes.json` 擴充：
```json
{
  "classes": [{ "name_en": "...", "active": true, ... }],
  "deactivated_defaults": [],
  "last_detected": { "cup": "2026-03-24T10:30:00", ... }
}
```

### 注意事項
- 目前預設 10 個 .env 類別 + 2 個自訂類別 = 12 個已註冊，其中最多 10 個可同時啟用
- 反饋更正自動新增的類別，若槽位已滿會以停用狀態註冊
- `last_detected` 的寫入已節流（每 30 幀），不影響偵測效能
- 未來計畫：類別別名系統（如 mug = cup 視為同一類別）

### 重啟指令
```bash
cd Djude_Area/yollo_E
uv run python src/main.py
```

---

## 2026-03-19 (第六次更新)

### 任務摘要
修正註冊新物品表單欄位順序顛倒問題，並優化網頁渲染效能解決卡頓。

### 解決的問題

1. **註冊表單欄位順序顛倒**
   - 問題：英文輸入欄在前、中文在後，不符合中文使用者操作直覺
   - 修正：中文名稱改為第一欄（必填），英文名稱改為第二欄（可選）
   - 後端自動查找：若未填英文名稱，自動透過 `label_mapper` 從中文查找對應英文

2. **網頁卡頓 / 畫面不流暢**
   - 原因 1：`sendFrame()` 每幀都 `createElement('canvas')` 產生大量 GC 壓力
   - 原因 2：`_drawServerFrame()` 每幀都 `new Image()` 加劇 GC
   - 原因 3：`updateResultsList()` 每幀重寫 `innerHTML` 觸發不必要的 DOM 重繪
   - 原因 4：`debugLog()` 每次請求都寫入 DOM 並觸發 `scrollTop` reflow
   - 修正：
     - 重用 `_tempCanvas` 和 `_serverImg` 物件
     - 結果列表 HTML 快取比對，相同時跳過更新
     - debug 日誌改為每 30 幀輸出一次
     - 面板收合時跳過非錯誤日誌的 DOM 操作

### 修改的檔案

| 檔案 | 修改內容 |
|------|----------|
| `src/static/index.html` | 註冊表單欄位順序：中文在前、英文在後 |
| `src/static/app.js` | 重用 canvas/Image、結果快取、日誌節流、面板收合跳過 |
| `src/web_server.py` | `AddClassRequest` 改為 `name_cn` 必填、`name_en` 可選，自動 CN→EN 查找 |

### Git 提交記錄

```
af7d854 - fix: swap registration form fields (CN first) and reduce frame rendering stutter
```

### 注意事項

1. **中文名稱為必填**：註冊新物品時必須輸入中文名稱，英文可選（系統會自動查找）
2. **CLIP 相容性**：若查無對應英文，會直接以中文名稱送入 CLIP 模型（CLIP 可處理部分中文）
3. **效能提升**：減少每幀 3 次 DOM 操作，改為每 30 幀 1 次，大幅降低瀏覽器負擔

---

## 2026-03-19 (第四次更新)

### 任務摘要
修正多使用者連續使用時的狀態殘留問題。

### 解決的問題

1. **多使用者連續使用延遲**
   - 問題：使用者 A 斷線後，使用者 B 連線時無法顯示 YOLO 視窗
   - 原因：`DetectionStabilizer` 的歷史記錄殘留，影響新使用者偵測結果
   - 修正：當檢測到間隔超過 5 秒無請求時，自動重置 stabilizer 狀態

2. **並發偵測問題**
   - 新增 `asyncio.Lock` 防止多個請求同時存取 GPU
   - 確保偵測操作序列化，避免資源競爭

### 修改的檔案

| 檔案 | 修改內容 |
|------|----------|
| `src/web_server.py` | 新增 `_detection_lock`、`_last_request_time`、會話管理邏輯 |

### Git 提交記錄

```
431fb18 - fix: add session management for multi-user detection
```

### 注意事項

1. **新使用者檢測**：超過 5 秒無請求視為新使用者，會重置偵測穩定化狀態
2. **並發保護**：所有偵測請求現在會排隊處理，避免 GPU 資源衝突

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
