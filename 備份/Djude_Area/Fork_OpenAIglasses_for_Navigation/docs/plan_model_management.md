# 計畫：Website 模型管理 + 通知系統

> 狀態：規劃中（尚未實作）
> 討論日期：2026-03-19

---

## 背景

專案由兩套獨立系統組成，未來跑在同一台機器上：

| 系統 | 技術 | 用途 |
|------|------|------|
| `Website/` | Django + React + Nginx（Docker） | 對外展示、購買、管理後台 |
| `app_main.py` | FastAPI | 眼鏡 AI 推理、ESP32 通訊（DEBUG 用監控頁） |

---

## 功能一：模型管理（Website 後台上傳 / 切換 .pt）

### 目標
管理員可透過 Website 後台上傳自訓練的 `.pt` 模型，並切換 `app_main.py` 使用的模型，無需手動操作伺服器。

### 架構選擇：方案 A（共用檔案系統 + File Watcher）

```
Website（Django）
  → 上傳 .pt 到 shared/models/
  → 更新 shared/config.json（寫入作用中的模型路徑）

app_main.py
  → 背景執行緒每 3 秒監控 shared/config.json
  → 偵測到變更 → 自動 hot-swap 模型（不重啟 process）
```

**選擇理由：**
- 兩套系統完全解耦，互不影響
- Website 或眼鏡任一方掛掉不影響另一方
- 不需要在 app_main.py 額外開 API 端點
- 同一台機器可直接共用檔案系統

### 共用目錄結構

```
shared/
├── models/
│   ├── yolo26l-seg.pt
│   ├── trafficlight.pt
│   └── （管理員上傳的自訓練模型）
└── config.json
```

`config.json` 格式範例：
```json
{
  "blind_path_model": "shared/models/yolo26l-seg.pt",
  "trafficlight_model": "shared/models/trafficlight.pt",
  "obstacle_model": "shared/models/yoloe-11l-seg.pt",
  "shopping_model": "shared/models/shoppingbest5.pt",
  "updated_at": "2026-03-19T02:00:00"
}
```

### Website 需新增

**Django 後端：**
- 新增 `models_mgmt` App
- `ModelFile` 資料模型（檔名、上傳時間、大小、備註）
- API 端點：
  - `POST /api/models/upload` — 上傳 .pt（admin 權限）
  - `GET  /api/models/` — 列出所有可用模型
  - `POST /api/models/activate` — 切換作用中的模型（寫入 config.json）

**React 前端：**
- 新增管理頁面（admin 角色可見）
- 顯示目前作用中的模型
- 上傳新模型的表單
- 一鍵切換模型的按鈕

### app_main.py 需新增

```python
# 背景執行緒：監控 config.json 變更
def _watch_config():
    while True:
        if config_changed():
            _hot_swap_models()
        time.sleep(3)
```

### Hot-swap 安全機制（重要）

**切換限制：**
- 只有當 `NavigationMaster` 處於 `IDLE` 狀態才允許切換
- 切換時加 Lock，確保推理執行緒等待完成
- 切換前語音提示：「系統升級中，請稍候」
- 切換完成語音提示：「系統已就緒」

**為何不能在使用中切換（危險）：**
1. Race Condition — 推理執行緒與 hot-swap 執行緒同時操作模型 → 崩潰 → 導航完全停止
2. 導航空白期（2~5 秒）— 過馬路等綠燈時模型失效，可能誤判燈號
3. 類別錯位 — 新舊模型類別 id 不同，瞬間錯誤判斷場景

---

## 功能二：模型更新預告通知

### 目標
管理員預先建立「模型更新公告」，使用者在 Android APP 和眼鏡端提前收到通知。

### 流程

```
管理員在 Website 後台建立更新通知
（標題、內容、預計更新時間）
         ↓
    Django 存入資料庫
         ↓
    ┌────┴────┐
    ↓         ↓
Android APP   app_main.py
輪詢 API      每小時輪詢 API
顯示通知橫幅  語音播報給使用者
```

### Django 資料模型

```python
class ModelUpdateNotification(models.Model):
    title        = models.CharField(max_length=100)
    message      = models.TextField()
    scheduled_at = models.DateTimeField()   # 預計更新時間
    created_at   = models.DateTimeField(auto_now_add=True)
    is_active    = models.BooleanField(default=True)
```

### API 端點

```
GET /api/notifications/pending/
→ 回傳目前 is_active=True 的通知清單
→ 公開端點（不需登入）
```

### Android APP

- 開啟 APP 時自動拉取通知
- 首頁顯示通知橫幅或卡片
- 已讀後可關閉

**未來可擴充：FCM 推播**（APP 未開啟也能即時收到通知，需申請 Firebase）

### app_main.py 眼鏡端

```python
def _watch_notifications():
    notified = set()
    while True:
        try:
            resp = requests.get("http://website/api/notifications/pending/")
            for n in resp.json():
                if n["id"] not in notified:
                    audio_player.speak(f"系統通知：{n['message']}")
                    notified.add(n["id"])
        except Exception:
            pass
        time.sleep(3600)  # 每小時檢查
```

---

## 實作順序建議

1. **Website Django** — `ModelUpdateNotification` 資料模型 + `/api/notifications/pending/` 端點
2. **Website React** — 通知管理頁面（建立 / 停用通知）
3. **Android APP** — 首頁輪詢通知並顯示
4. **app_main.py** — 眼鏡語音播報通知
5. **Website Django** — `models_mgmt` App（模型上傳 / 切換）
6. **Website React** — 模型管理頁面
7. **app_main.py** — File Watcher + hot-swap 機制（含安全 Lock）

---

## 未來可擴充

- FCM 推播（APP 背景收通知）
- 模型版本歷史紀錄
- 回滾到上一個模型
- 模型效能比較（上傳後自動跑 benchmark）
- YOLOE-26 升級（替換現有 `yoloe-11l-seg.pt`）
