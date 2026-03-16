<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-14 | Updated: 2026-03-14 -->

# YOLO_Training_Datasets

## Purpose
YOLO 訓練數據集目錄，包含標註好的圖片數據用於模型訓練。

## Key Files

| File | Description |
|------|-------------|
| `11246001,38v3.zip` | 訓練數據集 (標註者 ID) |
| `11246034.zip` | 訓練數據集 |
| `11246038.zip` | 訓練數據集 |
| `11246041v3.zip` | 訓練數據集 |
| `data.zip` | 通用訓練數據 |

## For AI Agents

### Working In This Directory
- 數據集格式: YOLO 格式 (images/ + labels/)
- 解壓後結構:
  ```
  dataset/
  ├── images/
  │   ├── train/
  │   └── val/
  └── labels/
      ├── train/
      └── val/
  ```
- 標註文件: .txt (class_id x_center y_center width height)

### Training Usage
```python
from ultralytics import YOLO
model = YOLO('yolo11n.pt')
model.train(data='dataset.yaml', epochs=100)
```

## Dependencies

### External
- Ultralytics YOLO
- 標註工具 (LabelImg, CVAT, etc.)

<!-- MANUAL: -->
