# YOLOE 偵測準確率提升與用戶反饋系統 — 設計文件

**日期**: 2026-03-19
**狀態**: 已核准（v2 — 修正審核意見）

---

## 背景

YOLOE 網頁偵測系統在實際使用中存在三類準確率問題：
- **漏偵測**：物品在畫面中但未被偵測到
- **誤偵測**：偵測到但類別判斷錯誤
- **誤報**：將背景或不相關物體當成物品

系統用途為日常物品偵測（包含便利商店/超市場景），運行於 RTX 3060 Laptop GPU。

## 目標

1. 透過推論參數調優立即提升偵測準確率
2. 新增時序穩定化消除閃爍誤報
3. 建立用戶反饋機制，使系統越用越準
4. 保留動態新增偵測類別的能力

---

## 設計方案

### 一、預設類別精簡

將 `.env` 中的 `DETECTION_CLASSES` 從 30 個精簡為 10 個高頻測試物品：

```
cell phone, mouse, keyboard, laptop, bottle, cup, remote, book, backpack, keys
```

**理由**：CLIP 開放詞彙模型類別越少越精確，建議控制在 15-20 個以內。

**動態新增**：保留現有網頁「註冊新物品」機制，透過 `custom_classes.json` 持久化、`PromptEnhancer` 自動增強提示。用戶可隨時新增臨時測試物品。

---

### 二、推論參數調優

#### 2.1 信心度門檻分離

| 用途 | 環境變數 | 值 | 說明 |
|------|----------|-----|------|
| 畫面顯示 | `CONFIDENCE_THRESHOLD` | `0.3` | 寬鬆，避免漏報 |
| 記錄/資料庫 | `RECORD_CONFIDENCE_THRESHOLD` | `0.55` | 嚴格，減少誤報 |

**理由**：CLIP 文字-圖像對齊分數比封閉詞彙模型低 10-15%，`0.5` 作為顯示門檻偏高。

#### 2.2 其他推論參數

| 參數 | 現值 | 新值 | 理由 |
|------|------|------|------|
| `imgsz` | 640（硬編碼） | 可配置，預設 640 | 新增 `DETECTION_IMGSZ` 環境變數 |
| `iou_threshold` | 0.45 | 保持 0.45 | 改為可配置 `DETECTION_IOU_THRESHOLD`，觀察實際狀況再調 |
| `augment` | False | 保持 False | 穩定化 + 自適應門檻已足夠，避免雙倍 GPU 負載 |

#### 2.3 `.env` 新增參數

```env
DETECTION_IMGSZ=640
RECORD_CONFIDENCE_THRESHOLD=0.55
DETECTION_IOU_THRESHOLD=0.45
STABILIZER_WINDOW_SIZE=3
STABILIZER_MIN_HITS=2
```

#### 2.4 修改位置

- `src/config.py` (`ModelConfig` dataclass) — 新增欄位：
  - `detection_imgsz: int`（預設 640）
  - `record_confidence_threshold: float`（預設 0.55）
  - `detection_iou_threshold: float`（預設 0.45）
  - `stabilizer_window_size: int`（預設 3）
  - `stabilizer_min_hits: int`（預設 2）
- `src/detection/yolo_detector.py` — `__init__` 新增 `imgsz` 參數，`detect()` 使用 `self.imgsz`
- `src/web_server.py` — 透過 `get_config().model` 讀取所有新參數，CLI `--confidence` 預設改為 `None`，以 `.env` 為單一真實來源

---

### 三、時序穩定化

#### 3.1 DetectionStabilizer

新增 `src/detection/stabilizer.py`：

```python
class DetectionStabilizer:
    """時序偵測結果穩定化：物品需連續出現 N 幀才報告"""

    def __init__(self, window_size=3, min_hits=2):
        ...

    def update(self, detections: list) -> list:
        """輸入原始 DetectionResult 列表，回傳穩定的偵測列表"""
        ...
```

**邏輯**：
- 維護最近 `window_size`（預設 3）幀的偵測結果
- 某類別需在視窗中出現至少 `min_hits`（預設 2）次才確認
- 從最新幀中篩選穩定的偵測結果回傳
- 參數可透過 `.env` 的 `STABILIZER_WINDOW_SIZE` / `STABILIZER_MIN_HITS` 調整

**延遲分析**：在 5-10 FPS 下，`window_size=3, min_hits=2` 的確認延遲約 0.2-0.4 秒，對視障輔助系統是可接受的範圍。

#### 3.2 假正例後處理過濾

在 `stabilizer.py` 中新增過濾函式：

```python
def filter_false_positives(detections: List[DetectionResult], frame_shape: tuple) -> List[DetectionResult]:
    """過濾明顯的假正例

    參數:
        detections: yolo_detector.DetectionResult 物件列表
        frame_shape: frame.shape (numpy array 的 shape，即 (H, W, C))
    """
```

