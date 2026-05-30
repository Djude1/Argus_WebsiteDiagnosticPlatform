# AI 智慧眼鏡 Android App

Flutter Android App，用來**取代 ESP32 硬體**，讓 Android 手機直接作為 AI 智慧眼鏡裝置使用。

---

## 功能總覽

| 功能 | 說明 |
|------|------|
| 自動找伺服器 | 啟動時自動發現同一 Wi-Fi 的伺服器，不需手動輸入 IP |
| 前台免登入 | 所有導航功能直接使用，不需帳號 |
| 5 大導航按鈕 | 盲道導航 / 過馬路 / 紅綠燈 / 找物品 / 停止 |
| 語音 + 按鈕並存 | 兩種方式都能觸發，視障友善 |
| 緊急連絡人 | 本機儲存，說「打給媽媽」自動撥號 |
| 後台管理 | 獨立入口，需 Admin / Operator 帳密 |
| 背景監聽 | 螢幕關閉後仍持續運作（前台服務） |

---

## 環境需求

| 項目 | 需求 |
|------|------|
| Flutter | 3.x stable |
| Android SDK | API 21+（Android 5.0 以上） |
| 測試裝置 | Android 實體手機（建議）或模擬器 |
| 伺服器 | 先啟動 `app_main.py`，與手機同一 Wi-Fi |

---

## 第一次設定

### 1. 安裝套件

```bash
cd Android
flutter pub get
```

### 2. 連接 Android 裝置

手機開啟「開發人員選項」→「USB 偵錯」，接上電腦。

```bash
flutter devices   # 確認裝置已偵測到
```

### 3. 啟動伺服器

```bash
cd ..                        # 回到專案根目錄
uv run python app_main.py    # FastAPI on port 8081
```

伺服器啟動時會顯示：
```
[AUTH] 資料庫初始化完成（預設帳號 admin / 1124）
[DISCOVERY] UDP 廣播已啟動（port 47777，每 2 秒）
```

### 4. 執行 App

```bash
cd Android
flutter run          # 自動選連接的 Android 裝置
```

> ⚠️ 不要用 `-d chrome`，此 App 目標是 Android。

---

## 使用流程

### 自動連線

App 啟動後自動搜尋伺服器（最多 6 秒），找到後立即連線並進入主畫面。

- **找到** → 直接進入主畫面，可立刻使用
- **找不到** → 跳到設定頁，手動輸入伺服器 IP

### 主畫面（前台，不需登入）

直接點擊 5 顆大按鈕使用：

| 按鈕 | 功能 | 等同語音指令 |
|------|------|-------------|
| 🔵 盲道導航 | 偵測盲道並引導方向 | 「開始導航」 |
| 🟢 過馬路 | 尋找斑馬線 + 等待綠燈 | 「開始過馬路」 |
| 🟠 紅綠燈偵測 | 持續偵測燈號 | 「檢測紅綠燈」 |
| 🟣 找物品 | 輸入物品名稱搜尋 | 「幫我找手機」 |
| 🔴 停止 | 停止所有導航 | 「停止導航」 |

---

## 緊急連絡人

**設定步驟：**
1. 主畫面右上角 → 聯絡人圖示
2. 點「新增連絡人」→ 輸入姓名 + 電話 → 儲存

**語音撥打（以「媽媽」為例）：**
- 說「打給媽媽」→ 自動撥號
- 說「聯絡媽媽」→ 自動撥號
- 說「媽媽打電話」→ 自動撥號

> 連絡人儲存在手機本機，不需伺服器登入。

---

## 後台管理（需管理員帳密）

### 進入方式

主畫面右上角有一個**不顯眼的小鎖圖示**，**長按**即可進入後台登入頁面。

### 預設帳密

| 帳號 | 密碼 |
|------|------|
| admin | 1124 |

> 建議登入後立即到使用者管理修改密碼。

### 後台功能

- **使用者管理**（Admin 限定）：新增 / 停用 / 改角色 / 改密碼 / 刪除
- **系統狀態**：伺服器連線、導航狀態
- **角色權限**：

| 角色 | 使用前台 | 進後台 | 管理用戶 |
|------|----------|--------|----------|
| User | ✅ | ❌ | ❌ |
| Operator | ✅ | ✅ | ❌ |
| Admin | ✅ | ✅ | ✅ |

### 登出後台

後台頁面右上角 → 登出圖示 → 回到前台（前台功能不受影響）。

---

## 伺服器自動發現說明

App 使用 **UDP 廣播**發現伺服器：

1. 伺服器每 2 秒在區網廣播 `{"service":"ai_glasses","port":8081}`
2. App 啟動後監聽 UDP port 47777，最多等 6 秒
3. 收到廣播封包後取得 IP，自動連線

如果自動發現失敗（例如 Wi-Fi 封鎖廣播封包），可在「設定」頁手動輸入 IP。

---

## 手動設定伺服器 IP

1. 主畫面右上角 → 設定圖示（齒輪）
2. 輸入伺服器 IP 和 Port（預設 8081）
3. 儲存後重新連線

查詢電腦 IP（Windows）：
```
ipconfig
# 找「IPv4 位址」，例如 192.168.1.100
```

---

## 常見問題

**Q: App 顯示「搜尋伺服器中…」然後跳到設定頁**
- 確認手機和電腦在**同一 Wi-Fi**
- 確認伺服器已啟動（看到 `[DISCOVERY] UDP 廣播已啟動`）
- 部分 Wi-Fi 路由器會封鎖廣播封包 → 改用手動設定 IP

**Q: 語音沒有反應**
- 確認已允許麥克風權限
- 先說喚醒詞「哈囉曼波」再說指令
- 或直接按畫面按鈕

**Q: 背景服務被系統殺掉**
- 手機設定 → 電池 → 找到「AI智慧眼鏡」→ 設為「不限制背景活動」
- 各品牌手機位置略有不同（Samsung / Xiaomi / OPPO）

**Q: build 失敗**
```bash
flutter clean && flutter pub get && flutter run
```

---

## 目錄結構

```
Android/lib/
├── main.dart                      # 進入點（前台服務初始化）
├── app.dart                       # 路由設定
├── core/
│   ├── constants.dart             # API 端點常數
│   └── theme.dart                 # 視障友善深色主題
├── providers/
│   ├── auth_provider.dart         # 登入狀態（guest / admin）
│   └── app_provider.dart          # 連線、導航、連絡人
├── services/
│   ├── discovery_service.dart     # UDP 自動發現伺服器
│   ├── contacts_service.dart      # 本機 SQLite 連絡人
│   ├── auth_service.dart          # JWT 本地儲存
│   ├── api_service.dart           # HTTP API
│   ├── websocket_service.dart     # WS 連線管理
│   ├── camera_service.dart        # 攝影機串流
│   ├── audio_service.dart         # 麥克風 + 播放 + 前台服務
│   └── imu_service.dart           # 加速度計 / 陀螺儀
├── screens/
│   ├── splash_screen.dart         # 啟動 + 自動發現
│   ├── home_screen.dart           # 前台主畫面（免登入）
│   ├── settings_screen.dart       # 手動設定 IP
│   ├── contacts_screen.dart       # 緊急連絡人
│   ├── admin_login_screen.dart    # 後台登入（長按鎖圖示進入）
│   └── admin/
│       ├── admin_screen.dart      # 後台首頁
│       └── user_manage_screen.dart # 使用者管理
└── widgets/
    ├── nav_button.dart            # 大按鈕元件
    └── status_banner.dart         # 狀態橫幅
```
