# YOLOE 偵測準確率提升與用戶反饋系統 — 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 透過參數調優、時序穩定化、用戶反饋機制提升 YOLOE 日常物品偵測準確率

**Architecture:** 分層改進：(1) `.env` + `config.py` 參數層 (2) `stabilizer.py` + `feedback.py` 新模組 (3) `web_server.py` 整合層 (4) 前端 UI 層。每層獨立可測試，逐層整合。

**Tech Stack:** Python 3.11+, FastAPI, Ultralytics YOLOE 8.4.21, JavaScript (vanilla), HTML/CSS

**Spec:** `docs/superpowers/specs/2026-03-19-accuracy-improvement-design.md`

---

## 檔案結構

| 檔案 | 職責 | 類型 |
|------|------|------|
| `.env` | 環境參數（精簡類別、新門檻、stabilizer 設定） | 修改 |
| `src/config.py` | `ModelConfig` 新增欄位讀取新環境變數 | 修改 |
| `src/detection/stabilizer.py` | `DetectionStabilizer` 時序穩定 + `filter_false_positives` 過濾 | 新增 |
| `src/detection/feedback.py` | `FeedbackManager` 反饋收集、截圖儲存、自適應門檻 | 新增 |
| `src/detection/yolo_detector.py` | `imgsz` 可配置 + 修正 `update_classes()` | 修改 |
| `src/web_server.py` | 整合 stabilizer/feedback、新增 API、雙路輸出 | 修改 |
| `src/static/app.js` | 反饋 modal、截圖裁剪、標註狀態面板 | 修改 |
| `src/static/index.html` | 除錯面板收合、反饋 modal HTML、標註面板 | 修改 |
| `src/static/style.css` | 新 UI 元件樣式 | 修改 |

---

## Task 1: 環境參數與設定擴展

**Files:**
- Modify: `.env`
- Modify: `src/config.py:64-91`

- [ ] **Step 1: 更新 `.env` 參數**

**替換** 現有的 `DETECTION_CLASSES`（約 30 個類別）為 10 個測試類別。
**修改** `CONFIDENCE_THRESHOLD` 從 `0.5` 改為 `0.3`。
**新增** 以下參數：

```env
# 精簡偵測類別（測試用，從原本 30 個縮減為 10 個）
DETECTION_CLASSES=cell phone,mouse,keyboard,laptop,bottle,cup,remote,book,backpack,keys

# 辨識設定（修改 CONFIDENCE_THRESHOLD 從 0.5 → 0.3）
CONFIDENCE_THRESHOLD=0.3
IOU_THRESHOLD=0.45
DETECTION_IMGSZ=640
RECORD_CONFIDENCE_THRESHOLD=0.55

# 穩定化設定
STABILIZER_WINDOW_SIZE=3
STABILIZER_MIN_HITS=2
```

- [ ] **Step 2: 擴展 `ModelConfig`**

在 `src/config.py` 的 `ModelConfig` dataclass 中新增欄位：

```python
# 在 detection_classes 欄位（第 91 行）之後新增：
detection_imgsz: int = field(
    default_factory=lambda: int(os.getenv("DETECTION_IMGSZ", "640"))
)
record_confidence_threshold: float = field(
    default_factory=lambda: float(os.getenv("RECORD_CONFIDENCE_THRESHOLD", "0.55"))
)
stabilizer_window_size: int = field(
    default_factory=lambda: int(os.getenv("STABILIZER_WINDOW_SIZE", "3"))
)
stabilizer_min_hits: int = field(
    default_factory=lambda: int(os.getenv("STABILIZER_MIN_HITS", "2"))
)
```

- [ ] **Step 3: 驗證設定載入**

```bash
cd c:/Users/user/Desktop/OpenAIDevice_For_VisualImpairment/Djude_Area/yollo_E
.venv/Scripts/python.exe -c "from src.config import get_config; c = get_config(); print(f'conf={c.model.confidence_threshold}, imgsz={c.model.detection_imgsz}, rec={c.model.record_confidence_threshold}, win={c.model.stabilizer_window_size}, hits={c.model.stabilizer_min_hits}')"
```

預期輸出：`conf=0.3, imgsz=640, rec=0.55, win=3, hits=2`

- [ ] **Step 4: Commit**

```bash
git add .env src/config.py
git commit -m "feat: 新增偵測參數設定（信心度分離、stabilizer、imgsz）"
```

---

## Task 2: DetectionStabilizer 時序穩定化模組

**Files:**
- Create: `src/detection/stabilizer.py`

- [ ] **Step 1: 建立 `stabilizer.py`**

