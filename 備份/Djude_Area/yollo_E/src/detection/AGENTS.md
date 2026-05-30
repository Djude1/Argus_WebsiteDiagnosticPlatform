<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-16 | Updated: 2026-03-16 -->

# detection

## Purpose
YOLO 物件偵測模組，支援 YOLOE-26 開放詞彙實例分割模型，可偵測任意物品不限於預訓練類別。

## Key Files

| File | Description |
|------|-------------|
| `yolo_detector.py` | YOLO 偵測器核心類別，封裝 Ultralytics YOLOE 模型 |
| `label_mapper.py` | 中英文標籤對應表，物品名稱翻譯 |
| `__init__.py` | 模組匯出 |

## For AI Agents

### Working In This Directory
- 使用 Ultralytics YOLOE 模型進行開放詞彙偵測
- 透過 `prompt_classes` 參數指定要偵測的物品名稱
- 支援 GPU (CUDA) 和 CPU 自動切換

### YOLOE-26 開放詞彙偵測

```python
# 初始化偵測器
detector = YOLOE_26Detector(
    model_path="yoloe-26s-seg.pt",
    confidence_threshold=0.5,
    device="auto",
    prompt_classes=["cell phone", "bottle", "cup", "backpack"]
)

# 執行偵測
result = detector.detect(frame)
# result.detections: List[Detection]
# result.fps: float
```

### Class Interface

```python
class FrameDetectionResult:
    detections: List[Detection]  # 偵測結果列表
    fps: float                  # 偵測幀率
    count: int                  # 偵測物體數量
    timestamp: float            # 時間戳

class Detection:
    bbox: List[float]           # 邊界框 [x1, y1, x2, y2]
    confidence: float           # 信心度
    class_id: int              # 類別 ID
    class_name: str            # 類別名稱（英文）
    class_name_cn: str         # 類別名稱（中文）
    mask: np.ndarray           # 分割遮罩（可選）
```

### DETECTION_CLASSES 環境變數
設定要偵測的物品（用逗號分隔）：
```env
DETECTION_CLASSES=cell phone,bottle,cup,handbag,backpack,remote,mouse,keyboard,laptop,wallet,keys
```

## Dependencies

### Internal
- `src/config.py` - 取得模型路徑和偵測類別

### External
- ultralytics - YOLO 框架
- numpy - 陣列處理

