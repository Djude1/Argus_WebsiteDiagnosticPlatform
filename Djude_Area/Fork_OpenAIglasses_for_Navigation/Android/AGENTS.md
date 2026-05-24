<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-19 | Updated: 2026-05-19 -->

# Android（Flutter App）

## 用途

Flutter 行動 App（package `android_ai_glasses`），定位為**取代 ESP32 硬體**、提供視障友善的導航介面。負責相機/麥克風採集、與 Python 後端 WebSocket 連線、本地語音播報、緊急聯絡與 GPS 導航。

## 關鍵檔案 / 目錄

| 路徑 | 用途 |
|------|------|
| `pubspec.yaml` | 套件相依與資產宣告 |
| `analysis_options.yaml` | Dart 靜態分析規則 |
| `lib/` | App 原始碼（見 `lib/AGENTS.md`） |
| `assets/audio/` | 預生成語音檔（以雜湊命名的 `.wav`） |
| `assets/models/` | 裝置端推論模型資產 |
| `android/` | Android 原生專案（Gradle、Kotlin host） |
| `web/` | Flutter web 載入頁 |
| `test/` | Flutter 測試 |

## For AI Agents

### 在本目錄工作

- 程式碼註釋一律 **繁體中文**
- 任何 UI 修改須以視障可用性為前提；修改前後跑 `app-check` skill 檢查
- 後端連線位址、API 金鑰勿硬編碼，走設定/`.env` 機制

### 測試要求

- 修改後執行 `flutter analyze`（靜態檢查），並**明確提醒使用者需實機測試**
- 摔倒偵測為全域功能（任何分頁皆可彈倒數），改動相關流程須回歸測試

### 常見模式

- 畫面在 `lib/screens/`、邏輯服務在 `lib/services/`、狀態在 `lib/providers/`
- 與後端互動透過 `lib/services/websocket_service.dart` 與 `api_service.dart`

## 相依

### 內部
- 根目錄 Python 後端（WebSocket 端點，見根 `AGENTS.md`）

### 外部
- Flutter SDK、camera、各 ASR/TTS/定位相關套件（詳見 `pubspec.yaml`）

<!-- MANUAL: 此線以下手動註記在重新產生時會保留 -->
