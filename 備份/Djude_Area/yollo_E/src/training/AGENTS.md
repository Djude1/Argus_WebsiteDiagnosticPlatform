<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-16 | Updated: 2026-03-16 -->

# training

## Purpose
自定義模型訓練模組，收集訓練資料並使用 Ultralytics 框架訓練自定義 YOLO 模型。

## Key Files

| File | Description |
|------|-------------|
| `train_custom.py` | 自定義模型訓練腳本 |
| `data_collector.py` | 訓練資料收集器，自動收集偵測圖片 |
| `__init__.py` | 模組匯出 |

## For AI Agents

### Working In This Directory
- 使用 Ultralytics YOLO 訓練框架
- 資料格式：YOLO COCO 格式（邊界框 + 類別）
- 支援遷移學習（從預訓練模型微調）

### 訓練流程

```bash
# 1. 收集訓練資料
uv run python src/training/data_collector.py

# 2. 使用 labelimg 標註圖片
uv run labelimg

# 3. 訓練模型
uv run python src/training/train_custom.py \
    --data data/datasets/custom/data.yaml \
    --epochs 100 \
    --model yoloe-26s-seg.pt
```

### data_collector.py 功能
- 自動儲存偵測到物品的畫面
- 儲存格式：YOLO 邊界框格式
- 儲存位置：`data/datasets/annotated/`

### train_custom.py 功能
- 使用 Ultralytics YOLO 訓練
- 支援 GPU 加速
- 自動驗證模型準確率

## Dependencies

### Internal
- `src/detection/` - YOLO 偵測器
- `src/config.py` - 配置管理

### External
- ultralytics - 訓練框架
- labelimg - 圖片標註工具

