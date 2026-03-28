# AI 智慧眼鏡 — Android APP 使用說明

Flutter Android App，讓 Android 手機直接作為 AI 智慧眼鏡裝置使用，**取代 ESP32 硬體**，功能與硬體眼鏡完全相同。

---

## 目錄

- [功能總覽](#功能總覽)
- [環境需求](#環境需求)
- [安裝與執行](#安裝與執行)
- [連線方式](#連線方式)
  - [自動發現（區網）](#自動發現區網)
  - [手動輸入 IP（區網）](#手動輸入-ip區網)
  - [公網連線（外出時）](#公網連線外出時)
- [主畫面操作](#主畫面操作)
- [緊急連絡人](#緊急連絡人)
- [後台管理](#後台管理)
- [連線模式切換](#連線模式切換)
- [常見問題](#常見問題)
- [專案目錄結構](#專案目錄結構)

---

## 功能總覽

| 功能 | 說明 |
|------|------|
| 自動找伺服器 | 啟動時自動發現同一 Wi-Fi 的伺服器，不需手動輸入 IP |
| 前台免登入 | 所有導航功能直接使用，不需帳號 |
| 5 大導航按鈕 | 盲道導航 / 過馬路 / 紅綠燈 / 找物品 / 停止 |
| 語音 + 按鈕並存 | 兩種方式都能觸發功能，視障友善 |
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
| 伺服器 | 先啟動 `app_main.py`，與手機在同一網路下 |

---

## 安裝與執行

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
flutter run          # 自動選已連接的 Android 裝置
```

> 注意：不要使用 `-d chrome`，此 App 目標平台為 Android。

---

## 連線方式

### 自動發現（區網）

App 啟動後自動搜尋伺服器（最多 6 秒），找到後立即連線並進入主畫面。

- **找到** → 直接進入主畫面，可立刻使用
- **找不到** → 跳到設定頁，手動輸入伺服器 IP

**自動發現原理**：伺服器每 2 秒在區網廣播 `{"service":"ai_glasses","port":8081}`，App 監聽 UDP port 47777，收到後自動取得 IP 連線。部分 Wi-Fi 路由器會封鎖廣播封包，此時需手動輸入 IP。

### 手動輸入 IP（區網）

1. 主畫面右上角 → 設定圖示（齒輪）
2. 切換到 **IP 模式**
3. 輸入伺服器 IP 和 Port（預設 `8081`）
4. 儲存後重新連線

查詢電腦 IP（Windows）：
```
ipconfig
# 找「IPv4 位址」，例如 192.168.1.100
```

### 公網連線（外出時）

當手機與伺服器不在同一 Wi-Fi 時，需使用公網穿透方案。

#### 方案一：Cloudflare Tunnel（推薦）

```bash
# 安裝（一次性）
winget install Cloudflare.cloudflared   # Windows
brew install cloudflared                # macOS

# 每次使用時執行
cloudflared tunnel --url http://localhost:8081
```

取得類似 `https://xxxx.trycloudflare.com` 的網址，複製到 APP 設定頁的 **URL 模式**。

#### 方案二：VSCode Dev Tunnels

1. 在 VSCode 開啟終端機
2. 點選狀態列「連接埠轉接」→「新增連接埠轉接」→ 輸入 `8081`
3. 右鍵轉接的連接埠 → 「設定連接埠可見性」→「公用」
4. 複製產生的 URL，貼到 APP 設定頁的 **URL 模式**

---

## 主畫面操作

App 啟動並連線成功後，進入主畫面，直接點擊 5 顆大按鈕使用：

| 按鈕 | 功能 | 等同語音指令 |
|------|------|-------------|
| 盲道導航 | 偵測盲道並語音引導方向 | 「開始導航」 |
| 過馬路 | 尋找斑馬線 + 等待綠燈 + 引導通過 | 「開始過馬路」 |
| 紅綠燈偵測 | 持續偵測燈號並語音回報 | 「檢測紅綠燈」 |
| 找物品 | 輸入物品名稱後搜尋 | 「幫我找手機」 |
| 停止 | 停止所有導航與偵測 | 「停止導航」 |

語音指令同樣有效，詳細說法請參考「語音指令.md」。

---

## 緊急連絡人

### 設定步驟

1. 主畫面右上角 → 聯絡人圖示
2. 點「新增連絡人」→ 輸入姓名 + 電話 → 儲存

### 語音撥打

說出以下任一形式觸發撥號（以「媽媽」為例）：

| 說法 | 效果 |
|------|------|
| 「打給媽媽」 | 自動撥號給聯絡人「媽媽」 |
| 「聯絡媽媽」 | 自動撥號 |
| 「媽媽打電話」 | 自動撥號 |

> 連絡人儲存在手機本機 SQLite，不需伺服器登入即可使用。

---

## 後台管理

### 進入方式

主畫面右上角有一個**不顯眼的小鎖圖示**，**長按**即可進入後台登入頁面。

### 預設帳密

| 帳號 | 密碼 |
|------|------|
| admin | 1124 |

> 建議登入後立即到使用者管理修改密碼。

### 角色權限

| 角色 | 使用前台 | 進後台 | 管理用戶 |
|------|----------|--------|----------|
| User | 可 | 不可 | 不可 |
| Operator | 可 | 可 | 不可 |
| Admin | 可 | 可 | 可 |

### 後台功能

- **使用者管理**（Admin 限定）：新增 / 停用 / 改角色 / 改密碼 / 刪除
- **系統狀態**：伺服器連線狀態、目前導航狀態

### 登出後台

後台頁面右上角 → 登出圖示 → 回到前台（前台功能不受影響）。

---

## 連線模式切換

APP 設定頁支援兩種連線模式，視使用情境切換：

| 模式 | 適用情境 | 設定內容 |
|------|---------|---------|
| **IP 模式** | 手機與伺服器在同一 Wi-Fi | 輸入伺服器的區網 IP（例如 `192.168.1.100`）與 Port |
| **URL 模式** | 手機在外出、不同網路 | 輸入 Cloudflare Tunnel 或 VSCode Dev Tunnels 產生的公網 URL |

切換方式：主畫面右上角 → 設定圖示 → 選擇「IP 模式」或「URL 模式」→ 填入對應資訊 → 儲存。

---

## 常見問題

**Q：App 顯示「搜尋伺服器中...」然後跳到設定頁**

- 確認手機和電腦在**同一 Wi-Fi**
- 確認伺服器已啟動（看到 `[DISCOVERY] UDP 廣播已啟動`）
- 部分 Wi-Fi 路由器會封鎖廣播封包 → 改用手動設定 IP

**Q：語音沒有反應**

- 確認已允許麥克風權限（手機設定 → 應用程式 → AI 智慧眼鏡 → 權限）
- 先說喚醒詞「哈囉 曼波」再說指令
- 或直接按畫面按鈕

**Q：背景服務被系統殺掉**

手機設定 → 電池 → 找到「AI智慧眼鏡」→ 設為「不限制背景活動」（各品牌手機設定位置略有不同）

**Q：build 失敗**

```bash
flutter clean && flutter pub get && flutter run
```

**Q：如何使用公網連線？**

啟動 Cloudflare Tunnel（`cloudflared tunnel --url http://localhost:8081`），複製產生的 URL，在 APP 設定頁切換到「URL 模式」並貼上。

---

## 專案目錄結構

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
│   ├── websocket_service.dart     # WebSocket 連線管理
│   ├── camera_service.dart        # 攝影機串流
│   ├── audio_service.dart         # 麥克風 + 播放 + 前台服務
│   └── imu_service.dart           # 加速度計 / 陀螺儀
├── screens/
│   ├── splash_screen.dart         # 啟動 + 自動發現
│   ├── home_screen.dart           # 前台主畫面（免登入）
│   ├── settings_screen.dart       # 手動設定 IP / URL
│   ├── contacts_screen.dart       # 緊急連絡人
│   ├── admin_login_screen.dart    # 後台登入（長按鎖圖示進入）
│   └── admin/
│       ├── admin_screen.dart      # 後台首頁
│       └── user_manage_screen.dart # 使用者管理
└── widgets/
    ├── nav_button.dart            # 大按鈕元件
    └── status_banner.dart         # 狀態橫幅
```
