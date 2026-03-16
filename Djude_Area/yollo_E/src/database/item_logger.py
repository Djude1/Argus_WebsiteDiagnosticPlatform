# ============================================
# 物品記錄器
# ============================================
"""
將 YOLO 辨識結果記錄到資料庫
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Set
from dataclasses import dataclass
import cv2
import numpy as np
from loguru import logger
import sys

# 設定 loguru
logger.remove()
logger.add(
    sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>"
)

# 支援直接執行和套件匯入兩種模式
try:
    from ..database.db_manager import DatabaseManager
    from ..database.models import Item, DetectionSession
    from ..detection.yolo_detector import FrameDetectionResult, DetectionResult
    from ..detection.label_mapper import LabelMapper
except ImportError:
    from database.db_manager import DatabaseManager
    from database.models import Item, DetectionSession
    from detection.yolo_detector import FrameDetectionResult, DetectionResult
    from detection.label_mapper import LabelMapper


@dataclass
class LoggerConfig:
    """記錄器配置"""

    save_images: bool = False  # 是否儲存辨識圖片
    image_dir: str = "data/detections"  # 圖片儲存目錄
    min_confidence: float = 0.5  # 最小信心度
    dedup_interval: float = 5.0  # 去重間隔（秒）
    log_all: bool = False  # 是否記錄所有偵測（包括重複）


class ItemLogger:
    """物品記錄器"""

    def __init__(self, db_manager: DatabaseManager, config: LoggerConfig = None):
        """
        初始化物品記錄器

        參數:
            db_manager: 資料庫管理器
            config: 記錄器配置
        """
        self.db = db_manager
        self.config = config or LoggerConfig()
        self.label_mapper = LabelMapper()

        # 當前會話
        self.current_session: Optional[DetectionSession] = None

        # 去重用的追蹤集合
        self._seen_items: Dict[str, float] = {}  # {item_key: last_seen_time}

        # 統計
        self._total_logged = 0
        self._total_skipped = 0

        # 確保圖片目錄存在
        if self.config.save_images:
            Path(self.config.image_dir).mkdir(parents=True, exist_ok=True)

        logger.info("物品記錄器已初始化")

    def start_session(self, source: str = "esp32", source_ip: str = None) -> int:
        """
        開始新的辨識會話

        參數:
            source: 影像來源
            source_ip: ESP32 IP 位址

        回傳:
            會話 ID
        """
        self.current_session = self.db.create_session(source=source, source_ip=source_ip)
        self._seen_items.clear()
        self._total_logged = 0
        self._total_skipped = 0

        logger.info(f"開始新會話: ID={self.current_session.id}")
        return self.current_session.id

    def end_session(self, total_frames: int = 0, avg_fps: float = 0.0):
        """結束當前會話"""
        if self.current_session:
            self.db.end_session(self.current_session.id, total_frames=total_frames, avg_fps=avg_fps)
            logger.info(
                f"會話結束: ID={self.current_session.id}, "
                f"記錄={self._total_logged}, 跳過={self._total_skipped}"
            )
            self.current_session = None

    def log_detection(
        self, detection: DetectionResult, frame: np.ndarray = None, session_id: int = None
    ) -> Optional[Item]:
        """
        記錄單一偵測結果

        參數:
            detection: 偵測結果
            frame: 原始影像（用於儲存圖片）
            session_id: 會話 ID（預設使用當前會話）

        回傳:
            新增的物品記錄，如果跳過則回傳 None
        """
        # 檢查信心度
        if detection.confidence < self.config.min_confidence:
            self._total_skipped += 1
            return None

        # 去重檢查
        item_key = self._make_item_key(detection)
        current_time = time.time()

        if not self.config.log_all:
            if item_key in self._seen_items:
                time_since_last = current_time - self._seen_items[item_key]
                if time_since_last < self.config.dedup_interval:
                    self._total_skipped += 1
                    return None

            self._seen_items[item_key] = current_time

        # 取得中文名稱和分類
        name_cn = self.label_mapper.get_chinese_name(detection.class_id, detection.class_name)
        category = self.label_mapper.get_category(detection.class_id)

        # 儲存圖片
        image_path = None
        if self.config.save_images and frame is not None:
            image_path = self._save_detection_image(detection, frame)

        # 使用當前會話或指定的會話
        sid = session_id or (self.current_session.id if self.current_session else None)

        # 新增記錄
        bbox_str = f"{detection.bbox.x1:.0f},{detection.bbox.y1:.0f},{detection.bbox.x2:.0f},{detection.bbox.y2:.0f}"

        item = self.db.add_item(
            name=name_cn,
            confidence=detection.confidence,
            name_en=detection.class_name,
            category=category,
            class_id=detection.class_id,
            image_path=image_path,
            bbox=bbox_str,
            session_id=sid,
        )

        self._total_logged += 1
        logger.debug(f"記錄物品: {name_cn} (信心度: {detection.confidence:.2f})")

        return item

    def log_frame(self, result: FrameDetectionResult, frame: np.ndarray = None) -> List[Item]:
        """
        記錄整個畫面的偵測結果

        參數:
            result: 畫面偵測結果
            frame: 原始影像

        回傳:
            新增的物品記錄列表
        """
        logged_items = []

        for detection in result.detections:
            item = self.log_detection(detection, frame)
            if item:
                logged_items.append(item)

        return logged_items

    def _make_item_key(self, detection: DetectionResult) -> str:
        """產生去重用的 key"""
        # 使用類別和大致位置作為 key
        center = detection.bbox.center
        return f"{detection.class_id}_{int(center[0] / 50)}_{int(center[1] / 50)}"

    def _save_detection_image(self, detection: DetectionResult, frame: np.ndarray) -> str:
        """儲存偵測圖片"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{detection.class_name}_{timestamp}.jpg"
        filepath = Path(self.config.image_dir) / filename

        # 裁切偵測區域
        x1, y1, x2, y2 = detection.bbox.to_tuple()

        # 確保座標在範圍內
        h, w = frame.shape[:2]
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(w, x2)
        y2 = min(h, y2)

        if x2 > x1 and y2 > y1:
            crop = frame[y1:y2, x1:x2]
            cv2.imwrite(str(filepath), crop)
            return str(filepath)

        return None

    def get_stats(self) -> Dict:
        """取得統計資訊"""
        return {
            "total_logged": self._total_logged,
            "total_skipped": self._total_skipped,
            "unique_items": len(self._seen_items),
            "session_id": self.current_session.id if self.current_session else None,
        }

    def get_recent_items(self, limit: int = 20) -> List[Item]:
        """取得最近記錄的物品"""
        return self.db.get_recent_items(limit)

    def search_items(self, keyword: str) -> List[Item]:
        """搜尋物品"""
        return self.db.get_items_by_name(keyword)


