<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-14 | Updated: 2026-03-14 -->

# ocr_34

## Purpose
OCR (光學字符識別) 功能實現，包含 ESP32 端和伺服器端。

## Key Files

| File | Description |
|------|-------------|
| `relay_server.py` | OCR 中繼伺服器 |
| `pyproject.toml` | Python 專案配置 (uv) |
| `uv.lock` | 依賴鎖定檔案 |
| `README.md` | 說明文檔 |
| `.python-version` | Python 版本要求 |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `ocr/` | ESP32 OCR Arduino 程式 |

## For AI Agents

### Working In This Directory
- Python 服務: `uv run python relay_server.py`
- Arduino 程式上傳至 ESP32

### Data Flow
```
ESP32-CAM → Image → relay_server.py → OCR API → Text Result
```

## Dependencies

### External
- Python 3.10+
- uv
- OCR API (PaddleOCR, Tesseract, etc.)

<!-- MANUAL: -->