```python
# ============================================
# 偵測結果時序穩定化與假正例過濾
# ============================================
"""
透過滑動視窗過濾閃爍的偵測結果，僅保留持續出現的穩定偵測。
同時提供基於面積/長寬比的假正例過濾。
"""

from collections import deque, Counter
from typing import List, Tuple
from loguru import logger


class DetectionStabilizer:
    """時序偵測結果穩定化：物品需連續出現 N 幀才報告"""

    def __init__(self, window_size: int = 3, min_hits: int = 2):
        """
        參數:
            window_size: 滑動視窗大小（幀數）
            min_hits: 某類別至少出現幾次才確認為穩定偵測
        """
        self.window_size = window_size
        self.min_hits = min_hits
        self._history: deque = deque(maxlen=window_size)

        logger.info(f"偵測穩定化已初始化: window={window_size}, min_hits={min_hits}")

    def update(self, detections: list) -> list:
        """
        輸入原始偵測結果，回傳穩定的偵測列表

        參數:
            detections: DetectionResult 物件列表（來自 yolo_detector.detect()）

        回傳:
            穩定的 DetectionResult 物件列表（從最新幀中篩選）
        """
        # 記錄本幀的類別名稱
        current_classes = [d.class_name for d in detections]
        self._history.append(current_classes)

        # 資料不足時直接回傳
        if len(self._history) < 2:
            return detections

        # 統計各類別在視窗中出現的次數
        all_classes = [cls for frame_classes in self._history for cls in frame_classes]
        counts = Counter(all_classes)

        # 篩選穩定的類別
        stable_classes = {
            cls for cls, cnt in counts.items()
            if cnt >= self.min_hits
        }

        # 從最新幀中篩選穩定的偵測結果
        return [d for d in detections if d.class_name in stable_classes]

    def reset(self):
        """重置歷史記錄"""
        self._history.clear()


def filter_false_positives(detections: list, frame_shape: tuple) -> list:
    """
    過濾明顯的假正例

    參數:
        detections: DetectionResult 物件列表
        frame_shape: 影像的 shape (H, W, C)

    回傳:
        過濾後的 DetectionResult 物件列表
    """
    if not detections or len(frame_shape) < 2:
        return detections

    h, w = frame_shape[:2]
    frame_area = h * w
    filtered = []

    for det in detections:
        bbox = det.bbox
        box_w = bbox.x2 - bbox.x1
        box_h = bbox.y2 - bbox.y1
        box_area = box_w * box_h
        area_ratio = box_area / frame_area if frame_area > 0 else 0

        # 規則 1: 過濾極小框（面積 < 畫面 0.1%）
        if area_ratio < 0.001:
            continue

        # 規則 2: 過濾佔滿畫面的框（面積 > 90%）
        if area_ratio > 0.9:
            continue

        # 規則 3: 過濾長寬比異常的框（> 10:1 或 < 1:10）
        aspect_ratio = box_w / (box_h + 1e-6)
        if aspect_ratio > 10 or aspect_ratio < 0.1:
            continue

        filtered.append(det)

    removed = len(detections) - len(filtered)
    if removed > 0:
        logger.debug(f"假正例過濾: 移除 {removed} 個異常偵測框")

    return filtered
```

- [ ] **Step 2: 驗證模組可匯入**

```bash
.venv/Scripts/python.exe -c "from src.detection.stabilizer import DetectionStabilizer, filter_false_positives; s = DetectionStabilizer(3, 2); print('stabilizer OK')"
```

預期：`stabilizer OK`

- [ ] **Step 3: Commit**

```bash
git add src/detection/stabilizer.py
git commit -m "feat: 新增 DetectionStabilizer 時序穩定化與假正例過濾"
```

---

## Task 3: FeedbackManager 反饋系統模組

**Files:**
- Create: `src/detection/feedback.py`

- [ ] **Step 1: 建立 `feedback.py`**

