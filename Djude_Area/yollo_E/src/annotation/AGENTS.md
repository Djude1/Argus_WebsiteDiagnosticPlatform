<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-16 | Updated: 2026-03-16 -->

# annotation

## Purpose
物品標註管理模組，記錄偵測到的物品並提供標籤編輯介面，支援中文/英文標籤對應。

## Key Files

| File | Description |
|------|-------------|
| `annotation_manager.py` | 標註管理器，處理標註 CRUD 操作 |
| `models.py` | 標註資料模型定義 |
| `__init__.py` | 模組匯出 |

## For AI Agents

### Working In This Directory
- 標註檔案格式：JSON (`data/annotations/annotations.json`)
- 圖片儲存：`data/annotation_images/`
- 支援 Tkinter GUI 進行標籤編輯

### AnnotationRecord 結構

```python
class AnnotationRecord:
    id: str                    # UUID
    timestamp: float          # 時間戳
    session_id: Optional[int] # 關聯的偵測會話 ID
    class_name: str           # YOLO 類別名稱（英文）
    class_name_cn: str        # YOLO 類別名稱（中文）
    confidence: float         # 信心度
    bbox: List[float]         # 邊界框 [x1, y1, x2, y2]
    image_path: str           # 關聯圖片路徑
    description: str         # 物品描述（中文標籤）
    custom_label: str         # 自定義標籤（英文）
    status: AnnotationStatus  # 標註狀態
    owner: str                # 標註者
    notes: str                # 備註
```

### AnnotationStatus 枚舉
- `PENDING` - 待標註
- `ANNOTATED` - 已標註
- `REJECTED` - 已拒絕

### 使用範例

```python
from src.annotation.annotation_manager import AnnotationManager, AnnotationConfig

config = AnnotationConfig(
    annotation_file="data/annotations/annotations.json",
    image_dir="data/annotation_images",
    auto_save=True
)
manager = AnnotationManager(config)

# 新增偵測結果
records = manager.add_detections(detections, frame=frame)

# 取得標籤歷史
history = manager.get_label_history()

# 標記為已標註
manager.mark_annotated(
    record_id=record_id,
    owner="使用者",
    description="手機",
    custom_label="cell phone",
    notes=""
)

# 匯出 CSV
manager.export_to_csv("data/annotations/export.csv")
```

## Dependencies

### Internal
- `src/detection/` - 偵測結果結構
- `src/label_mapper.py` - 中英文對應

### External
- json - 標註檔案格式
- PIL - 圖片處理
- tkinter - GUI 介面

