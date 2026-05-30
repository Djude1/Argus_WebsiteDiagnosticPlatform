<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-14 | Updated: 2026-03-14 -->

# CameraWebServer_34

## Purpose
攝影機 Web 伺服器目錄，包含 ESP32 Camera Server 和 Python YOLO Server。

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `CameraWebServer/` | ESP32 Camera Web Server (Arduino) |
| `Yolo_Server/` | Python YOLO 推理伺服器 |

## For AI Agents

### Working In This Directory
- CameraWebServer: Arduino 程式，上傳至 ESP32
- Yolo_Server: Python 服務，使用 uv 管理

### Data Flow
```
ESP32-CAM → MJPEG Stream → Yolo_Server → Detection Results
```

## Dependencies

### Internal
- `../../../../YOLO_Module/` - YOLO 模型

### External
- Arduino IDE
- Python 3.10+ (uv)

<!-- MANUAL: -->
