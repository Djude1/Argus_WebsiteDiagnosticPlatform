<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-14 | Updated: 2026-03-14 -->

# ocr

## Purpose
ESP32 OCR Arduino 程式，負責拍照並發送至 OCR 伺服器。

## Key Files

| File | Description |
|------|-------------|
| `ocr.ino` | Arduino OCR 程式 |

## For AI Agents

### Working In This Directory
- 編譯並上傳至 XIAO ESP32-S3 Sense
- 需要配合 `../relay_server.py` 使用

### Program Flow
1. 初始化攝影機
2. 連接 WiFi
3. 拍攝照片
4. 發送至 relay_server
5. 接收 OCR 結果

## Dependencies

### Internal
- `../relay_server.py`

### External
- Arduino ESP32 Core
- esp_camera

<!-- MANUAL: -->