```python
# ============================================
# 用戶反饋收集與自適應信心度門檻
# ============================================
"""
收集用戶對偵測結果的反饋（確認正確/更正類別/標記誤報），
並根據累積反饋自動計算每個類別的最佳信心度門檻。
同時儲存反饋時的物品截圖，供未來模型增強使用。
"""

import json
import time
import base64
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from loguru import logger


class FeedbackManager:
    """用戶反饋收集與自適應信心度門檻"""

    def __init__(
        self,
        feedback_dir: Optional[str] = None,
        default_threshold: float = 0.3,
    ):
        """
        參數:
            feedback_dir: 反饋資料存放目錄
            default_threshold: 全域預設信心度門檻
        """
        if feedback_dir is None:
            self._feedback_dir = Path(__file__).parent.parent.parent / "data" / "feedback"
        else:
            self._feedback_dir = Path(feedback_dir)

        self._feedback_dir.mkdir(parents=True, exist_ok=True)
        (self._feedback_dir / "images").mkdir(parents=True, exist_ok=True)

        self._feedback_file = self._feedback_dir / "feedback.jsonl"
        self._thresholds_file = self._feedback_dir / "class_thresholds.json"

        self._lock = threading.Lock()
        self._default_threshold = default_threshold

        # 記憶體快取：自適應門檻
        self._thresholds_cache: Dict[str, float] = {"_default": default_threshold}

        # 啟動時載入已有的門檻
        self._load_thresholds()

        logger.info(f"反饋管理器已初始化，目錄: {self._feedback_dir}")

    def _load_thresholds(self):
        """從磁碟載入自適應門檻"""
        if self._thresholds_file.exists():
            try:
                with open(self._thresholds_file, "r", encoding="utf-8") as f:
                    self._thresholds_cache = json.load(f)
                logger.info(f"已載入 {len(self._thresholds_cache)} 個自適應門檻")
            except Exception as e:
                logger.warning(f"載入自適應門檻失敗: {e}")

    def record_feedback(
        self,
        feedback_type: str,
        class_name: str,
        confidence: float,
        bbox: Optional[List[int]] = None,
        correct_class: Optional[str] = None,
        image_base64: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        記錄一筆反饋（執行緒安全）

        參數:
            feedback_type: "confirm" | "correct" | "false_positive"
            class_name: 偵測到的類別名稱
            confidence: 偵測信心度
            bbox: 邊界框 [x1, y1, x2, y2]
            correct_class: 正確的類別名稱（僅 correct 類型需要）
            image_base64: 裁剪的物品區域圖片（base64 編碼）

        回傳:
            記錄結果 dict
        """
        timestamp = datetime.now().isoformat()
        image_path = None

        # 儲存截圖
        if image_base64:
            try:
                safe_name = class_name.replace(" ", "_").replace("/", "_")
                ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{safe_name}_{ts_str}.jpg"
                image_path = str(self._feedback_dir / "images" / filename)

                # 解碼並儲存
                if "," in image_base64:
                    image_base64 = image_base64.split(",", 1)[1]
                image_data = base64.b64decode(image_base64)
                with open(image_path, "wb") as f:
                    f.write(image_data)

                logger.debug(f"已儲存反饋截圖: {filename}")
            except Exception as e:
                logger.warning(f"儲存反饋截圖失敗: {e}")
                image_path = None

        record = {
            "type": feedback_type,
            "class": class_name,
            "confidence": round(confidence, 3),
            "bbox": bbox,
            "correct_class": correct_class,
            "image_path": image_path,
            "timestamp": timestamp,
        }

        with self._lock:
            try:
                with open(self._feedback_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                logger.info(f"反饋已記錄: {feedback_type} - {class_name} ({confidence:.3f})")
            except Exception as e:
                logger.error(f"寫入反饋失敗: {e}")
                return {"success": False, "error": str(e)}

        return {"success": True, "record": record}

    def get_class_threshold(self, class_name: str) -> float:
        """取得某類別的自適應門檻（讀取記憶體快取）"""
        return self._thresholds_cache.get(
            class_name,
            self._thresholds_cache.get("_default", self._default_threshold)
        )

    def recalculate_thresholds(self) -> Dict[str, float]:
        """根據累積反饋重新計算各類別最佳門檻（執行緒安全）"""
        with self._lock:
            return self._recalculate_thresholds_internal()

    def _recalculate_thresholds_internal(self) -> Dict[str, float]:
        """內部門檻計算（須持有 _lock）"""
        if not self._feedback_file.exists():
            return self._thresholds_cache

        # 收集各類別的反饋
        class_confirms: Dict[str, List[float]] = {}
        class_false_positives: Dict[str, List[float]] = {}

        try:
            with open(self._feedback_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        cls = record.get("class", "")
                        conf = record.get("confidence", 0)
                        fb_type = record.get("type", "")

                        if fb_type == "confirm":
                            class_confirms.setdefault(cls, []).append(conf)
                        elif fb_type == "false_positive":
                            class_false_positives.setdefault(cls, []).append(conf)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"讀取反饋檔案失敗: {e}")
            return self._thresholds_cache

        # 計算各類別門檻
        new_thresholds = {"_default": self._default_threshold}
        all_classes = set(list(class_confirms.keys()) + list(class_false_positives.keys()))

        for cls in all_classes:
            confirms = class_confirms.get(cls, [])
            false_pos = class_false_positives.get(cls, [])

            # 至少需要 10 筆反饋
            if len(confirms) + len(false_pos) < 10:
                continue

            if confirms and false_pos:
                # 兩者都有：取中間值
                p10_confirm = sorted(confirms)[max(0, len(confirms) // 10)]
                p90_fp = sorted(false_pos)[min(len(false_pos) - 1, len(false_pos) * 9 // 10)]
                new_thresholds[cls] = round((p10_confirm + p90_fp) / 2, 3)
            elif confirms:
                # 只有 confirm：用 P10
                p10 = sorted(confirms)[max(0, len(confirms) // 10)]
                new_thresholds[cls] = round(p10, 3)
            elif false_pos:
                # 只有 false_positive：用 P90
                p90 = sorted(false_pos)[min(len(false_pos) - 1, len(false_pos) * 9 // 10)]
                new_thresholds[cls] = round(p90, 3)

        self._thresholds_cache = new_thresholds

        # 寫入磁碟
        try:
            with open(self._thresholds_file, "w", encoding="utf-8") as f:
                json.dump(new_thresholds, f, ensure_ascii=False, indent=2)
            logger.info(f"已更新 {len(new_thresholds) - 1} 個類別的自適應門檻")
        except Exception as e:
            logger.error(f"寫入門檻檔案失敗: {e}")

        return new_thresholds

    def get_stats(self) -> Dict[str, Any]:
        """取得反饋統計"""
        stats = {
            "total": 0,
            "by_type": {"confirm": 0, "correct": 0, "false_positive": 0},
            "by_class": {},
            "class_thresholds": self._thresholds_cache.copy(),
        }

        if not self._feedback_file.exists():
            return stats

        with self._lock:
            try:
                with open(self._feedback_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                            stats["total"] += 1
                            fb_type = record.get("type", "")
                            cls = record.get("class", "unknown")

                            if fb_type in stats["by_type"]:
                                stats["by_type"][fb_type] += 1

                            if cls not in stats["by_class"]:
                                stats["by_class"][cls] = {"confirm": 0, "correct": 0, "false_positive": 0}
                            if fb_type in stats["by_class"][cls]:
                                stats["by_class"][cls][fb_type] += 1
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                stats["error"] = str(e)

        return stats
```

- [ ] **Step 2: 驗證模組可匯入**

```bash
.venv/Scripts/python.exe -c "from src.detection.feedback import FeedbackManager; fm = FeedbackManager(); print(f'feedback OK, dir={fm._feedback_dir}')"
```

- [ ] **Step 3: Commit**

```bash
git add src/detection/feedback.py
git commit -m "feat: 新增 FeedbackManager 用戶反饋收集與自適應門檻"
```

---

## Task 4: YOLODetector 修改

**Files:**
- Modify: `src/detection/yolo_detector.py:100-130` (\_\_init\_\_)
- Modify: `src/detection/yolo_detector.py:280-290` (detect)
- Modify: `src/detection/yolo_detector.py:440-468` (update_classes)

- [ ] **Step 1: `__init__` 新增 `imgsz` 參數**

在 `src/detection/yolo_detector.py` 的 `__init__` 中，`use_fp16` 後新增 `imgsz`：

