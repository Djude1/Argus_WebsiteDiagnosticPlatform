# Webcam/Web 版本整合實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 統一 Webcam 版本 (main.py) 和 Web 版本 (web_server.py) 的偵測邏輯與資料格式

**Architecture:** 建立 `DetectionEngine` 封裝所有偵測邏輯（YOLO、Stabilizer、別名解析、槽位管理），建立 `DataManager` 統一管理 annotations.json 輸出，遷移現有 feedback 資料到統一格式。

**Tech Stack:** Python, YOLOE-26, FastAPI, Tkinter, OpenCV

---

## 檔案結構

```
src/
├── core/                              # 新建：核心共用模組
│   ├── __init__.py
│   ├── detection_engine.py            # DetectionEngine 類別
│   └── data_manager.py               # DataManager 類別
├── detection/
│   ├── yolo_detector.py              # YOLODetector（現有）
│   ├── stabilizer.py                  # DetectionStabilizer（現有）
│   ├── prompt_enhancer.py            # PromptEnhancer（現有）
│   └── label_mapper.py               # LabelMapper（現有）
├── annotation/
│   ├── annotation_manager.py          # AnnotationManager（現有）
│   └── models.py                     # AnnotationRecord 等（現有）
├── main.py                           # 修改：使用 DetectionEngine + DataManager
├── web_server.py                     # 修改：使用 DetectionEngine + DataManager
scripts/
└── migrate_data.py                   # 新建：資料遷移腳本
data/
├── annotations/
│   └── annotations.json             # 修改：統一格式
└── feedback/                        # 遷移後保留 .migrated 標記
    ├── feedback.jsonl.migrated
    └── images/                       # 圖片遷移到 annotation_images/
```

---

## Task 1: 建立 core 模組結構

**Files:**
- Create: `src/core/__init__.py`

- [ ] **Step 1: 建立目錄結構**

```bash
mkdir -p src/core
```

- [ ] **Step 2: 建立 src/core/__init__.py**

```python
"""核心共用模組"""

from .detection_engine import DetectionEngine, DetectionConfig
from .data_manager import DataManager

__all__ = ["DetectionEngine", "DetectionConfig", "DataManager"]
```

- [ ] **Step 3: Commit**

```bash
git add src/core/__init__.py
git commit -m "feat: create core module structure"
```

---

## Task 2: 建立 DetectionEngine

**Files:**
- Create: `src/core/detection_engine.py`
- Reference: `src/detection/yolo_detector.py`, `src/detection/stabilizer.py`, `src/detection/prompt_enhancer.py`

- [ ] **Step 1: 建立 DetectionConfig 資料類別**

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class DetectionConfig:
    """偵測引擎配置"""
    model_path: str = "models/yoloe-26-seg.pt"
    device: str = "cuda"
    confidence: float = 0.25
    max_active_classes: int = 10
    custom_classes_path: str = "data/custom_classes.json"
```

- [ ] **Step 2: 建立 DetectionEngine 類別框架**

```python
from pathlib import Path
from typing import List, Optional, OrderedDict
import numpy as np
from loguru import logger

from detection.yolo_detector import YOLODetector, DetectionResult
from detection.stabilizer import DetectionStabilizer
from detection.prompt_enhancer import PromptEnhancer, ALIAS_MAPPING
from detection.label_mapper import LabelMapper

class DetectionEngine:
    """完整封裝的偵測引擎"""

    def __init__(self, config: DetectionConfig):
        self.config = config
        self.detector = YOLODetector(config.model_path, config.device)
        self.stabilizer = DetectionStabilizer(window_size=3, min_hits=2)
        self.prompt_enhancer = PromptEnhancer()
        self.label_mapper = LabelMapper()
        self.max_active_classes = config.max_active_classes
        self._active_classes: OrderedDict = {}
        self._load_custom_classes(Path(config.custom_classes_path))
        logger.info("DetectionEngine 已初始化")
```

- [ ] **Step 3: 實作 detect() 方法**

```python
    def detect(self, frame: np.ndarray) -> List[DetectionResult]:
        """完整偵測流程"""
        raw_detections = self.detector.detect(frame, conf=config.confidence)
        stable_detections = self.stabilizer.update(raw_detections)
        results = []
        for det in stable_detections:
            resolved_name = self._resolve_alias(det.class_name)
            cn_name = self.label_mapper.get_cn_label(resolved_name)
            det.class_name = resolved_name
            det.class_name_cn = cn_name
            results.append(det)
        return results
```

- [ ] **Step 4: 實作 _resolve_alias() 方法**

```python
    def _resolve_alias(self, class_name: str) -> str:
        """解析類別別名"""
        return ALIAS_MAPPING.get(class_name, class_name)
