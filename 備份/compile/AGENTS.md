<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-14 | Updated: 2026-03-14 -->

# compile

## Purpose
ESP32 Arduino 編譯相關檔案，包含 IMU 驅動 (ICM42688)、攝影機引腳配置和主程式。

## Key Files

| File | Description |
|------|-------------|
| `compile.ino` | Arduino 主程式 (ESP32-CAM + IMU 整合) |
| `camera_pins.h` | 攝影機引腳定義 (XIAO ESP32S3) |
| `ICM42688.cpp` | ICM42688 IMU 驅動實現 |
| `ICM42688.h` | ICM42688 IMU 驅動頭文件 |

## For AI Agents

### Working In This Directory
- 目標硬體: XIAO ESP32-S3 Sense
- IMU 感測器: ICM42688 (6-axis IMU)
- 攝影機: OV2640

### Pin Configuration
- 攝影機引腳定義在 `camera_pins.h`
- IMU 通訊: SPI 或 I2C (見 `ICM42688.h`)

### Testing Requirements
- Arduino IDE 編譯無誤
- 上傳至 ESP32 後驗證串口輸出
- 驗證攝影機初始化和 IMU 讀數

### Common Patterns
- FreeRTOS 多任務處理
- WebSocket 通訊
- UDP 數據傳輸 (IMU)

## Dependencies

### External
- Arduino IDE
- ESP32 Arduino Core
- ICM42688 庫

<!-- MANUAL: -->
