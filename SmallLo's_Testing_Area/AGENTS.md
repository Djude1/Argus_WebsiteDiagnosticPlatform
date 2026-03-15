<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-14 | Updated: 2026-03-16 -->

# SmallLo's_Testing_Area

## Purpose
SmallLo 的測試區域，建構 Flutter Android App 作為視障輔助系統的客戶端，使用手機感測器替代 ESP32 硬體。

## Key Files

| File | Description |
|------|-------------|
| `ARCHITECTURE.md` | 系統架構文檔 |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `flutter_app/` | Flutter Android App (連接主專案 FastAPI 伺服器) |

## For AI Agents

### Working In This Directory
- Flutter App 連接主專案的 FastAPI 伺服器 (`../../app_main.py`)
- 主要功能: 相機串流 + 語音對話

### Architecture Overview
```
Flutter App (Camera/Mic) → WebSocket → Main Project FastAPI Server → AI Processing
```

### Build & Run
```bash
cd flutter_app
flutter build apk --debug
# APK: flutter_app/build/app/outputs/flutter-apk/app-debug.apk
```

## Dependencies

### Internal
- Main project server: `../../app_main.py` (port 8081)

### External
- Flutter SDK, Android SDK

<!-- MANUAL: -->
