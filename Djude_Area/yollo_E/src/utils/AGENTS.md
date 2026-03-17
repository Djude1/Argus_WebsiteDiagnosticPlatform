<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-16 | Updated: 2026-03-16 -->

# utils

## Purpose
工具函式模組，提供日誌處理、偵測結果視覺化等輔助功能。

## Key Files

| File | Description |
|------|-------------|
| `logger.py` | 日誌配置和管理（已整合至 main.py 使用 loguru） |
| `visualization.py` | 偵測結果視覺化，繪製邊界框、標籤、FPS 等 |
| `__init__.py` | 模組匯出 |

## For AI Agents

### Working In This Directory
- visualization.py 使用 OpenCV 進行影像繪製
- 支援中文文字顯示（使用 Pillow 載入字體）
- 輸出圖片儲存至 `data/screenshots/`

### visualization.py 主要函式

```python
# 繪製偵測結果邊界框和標籤
def draw_detections(
    frame: np.ndarray,
    result: FrameDetectionResult,
    show_label_cn: bool = True
) -> np.ndarray

# 繪製 FPS 資訊
def draw_fps(frame: np.ndarray, fps: float, position: tuple) -> np.ndarray

# 繪製資訊面板
def draw_info_panel(frame: np.ndarray, info: dict, position: tuple) -> np.ndarray

# 繪製按鍵說明面板
def draw_help_panel(frame: np.ndarray, position: tuple) -> np.ndarray

# 繪製記錄指示器
def draw_recording_indicator(frame: np.ndarray, is_recording: bool, position: tuple) -> np.ndarray

# 儲存偵測圖片
def save_detection_image(frame: np.ndarray, subdir: str = "screenshots") -> str
```

### 使用範例

```python
from src.utils.visualization import draw_detections, draw_fps, draw_info_panel

# 繪製偵測結果
output = draw_detections(frame, result, show_label_cn=True)

# 繪製資訊面板
info = {"FPS": "25.0", "Objects": "3", "Source": "esp32"}
output = draw_info_panel(output, info, position=(10, 30))

# 儲存圖片
filepath = save_detection_image(output, "screenshots")
```

## Dependencies

### Internal
- `src/detection/` - FrameDetectionResult 結構

### External
- opencv-python - 影像處理和繪製
- pillow - 中文字體處理
- numpy - 陣列處理
- loguru - 日誌輸出

