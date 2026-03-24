# Webcam/Web 版本整合設計規格

> 建立日期：2026-03-24
> 目標：統一 Webcam 版本 (main.py) 和 Web 版本 (web_server.py) 的偵測邏輯與資料格式

---

## 一、設計決策摘要

| 決策項目 | 選擇 | 說明 |
|----------|------|------|
| 整合範圍 | P0 + P1 一次性完成 | 核心功能全部統一 |
| 架構模式 | 完整封裝 | `DetectionEngine` 封裝所有邏輯 |
| 資料格式 | 保持 `annotations.json` 為唯一格式 | 遷移 feedback 資料 |
| 圖片整合 | 統一存放到 `annotation_images/` | Web 圖片加 `feedback_` 前綴 |

---

## 二、架構總覽

```
┌─────────────────────────────────────────────────────────────┐
│                    共用核心模組 (src/core/)                    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              DetectionEngine                         │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │   │
│  │  │ YOLODetector │→│ Stabilizer │→│ 別名解析 + 槽位  │  │   │
│  │  └──────────┘  └──────────┘  └──────────────────┘  │   │
│  │         ↑                                      ↓    │   │
│  │  ┌──────────────────┐                  ┌───────────┐│   │
│  │  │ PromptEnhancer   │                  │ 中文映射  ││   │
│  │  └──────────────────┘                  └───────────┘│   │
│  └─────────────────────────────────────────────────────┘   │
│                          ↓                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              DataManager                             │   │
│  │  - 統一寫入 annotations.json                        │   │
│  │  - 統一圖片存放到 annotation_images/                 │   │
│  │  - 合併現有 FeedbackManager + AnnotationManager     │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                     UI 層（獨立）                            │
│  ┌──────────────────┐        ┌──────────────────────┐      │
│  │ Webcam (main.py) │        │ Web (web_server.py)  │      │
│  │ Tkinter + OpenCV │        │ FastAPI + WebSocket  │      │
│  └────────┬─────────┘        └──────────┬───────────┘      │
│           │                              │                  │
│           └──────────┬───────────────────┘                  │
│                      ↓                                      │
│           DetectionEngine.detect(frame)                     │
│                      ↓                                      │
│           DataManager.record(detections)                    │
└─────────────────────────────────────────────────────────────┘
```

**核心原則：**
- 兩版本共用 `DetectionEngine` 和 `DataManager`
- UI 層完全獨立，只負責影像擷取和結果顯示
- 所有資料統一輸出為 `annotations.json` 格式

---

## 三、DetectionEngine 設計

### 3.1 類別結構

```python
# src/core/detection_engine.py

class DetectionEngine:
    """完整封裝的偵測引擎"""

    def __init__(self, config: DetectionConfig):
        # 核心組件
        self.detector = YOLODetector(config.model_path, config.device)
        self.stabilizer = DetectionStabilizer(window_size=3, min_hits=2)
        self.prompt_enhancer = PromptEnhancer()
        self.label_mapper = LabelMapper()

        # 槽位管理
        self.max_active_classes = config.max_active_classes  # 預設 10
        self._active_classes: OrderedDict = {}  # LRU 快取

        # 載入自訂類別和別名
        self._load_custom_classes(config.custom_classes_path)
        self._load_aliases()

    def detect(self, frame: np.ndarray) -> List[DetectionResult]:
        """
        完整偵測流程（兩版本共用）

        流程：
        1. YOLO 原始偵測
        2. 時序穩定化（Stabilizer）
        3. 別名解析（mug → cup）
        4. 中文標籤映射
        5. 回傳穩定的偵測結果
        """
        # 1. 原始偵測
        raw_detections = self.detector.detect(frame)

        # 2. 時序穩定化
        stable_detections = self.stabilizer.update(raw_detections)

        # 3. 別名解析 + 中文映射
        results = []
        for det in stable_detections:
            resolved_name = self._resolve_alias(det.class_name)
            cn_name = self.label_mapper.get_cn_label(resolved_name)
            results.append(DetectionResult(
                class_name=resolved_name,
                class_name_cn=cn_name,
                confidence=det.confidence,
                bbox=det.bbox
            ))

        return results

    def add_class(self, name_en: str, name_cn: str) -> dict:
        """新增偵測類別（含槽位檢查與 LRU 替換）"""
        ...

    def toggle_class(self, name_en: str, active: bool) -> dict:
        """啟用/停用類別"""
        ...

    def reset_session(self):
        """重置偵測狀態（新使用者連線時呼叫）"""
        self.stabilizer.reset()
```

### 3.2 關鍵特性

- 單一入口 `detect(frame)` 完成所有偵測流程
- 內建 LRU 槽位管理，超過上限自動替換
- 支援別名解析（mug→cup 等 35+ 映射）
- `reset_session()` 供 Web 版本處理多使用者切換

---

## 四、DataManager 設計

### 4.1 類別結構