```python
# 修改 __init__ 簽名，新增 imgsz 參數
def __init__(
    self,
    model_path: str = "yoloe-26s-seg.pt",
    confidence_threshold: float = 0.5,
    iou_threshold: float = 0.45,
    device: str = "auto",
    prompt_classes: Optional[List[str]] = None,
    use_fp16: bool = True,
    imgsz: int = 640,  # 新增：推論解析度
):
```

在 `self.use_fp16 = use_fp16` 後加入：

```python
self.imgsz = imgsz
```

- [ ] **Step 2: `detect()` 使用 `self.imgsz`**

在 `detect()` 方法中，將硬編碼的 `imgsz=640` 改為 `self.imgsz`：

```python
results = self.model(
    image,
    conf=conf,
    iou=iou,
    classes=classes,
    imgsz=self.imgsz,  # 改為使用設定值
    augment=False,
    verbose=False
)
```

- [ ] **Step 3: 修正 `update_classes()` 使用 `get_text_pe()`**

將 `update_classes()` 中的 `self.model.set_classes(enhanced)` 改為兩步驟：

```python
def update_classes(self, new_classes: List[str]) -> bool:
    if not self._is_yoloe:
        logger.warning("非 YOLOE 模型，無法動態更新偵測類別")
        return False

    if not new_classes:
        logger.warning("偵測類別列表為空，跳過更新")
        return False

    try:
        enhanced, mapping = self._prompt_enhancer.enhance_list(new_classes)
        self._enhanced_to_original = mapping

        # 注意：CLIP 的 get_text_pe() 需要 FP32 精度。
        # 若模型已啟用 FP16，需暫時切回 FP32 執行嵌入生成，再切回 FP16。
        was_fp16 = False
        if self.use_fp16 and self._cuda_available:
            try:
                self.model.model.float()  # 暫時切回 FP32
                was_fp16 = True
            except Exception:
                pass

        # 使用 get_text_pe() + set_classes() 兩步驟（與 _load_model 一致）
        text_embeddings = self.model.get_text_pe(enhanced)
        self.model.set_classes(enhanced, text_embeddings)

        # 若之前是 FP16，切回
        if was_fp16:
            try:
                self.model.model.half()
            except Exception:
                pass

        self.prompt_classes = new_classes
        self.class_names = self.model.names
        logger.success(f"已更新偵測類別（共 {len(new_classes)} 個，已增強提示 + 文字嵌入）")
        return True
    except Exception as e:
        logger.error(f"更新偵測類別失敗: {e}")
        return False
```

- [ ] **Step 4: 驗證**

```bash
.venv/Scripts/python.exe -c "from src.detection.yolo_detector import YOLODetector; print('yolo_detector import OK')"
```

- [ ] **Step 5: Commit**

```bash
git add src/detection/yolo_detector.py
git commit -m "feat: YOLODetector 支援 imgsz 設定，修正 update_classes 使用文字嵌入"
```

---

## Task 5: web_server.py 後端整合

**Files:**
- Modify: `src/web_server.py:34-38` (imports)
- Modify: `src/web_server.py:178-268` (WebDetectionServer.__init__)
- Modify: `src/web_server.py:270-498` (_setup_routes)
- Modify: `src/web_server.py:626-717` (_detect_frame)
- Modify: `src/web_server.py:828-833` (CLI args)

- [ ] **Step 1: 新增 imports**

在 `src/web_server.py` 的現有 import 區塊（`from detection.detection_logger import DetectionLogger` 之後）加入：

```python
from detection.stabilizer import DetectionStabilizer, filter_false_positives
from detection.feedback import FeedbackManager
from detection.yolo_detector import FrameDetectionResult
```

- [ ] **Step 2: `__init__` 中初始化 stabilizer 和 feedback_manager**

在 `WebDetectionServer.__init__` 中，`self.detection_logger = DetectionLogger()` 之後加入：

```python
# 偵測穩定化
self.stabilizer = DetectionStabilizer(
    window_size=self.config.model.stabilizer_window_size,
    min_hits=self.config.model.stabilizer_min_hits,
)

# 用戶反饋管理器
self.feedback_manager = FeedbackManager(
    default_threshold=self.confidence,
)

# 記錄信心度門檻
self.record_confidence = self.config.model.record_confidence_threshold
```

- [ ] **Step 3: 在 `__init__` 中傳入 `imgsz` 到 detector**

修改 `_detect_frame()` 中初始化 detector 的部分（第 637 行附近）：

```python
self.detector = YOLODetector(
    model_path=self.model_path,
    confidence_threshold=self.confidence,
    iou_threshold=self.config.model.iou_threshold,
    device=get_device(),
    prompt_classes=prompt_classes,
    use_fp16=not self.config.model.force_cpu,
    imgsz=self.config.model.detection_imgsz,  # 新增
)
```

- [ ] **Step 4: 修改 `_detect_frame()` 整合 stabilizer + 雙路輸出**

**替換** `_detect_frame()` 方法中第 654 行 `result = self.detector.detect(frame)` 之後到第 717 行 return 為止的整段程式碼。完整替換內容如下（從 `result = self.detector.detect(frame)` 之後開始）：

