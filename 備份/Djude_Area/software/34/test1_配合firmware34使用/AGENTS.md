<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-14 | Updated: 2026-03-14 -->

# test1_配合firmware34使用

## Purpose
測試程式 1，配合 ESP32 firmware_34 韌體使用，實現攝影機串流和 YOLO 檢測。

## Key Files

| File | Description |
|------|-------------|
| `main.py` | Python 主程式 |
| `pyproject.toml` | Python 專案配置 (uv) |
| `uv.lock` | 依賴鎖定檔案 |
| `README.md` | 說明文檔 |
| `yolo11n.pt` | YOLO 模型檔案 |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `firmware/` | 對應的 ESP32 韌體副本 |

## For AI Agents

### Working In This Directory
- 執行: `uv run python main.py`
- 需要 ESP32 運行 firmware_34 韌體

### Data Flow
```
ESP32 (firmware_34) → MJPEG Stream → main.py → YOLO Detection
```

## Dependencies

### Internal
- `firmware/` - 韌體副本 (參考用)

### External
- ultralytics
- opencv-python
- httpx

<!-- MANUAL: -->
