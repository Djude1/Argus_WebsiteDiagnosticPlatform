<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-14 | Updated: 2026-03-14 -->

# Yolo_Server

## Purpose
Python YOLO 推理伺服器，從 ESP32 接收 MJPEG 串流並進行物件檢測。

## Key Files

| File | Description |
|------|-------------|
| `main.py` | 主程式 (MJPEG 拉取 + YOLO 推理) |
| `pyproject.toml` | Python 專案配置 (uv) |
| `uv.lock` | 依賴鎖定檔案 |
| `README.md` | 說明文檔 |
| `.python-version` | Python 版本要求 |

## For AI Agents

### Working In This Directory
- 使用 uv 管理依賴: `uv sync`
- 執行: `uv run python main.py`

### Configuration
- ESP32 IP 地址在 `main.py` 中配置
- YOLO 模型路徑需要指向 `../../../../YOLO_Module/`

## Dependencies

### External
- ultralytics
- opencv-python
- httpx

<!-- MANUAL: -->