```python
            detect_time = (time.time() - start_time) * 1000
            logger.debug(f"偵測完成: {result.count} 個物件 | {detect_time:.0f}ms")
        except Exception as e:
            logger.error(f"偵測過程發生錯誤: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "detections": [],
                "count": 0,
                "fps": 0.0,
                "timestamp": time.time(),
            }

        # === 新增：假正例過濾 ===
        filtered_detections = filter_false_positives(result.detections, frame.shape)

        # === 新增：時序穩定化 ===
        stable_detections = self.stabilizer.update(filtered_detections)

        # 為每個 detection 設置中文標籤（改用 stable_detections）
        for detection in stable_detections:
            if not detection.class_name_cn:
                detection.class_name_cn = self.label_mapper.get_chinese_name_from_en(
                    detection.class_name
                )

        # 更新 FPS
        self.frame_count += 1
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            self.fps = self.frame_count / elapsed

        # 每 30 幀記錄一次統計
        if self.frame_count % 30 == 1:
            logger.info(f"統計: 已處理 {self.frame_count} 幀 | FPS: {self.fps:.1f}")

        # 構建結果（改用 stable_detections）
        detections = []
        for det in stable_detections:
            detections.append({
                "class_name": det.class_name,
                "class_name_cn": det.class_name_cn or det.class_name,
                "confidence": round(det.confidence, 3),
                "bbox": list(det.bbox.to_tuple()) if det.bbox is not None else None,
            })

        # === 新增：雙路輸出 — 記錄門檻 ===
        if detections:
            high_conf_detections = [
                d for d in detections if d["confidence"] >= self.record_confidence
            ]
            if high_conf_detections:
                self.detection_logger.log(
                    detections=high_conf_detections,
                    fps=result.fps,
                    frame_count=self.frame_count,
                )

        # 建立穩定結果的 FrameDetectionResult 給繪製用
        # （FrameDetectionResult 已在頂部 imports 匯入）
        stable_result = FrameDetectionResult(
            detections=stable_detections,
            inference_time_ms=result.inference_time_ms,
            fps=result.fps,
            frame_shape=result.frame_shape,
        )
        annotated_frame = self.detector.draw_detections(frame, stable_result)

        # 將處理後的畫面編碼為 base64
        _, buffer = cv2.imencode('.jpg', annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        annotated_base64 = base64.b64encode(buffer).decode('utf-8')

        return {
            "detections": detections,
            "count": len(detections),
            "fps": round(result.fps, 1),
            "timestamp": time.time(),
            "annotated_frame": annotated_base64,
        }
```

- [ ] **Step 5: 新增反饋 API 路由**

在 `_setup_routes()` 中，`remove_class` 路由（約第 498 行）之後新增。

**注意**：`TypingList` 是在 `_setup_routes()` 第 326 行定義的 `from typing import List as TypingList`，`FeedbackRequest` 定義在此之後所以可正確引用。

```python
# ============================================
# 反饋 API
# ============================================

class FeedbackRequest(BaseModel):
    type: str  # "confirm" | "correct" | "false_positive"
    class_name: str
    confidence: float = 0.0
    bbox: Optional[TypingList[int]] = None
    correct_class: Optional[str] = None
    image: Optional[str] = None  # base64 截圖

@self.app.post("/api/feedback")
async def submit_feedback(request: FeedbackRequest):
    """提交偵測反饋"""
    if request.type not in ("confirm", "correct", "false_positive"):
        return {"error": "無效的反饋類型"}

    result = self.feedback_manager.record_feedback(
        feedback_type=request.type,
        class_name=request.class_name,
        confidence=request.confidence,
        bbox=request.bbox,
        correct_class=request.correct_class,
        image_base64=request.image,
    )

    # 如果是 correct 且正確類別是新的，同時新增類別
    if request.type == "correct" and request.correct_class:
        env_classes = self._get_env_classes()
        custom = self._load_custom_classes()
        existing = env_classes + [c["name_en"] for c in custom]
        if request.correct_class.lower() not in existing:
            custom.append({
                "name_en": request.correct_class.lower(),
                "name_cn": "",
                "added_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
            self._save_custom_classes(custom)
            self._reload_detector_classes()

    # 每 20 筆反饋重新計算門檻
    stats = self.feedback_manager.get_stats()
    if stats["total"] > 0 and stats["total"] % 20 == 0:
        self.feedback_manager.recalculate_thresholds()

    return result

@self.app.get("/api/feedback/stats")
async def get_feedback_stats():
    """取得反饋統計"""
    return self.feedback_manager.get_stats()
```

- [ ] **Step 6: 修改 CLI `--confidence` 預設值**

修改 `src/web_server.py` 第 828-833 行的 `--confidence` argparse 預設值：

```python
parser.add_argument(
    "--confidence",
    type=float,
    default=None,  # 改為 None（原為 0.5），從 config 讀取
    help="信心度門檻 (0.0 - 1.0)，預設使用 .env 設定",
)
```

修改 `main()` 中第 871-876 行建立 server 的部分：

```python
confidence = args.confidence if args.confidence is not None else get_config().model.confidence_threshold
server = WebDetectionServer(
    model_path=args.model,
    confidence=confidence,
    host=args.host,
    port=args.port,
)
```

- [ ] **Step 7: 驗證伺服器可啟動**

```bash
.venv/Scripts/python.exe -c "from src.web_server import WebDetectionServer; print('web_server import OK')"
```

- [ ] **Step 8: Commit**

```bash
git add src/web_server.py
git commit -m "feat: 整合 stabilizer/feedback 至 web_server，新增反饋 API"
```

---

## Task 6: 前端 — 除錯面板收合 + 標註狀態面板

**Files:**
- Modify: `src/static/index.html:148-163`
- Modify: `src/static/style.css:723-818`

- [ ] **Step 1: 修改 `index.html` — 除錯面板收合 + 標註狀態面板**

將除錯面板區塊替換為：