# ============================================
# 測試程式
# ============================================

if __name__ == "__main__":
    import tempfile
    import os
    from ..detection.yolo_detector import BoundingBox

    # 建立臨時資料庫
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")

        print("=" * 50)
        print("物品記錄器測試")
        print("=" * 50)

        # 建立管理器和記錄器
        db = DatabaseManager(db_path)
        config = LoggerConfig(save_images=False, min_confidence=0.5, dedup_interval=2.0)
        logger_instance = ItemLogger(db, config)

        # 開始會話
        session_id = logger_instance.start_session(source="test")
        print(f"會話 ID: {session_id}")

        # 模擬偵測結果
        detection1 = DetectionResult(
            bbox=BoundingBox(x1=100, y1=100, x2=200, y2=300),
            confidence=0.95,
            class_id=67,
            class_name="cell phone",
        )

        detection2 = DetectionResult(
            bbox=BoundingBox(x1=300, y1=200, x2=400, y2=400),
            confidence=0.88,
            class_id=39,
            class_name="bottle",
        )

        # 記錄偵測
        item1 = logger_instance.log_detection(detection1)
        print(f"記錄: {item1.name if item1 else '跳過'}")

        item2 = logger_instance.log_detection(detection2)
        print(f"記錄: {item2.name if item2 else '跳過'}")

        # 重複偵測（應該被跳過）
        time.sleep(0.5)
        item3 = logger_instance.log_detection(detection1)
        print(f"重複偵測: {'跳過' if item3 is None else '記錄'}")

        # 取得統計
        stats = logger_instance.get_stats()
        print(f"\n統計: {stats}")

        # 結束會話
        logger_instance.end_session(total_frames=100, avg_fps=15.0)
