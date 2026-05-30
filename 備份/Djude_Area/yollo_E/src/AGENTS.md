<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-16 | Updated: 2026-03-16 -->

# src

## Purpose
Python 原始碼主目錄，包含所有核心模組：攝影機串流、YOLO 偵測、資料庫管理、訓練模組、標註管理、工具函式。

## Key Files

| File | Description |
|------|-------------|
| `main.py` | 主程式入口，整合所有模組 |
| `config.py` | 配置管理，從 .env 讀取環境變數 |
| `__init__.py` | 套件初始化 |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `camera/` | 攝影機串流接收模組 |
| `detection/` | YOLO 物件偵測模組 |
| `database/` | SQLite 資料庫管理模組 |
| `training/` | 自定義模型訓練模組 |
| `annotation/` | 物品標註管理模組 |
| `utils/` | 工具函式（視覺化、日誌） |

## For AI Agents

### Working In This Directory
- 所有模組使用相對匯入（`from .camera.esp32_stream import ...`）
- 主程式支援直接執行和套件匯入兩種模式
- 設定路徑使用 `pathlib.Path`

### Testing Requirements
- 使用 pytest 進行單元測試
- 執行：`uv run pytest`

### Common Patterns
- 使用 dataclasses 定義配置結構
- Loguru 用於日誌輸出
- 所有路徑使用相對專案根目錄的相對路徑

## Dependencies

### Internal
- `camera/` → `esp32_stream.py`, `webcam_fallback.py`
- `detection/` → `yolo_detector.py`, `label_mapper.py`
- `database/` → `db_manager.py`, `item_logger.py`
- `annotation/` → `annotation_manager.py`, `models.py`
- `utils/` → `logger.py`, `visualization.py`

### External
- ultralytics, opencv-python, numpy, sqlalchemy, loguru

