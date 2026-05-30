<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-16 | Updated: 2026-03-16 -->

# models

## Purpose
模型檔案存放目錄，包含預訓練模型和自定義訓練模型。

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `pretrained/` | 預訓練模型存放處 |
| `custom/` | 自定義訓練模型存放處 |

## For AI Agents

### Working In This Directory
- 預訓練模型：放在 `models/pretrained/`
- 自定義模型：放在 `models/custom/`
- 預設使用專案根目錄的 `yoloe-26s-seg.pt`

### 模型配置

```python
# config.py 中的模型配置
@dataclass
class ModelConfig:
    model_path: str = "yoloe-26s-seg.pt"  # 預訓練模型
    custom_model_path: str = "models/custom/yoloe_custom.pt"  # 自定義模型
```

### YOLOE-26S 模型資訊
| 特性 | 說明 |
|------|------|
| 開放詞彙 | 可偵測任何物品，不限於 COCO 80 類 |
| 文字提示 | 透過 DETECTION_CLASSES 設定要偵測的物品 |
| 實例分割 | 同時輸出邊界框和分割遮罩 |
| 模型大小 | YOLOE-26S 約 29MB |
| 最低 GPU | NVIDIA RTX 3060 (6GB VRAM) |

### 模型下載
首次執行時會自動下載到快取目錄：
```python
from ultralytics import YOLO
model = YOLO("yoloe-26s-seg.pt")  # 自動下載
```

