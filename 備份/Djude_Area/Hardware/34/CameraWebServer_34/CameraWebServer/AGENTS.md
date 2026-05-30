<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-14 | Updated: 2026-03-14 -->

# CameraWebServer

## Purpose
ESP32 Camera Web Server Arduino 程式，提供 MJPEG 串流和 HTTP API。

## Key Files

| File | Description |
|------|-------------|
| `CameraWebServer.ino` | Arduino 主程式 |
| `app_httpd.cpp` | HTTP 伺服器實現 |
| `camera_index.h` | 攝影機首頁 HTML (壓縮) |
| `camera_pins.h` | 攝影機引腳定義 |
| `board_config.h` | 開發板配置 |
| `partitions.csv` | ESP32 分區表 |
| `ci.yml` | CI 配置 |

## For AI Agents

### Working In This Directory
- 編譯環境: Arduino IDE with ESP32 Core
- 上傳目標: XIAO ESP32-S3 Sense

### API Endpoints
- `/` - 控制首頁
- `/stream` - MJPEG 串流
- `/capture` - 單張截圖
- `/status` - 狀態查詢

### Pin Configuration
定義在 `camera_pins.h`，針對 XIAO ESP32-S3:
- PWDN_GPIO_NUM
- RESET_GPIO_NUM
- XCLK_GPIO_NUM
- SIOD_GPIO_NUM, etc.

## Dependencies

### External
- Arduino ESP32 Core
- esp_camera library

<!-- MANUAL: -->
