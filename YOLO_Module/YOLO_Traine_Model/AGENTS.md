<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-14 | Updated: 2026-03-14 -->

# YOLO_Traine_Model

## Purpose
已訓練的 YOLO 模型檔案目錄，用於物件檢測和分割任務。

## Key Files

| File | Description |
|------|-------------|
| `yolo11n.pt` | YOLO 11 nano 基礎模型 |
| `yolo26n.pt` | YOLO 26 nano 模型 |
| `1_test.pt` | 測試用自定義訓練模型 |

## For AI Agents

### Working In This Directory
- 模型格式: PyTorch (.pt)
- 載入方式: `YOLO('yolo11n.pt')`
- 主要用途: 通用物件檢測

### Model Selection Guide
| Model | Size | Speed | Accuracy | Use Case |
|-------|------|-------|----------|----------|
| yolo11n.pt | Nano | 最快 | 較低 | 即時檢測 |
| yolo26n.pt | Nano | 快 | 中等 | 通用檢測 |

## Dependencies

### External
- Ultralytics YOLO
- PyTorch

<!-- MANUAL: -->
