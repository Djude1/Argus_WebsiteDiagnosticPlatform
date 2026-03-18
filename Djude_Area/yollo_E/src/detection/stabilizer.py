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
