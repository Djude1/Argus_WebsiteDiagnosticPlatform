# ============================================
# 資料管理器
# ============================================
"""
統一資料管理器 - 輸出 annotations.json 格式
支援 Webcam 和 Web 版本的統一資料輸出
"""

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from loguru import logger
import cv2
import numpy as np


class DataManager:
    """統一資料管理器 - 輸出 annotations.json 格式"""

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._annotations_file = data_dir / "annotations" / "annotations.json"
        self._images_dir = data_dir / "annotations" / "annotation_images"
        self._lock = threading.Lock()
        self._annotations: Dict[str, Any] = {"records": []}
        self._load_existing_annotations()
        logger.info("DataManager 已初始化")

    def _load_existing_annotations(self):
        """載入現有 annotations.json"""
        if self._annotations_file.exists():
            with open(self._annotations_file, "r", encoding="utf-8") as f:
                self._annotations = json.load(f)
        else:
            self._annotations = {"version": "2.0", "records": []}

    def record(
        self,
        detection: Any,
        frame: np.ndarray,
        source: str = "webcam",
        feedback_type: str = "annotation",
        correct_class: Optional[str] = None,
        owner: Optional[str] = None,
        notes: str = "",
    ) -> dict:
        """統一記錄偵測/回饋資料"""
        with self._lock:
            timestamp = datetime.now()
            class_name_safe = (detection.class_name or "unknown").replace(' ', '_')
            record_id = f"{timestamp.strftime('%Y%m%d_%H%M%S_%f')}_{class_name_safe}"
            image_filename = f"{record_id}.jpg"
            image_path = self._images_dir / image_filename
            self._images_dir.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(image_path), frame)
            record = {
                "id": record_id,
                "source": source,
                "type": feedback_type,
                "class_name": detection.class_name,
                "class_name_cn": getattr(detection, "class_name_cn", ""),
                "confidence": float(detection.confidence),
                "bbox": list(detection.bbox.to_tuple()) if hasattr(detection.bbox, "to_tuple") else list(detection.bbox),
                "timestamp": timestamp.isoformat(),
                "session_id": "",
                "image_path": f"annotation_images/{image_filename}",
                "status": "annotated",
                "owner": owner or "",
                "correct_class": correct_class,
                "notes": notes,
            }
            self._annotations["records"].append(record)
            self._save_annotations()
            return record

    def _save_annotations(self):
        """儲存 annotations.json"""
        self._annotations_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._annotations_file, "w", encoding="utf-8") as f:
            json.dump(self._annotations, f, indent=2, ensure_ascii=False)

    def get_stats(self) -> dict:
        """取得統計資訊（格式相容前端 _updateAnnotationPanel）"""
        records = self._annotations.get("records", [])
        return {
            "total": len(records),
            "by_source": self._count_by_field(records, "source"),
            "by_type": self._count_by_field(records, "type"),
            # by_class: {"cup": {"confirm": 3, "correct": 1, "false_positive": 0}, ...}
            "by_class": self._count_by_class_and_type(records),
        }

    def _count_by_field(self, records: List[dict], field: str) -> Dict[str, int]:
        counts = {}
        for r in records:
            key = r.get(field, "unknown")
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _count_by_class_and_type(self, records: List[dict]) -> Dict[str, Dict[str, int]]:
        """依類別統計各回饋類型數量，格式符合前端期望"""
        result: Dict[str, Dict[str, int]] = {}
        for r in records:
            cls = r.get("class_name", "unknown")
            rtype = r.get("type", "annotation")
            if cls not in result:
                result[cls] = {"confirm": 0, "correct": 0, "false_positive": 0}
            if rtype in result[cls]:
                result[cls][rtype] += 1
        return result