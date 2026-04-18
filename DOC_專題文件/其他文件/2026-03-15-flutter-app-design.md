# Flutter App Design Specification

**日期**: 2026-03-15
**狀態**: Draft
**目標平台**: Android

## 1. 概述

### 1.1 專案目標

將現有的視障輔助系統 (OpenAIDevice_For_VisualImpairment) 製作成 Flutter 版本，利用 Android 手機的硬體感測器替代 ESP32，實現：

1. **攝影機串流** - 手機攝影機畫面發送至伺服器，接收 AI 標註後的影像
2. **語音對話** - 語音輸入識別 + AI 回覆播放

### 1.2 架構選擇

| 決策項目 | 選擇 | 原因 |
|----------|------|------|
| 目標平台 | Android | 簡化開發，專注於單一平台 |
| 後端架構 | 連接現有伺服器 | 可用完整 AI 模型，手機負載低 |
| 狀態管理 | Riverpod | 編譯時安全，適合 WebSocket 全局存取 |
| 專案位置 | `flutter_app/` | 與現有專案整合，便於管理 |

### 1.3 核心設計決策

- **Decided**:
  - WebSocket 作為主要通訊協議（與現有 FastAPI 伺服器對接）
  - Riverpod 作為狀態管理方案
  - 手機攝影機替代 ESP32-CAM
  - 手機麥克風/喇叭替代 ESP32 音頻硬體

- **Rejected**:
  - 純本地端 AI（手機效能不足以運行完整 YOLO + 語音模型）
  - REST + WebSocket 混合（增加複雜度，即時性較差）
  - gRPC（需大幅修改伺服器）
  - Provider（Riverpod 更安全且功能更強）

## 2. 系統架構

### 2.1 整體架構圖

```
┌─────────────────────────────────────────────────────────────────┐
│                      Flutter App (Android)                      │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Camera Page │  │ Voice Page  │  │     Settings Page       │  │
│  └──────┬──────┘  └──────┬──────┘  └────────────┬────────────┘  │
│         │                │                      │                │
│         ▼                ▼                      ▼                │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              Riverpod Providers (狀態管理)                  ││
│  │  • connectionProvider - 連線狀態                            ││
│  │  • cameraProvider - 影像幀                                  ││
│  │  • voiceProvider - 語音輸入/輸出狀態                        ││
│  └─────────────────────────────────────────────────────────────┘│
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                WebSocketService (單例)                      ││
│  │  • 自動重連                                                  ││
│  │  • 心跳檢測                                                  ││
│  │  • 訊息路由                                                  ││
│  └─────────────────────────────────────────────────────────────┘│
└──────────────────────────────┬──────────────────────────────────┘
                               │ WebSocket
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                 FastAPI Server (現有)                            │
│  ws://server:8081/ws/camera  → 發送手機攝影機畫面                │
│  ws://server:8081/ws/viewer  → 接收標註後的影像                  │
│  ws://server:8081/ws_audio   → 發送麥克風 / 接收 AI 音頻         │
│  ws://server:8081/ws         → IMU 數據 (預留)                  │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 數據流

#### 攝影機串流

```
Flutter App                    FastAPI Server
     │                              │
     │  手機攝影機幀 (JPEG)         │
     │ ──────────────────────────►  │ /ws/camera
     │                              │ → YOLO 檢測
     │                              │ → 導航/物品識別
     │  標註後影像 (JPEG)           │
     │ ◄──────────────────────────  │ /ws/viewer
     │                              │
     ▼                              │
  顯示在畫面                        │
```

#### 語音對話

```
Flutter App                    FastAPI Server
     │                              │
     │  麥克風音頻 (PCM16)          │
     │ ──────────────────────────►  │ /ws_audio
     │                              │ → DashScope ASR
     │                              │ → Qwen-Omni AI
     │  AI 回覆音頻 (WAV/PCM)       │ ← TTS 生成
     │ ◄──────────────────────────  │
     │                              │
     ▼                              │
  播放音頻                          │
