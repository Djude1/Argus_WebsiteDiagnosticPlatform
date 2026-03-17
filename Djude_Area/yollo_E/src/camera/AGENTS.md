<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-16 | Updated: 2026-03-16 -->

# camera

## Purpose
攝影機影像來源模組，支援 ESP32 HTTP MJPEG 串流和本地 Webcam 兩種輸入來源。

## Key Files

| File | Description |
|------|-------------|
| `esp32_stream.py` | ESP32 串流接收器，透過 HTTP GET /stream 接收 MJPEG 串流 |
| `webcam_fallback.py` | 本地 Webcam 輸入，作為測試或備援來源 |
| `__init__.py` | 模組匯出 |

## For AI Agents

### Working In This Directory
- ESP32StreamReceiver 使用 requests 庫接收串流
- 支援 mDNS 自動發現（`yollo.local`）或手動 IP
- WebcamFallback 使用 OpenCV (cv2.VideoCapture)

### Class Interface

```python
# ESP32StreamReceiver
class ESP32StreamReceiver:
    def connect() -> bool      # 連線到串流來源
    def read_frame() -> tuple # 讀取單幀影像 (ret, frame)
    def disconnect() -> None   # 斷開連線
    @property is_connected()   # 連線狀態

# WebcamFallback
class WebcamReceiver:
    def connect() -> bool
    def read_frame() -> tuple
    def disconnect() -> None
```

### Common Patterns
- 統一介面：connect() → read_frame() → disconnect()
- 返回格式：`(ret: bool, frame: np.ndarray)`
- 錯誤處理：frame 為 None 時返回 `(False, None)`

## Dependencies

### Internal
- `src/config.py` - 取得 ESP32 串流 URL 和參數

### External
- requests - HTTP 串流接收
- opencv-python - 影像處理
- numpy - 陣列處理

