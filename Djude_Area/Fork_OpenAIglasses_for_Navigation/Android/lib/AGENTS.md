<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-19 | Updated: 2026-05-19 -->

# Android/lib（Flutter 原始碼）

## 用途

App 全部 Dart 原始碼。進入點 `main.dart` → `app.dart`，狀態以 Provider 管理，畫面與服務分層。

## 關鍵檔案

| 檔案 | 用途 |
|------|------|
| `main.dart` | App 進入點 |
| `app.dart` | App 根 Widget、路由 |
| `core/constants.dart` | 全域常數（含後端位址等） |
| `core/theme.dart` | 主題（視障友善配色/字級） |
| `core/yoloe_label_zh.dart` | YOLO-E 類別中文標籤對照 |
| `providers/app_provider.dart` | 全域狀態管理 |

## 子目錄

| 目錄 | 用途 |
|------|------|
| `screens/` | 各分頁畫面：`home` `mode_select` `blind` `ar` `read` `nav_destination` `contacts`/`contact_form` `customer_service` `emergency_select`/`emergency_countdown` `settings` `permission` `splash` `yoloe_ar_test` |
| `services/` | 服務層：`websocket_service` `api_service` `camera_service` `audio_service` `local_voice_service` `voice_cache_service` `imu_service` `gps_navigation_service` `places_service` `discovery_service` `call_service` `contacts_service` `emergency_notification_service` `yoloe_inference` |
| `utils/` | `hardware_monitor.dart` 硬體狀態監控 |
| `widgets/` | 共用元件：`asr_status_overlay` `debug_panel` `nav_button` `status_banner` |

## For AI Agents

### 在本目錄工作

- 註釋繁體中文；維持現有分層（畫面不直接做網路/裝置 I/O，走 `services/`）
- 新增畫面須在 `app.dart` 註冊路由；新增服務維持單一職責
- 摔倒偵測為全域，相關 overlay/倒數流程改動需全分頁回歸

### 測試要求

- `flutter analyze` 通過後，提醒使用者實機驗證（相機/麥克風/GPS/通話權限）

### 常見模式

- `*_screen.dart` = 畫面，`*_service.dart` = 邏輯/IO，`*_provider.dart` = 狀態

## 相依

### 內部
- 根目錄 Python 後端 WebSocket（`websocket_service.dart` / `api_service.dart`）

<!-- MANUAL: 此線以下手動註記在重新產生時會保留 -->
