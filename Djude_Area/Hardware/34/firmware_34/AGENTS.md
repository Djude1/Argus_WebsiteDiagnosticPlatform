<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-14 | Updated: 2026-03-14 -->

# firmware_34

## Purpose
ESP32 版本 34 韌體原始碼，整合攝影機、陀螺儀和麥克風功能。

## Key Files

| File | Description |
|------|-------------|
| `camera.h` | 攝影機配置與操作 |
| `gyroscope.h` | ICM42688 陀螺儀驅動 |
| `mic.h` | I2S 麥克風配置 |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `main/` | Arduino 主程式 |

## For AI Agents

### Working In This Directory
- 目標硬體: XIAO ESP32-S3 Sense
- 攝影機: OV2640
- IMU: ICM42688
- 麥克風: INMP441 (I2S)

### Component Integration
```
main.ino
├── camera.h (OV2640)
├── gyroscope.h (ICM42688)
└── mic.h (INMP441)
```

## Dependencies

### External
- Arduino ESP32 Core
- ICM42688 庫
- esp_camera

<!-- MANUAL: -->
