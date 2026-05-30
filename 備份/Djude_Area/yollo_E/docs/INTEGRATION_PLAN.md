# 版本整合計畫：Webcam (main.py) ↔ Web (web_server.py)

> 建立日期：2026-03-24
> 目標：統一兩個版本的核心功能與資料格式，讓使用者不論使用哪個介面都能享有完整功能

---

## 一、現狀比較總覽

### 1.1 功能對照表

| 功能模組 | Web 版本 (web_server.py) | Webcam 版本 (main.py) | 整合方向 |
|----------|:------------------------:|:---------------------:|----------|
| **DetectionStabilizer** (時序穩定過濾) | ✅ 滑動窗口 window=3, min_hits=2 | ❌ 每幀獨立偵測 | → 移植到 Webcam |
| **FeedbackManager** (用戶回饋) | ✅ confirm/correct/false_positive | ❌ 無 | → 移植到 Webcam |
| **類別槽位管理** (max 10 active) | ✅ LRU 替換策略 | ❌ 無上限管理 | → 移植到 Webcam |
| **別名系統** (mug→cup 等 35+ 映射) | ✅ 自動合併偵測結果 | ❌ 無 | → 移植到 Webcam |
| **CLIP 變體擴展** (variant expansion) | ✅ 用戶可新增描述變體 | ❌ 無 | → 移植到 Webcam |
| **PromptEnhancer** (CLIP 提示優化) | ✅ 類別→描述性提示 | ❌ 直接使用原始名 | → 移植到 Webcam |
| **DetectionLogger** (每日 JSONL 日誌) | ✅ detections_YYYYMMDD.jsonl | ❌ 無 | → 移植到 Webcam |
| **AnnotationManager** (手動標註) | ❌ 無 | ✅ Tkinter 彈窗 + annotations.json | → 移植到 Web (API 化) |
| **DatabaseManager + ItemLogger** (SQLite) | ❌ 無 | ✅ 自動記錄 | → 共用 (兩版本都可寫入) |

### 1.2 資料格式差異

#### annotations.json（Webcam 版本，37 筆）
```json
{
  "id": "20260312_143704_512943_cell phone",
  "class_name": "cell phone",
  "class_name_cn": "手機",
  "confidence": 0.942,
  "bbox": { "x1": 179.86, "y1": 138.57, "x2": 317.60, "y2": 374.90 },
  "timestamp": "2026-03-12 14:37:04",
  "session_id": 12,
  "image_path": "D:\\...\\annotation_images\\xxx.jpg",
  "status": "annotated",
  "owner": "6",
  "description": "cell phone",
  "custom_label": "cell phone",
  "notes": "",
  "extra_data": {}
}
```

#### feedback.jsonl（Web 版本，20 筆）
```json
{
  "type": "confirm",
  "class": "cup",
  "confidence": 0.833,
  "bbox": [284, 238, 723, 550],
  "correct_class": null,
  "image_path": "C:\\...\\feedback\\images\\cup_20260319.jpg",
  "timestamp": "2026-03-19T02:41:22.354595"
}
```

#### 主要差異
| 欄位 | annotations.json | feedback.jsonl |
|------|-----------------|----------------|
| bbox 格式 | `{x1, y1, x2, y2}` 物件 | `[x1, y1, x2, y2]` 陣列 |
| 圖片儲存 | 檔案路徑（絕對） | 檔案路徑（絕對） |
| 回饋類型 | `status` (pending/annotated) | `type` (confirm/correct/false_positive) |
| 額外資訊 | owner, description, custom_label, notes | correct_class |
| 時間格式 | `"2026-03-12 14:37:04"` | `"2026-03-19T02:41:22.354595"` (ISO 8601) |
| 中文名稱 | ✅ `class_name_cn` | ❌ 無 |

---

## 二、整合架構設計

### 2.1 核心理念：共用偵測引擎，獨立 UI 層

