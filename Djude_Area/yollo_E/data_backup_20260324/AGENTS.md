<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-16 | Updated: 2026-03-16 -->

# data

## Purpose
資料儲存目錄，包含 SQLite 資料庫、標註檔案、訓練資料集、圖片儲存等。

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `annotations/` | 標註 JSON 檔案和圖片 |
| `datasets/` | 訓練資料集（raw/annotated） |

## For AI Agents

### Working In This Directory
- 資料庫路徑：`data/database/items.db`（由 config.py 管理）
- 標註檔案：`data/annotations/annotations.json`
- 訓練圖片：`data/datasets/annotated/`
- 原始圖片：`data/datasets/raw/`

### 資料庫初始化
首次執行時會自動建立 SQLite 資料庫：
```python
from src.database.db_manager import DatabaseManager
db = DatabaseManager("data/database/items.db")  # 自動建立 tables
```

### 標註檔案格式
```json
{
  "version": "1.0",
  "records": [
    {
      "id": "uuid",
      "timestamp": 1234567890.0,
      "session_id": 1,
      "class_name": "cell phone",
      "class_name_cn": "手機",
      "confidence": 0.95,
      "bbox": [100, 100, 200, 200],
      "image_path": "data/annotation_images/uuid.jpg",
      "description": "手機",
      "custom_label": "cell phone",
      "status": "annotated",
      "owner": "使用者",
      "notes": ""
    }
  ]
}
```

