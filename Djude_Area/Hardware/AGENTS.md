<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-14 | Updated: 2026-03-14 -->

# Hardware

## Purpose
硬體相關開發目錄，針對 ESP32-S3 (版本 34) 的韌體、攝影機伺服器和 OCR 功能實現。

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `34/` | ESP32-S3 版本 34 開發 (CameraWebServer、firmware、OCR) |

## For AI Agents

### Working In This Directory
- 目標硬體: XIAO ESP32-S3 Sense
- 開發工具: Arduino IDE
- Python 服務使用 `uv` 套件管理器

### Hardware Components
- ESP32-S3 微控制器
- OV2640 攝影機模組
- ICM42688 IMU (6-axis)
- MAX98357 I2S 音頻放大器
- INMP441 麥克風

## Dependencies

### External
- Arduino IDE
- Python 3.10+
- uv (Python 套件管理器)

<!-- MANUAL: -->
