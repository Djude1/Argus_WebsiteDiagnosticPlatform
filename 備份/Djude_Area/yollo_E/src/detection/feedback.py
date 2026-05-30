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