```
┌─────────────────────────────────────────────────┐
│              共用偵測引擎 (shared_core)            │
│                                                   │
│  YOLODetector ← PromptEnhancer ← Variants       │
│       │                                           │
│       ▼                                           │
│  DetectionStabilizer → 別名解析 → 槽位管理         │
│       │                                           │
│       ▼                                           │
│  UnifiedDataManager (統一資料管理)                  │
│  ├── FeedbackManager (用戶回饋)                    │
│  ├── AnnotationManager (手動標註)                  │
│  ├── DetectionLogger (偵測日誌)                    │
│  └── DatabaseManager (SQLite 記錄)                │
├─────────────────────────────────────────────────┤
│          UI 層（獨立實作）                          │
│                                                   │
│  ┌──────────────┐    ┌──────────────────┐        │
│  │ Webcam 版本   │    │ Web 版本          │        │
│  │ Tkinter GUI  │    │ FastAPI+WebSocket │        │
│  │ OpenCV 視窗   │    │ 瀏覽器界面         │        │
│  └──────────────┘    └──────────────────┘        │
└─────────────────────────────────────────────────┘
```

### 2.2 統一資料格式設計

建立 `unified_record.jsonl` 作為統一的資料儲存格式：

```json
{
  "id": "20260312_143704_512943_cell_phone",
  "source": "webcam",
  "type": "annotation",
  "class_name": "cell phone",
  "class_name_cn": "手機",
  "confidence": 0.942,
  "bbox": [179.86, 138.57, 317.60, 374.90],
  "timestamp": "2026-03-12T14:37:04.000000",
  "session_id": "12",
  "image_path": "data/images/20260312_143704_cell_phone.jpg",
  "feedback": {
    "status": "annotated",
    "correct_class": null,
    "owner": "user1",
    "description": "cell phone",
    "custom_label": "cell phone",
    "notes": ""
  }
}
```

**格式統一規則：**
- `bbox`：統一為 `[x1, y1, x2, y2]` 陣列格式
- `timestamp`：統一為 ISO 8601 格式 (`YYYY-MM-DDTHH:mm:ss.ffffff`)
- `image_path`：統一為相對路徑（相對於專案根目錄）
- `source`：標記資料來源 (`"webcam"` / `"web"`)
- `type`：統一為 `"annotation"` / `"confirm"` / `"correct"` / `"false_positive"`

---

## 三、詳細整合流程

### 階段一：建立共用核心模組 `DetectionEngine`

**目標**：將目前 `web_server.py` 中散落的偵測邏輯抽取為獨立類別

**步驟：**

1. **建立 `src/core/detection_engine.py`**
   - 封裝以下功能：
     - YOLO 模型載入與偵測
     - PromptEnhancer 初始化與變體載入
     - DetectionStabilizer 時序過濾
     - 別名解析 (resolve_alias)
     - 槽位管理 (max_active_classes, LRU)
     - 中文標籤映射
   - 輸入：影像 frame (numpy array)
   - 輸出：穩定化、別名解析後的偵測結果

```python
# 預期介面
class DetectionEngine:
    def __init__(self, config):
        self.detector = YOLODetector(...)
        self.stabilizer = DetectionStabilizer(...)
        self.label_mapper = LabelMapper()
        self.prompt_enhancer = PromptEnhancer()
        # 載入別名、變體、槽位設定...

    def detect(self, frame) -> List[Detection]:
        """完整偵測流程：YOLO → 穩定化 → 別名解析 → 中文映射"""
        ...

    def add_class(self, name_en, name_cn) -> dict:
        """新增偵測類別（含槽位檢查）"""
        ...

    def toggle_class(self, name_en, active) -> dict:
        """啟用/停用類別"""
        ...
```

2. **建立 `src/core/data_manager.py`**
   - 統一管理所有資料寫入：
     - annotations (手動標註)
     - feedback (用戶回饋)
     - detection_logs (偵測日誌)
     - database (SQLite)
   - 提供統一的儲存 API

```python
class UnifiedDataManager:
    def __init__(self, data_dir):
        self.feedback_manager = FeedbackManager(...)
        self.annotation_manager = AnnotationManager(...)
        self.detection_logger = DetectionLogger(...)
        self.db_manager = DatabaseManager(...)

    def record_feedback(self, feedback_type, detection, image, **kwargs):
        """統一記錄回饋（兩個版本共用）"""
        ...

    def record_annotation(self, detections, frame, session_id):
        """統一記錄標註（兩個版本共用）"""
        ...
```

### 階段二：移植功能到 Webcam 版本

**步驟：**

