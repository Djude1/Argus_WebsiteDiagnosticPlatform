# ============================================
# 偵測引擎封裝
# ============================================

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import List
import time
import numpy as np
from loguru import logger

from detection.yolo_detector import YOLODetector, DetectionResult
from detection.stabilizer import DetectionStabilizer, filter_false_positives
from detection.label_mapper import LabelMapper


@dataclass
class DetectionConfig:
    model_path: str = "models/yoloe-26-seg.pt"
    device: str = "cuda"
    confidence: float = 0.25
    max_active_classes: int = 10
    custom_classes_path: str = "data/custom_classes.json"


class DetectionEngine:
    def __init__(self, config: DetectionConfig):
        self.config = config
        self.detector = YOLODetector(config.model_path, config.device)
        self.stabilizer = DetectionStabilizer(window_size=3, min_hits=2)
        self.label_mapper = LabelMapper()
        self.max_active_classes = config.max_active_classes
        self._active_classes = {}
        self._load_custom_classes(Path(config.custom_classes_path))
        if self._active_classes:
            self.update_classes(list(self._active_classes.keys()))
        logger.info("DetectionEngine 已初始化")

    def detect(self, frame):
        t0 = time.perf_counter()
        logger.debug(f"[DetectionEngine] 輸入影像: {frame.shape}, confidence: {self.config.confidence}")

        raw = self.detector.detect(frame, conf_threshold=self.config.confidence)
        t1 = time.perf_counter()
        logger.debug(f"[DetectionEngine] 原始偵測: {len(raw.detections)}")

        filtered = filter_false_positives(raw.detections, frame.shape)
        t2 = time.perf_counter()
        logger.debug(f"[DetectionEngine] filter後: {len(filtered)}")

        stable = self.stabilizer.update(filtered)
        t3 = time.perf_counter()
        logger.debug(f"[DetectionEngine] stable後: {len(stable)}")

        results = []
        for det in stable:
            resolved = self.label_mapper.resolve_alias(det.class_name)
            cn = self.label_mapper.get_chinese_name_from_en(resolved)
            det.class_name = resolved
            det.class_name_cn = cn
            results.append(det)
        t4 = time.perf_counter()
        logger.debug(f"[DetectionEngine] 最終: {len(results)}")

        logger.info(f"[PROFILE] detector.detect: {(t1-t0)*1000:.2f}ms | filter_false_positives: {(t2-t1)*1000:.2f}ms | stabilizer.update: {(t3-t2)*1000:.2f}ms | label_mapping: {(t4-t3)*1000:.2f}ms | total: {(t4-t0)*1000:.2f}ms")
        return results

    def _load_custom_classes(self, path):
        if not path.exists():
            return
        import json
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for cls in data.get("classes", []):
            if cls.get("active"):
                self._active_classes[cls["name_en"]] = cls["name_cn"]
        logger.info(f"已載入 {len(self._active_classes)} 個自訂類別")

    def update_classes(self, classes):
        if not classes:
            return False
        return self.detector.update_classes(classes)

    def reset_session(self):
        self.stabilizer.reset()
        logger.info("偵測狀態已重置")
