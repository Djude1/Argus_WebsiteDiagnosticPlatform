<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-14 | Updated: 2026-03-14 -->

# Djude_Area

## Purpose
Djude 的開發區域，包含硬體相關的 ESP32 韌體、攝影機伺服器、OCR 功能，以及軟體測試區域。

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `Hardware/` | 硬體相關開發 (ESP32 韌體、Camera Server、OCR) |
| `software/` | 軟體相關開發與測試 |

## For AI Agents

### Working In This Directory
- 硬體開發在 `Hardware/34/` 目錄下，針對 ESP32-S3 (XIAO)
- 軟體測試需要配合對應的韌體版本使用
- YOLO Server 使用 `uv` 作為 Python 套件管理器

### Testing Requirements
- Arduino 韌體需上傳至 ESP32 後測試
- Python 服務需安裝 `pyproject.toml` 中的依賴

## Dependencies

### Internal
- 根目錄的 `YOLO_Module/` 提供訓練模型
- 根目錄的 `compile/` 提供共用 Arduino 配置

### External
- Arduino IDE / PlatformIO
- Python 3.10+
- uv (Python 套件管理器)

<!-- MANUAL: -->