1. **整合 DetectionStabilizer**
   ```
   修改檔案：src/main.py
   - import DetectionStabilizer
   - 在 initialize() 中建立 stabilizer 實例
   - 在主迴圈的 detect() 後加入 stabilizer.update()
   - 使用穩定化後的結果進行顯示和記錄
   ```

2. **整合別名系統**
   ```
   修改檔案：src/main.py
   - 在偵測結果設置中文標籤前，先執行 resolve_alias()
   - 載入 custom_classes.json 中的自訂別名
   ```

3. **整合 PromptEnhancer + 變體擴展**
   ```
   修改檔案：src/main.py
   - 在 YOLODetector 初始化後，載入 PromptEnhancer
   - 載入 custom_classes.json 中的 variants
   - 使用 enhanced prompt 建立 CLIP embeddings
   ```

4. **整合槽位管理**
   ```
   修改檔案：src/main.py
   - 讀取 MAX_ACTIVE_CLASSES 環境變數
   - 載入 custom_classes.json 的 active 狀態
   - 僅對 active 類別建立 CLIP embeddings
   ```

5. **整合 DetectionLogger**
   ```
   修改檔案：src/main.py
   - import DetectionLogger
   - 在主迴圈中記錄每幀偵測結果
   ```

6. **整合 FeedbackManager（Tkinter 版）**
   ```
   修改檔案：src/main.py
   - 在 Tkinter 標註對話框中新增「確認正確」和「糾正名稱」按鈕
   - 將回饋寫入 feedback.jsonl
   ```

### 階段三：移植 AnnotationManager 到 Web 版本

**步驟：**

1. **建立 Web API 端點**
   ```
   修改檔案：src/web_server.py
   新增端點：
   - POST /api/annotations      — 記錄標註
   - GET  /api/annotations       — 查看標註列表
   - PUT  /api/annotations/{id}  — 更新標註
   - GET  /api/annotations/stats — 標註統計
   ```

2. **在前端新增標註介面**
   ```
   修改檔案：src/static/app.js
   - 新增「標註模式」按鈕
   - 點擊偵測框可開啟標註對話框
   - 填寫中文/英文名稱後送出
   ```

### 階段四：歷史資料遷移

**步驟：**

1. **建立資料遷移腳本 `scripts/migrate_data.py`**

   ```python
   # 功能：將現有的 annotations.json 和 feedback.jsonl 轉換為統一格式

   def migrate_annotations(input_path, output_path):
       """將 annotations.json → 統一格式"""
       # 1. 讀取 annotations.json
       # 2. 轉換 bbox: {x1,y1,x2,y2} → [x1,y1,x2,y2]
       # 3. 轉換 timestamp → ISO 8601
       # 4. 轉換 image_path → 相對路徑
       # 5. 標記 source = "webcam"
       # 6. 寫入統一格式

   def migrate_feedback(input_path, output_path):
       """將 feedback.jsonl → 統一格式"""
       # 1. 讀取 feedback.jsonl
       # 2. 補充 class_name_cn（從 LabelMapper 取得）
       # 3. 標記 source = "web"
       # 4. 寫入統一格式

   def merge_and_deduplicate(annotations, feedback):
       """合併並去重"""
       # 根據 timestamp + class_name + bbox 相似度判斷重複
   ```

2. **執行遷移**
   ```bash
   # 備份原始資料
   cp data/annotations/annotations.json data/annotations/annotations.json.bak
   cp data/feedback/feedback.jsonl data/feedback/feedback.jsonl.bak

   # 執行遷移
   uv run python scripts/migrate_data.py

   # 驗證遷移結果
   uv run python scripts/migrate_data.py --verify
   ```

### 階段五：重構 main.py 使用共用引擎

**步驟：**

1. **替換 main.py 中的直接偵測邏輯**
   ```python
   # 之前
   self.detector = YOLODetector(...)
   result = self.detector.detect(frame)

   # 之後
   self.engine = DetectionEngine(config)
   detections = self.engine.detect(frame)
   ```

2. **替換 web_server.py 中的偵測邏輯**
   ```python
   # 之前（散落在 WebDetectionServer 各處）
   self.detector = YOLODetector(...)
   self.stabilizer = DetectionStabilizer(...)
   # ... 大量獨立初始化和處理

   # 之後
   self.engine = DetectionEngine(config)
   detections = self.engine.detect(frame)
   ```