```

- [ ] **Step 5: 實作 _load_custom_classes() 方法**

```python
    def _load_custom_classes(self, custom_classes_path: Path):
        """載入自訂類別"""
        if not custom_classes_path.exists():
            return
        import json
        with open(custom_classes_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for cls in data.get("classes", []):
            if cls.get("active"):
                self._active_classes[cls["name_en"]] = cls["name_cn"]
        logger.info(f"已載入 {len(self._active_classes)} 個自訂類別")
```

- [ ] **Step 6: 實作 reset_session() 方法**

```python
    def reset_session(self):
        """重置偵測狀態（新使用者連線時呼叫）"""
        self.stabilizer.reset()
        logger.info("偵測狀態已重置")
```

- [ ] **Step 7: Commit**

```bash
git add src/core/detection_engine.py
git commit -m "feat: implement DetectionEngine class"
```

---

## Task 3: 建立 DataManager

**Files:**
- Create: `src/core/data_manager.py`
- Reference: `src/annotation/annotation_manager.py`, `src/annotation/models.py`

- [ ] **Step 1: 建立 DataManager 類別框架**

```python
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from loguru import logger
import cv2
import numpy as np

class DataManager:
    """統一資料管理器 - 輸出 annotations.json 格式"""

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._annotations_file = data_dir / "annotations" / "annotations.json"
        self._images_dir = data_dir / "annotations" / "annotation_images"
        self._lock = threading.Lock()
        self._annotations: Dict[str, Any] = {"records": []}
        self._load_existing_annotations()
        logger.info("DataManager 已初始化")
```

- [ ] **Step 2: 實作 _load_existing_annotations() 方法**

```python
    def _load_existing_annotations(self):
        """載入現有 annotations.json"""
        if self._annotations_file.exists():
            with open(self._annotations_file, "r", encoding="utf-8") as f:
                self._annotations = json.load(f)
        else:
            self._annotations = {"version": "2.0", "records": []}
```

- [ ] **Step 3: 實作 record() 方法**

```python
    def record(
        self,
        detection: Any,
        frame: np.ndarray,
        source: str = "webcam",
        feedback_type: str = "annotation",
        correct_class: Optional[str] = None,
        owner: Optional[str] = None,
        notes: str = "",
    ) -> dict:
        """統一記錄偵測/回饋資料"""
        with self._lock:
            timestamp = datetime.now()
            record_id = f"{timestamp.strftime('%Y%m%d_%H%M%S_%f')}_{detection.class_name.replace(' ', '_')}"
            image_filename = f"{record_id}.jpg"
            image_path = self._images_dir / image_filename
            self._images_dir.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(image_path), frame)
            record = {
                "id": record_id,
                "source": source,
                "type": feedback_type,
                "class_name": detection.class_name,
                "class_name_cn": getattr(detection, "class_name_cn", ""),
                "confidence": float(detection.confidence),
                "bbox": list(detection.bbox.to_tuple()) if hasattr(detection.bbox, "to_tuple") else list(detection.bbox),
                "timestamp": timestamp.isoformat(),
                "session_id": "",
                "image_path": f"annotation_images/{image_filename}",
                "status": "annotated",
                "owner": owner or "",
                "correct_class": correct_class,
                "notes": notes,
            }
            self._annotations["records"].append(record)
            self._save_annotations()
            return record
```

- [ ] **Step 4: 實作 _save_annotations() 方法**

```python
    def _save_annotations(self):
        """儲存 annotations.json"""
        self._annotations_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._annotations_file, "w", encoding="utf-8") as f:
            json.dump(self._annotations, f, indent=2, ensure_ascii=False)
```

- [ ] **Step 5: 實作 get_stats() 方法**

```python
    def get_stats(self) -> dict:
        """取得統計資訊"""
        records = self._annotations.get("records", [])
        return {
            "total": len(records),
            "by_source": self._count_by_field(records, "source"),
            "by_type": self._count_by_field(records, "type"),
            "by_class": self._count_by_field(records, "class_name"),
        }

    def _count_by_field(self, records: List[dict], field: str) -> Dict[str, int]:
        counts = {}
        for r in records:
            key = r.get(field, "unknown")
            counts[key] = counts.get(key, 0) + 1
        return counts