**過濾規則**：
- 極小框：面積 < 畫面 0.1%
- 佔滿畫面框：面積 > 畫面 90%
- 異常長寬比：> 10:1 或 < 1:10

**注意**：過濾操作在 `DetectionResult` 物件上進行（非 dict），必須在 dict 轉換之前執行。

#### 3.3 整合位置

- `WebDetectionServer.__init__()` 中實例化 `self.stabilizer = DetectionStabilizer()`（跨幀狀態持久化）
- `src/web_server.py` 的 `_detect_frame()` 中，呼叫順序：
  1. `self.detector.detect(frame)` → 取得原始 `FrameDetectionResult`
  2. `filter_false_positives(result.detections, frame.shape)` → 過濾假正例
  3. `self.stabilizer.update(filtered_detections)` → 時序穩定化
  4. 將穩定結果轉為 dict 回傳

---

### 四、用戶反饋系統

#### 4.1 FeedbackManager

新增 `src/detection/feedback.py`：

```python
import threading

class FeedbackManager:
    """用戶反饋收集與自適應信心度門檻

    執行緒安全：所有檔案 I/O 使用 threading.Lock 保護。
    自適應門檻快取在記憶體中，僅在 recalculate_thresholds() 時寫入磁碟。
    """

    def __init__(self, feedback_dir: str = "data/feedback"):
        self._lock = threading.Lock()
        self._thresholds_cache: Dict[str, float] = {}  # 記憶體快取
        ...

    def record_feedback(self, feedback_type, class_name, confidence, bbox, correct_class=None):
        """記錄一筆反饋（執行緒安全）"""
        with self._lock:
            # 追加寫入 feedback.jsonl
            ...

    def get_class_threshold(self, class_name) -> float:
        """取得某類別的自適應門檻（讀取記憶體快取，無需加鎖）"""
        return self._thresholds_cache.get(class_name, self._thresholds_cache.get("_default", 0.3))

    def recalculate_thresholds(self):
        """根據累積反饋重新計算各類別最佳門檻（執行緒安全）"""
        with self._lock:
            # 讀取 feedback.jsonl → 計算 → 更新記憶體快取 → 寫入 class_thresholds.json
            ...
```

#### 4.2 反饋類型

| 類型 | 觸發操作 | 儲存資料 |
|------|----------|----------|
| `confirm` | 點擊偵測框 → 「正確」 | 類別名、信心度、bbox、時間戳 |
| `correct` | 點擊偵測框 → 選擇正確類別 | 原判斷、正確類別、信心度 |
| `false_positive` | 點擊偵測框 → 「誤報」 | 類別名、信心度 |

#### 4.3 資料儲存

- 反饋記錄：`data/feedback/feedback.jsonl`（每行一筆 JSON，追加寫入）
- 自適應門檻：`data/feedback/class_thresholds.json`

```json
// feedback.jsonl 範例
{"type": "confirm", "class": "mouse", "confidence": 0.42, "timestamp": "2026-03-19T14:30:00"}
{"type": "false_positive", "class": "keys", "confidence": 0.31, "timestamp": "2026-03-19T14:31:00"}
{"type": "correct", "class": "cup", "correct_class": "bottle", "confidence": 0.38, "timestamp": "2026-03-19T14:32:00"}
```

```json
// class_thresholds.json 範例
{
  "mouse": 0.28,
  "keys": 0.45,
  "cell phone": 0.32,
  "_default": 0.3
}
```

#### 4.4 自適應門檻計算邏輯

- 收集某類別至少 10 筆反饋後才計算
- 取所有 `confirm` 的信心度值的 P10（第 10 百分位數）作為門檻下限
- 取所有 `false_positive` 的信心度值的 P90（第 90 百分位數）作為門檻上限
- 最佳門檻 = 下限與上限的中間值
- **邊界條件**：
  - 若只有 `confirm` 反饋（無 `false_positive`）：門檻 = P10 of confirms
  - 若只有 `false_positive` 反饋（無 `confirm`）：門檻 = P90 of false_positives
  - 若兩者皆不足 10 筆：使用全域預設值 `0.3`

#### 4.5 API 端點

```
POST /api/feedback
Body: { "type": "confirm|correct|false_positive", "class_name": "mouse", "confidence": 0.42, "bbox": [x1,y1,x2,y2], "correct_class": "bottle" }
Response: { "success": true, "message": "反饋已記錄" }

GET /api/feedback/stats
Response: { "total": 50, "by_type": {"confirm": 30, "correct": 10, "false_positive": 10}, "class_thresholds": {...} }
```

#### 4.6 前端 UI

**替換現有的 `_showCorrectionDialog()` prompt 對話框**，改為 modal 彈窗：

點擊偵測框後彈出選項：
- 「正確」按鈕（綠色）→ 呼叫 `POST /api/feedback` (`type: "confirm"`)
- 「這不是 {class_name}」→ 展開類別選擇器 → 呼叫 `POST /api/feedback` (`type: "correct"`)，若選擇的類別不存在，同時呼叫 `POST /api/classes` 新增
- 「誤報」按鈕（紅色）→ 呼叫 `POST /api/feedback` (`type: "false_positive"`)

