<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-14 | Updated: 2026-03-14 -->

# YOLO_Module

## Purpose
YOLO 模型訓練模組，包含已訓練的模型檔案、訓練數據集和訓練筆記本。

## Key Files

| File | Description |
|------|-------------|
| `yolo_wandb_training.ipynb` | YOLO 訓練 Jupyter 筆記本 (整合 Weights & Biases) |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `YOLO_Traine_Model/` | 已訓練的 YOLO 模型檔案 |
| `YOLO_Training_Datasets/` | 訓練數據集 (壓縮檔) |

## For AI Agents

### Working In This Directory
- 訓練模型使用 Ultralytics YOLO
- 數據集格式: YOLO 格式 (images + labels)
- 使用 W&B 追蹤訓練實驗

### Model Files
| File | Description |
|------|-------------|
| `yolo11n.pt` | YOLO 11 nano 模型 |
| `yolo26n.pt` | YOLO 26 nano 模型 |
| `1_test.pt` | 測試模型 |

### Testing Requirements
- 訓練前驗證數據集完整性
- 訓練後使用驗證集評估 mAP

## Dependencies

### External
- Ultralytics
- Weights & Biases (wandb)
- PyTorch

<!-- MANUAL: -->
