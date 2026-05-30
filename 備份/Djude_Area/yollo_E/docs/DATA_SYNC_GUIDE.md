# 資料同步指南

> 確保所有組員的訓練資料保持一致，避免資料缺漏或訓練偏差。

---

## 必須回傳 GitHub 的資料

使用系統後，以下檔案會在本地產生或更新，**每次使用完畢後都必須 commit 並 push**：

### 1. 使用者回饋紀錄（最重要）

| 檔案 | 說明 |
|------|------|
| `data/feedback/feedback.jsonl` | 所有「確認正確」和「更正錯誤」的回饋紀錄 |
| `data/feedback/images/*.jpg` | 回饋時自動裁切的偵測區域截圖 |

這是未來訓練模型的核心資料。每筆紀錄包含：
- `type`: `confirm`（確認正確）或 `correct`（更正誤判）
- `class`: 原始偵測類別
- `correct_class`: 更正後的正確類別（僅 correct 類型）
- `confidence`: 模型信心度
- `bbox`: 偵測框座標
- `image_path`: 對應截圖路徑

### 2. 自定義類別

| 檔案 | 說明 |
|------|------|
| `data/custom_classes.json` | 使用者透過網頁「註冊新物品」新增的類別 |

包含新增的英文名稱、中文名稱、新增時間。所有人共用同一份類別清單。

### 3. 偵測紀錄

| 檔案 | 說明 |
|------|------|
| `data/detection_logs/detections_YYYYMMDD.jsonl` | 每日偵測紀錄（按日期分檔） |

記錄每次偵測的類別、信心度、時間戳，可用於分析模型表現趨勢。

### 4. 標註資料

| 檔案 | 說明 |
|------|------|
| `data/annotations/annotations.json` | 標註過的偵測紀錄（含 bbox、類別、圖片路徑） |
| `data/annotation_images/*.jpg` | 標註對應的原始圖片 |

---

## 不需要上傳的檔案（已被 .gitignore 排除）

| 檔案/目錄 | 原因 |
|-----------|------|
| `.env` | 包含敏感設定（API Key、模型路徑等） |
| `models/pretrained/*.pt` | 模型檔案太大 |
| `data/database/*.db` | 本地資料庫，各自獨立 |
| `runs/`、`weights/` | 訓練輸出，各自獨立 |
| `logs/`、`*.log` | 執行日誌，僅本地使用 |

---

## 每次使用後的同步流程

```bash
# 1. 先拉取最新資料（避免衝突）
git pull origin main

# 2. 查看本地有哪些新資料
git status

# 3. 加入所有資料檔案
git add data/feedback/ data/custom_classes.json data/detection_logs/ data/annotations/

# 4. 提交（訊息使用英文）
git commit -m "data: add feedback and detection logs from [你的名字/日期]"

# 5. 推送
git push origin main
```

---

## 注意事項

### 資料衝突處理
- `feedback.jsonl` 是逐行附加格式（JSONL），多人同時使用可能產生衝突
- 如果遇到 merge conflict，**保留所有行**（兩邊的資料都是有效的）
- `custom_classes.json` 如果衝突，需手動合併確保所有類別都保留

### 避免訓練偏差
- **所有組員的回饋資料都要上傳**，否則模型只會學到部分人的校正結果
- 確認（confirm）和更正（correct）同樣重要 — 確認幫助模型強化正確判斷
- 不同環境（光線、角度、背景）的資料越多越好

### 圖片路徑
- 回饋截圖的 `image_path` 記錄的是產生時的絕對路徑，僅供參考
- 實際圖片統一存放在 `data/feedback/images/` 目錄下
- 訓練時應以相對路徑 `data/feedback/images/檔名.jpg` 存取