```html
<!-- 除錯面板（預設收合） -->
<button class="debug-toggle-btn" id="debugToggleBtn" title="除錯日誌">🔧</button>
<div class="debug-panel collapsed" id="debugPanel">
    <div class="debug-header">
        <span>除錯日誌</span>
        <div class="debug-header-buttons">
            <button id="copyDebugBtn" class="debug-clear-btn" title="複製日誌">複製</button>
            <button id="clearDebugBtn" class="debug-clear-btn">清除</button>
            <button id="debugCollapseBtn" class="debug-clear-btn">收合</button>
        </div>
    </div>
    <div class="debug-content" id="debugContent">
        <div class="debug-line debug-info">[系統] 頁面已載入，等待啟動...</div>
    </div>
</div>

<!-- 標註狀態面板 -->
<div class="annotation-panel" id="annotationPanel">
    <div class="annotation-header">
        <span>📋 標註狀態</span>
        <button class="annotation-toggle" id="annotationToggleBtn">−</button>
    </div>
    <div class="annotation-content" id="annotationContent">
        <div class="annotation-empty">尚無反饋資料</div>
    </div>
    <div class="annotation-footer" id="annotationFooter">
        總反饋: 0 筆
    </div>
</div>
```

- [ ] **Step 2: 修改 `style.css` — 新增樣式**

替換整個 `/* Debug Panel */` 區塊並新增標註面板樣式：

```css
/* Debug Toggle Button */
.debug-toggle-btn {
    position: fixed;
    bottom: 10px;
    left: 10px;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    border: 1px solid var(--primary-color);
    background: rgba(20, 20, 30, 0.9);
    color: var(--primary-color);
    font-size: 16px;
    cursor: pointer;
    z-index: 998;
    transition: var(--transition);
}
.debug-toggle-btn:hover {
    background: var(--primary-color);
    color: var(--secondary-color);
}

/* Debug Panel */
.debug-panel {
    position: fixed;
    bottom: 55px;
    left: 10px;
    max-width: 400px;
    max-height: 200px;
    background-color: rgba(20, 20, 30, 0.95);
    border: 1px solid var(--primary-color);
    border-radius: var(--border-radius);
    z-index: 999;
    display: flex;
    flex-direction: column;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
    transition: var(--transition);
}
.debug-panel.collapsed {
    display: none;
}

.debug-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    background-color: var(--surface-color);
    border-bottom: 1px solid rgba(78, 204, 163, 0.3);
    border-radius: var(--border-radius) var(--border-radius) 0 0;
    font-size: 0.85rem;
    color: var(--primary-color);
    font-weight: 600;
}
.debug-header-buttons {
    display: flex;
    gap: 6px;
}
.debug-clear-btn {
    background: transparent;
    border: 1px solid var(--primary-color);
    color: var(--primary-color);
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.75rem;
    cursor: pointer;
    transition: var(--transition);
}
.debug-clear-btn:hover {
    background-color: var(--primary-color);
    color: var(--secondary-color);
}
.debug-content {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 0.75rem;
    line-height: 1.4;
}
.debug-line {
    padding: 2px 0;
    word-break: break-all;
}
.debug-info { color: var(--text-secondary); }
.debug-success { color: var(--success-color); }
.debug-warning { color: var(--warning-color); }
.debug-error { color: var(--error-color); }
.debug-content::-webkit-scrollbar { width: 6px; }
.debug-content::-webkit-scrollbar-track { background: var(--background-color); }
.debug-content::-webkit-scrollbar-thumb { background: var(--surface-color); border-radius: 3px; }
.debug-content::-webkit-scrollbar-thumb:hover { background: var(--primary-color); }

/* Annotation Status Panel */
.annotation-panel {
    position: fixed;
    bottom: 10px;
    right: 10px;
    width: 220px;
    max-height: 300px;
    background-color: rgba(20, 20, 30, 0.95);
    border: 1px solid var(--primary-color);
    border-radius: var(--border-radius);
    z-index: 997;
    display: flex;
    flex-direction: column;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
    font-size: 0.85rem;
}
.annotation-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    background-color: var(--surface-color);
    border-bottom: 1px solid rgba(78, 204, 163, 0.3);
    border-radius: var(--border-radius) var(--border-radius) 0 0;
    color: var(--primary-color);
    font-weight: 600;
}
.annotation-toggle {
    background: transparent;
    border: none;
    color: var(--primary-color);
    font-size: 1.1rem;
    cursor: pointer;
    padding: 0 4px;
}
.annotation-content {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
    max-height: 200px;
}
.annotation-content.collapsed {
    display: none;
}
.annotation-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
}
.annotation-item .class-name {
    color: var(--text-primary);
}
.annotation-item .count {
    font-size: 0.8rem;
    padding: 1px 6px;
    border-radius: 10px;
}
.annotation-item .count.good { background: rgba(76, 175, 80, 0.3); color: #4CAF50; }
.annotation-item .count.warning { background: rgba(255, 193, 7, 0.3); color: #FFC107; }
.annotation-item .count.bad { background: rgba(244, 67, 54, 0.3); color: #F44336; }
.annotation-empty {
    color: var(--text-secondary);
    text-align: center;
    padding: 12px 0;
}
.annotation-footer {
    padding: 6px 12px;
    border-top: 1px solid rgba(78, 204, 163, 0.3);
    color: var(--text-secondary);
    font-size: 0.75rem;
    text-align: right;
}

/* Feedback Modal */
.feedback-modal-overlay {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.6);
    z-index: 1000;
    display: flex;
    justify-content: center;
    align-items: center;
}
.feedback-modal {
    background: var(--surface-color);
    border: 1px solid var(--primary-color);
    border-radius: var(--border-radius);
    padding: 20px;
    min-width: 300px;
    max-width: 400px;
}
.feedback-modal h3 {
    margin: 0 0 12px;
    color: var(--primary-color);
}
.feedback-modal .detection-info {
    margin-bottom: 16px;
    padding: 8px;
    background: rgba(0,0,0,0.3);
    border-radius: 4px;
}
.feedback-modal .btn-group {
    display: flex;
    flex-direction: column;
    gap: 8px;
}
.feedback-modal .btn-confirm {
    background: #4CAF50; color: white; border: none;
    padding: 10px; border-radius: 4px; cursor: pointer; font-size: 0.9rem;
}
.feedback-modal .btn-correct {
    background: #FF9800; color: white; border: none;
    padding: 10px; border-radius: 4px; cursor: pointer; font-size: 0.9rem;
}
.feedback-modal .btn-false-positive {
    background: #F44336; color: white; border: none;
    padding: 10px; border-radius: 4px; cursor: pointer; font-size: 0.9rem;
}
.feedback-modal .btn-cancel {
    background: transparent; color: var(--text-secondary); border: 1px solid var(--text-secondary);
    padding: 8px; border-radius: 4px; cursor: pointer; font-size: 0.85rem; margin-top: 4px;
}
.feedback-modal .correction-input {
    display: none;
    margin-top: 8px;
}
.feedback-modal .correction-input.show {
    display: flex;
    gap: 8px;
}
.feedback-modal .correction-input input {
    flex: 1;
    padding: 8px;
    background: var(--background-color);
    border: 1px solid var(--primary-color);
    border-radius: 4px;
    color: var(--text-primary);
}
.feedback-modal .correction-input button {
    padding: 8px 12px;
    background: var(--primary-color);
    border: none;
    border-radius: 4px;
    cursor: pointer;
}
```