#### 4.7 記錄門檻的應用位置

在 `_detect_frame()` 中，偵測結果分為兩路：
- **顯示路徑**：使用 `CONFIDENCE_THRESHOLD`（0.3）的結果回傳給前端
- **記錄路徑**：從顯示結果中篩選 `confidence >= RECORD_CONFIDENCE_THRESHOLD`（0.55）的結果，傳入 `self.detection_logger.log()`

#### 4.8 反饋時截取物品區域圖片

當用戶提交 `confirm` 或 `correct` 反饋時：
1. 前端從 canvas 裁剪該偵測框區域，編碼為 base64
2. 隨反饋 API 一起上傳：`POST /api/feedback` body 新增 `"image": "base64..."`
3. 後端將截圖存入 `data/feedback/images/{class_name}_{timestamp}.jpg`
4. 反饋記錄中新增 `"image_path"` 欄位指向該圖片

**用途**：
- 累積的截圖可作為未來微調 YOLO 模型的訓練資料
- YOLOE 的 CLIP 架構支援圖像嵌入作為視覺提示，截圖可用於生成更精確的視覺嵌入（比純文字描述更強）
- 未來可實作：從已確認的截圖中提取 CLIP 視覺嵌入，與文字嵌入結合，提升特定物品的辨識能力

---

### 五、除錯面板改造

#### 5.1 預設收合

將除錯面板改為**預設隱藏、可展開/收合**：
- 右下角顯示一個小圖示按鈕（如 `🔧`），點擊展開除錯日誌
- 展開後可再點擊收合
- 不再佔用日常使用空間

#### 5.2 標註狀態面板（取代除錯面板的位置）

在右下角新增**標註狀態面板**，顯示：

```
┌─────────────────────────┐
│ 📋 標註狀態              │
│                         │
│ 🖱 滑鼠      ✅ 8 次     │
│ 📱 手機      ✅ 5 次     │
│ 🔑 鑰匙     ⚠️ 2 次     │
│ 🧴 瓶子      ❌ 3 次(誤報)│
│                         │
│ 總反饋: 18 筆           │
└─────────────────────────┘
```

- 即時顯示各類別的反饋次數（confirm / correct / false_positive）
- `✅` 表示以確認為主的類別，`⚠️` 表示反饋不足，`❌` 表示誤報較多
- 面板預設顯示（不大，不擋操作），可收合

#### 5.3 資料來源

標註狀態面板的資料來自 `GET /api/feedback/stats` API，前端每 10 秒輪詢一次更新。

---

## 修改檔案清單

| 檔案 | 類型 | 改動說明 |
|------|------|----------|
| `.env` | 修改 | 精簡 `DETECTION_CLASSES`、降低 `CONFIDENCE_THRESHOLD` 至 0.3、新增 `DETECTION_IMGSZ`、`RECORD_CONFIDENCE_THRESHOLD`、`DETECTION_IOU_THRESHOLD`、`STABILIZER_WINDOW_SIZE`、`STABILIZER_MIN_HITS` |
| `src/config.py` | 修改 | `ModelConfig` 新增 `detection_imgsz`、`record_confidence_threshold`、`detection_iou_threshold`、`stabilizer_window_size`、`stabilizer_min_hits` 欄位 |
| `src/detection/stabilizer.py` | 新增 | `DetectionStabilizer` + `filter_false_positives()` |
| `src/detection/feedback.py` | 新增 | `FeedbackManager` 反饋收集 + 自適應門檻（含 threading.Lock）+ 截圖儲存 |
| `src/detection/yolo_detector.py` | 修改 | `imgsz` 可配置；修正 `update_classes()` 使用 `get_text_pe()` + `set_classes()` 兩步驟（與 `_load_model()` 一致） |
| `src/web_server.py` | 修改 | 實例化 stabilizer/feedback_manager；`_detect_frame()` 整合 filter → stabilizer → 雙路輸出；新增反饋 API（含截圖接收）；新增 `GET /api/feedback/stats`；CLI `--confidence` 預設改 None |
| `src/static/app.js` | 修改 | 替換 `_showCorrectionDialog()` 為反饋 modal（正確/更正/誤報）；反饋時裁剪偵測區域上傳；新增標註狀態面板輪詢 |
| `src/static/index.html` | 修改 | 反饋 modal HTML；除錯面板改為可收合（預設隱藏）；新增標註狀態面板 |
| `src/static/style.css` | 修改 | 除錯面板收合樣式；標註狀態面板樣式 |

## 不改動的部分

- 模型檔案（保持 `yoloe-26s-seg.pt`）
- `src/detection/prompt_enhancer.py`（已完善）
- 現有「註冊新物品」功能（保留，反饋的「更正」可觸發新增類別）
- `src/detection/label_mapper.py`