```

- [ ] **Step 6: Commit**

```bash
git add src/core/data_manager.py
git commit -m "feat: implement DataManager class"
```

---

## Task 4: 修改 web_server.py 使用 DetectionEngine + DataManager

**Files:**
- Modify: `src/web_server.py`
- Reference: `src/core/detection_engine.py`, `src/core/data_manager.py`

- [ ] **Step 1: 更新匯入語句**

```python
# 替換
from detection.yolo_detector import YOLODetector
from detection.stabilizer import DetectionStabilizer
from detection.label_mapper import LabelMapper, EN_TO_CN_MAPPING, CN_TO_EN_MAPPING
from detection.feedback import FeedbackManager
# 改為
from core import DetectionEngine, DataManager, DetectionConfig
```

- [ ] **Step 2: 替換全域變數初始化**

```python
# 替換
detector = YOLODetector(...)
stabilizer = DetectionStabilizer(...)
label_mapper = LabelMapper()
# 改為
detection_config = DetectionConfig(
    model_path=str(model_path),
    device=device,
    custom_classes_path="data/custom_classes.json",
)
engine = DetectionEngine(detection_config)
data_manager = DataManager(Path("data"))
```

- [ ] **Step 3: 修改 detect_frame() 函數**

```python
# 替換
raw_results = detector.detect(frame, conf=CONF_TH)
stable_results = stabilizer.update(raw_results)
# 改為
stable_results = engine.detect(frame)
```

- [ ] **Step 4: 修改 record_feedback() 中的資料寫入**

```python
# 替換 AnnotationManager 或 FeedbackManager 的呼叫
# 改為 data_manager.record()
```

- [ ] **Step 5: 在新連線時呼叫 reset_session()**

```python
# 在 WebSocket 連線建立時
engine.reset_session()
```

- [ ] **Step 6: Commit**

```bash
git add src/web_server.py
git commit -m "refactor: web_server use DetectionEngine and DataManager"
```

---

## Task 5: 修改 main.py 使用 DetectionEngine + DataManager

**Files:**
- Modify: `src/main.py`
- Reference: `src/core/detection_engine.py`, `src/core/data_manager.py`

- [ ] **Step 1: 更新匯入語句**

```python
# 新增
from core import DetectionEngine, DataManager, DetectionConfig
```

- [ ] **Step 2: 在 YOLODetectionSystem.__init__ 中初始化 engine 和 data_manager**

```python
self.detection_config = DetectionConfig(
    model_path=str(model_path) if model_path else None,
    device=get_device(),
    custom_classes_path="data/custom_classes.json",
)
self.engine = DetectionEngine(self.detection_config)
self.data_manager = DataManager(Path("data"))
```

- [ ] **Step 3: 修改檢測流程**

```python
# 替換
raw_results = self.detector.detect(frame, conf=self.confidence)
# 改為
results = self.engine.detect(frame)
```

- [ ] **Step 4: Commit**

```bash
git add src/main.py
git commit -m "refactor: main use DetectionEngine and DataManager"
```

---

## Task 6: 建立資料遷移腳本

**Files:**
- Create: `scripts/migrate_data.py`
- Reference: `src/core/data_manager.py`, `data/feedback/feedback.jsonl`

- [ ] **Step 1: 建立遷移腳本框架**

```python
#!/usr/bin/env python3
"""資料遷移腳本：將 feedback.jsonl 遷移到 annotations.json 格式"""

import json
import shutil
from pathlib import Path
from datetime import datetime
from collections import OrderedDict

FEEDBACK_DIR = Path("data/feedback")
ANNOTATIONS_DIR = Path("data/annotations")
ANNOTATIONS_FILE = ANNOTATIONS_DIR / "annotations.json"
IMAGES_DIR = ANNOTATIONS_DIR / "annotation_images"
FEEDBACK_IMAGES_DIR = FEEDBACK_DIR / "images"
```

- [ ] **Step 2: 實作載入 feedback.jsonl**

```python
def load_feedback_data():
    """載入 feedback.jsonl"""
    feedback_file = FEEDBACK_DIR / "feedback.jsonl"
    if not feedback_file.exists():
        print("feedback.jsonl 不存在，跳過遷移")
        return []
    records = []
    with open(feedback_file, "r", encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line.strip()))
    print(f"載入 {len(records)} 筆 feedback 記錄")
    return records
```

- [ ] **Step 3: 實作轉換記錄格式**

```python
def convert_feedback_to_annotation(feedback_record: dict) -> dict:
    """將 feedback 格式轉換為 annotation 格式"""
    timestamp = feedback_record.get("timestamp", "")
    class_name = feedback_record.get("class_name", "unknown")
    record_id = f"feedback_{timestamp.replace(' ', '_').replace(':', '').replace('-', '')}_{class_name.replace(' ', '_')}"
    return {
        "id": record_id,
        "source": "web",
        "type": feedback_record.get("feedback_type", "confirm"),
        "class_name": class_name,
        "class_name_cn": feedback_record.get("class_name_cn", ""),
        "confidence": feedback_record.get("confidence", 0.0),
        "bbox": feedback_record.get("bbox", [0, 0, 0, 0]),
        "timestamp": timestamp,
        "session_id": feedback_record.get("session_id", ""),
        "image_path": f"annotation_images/feedback_{Path(feedback_record.get('image_path', '')).name}",
        "status": "annotated",
        "owner": feedback_record.get("owner", ""),
        "correct_class": feedback_record.get("correct_class"),
        "notes": feedback_record.get("notes", ""),
    }