```python
# src/core/data_manager.py

class DataManager:
    """統一資料管理器 - 輸出 annotations.json 格式"""

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._annotations_file = data_dir / "annotations" / "annotations.json"
        self._images_dir = data_dir / "annotations" / "annotation_images"

        self._lock = threading.Lock()
        self._load_existing_annotations()

    def record(
        self,
        detection: DetectionResult,
        frame: np.ndarray,
        source: str = "webcam",  # "webcam" | "web"
        feedback_type: str = "annotation",  # "annotation" | "confirm" | "correct" | "false_positive"
        correct_class: Optional[str] = None,
        owner: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """統一記錄偵測/回饋資料"""
        ...

    def migrate_feedback_data(self, feedback_dir: Path):
        """遷移 feedback.jsonl 到 annotations.json"""
        ...

    def get_stats(self) -> dict:
        """取得統計資訊"""
        ...
```

### 4.2 統一資料格式

```json
{
    "id": "20260324_143704_512943_cell_phone",
    "source": "webcam",
    "type": "annotation",
    "class_name": "cell phone",
    "class_name_cn": "手機",
    "confidence": 0.942,
    "bbox": [179.86, 138.57, 317.60, 374.90],
    "timestamp": "2026-03-24T14:37:04.512943",
    "session_id": "12",
    "image_path": "annotation_images/20260324_143704_cell_phone.jpg",
    "status": "annotated",
    "owner": "user1",
    "correct_class": null,
    "notes": ""
}
```

### 4.3 格式變更（相對於現有 annotations.json）

| 欄位 | 原格式 | 新格式 | 說明 |
|------|--------|--------|------|
| `bbox` | `{"x1":..., "y1":..., "x2":..., "y2":...}` | `[x1, y1, x2, y2]` | 統一為陣列 |
| `timestamp` | `"2026-03-12 14:37:04"` | `"2026-03-12T14:37:04.512943"` | ISO 8601 |
| `source` | 無 | `"webcam"` / `"web"` | 新增來源標記 |
| `type` | 無 | `"annotation"` / `"confirm"` / `"correct"` / `"false_positive"` | 新增類型標記 |
| `correct_class` | 無 | `string \| null` | 糾正時的正確類別 |

---

## 五、遷移策略

### 5.1 目錄結構變化

```
遷移前：
data/
├── annotations/
│   ├── annotations.json
│   └── annotation_images/
│       ├── 20260312_143704_cell_phone.jpg
│       └── ...
└── feedback/
    ├── feedback.jsonl
    └── images/
        ├── cup_20260319.jpg
        └── ...

遷移後：
data/
└── annotations/
    ├── annotations.json          # 合併後的統一格式
    ├── annotation_images/
    │   ├── 20260312_143704_cell_phone.jpg      # 原有
    │   ├── feedback_cup_20260319.jpg            # 遷移，加前綴
    │   └── ...
    └── annotations.json.bak      # 原檔備份
```

### 5.2 遷移腳本設計

```python
# scripts/migrate_data.py

def migrate_feedback_to_annotations():
    """
    將 feedback.jsonl 遷移到 annotations.json 格式

    步驟：
    1. 備份原始檔案
    2. 讀取 feedback.jsonl
    3. 轉換格式：
       - bbox: [x1,y1,x2,y2] ✓（已是陣列）
       - timestamp: 轉換為 ISO 8601
       - 新增 source="web"
       - 新增 type=feedback_type
       - 補充 class_name_cn（從 LabelMapper）
    4. 移動圖片到 annotation_images/，加 feedback_ 前綴
    5. 更新 image_path 為相對路徑
    6. 合併到 annotations.json
    7. 原地保留 feedback.jsonl（標記為 .migrated）
    """
    ...

def verify_migration():
    """驗證遷移結果"""
    ...

if __name__ == "__main__":
    migrate_feedback_to_annotations()
    verify_migration()
```

### 5.3 去重規則

- 若 `timestamp` 差距 < 5 秒 且 `class_name` 相同 且 bbox IoU > 0.5 → 視為重複，保留原有 annotations 版本

---

## 六、檔案變更清單

### 6.1 新建檔案

| 檔案 | 說明 |
|------|------|
| `src/core/__init__.py` | 核心模組初始化 |
| `src/core/detection_engine.py` | 共用偵測引擎 |
| `src/core/data_manager.py` | 統一資料管理器 |
| `scripts/migrate_data.py` | 資料遷移腳本 |

### 6.2 修改檔案

| 檔案 | 變更內容 |
|------|----------|
| `src/main.py` | 替換為使用 `DetectionEngine` + `DataManager` |
| `src/web_server.py` | 替換為使用 `DetectionEngine` + `DataManager` |
| `data/annotations/annotations.json` | 格式微調（bbox 陣列化、timestamp ISO 化） |

---

## 七、預期成果

- ✅ Webcam 版本偵測結果經過 DetectionStabilizer 穩定化
- ✅ Webcam 版本自動解析別名（mug → cup）
- ✅ 兩版本使用相同的偵測邏輯
- ✅ 所有資料統一為 annotations.json 格式
- ✅ 圖片統一存放在 annotation_images/
- ✅ 歷史資料完整遷移（37 + 20 筆全部保留）