- [ ] **Step 3: Commit**

```bash
git add src/static/index.html src/static/style.css
git commit -m "feat: 除錯面板改為可收合，新增標註狀態面板與反饋 modal 樣式"
```

---

## Task 7: 前端 — JavaScript 反饋邏輯

**Files:**
- Modify: `src/static/app.js:11-28` (constructor DOM refs)
- Modify: `src/static/app.js:90-100` (init)
- Modify: `src/static/app.js:946-1033` (click handler + correction dialog)

- [ ] **Step 1: constructor 新增 DOM 參考**

在 `this.copyDebugBtn` 相關程式碼後新增：

```javascript
// 除錯面板收合
this.debugPanel = document.getElementById('debugPanel');
this.debugToggleBtn = document.getElementById('debugToggleBtn');
this.debugCollapseBtn = document.getElementById('debugCollapseBtn');

// 標註狀態面板
this.annotationPanel = document.getElementById('annotationPanel');
this.annotationContent = document.getElementById('annotationContent');
this.annotationFooter = document.getElementById('annotationFooter');
this.annotationToggleBtn = document.getElementById('annotationToggleBtn');

// 反饋狀態
this._feedbackStatsInterval = null;
```

- [ ] **Step 2: init() 綁定除錯面板與標註面板事件**

在 `init()` 中 `this.closeSettings` 事件之後新增：

```javascript
// 除錯面板收合
if (this.debugToggleBtn) {
    this.debugToggleBtn.addEventListener('click', () => {
        this.debugPanel.classList.toggle('collapsed');
    });
}
if (this.debugCollapseBtn) {
    this.debugCollapseBtn.addEventListener('click', () => {
        this.debugPanel.classList.add('collapsed');
    });
}

// 標註面板收合
if (this.annotationToggleBtn) {
    this.annotationToggleBtn.addEventListener('click', () => {
        const content = this.annotationContent;
        const footer = this.annotationFooter;
        const isCollapsed = content.classList.toggle('collapsed');
        footer.classList.toggle('collapsed', isCollapsed);
        this.annotationToggleBtn.textContent = isCollapsed ? '+' : '−';
    });
}

// 定時更新標註統計
this._feedbackStatsInterval = setInterval(() => this._updateAnnotationPanel(), 10000);
this._updateAnnotationPanel();
```

- [ ] **Step 3: 替換 `_showCorrectionDialog` 為反饋 modal**

**刪除**現有的 `_showCorrectionDialog`（第 973-1003 行）和 `_submitCorrection`（第 1006-1033 行）兩個方法，**替換為**以下四個方法（`_showCorrectionDialog`、`_submitFeedback`、`_updateAnnotationPanel`），插入在同一位置：