```

- [ ] **Step 4: 實作遷移圖片**

```python
def migrate_images():
    """遷移圖片到 annotation_images/"""
    if not FEEDBACK_IMAGES_DIR.exists():
        return
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    for img_file in FEEDBACK_IMAGES_DIR.glob("*"):
        dest_file = IMAGES_DIR / f"feedback_{img_file.name}"
        shutil.copy2(img_file, dest_file)
        print(f"遷移圖片: {img_file.name} -> feedback_{img_file.name}")
```

- [ ] **Step 5: 實作主遷移函數**

```python
def migrate_feedback_to_annotations():
    """執行遷移"""
    print("=" * 50)
    print("開始遷移 feedback 到 annotations")
    print("=" * 50)
    # 1. 備份
    if ANNOTATIONS_FILE.exists():
        backup_file = ANNOTATIONS_DIR / "annotations.json.bak"
        shutil.copy2(ANNOTATIONS_FILE, backup_file)
        print(f"已備份 annotations.json -> annotations.json.bak")
    # 2. 載入現有 annotations
    if ANNOTATIONS_FILE.exists():
        with open(ANNOTATIONS_FILE, "r", encoding="utf-8") as f:
            annotations = json.load(f)
    else:
        annotations = {"version": "2.0", "records": []}
    # 3. 遷移圖片
    migrate_images()
    # 4. 轉換並新增 feedback 記錄
    feedback_records = load_feedback_data()
    for fb in feedback_records:
        ann = convert_feedback_to_annotation(fb)
        annotations["records"].append(ann)
    # 5. 儲存
    with open(ANNOTATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(annotations, f, indent=2, ensure_ascii=False)
    # 6. 標記 feedback.jsonl
    feedback_file = FEEDBACK_DIR / "feedback.jsonl"
    if feedback_file.exists():
        feedback_file.rename(FEEDBACK_DIR / "feedback.jsonl.migrated")
    print(f"遷移完成，共 {len(annotations['records'])} 筆記錄")
```

- [ ] **Step 6: 實作驗證函數**

```python
def verify_migration():
    """驗證遷移結果"""
    print("\n驗證遷移結果...")
    with open(ANNOTATIONS_FILE, "r", encoding="utf-8") as f:
        annotations = json.load(f)
    records = annotations.get("records", [])
    web_records = [r for r in records if r.get("source") == "web"]
    print(f"總記錄數: {len(records)}")
    print(f"Web 來源記錄數: {len(web_records)}")
    print(f"圖片數量: {len(list(IMAGES_DIR.glob('*')))}")
    return len(web_records) > 0
```

- [ ] **Step 7: Commit**

```bash
git add scripts/migrate_data.py
git commit -m "feat: add data migration script for feedback to annotations"
```

---

## Task 7: 執行遷移並驗證

**Files:**
- Execute: `scripts/migrate_data.py`
- Verify: `data/annotations/annotations.json`

- [ ] **Step 1: 備份現有資料**

```bash
cp -r data data_backup_20260324
```

- [ ] **Step 2: 執行遷移腳本**

```bash
uv run python scripts/migrate_data.py
```

- [ ] **Step 3: 驗證 annotations.json 格式**

```bash
python -c "import json; data=json.load(open('data/annotations/annotations.json')); print(f'總記錄: {len(data[\"records\"])}'); print(f'Version: {data.get(\"version\")}'); print(f'第一筆記錄: {data[\"records\"][0] if data[\"records\"] else \"無\"}')"
```

- [ ] **Step 4: 驗證圖片遷移**

```bash
ls data/annotations/annotation_images/ | wc -l
ls data/feedback/images/ 2>/dev/null || echo "feedback/images 已遷移"
```

- [ ] **Step 5: Commit 遷移後的 annotations.json**

```bash
git add data/annotations/annotations.json
git commit -m "data: migrate feedback to unified annotations format"
```

---

## Task 8: 整合測試

**Files:**
- Test: `src/main.py`, `src/web_server.py`

- [ ] **Step 1: 測試 Webcam 版本啟動**

```bash
timeout 10 uv run python src/main.py --source webcam || true
```

- [ ] **Step 2: 測試 Web 版本啟動**

```bash
timeout 10 uv run python src/web_server.py --port 8080 || true
```

- [ ] **Step 3: Commit 最終整合**

```bash
git add -A
git commit -m "feat: complete webcam/web integration"
```

---

## 預期產出

- `src/core/detection_engine.py` - DetectionEngine 類別
- `src/core/data_manager.py` - DataManager 類別
- `scripts/migrate_data.py` - 資料遷移腳本
- `src/main.py` - 使用 DetectionEngine + DataManager
- `src/web_server.py` - 使用 DetectionEngine + DataManager
- `data/annotations/annotations.json` - 統一格式（含遷移後的 feedback 資料）
