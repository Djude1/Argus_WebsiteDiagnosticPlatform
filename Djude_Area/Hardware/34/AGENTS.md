<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-14 | Updated: 2026-03-14 -->

# 34

## Purpose
ESP32-S3 版本 34 開發目錄，包含 Camera Web Server、韌體、麥克風測試和 OCR 功能。

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `CameraWebServer_34/` | 攝影機 Web 伺服器與 YOLO Server |
| `firmware_34/` | ESP32 韌體原始碼 |
| `MAX98357_MIC_TEST_34/` | MAX98357 麥克風測試 |
| `ocr_34/` | OCR 功能實現 |

## For AI Agents

### Working In This Directory
- 目標硬體: XIAO ESP32-S3 Sense
- 各子目錄可能有獨立的 Python 環境 (pyproject.toml)

### Hardware Specs
- MCU: ESP32-S3
- Camera: OV2640
- Audio: MAX98357 (I2S amplifier), INMP441 (microphone)
- IMU: ICM42688

## Dependencies

### External
- Arduino IDE
- Python 3.10+
- uv (Python 套件管理器)

<!-- MANUAL: -->