```javascript
_showCorrectionDialog(detection, index) {
    // 建立反饋 modal
    const overlay = document.createElement('div');
    overlay.className = 'feedback-modal-overlay';

    const currentName = detection.class_name_cn || detection.class_name;
    const currentNameEn = detection.class_name;

    overlay.innerHTML = `
        <div class="feedback-modal">
            <h3>偵測反饋</h3>
            <div class="detection-info">
                <div>偵測結果: <strong>${currentName}</strong> (${currentNameEn})</div>
                <div>信心度: ${(detection.confidence * 100).toFixed(1)}%</div>
            </div>
            <div class="btn-group">
                <button class="btn-confirm" data-action="confirm">✅ 正確</button>
                <button class="btn-correct" data-action="correct">✏️ 這不是 ${currentName}</button>
                <div class="correction-input" id="correctionInput">
                    <input type="text" id="correctionNameEn" placeholder="正確的英文名稱" />
                    <button id="correctionSubmit">確認</button>
                </div>
                <button class="btn-false-positive" data-action="false_positive">❌ 誤報（不是物品）</button>
                <button class="btn-cancel" data-action="cancel">取消</button>
            </div>
        </div>
    `;

    document.body.appendChild(overlay);

    // 裁剪偵測區域截圖
    let croppedImage = null;
    try {
        const [x1, y1, x2, y2] = detection.bbox;
        const tempCanvas = document.createElement('canvas');
        const cropW = x2 - x1;
        const cropH = y2 - y1;
        tempCanvas.width = cropW;
        tempCanvas.height = cropH;
        const tempCtx = tempCanvas.getContext('2d');

        // 從本地視頻裁剪
        const videoW = this.localVideo.videoWidth;
        const videoH = this.localVideo.videoHeight;
        const scaleX = videoW / this.canvasWidth;
        const scaleY = videoH / this.canvasHeight;
        tempCtx.drawImage(
            this.localVideo,
            x1 * scaleX, y1 * scaleY, cropW * scaleX, cropH * scaleY,
            0, 0, cropW, cropH
        );
        croppedImage = tempCanvas.toDataURL('image/jpeg', 0.85);
    } catch (e) {
        this.debugLog(`截圖裁剪失敗: ${e.message}`, 'warning');
    }

    // 事件處理
    overlay.addEventListener('click', (e) => {
        const action = e.target.dataset?.action;
        if (!action) return;

        if (action === 'cancel') {
            overlay.remove();
            return;
        }

        if (action === 'correct') {
            document.getElementById('correctionInput').classList.add('show');
            return;
        }

        if (action === 'confirm' || action === 'false_positive') {
            this._submitFeedback(action, detection, null, croppedImage);
            overlay.remove();
        }
    });

    // 更正提交
    const submitBtn = overlay.querySelector('#correctionSubmit');
    if (submitBtn) {
        submitBtn.addEventListener('click', () => {
            const nameEn = overlay.querySelector('#correctionNameEn').value.trim();
            if (!nameEn) {
                this.showNotification('請輸入正確的英文名稱', 'warning');
                return;
            }
            this._submitFeedback('correct', detection, nameEn.toLowerCase(), croppedImage);
            overlay.remove();
        });
    }

    // 點擊背景關閉
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.remove();
    });
}

async _submitFeedback(type, detection, correctClass, imageBase64) {
    try {
        const body = {
            type: type,
            class_name: detection.class_name,
            confidence: detection.confidence,
            bbox: detection.bbox,
            correct_class: correctClass || undefined,
            image: imageBase64 || undefined,
        };

        const res = await fetch(`${this._getApiBaseUrl()}/api/feedback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        const data = await res.json();

        if (data.success) {
            const msgs = {
                confirm: `已確認「${detection.class_name_cn || detection.class_name}」正確`,
                correct: `已更正為「${correctClass}」`,
                false_positive: `已標記為誤報`,
            };
            this.showNotification(msgs[type] || '反饋已提交', 'success');
            this._updateAnnotationPanel();

            // 如果是更正，重新載入類別列表
            if (type === 'correct') {
                await this.loadClasses();
            }
        } else {
            this.showNotification(`反饋失敗: ${data.error || '未知錯誤'}`, 'error');
        }
    } catch (e) {
        this.showNotification(`反饋失敗: ${e.message}`, 'error');
        this.debugLog(`反饋失敗: ${e.message}`, 'error');
    }
}

async _updateAnnotationPanel() {
    try {
        const res = await fetch(`${this._getApiBaseUrl()}/api/feedback/stats`);
        const stats = await res.json();

        if (!this.annotationContent) return;

        if (stats.total === 0) {
            this.annotationContent.innerHTML = '<div class="annotation-empty">尚無反饋資料</div>';
            this.annotationFooter.textContent = '總反饋: 0 筆';
            return;
        }

        let html = '';
        const byClass = stats.by_class || {};
        for (const [cls, counts] of Object.entries(byClass)) {
            const total = (counts.confirm || 0) + (counts.correct || 0) + (counts.false_positive || 0);
            const fpRatio = (counts.false_positive || 0) / total;

            let statusClass = 'good';
            let statusIcon = '✅';
            if (total < 5) {
                statusClass = 'warning';
                statusIcon = '⚠️';
            } else if (fpRatio > 0.5) {
                statusClass = 'bad';
                statusIcon = '❌';
            }

            html += `<div class="annotation-item">
                <span class="class-name">${cls}</span>
                <span class="count ${statusClass}">${statusIcon} ${total} 次</span>
            </div>`;
        }

        this.annotationContent.innerHTML = html;
        this.annotationFooter.textContent = `總反饋: ${stats.total} 筆`;
    } catch (e) {
        // 靜默失敗，不影響使用
    }
}
```

- [ ] **Step 4: Commit**

```bash
git add src/static/app.js
git commit -m "feat: 前端反饋 modal、截圖裁剪與標註狀態面板"
```

---

## Task 8: 端對端驗證

**Files:** 無新檔案

- [ ] **Step 1: 啟動伺服器**

```bash
.venv/Scripts/python.exe src/web_server.py --port 8080
```

確認：
- 伺服器正常啟動
- 顯示 `信心度門檻: 0.3`
- 顯示 `偵測穩定化已初始化: window=3, min_hits=2`
- 顯示 `反饋管理器已初始化`

- [ ] **Step 2: 瀏覽器測試**

1. 開啟 `http://localhost:8080`
2. 確認除錯面板預設隱藏，右下有 🔧 按鈕
3. 確認右下角有標註狀態面板
4. 按「開始偵測」，確認偵測框顯示
5. 點擊偵測框，確認反饋 modal 彈出（正確/更正/誤報三個按鈕）

- [ ] **Step 3: 反饋功能測試**

1. 點擊偵測框 → 按「正確」→ 確認通知顯示成功
2. 點擊偵測框 → 按「誤報」→ 確認通知顯示成功
3. 確認 `data/feedback/feedback.jsonl` 有記錄
4. 確認 `data/feedback/images/` 有截圖
5. 確認標註狀態面板更新顯示反饋次數

- [ ] **Step 4: API 測試**

```bash
curl http://localhost:8080/api/feedback/stats
```

確認回傳有 `total`、`by_type`、`by_class` 欄位

- [ ] **Step 5: 更新工作日誌並 Commit**

更新 `WORK_LOG.md`，然後：

```bash
git add WORK_LOG.md
git commit -m "docs: 更新工作日誌 — 偵測準確率提升與反饋系統"
```
