<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-14 | Updated: 2026-03-14 -->

# main

## Purpose
ESP32 韌體主程式目錄，整合所有硬體元件。

## Key Files

| File | Description |
|------|-------------|
| `main.ino` | Arduino 主程式 (攝影機 + IMU + 麥克風整合) |

## For AI Agents

### Working In This Directory
- 編譯並上傳至 XIAO ESP32-S3 Sense
- 引用父目錄的 `camera.h`, `gyroscope.h`, `mic.h`

### Main Program Structure
```cpp
#include "../camera.h"
#include "../gyroscope.h"
#include "../mic.h"

void setup() {
  // 初始化攝影機、IMU、麥克風
  // 建立 WiFi 連接
  // 啟動 WebSocket/HTTP 服務
}

void loop() {
  // 處理攝影機幀
  // 讀取 IMU 數據
  // 處理音頻
  // 通訊處理
}
```

## Dependencies

### Internal
- `../camera.h`
- `../gyroscope.h`
- `../mic.h`

### External
- Arduino ESP32 Core

<!-- MANUAL: -->