---

## 四、檔案變更清單

### 新建檔案
| 檔案 | 說明 |
|------|------|
| `src/core/__init__.py` | 核心模組初始化 |
| `src/core/detection_engine.py` | 共用偵測引擎 |
| `src/core/data_manager.py` | 統一資料管理 |
| `scripts/migrate_data.py` | 歷史資料遷移腳本 |

### 修改檔案
| 檔案 | 變更內容 |
|------|----------|
| `src/main.py` | 替換為使用 DetectionEngine，整合所有新功能 |
| `src/web_server.py` | 替換為使用 DetectionEngine，新增 annotation API |
| `src/static/app.js` | 新增標註介面 |
| `src/static/style.css` | 標註介面樣式 |
| `data/custom_classes.json` | 不變，兩版本共用 |

---

## 五、優先順序建議

| 優先級 | 任務 | 預估影響 | 前置條件 |
|:------:|------|----------|----------|
| 🔴 P0 | 建立共用 DetectionEngine | 消除程式碼重複，後續所有工作的基礎 | 無 |
| 🔴 P0 | 移植 DetectionStabilizer 到 Webcam | 直接提升偵測穩定性 | DetectionEngine |
| 🟡 P1 | 移植別名 + PromptEnhancer 到 Webcam | 提升辨識準確度 | DetectionEngine |
| 🟡 P1 | 統一資料格式 + 遷移腳本 | 兩版本資料可互通 | 無 |
| 🟡 P1 | 移植槽位管理到 Webcam | 控制 CLIP 類別數量 | DetectionEngine |
| 🟢 P2 | 移植 AnnotationManager 到 Web | Web 版本也能手動標註 | 統一資料格式 |
| 🟢 P2 | 移植 DatabaseManager 到 Web | 長期記錄統一 | UnifiedDataManager |
| 🔵 P3 | 整合 FeedbackManager 到 Webcam (Tkinter UI) | Webcam 版也能糾正偵測 | DetectionEngine |

---

## 六、資料整合策略

### 6.1 現有資料統計

| 資料來源 | 筆數 | 時間範圍 | 類別 |
|----------|:----:|----------|------|
| annotations.json (Webcam) | 37 筆 | 2026-03-12 ~ 03-15 | cell phone, bottle, cup, laptop, mouse, remote 等 |
| feedback.jsonl (Web) | 20 筆 | 2026-03-19 | cup, cell phone, book, remote, laptop, mouse, glasses |
| detection_logs (Web) | 每日 JSONL | 2026-03-18 ~ 03-19 | 所有偵測類別 |

### 6.2 整合原則

1. **保留所有原始資料**：遷移時不刪除原始檔案，只建立新的統一格式檔案
2. **以相對路徑為準**：所有圖片路徑轉換為相對於專案根目錄的路徑
3. **annotations 資料視為高品質標註**：因為是人工透過 Tkinter 彈窗確認的
4. **feedback 資料視為用戶互動回饋**：包含 confirm/correct/false_positive 語意
5. **兩種資料互補**：annotations 提供精確標註，feedback 提供信心度校正

### 6.3 去重規則

當同一物品在兩個資料來源中都出現時：
- 若 `timestamp` 差距 < 5 秒 且 `class_name` 相同 且 bbox IoU > 0.5 → 視為重複，保留 annotations 版本（較完整）
- 其餘情況視為不同記錄，全部保留

---

## 七、驗證清單

整合完成後的驗證項目：

- [ ] Webcam 版本偵測結果經過 DetectionStabilizer 穩定化
- [ ] Webcam 版本自動解析別名（mug → cup）
- [ ] Webcam 版本使用 PromptEnhancer 增強 CLIP 提示
- [ ] Webcam 版本遵守 10 類別上限
- [ ] Web 版本可以查看/新增標註
- [ ] 兩個版本寫入的資料可互相讀取
- [ ] 歷史資料遷移無遺失（37 + 20 筆全部保留）
- [ ] custom_classes.json 兩版本共用，變更即時同步
- [ ] 重啟任一版本後，能正確載入所有設定和資料