```

## 3. 專案結構

```
OpenAIDevice_For_VisualImpairment/
├── flutter_app/
│   ├── lib/
│   │   ├── main.dart                 # 應用入口
│   │   ├── app.dart                  # MaterialApp 配置
│   │   │
│   │   ├── core/
│   │   │   ├── constants.dart        # API 端點、設定常數
│   │   │   └── theme.dart            # 深色主題 (與 Web 一致)
│   │   │
│   │   ├── data/
│   │   │   ├── services/
│   │   │   │   ├── websocket_service.dart    # WebSocket 連接管理
│   │   │   │   ├── camera_stream_service.dart # 攝影機串流服務
│   │   │   │   ├── audio_service.dart        # 音頻錄製/播放
│   │   │   │   └── imu_service.dart          # IMU 數據 (預留)
│   │   │   └── models/
│   │   │       ├── server_config.dart        # 伺服器連線配置
│   │   │       └── imu_data.dart             # IMU 數據模型
│   │   │
│   │   ├── features/
│   │   │   ├── camera/
│   │   │   │   ├── camera_viewer.dart        # 即時影像顯示
│   │   │   │   └── camera_controller.dart    # 攝影機狀態控制
│   │   │   ├── voice/
│   │   │   │   ├── voice_input.dart          # 語音輸入按鈕
│   │   │   │   ├── voice_output.dart         # AI 回覆播放
│   │   │   │   └── chat_panel.dart           # 對話紀錄顯示
│   │   │   └── settings/
│   │   │       └── server_settings.dart      # 伺服器 IP/Port 設定
│   │   │
│   │   ├── shared/
│   │   │   ├── widgets/
│   │   │   │   ├── status_indicator.dart     # 連線狀態指示器
│   │   │   │   └── loading_overlay.dart      # 載入中覆蓋層
│   │   │   └── providers/
│   │   │       └── app_state.dart            # 全局狀態
│   │   │
│   │   └── platform/
│   │       └── sensors/
│   │           └── mobile_sensors.dart       # 手機感測器 (預留)
│   │
│   ├── pubspec.yaml                  # 依賴配置
│   ├── android/                      # Android 原生配置
│   │   ├── app/src/main/AndroidManifest.xml  # 權限聲明
│   │   └── build.gradle              # Android 建構配置
│   └── test/                         # 測試目錄
│
├── (現有 Python 檔案...)             # FastAPI 伺服器
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-03-15-flutter-app-design.md  # 本文件
```

## 4. 核心功能設計

### 4.1 攝影機串流 (Camera Stream)

#### UI 設計

```
┌────────────────────────────────┐
│  ┌──────────────────────────┐  │
│  │                          │  │
│  │   手機攝影機畫面         │  │
│  │   + 伺服器回傳的標註     │  │
│  │   (盲道框/障礙物/方向)   │  │
│  │                          │  │
│  └──────────────────────────┘  │
│  ┌────────────────────────────┐│
│  │ FPS: 24 │ 延遲: 120ms │ ●  ││  ← 狀態列
│  └────────────────────────────┘│
│  ┌────────────────────────────┐│
│  │    📷 攝影機開關           ││
│  └────────────────────────────┘│
└────────────────────────────────┘
```

#### 實現要點

1. **攝影機存取**: 使用 `camera` 套件存取手機攝影機
2. **影像編碼**: 將幀編碼為 JPEG 格式
3. **發送到伺服器**: 透過 `/ws/camera` WebSocket 發送
4. **接收標註影像**: 監聽 `/ws/viewer` 接收伺服器回傳的標註影像
5. **顯示**: 使用 `Image.memory()` 顯示 JPEG 二進位數據

### 4.2 語音對話 (Voice Chat)

#### UI 設計

```
┌────────────────────────────────┐
│  ┌──────────────────────────┐  │
│  │   識別中: "我想找水壺"    │  │  ← 即時識別文字
│  └──────────────────────────┘  │
│                                │
│  ┌────────────────────────────┐│
│  │                            ││
│  │      🎤 按住說話           ││  ← 大型錄音按鈕
│  │                            ││
│  └────────────────────────────┘│
│                                │
│  ┌──────────────────────────┐  │
│  │ AI: 好的，我來幫您找水壺  │  │  ← AI 回覆文字
│  └──────────────────────────┘  │
└────────────────────────────────┘
```

#### 實現要點

1. **錄音**: 使用 `record` 套件錄製 PCM16 格式音頻
2. **發送到伺服器**: 透過 `/ws_audio` WebSocket 發送音頻數據
3. **接收 AI 回覆**: 監聽同一 WebSocket 接收 AI 生成的音頻
4. **播放**: 使用 `audioplayers` 套件播放音頻

### 4.3 連線設定頁面

#### UI 設計

```
┌────────────────────────────────┐
│        伺服器設定              │
├────────────────────────────────┤
│                                │
│  伺服器 IP                     │
│  ┌──────────────────────────┐  │
│  │ 192.168.1.100            │  │
│  └──────────────────────────┘  │
│                                │
│  通訊埠                        │
│  ┌──────────────────────────┐  │
│  │ 8081                     │  │
│  └──────────────────────────┘  │
│                                │
│  連線狀態: ● 已連線            │
│                                │
│  ┌────────────────────────┐    │
│  │      測試連線           │    │
│  └────────────────────────┘    │
└────────────────────────────────┘
```

## 5. 頁面導航

### 5.1 頁面結構

| 頁面 | 路由 | 功能 |
|------|------|------|
| `MainPage` | `/` | 攝影機 + 語音對話 |
| `SettingsPage` | `/settings` | 伺服器連線設定 |
| `HistoryPage` | `/history` | 對話紀錄 (預留) |

### 5.2 底部導航

```
┌───────────┬───────────┬───────────┐
│   首頁    │   設定    │   紀錄    │
└───────────┴───────────┴───────────┘
```

## 6. 套件依賴

### 6.1 核心依賴

```yaml
dependencies:
  flutter:
    sdk: flutter

  # 狀態管理
  flutter_riverpod: ^2.4.9

  # 網路通訊
  web_socket_channel: ^2.4.0

  # 攝影機
  camera: ^0.10.5+7
  image: ^4.1.3            # 圖像處理/編碼

  # 音頻
  record: ^5.0.4           # 錄音 (PCM16)
  audioplayers: ^5.2.1     # 播放音頻

  # 權限
  permission_handler: ^11.1.0

  # 工具
  connectivity_plus: ^5.0.2  # 網路狀態
  shared_preferences: ^2.2.2 # 儲存設定
  uuid: ^4.2.2               # 唯一 ID 生成
  logger: ^2.0.2+1           # 結構化日誌
  freezed_annotation: ^2.4.0 # 不可變資料類別

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^3.0.1
  build_runner: ^2.4.7      # freezed 代碼生成
  freezed: ^2.4.6           # freezed 代碼生成
```

### 6.2 套件用途說明

| 套件 | 用途 |
|------|------|
| `flutter_riverpod` | 狀態管理，適合 WebSocket 全局存取 |
| `web_socket_channel` | WebSocket 通訊 |
| `camera` | 存取手機攝影機 |
| `image` | 圖像編碼/解碼 |
| `record` | 錄製 PCM16 音頻 |
| `audioplayers` | 播放 AI 回覆音頻 |
| `permission_handler` | 請求攝影機/麥克風權限 |
| `connectivity_plus` | 檢測網路狀態 |
| `shared_preferences` | 儲存伺服器設定 |
| `uuid` | 生成唯一 ID |
| `logger` | 結構化日誌輸出 |
| `freezed` | 不可變資料類別生成 |

## 7. Android 權限

### 7.1 AndroidManifest.xml

```xml
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <!-- 網路權限 -->
    <uses-permission android:name="android.permission.INTERNET"/>
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE"/>

    <!-- 攝影機權限 -->
    <uses-permission android:name="android.permission.CAMERA"/>
    <uses-feature android:name="android.hardware.camera" android:required="true"/>
    <uses-feature android:name="android.hardware.camera.autofocus" android:required="false"/>

    <!-- 麥克風權限 -->
    <uses-permission android:name="android.permission.RECORD_AUDIO"/>
    <uses-permission android:name="android.permission.MODIFY_AUDIO_SETTINGS"/>

    <!-- 藍牙 (音頻輸出) -->
    <uses-permission android:name="android.permission.BLUETOOTH"/>
    <uses-permission android:name="android.permission.BLUETOOTH_CONNECT"/>

    <application ...>
        ...
    </application>
</manifest>
```

## 8. 錯誤處理

### 8.1 連線錯誤

| 錯誤類型 | 處理方式 |
|----------|----------|
| 伺服器無回應 | 顯示錯誤訊息，提供重試按鈕 |
| WebSocket 斷線 | 自動重連（最多 3 次），顯示重連狀態 |
| 網路切換 | 檢測網路變化，自動重連 |

### 8.2 權限錯誤

| 錯誤類型 | 處理方式 |
|----------|----------|
| 攝影機權限拒絕 | 顯示設定引導，無法使用攝影機功能 |
| 麥克風權限拒絕 | 顯示設定引導，無法使用語音功能 |

### 8.3 音頻錯誤

| 錯誤類型 | 處理方式 |
|----------|----------|
| 錄音失敗 | 顯示錯誤訊息，重試按鈕 |
| 播放失敗 | 跳過當前音頻，繼續下一個 |

## 9. 未來擴展

以下功能預留介面，但不在第一版實現範圍：

1. **盲道導航** - 盲道偵測 + 方向引導語音
2. **過馬路** - 斑馬線偵測 + 紅綠燈識別
3. **物品尋找** - YOLO 檢測 + 手部追蹤引導
4. **IMU 3D 可視化** - 手機姿態 3D 顯示
5. **iOS 支援** - 擴展到 iOS 平台

## 10. 驗收標準

### 10.1 功能驗收

- [ ] 可以連接到指定的 FastAPI 伺服器
- [ ] 可以顯示即時影像（含 AI 標註）
- [ ] 可以錄製語音並發送到伺服器
- [ ] 可以播放 AI 回覆的音頻
- [ ] 可以設定和儲存伺服器 IP/Port
- [ ] 在網路斷線時自動重連

### 10.2 效能驗收

- [ ] 影像延遲 < 500ms (區域網路)
- [ ] 語音識別回應 < 2s
- [ ] 應用啟動時間 < 3s
- [ ] 記憶體使用 < 200MB

### 10.3 穩定性驗收

- [ ] 連續運行 1 小時不崩潰
- [ ] 網路切換後可自動恢復
- [ ] 來電後可恢復正常運作

---

**文件歷史**

| 版本 | 日期 | 變更 |
|------|------|------|
| 1.0 | 2026-03-15 | 初始設計文檔 |
