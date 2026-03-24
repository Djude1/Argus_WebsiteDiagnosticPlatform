# ============================================
# 偵測引擎封裝
# ============================================
"""
完整封裝的偵測引擎
整合 YOLODetector、DetectionStabilizer、PromptEnhancer、LabelMapper
提供統一的偵測介面給 Webcam 和 Web 版本使用
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, OrderedDict
import numpy as np
from loguru import logger

from detection.yolo_detector import YOLODetector, DetectionResult, FrameDetectionResult
from detection.stabilizer import DetectionStabilizer
from detection.prompt_enhancer import PromptEnhancer, ENHANCED_PROMPTS
from detection.label_mapper import LabelMapper

# 類別別名對照表
ALIAS_MAPPING = ENHANCED_PROMPTS.copy()


@dataclass
class DetectionConfig:
    """偵測引擎配置"""

    model_path: str = "models/yoloe-26-seg.pt"
    device: str = "cuda"
    confidence: float = 0.25
    max_active_classes: int = 10
    custom_classes_path: str = "data/custom_classes.json"


class DetectionEngine:
    """完整封裝的偵測引擎"""

    def __init__(self, config: DetectionConfig):
        self.config = config
        self.detector = YOLODetector(config.model_path, config.device)
        self.stabilizer = DetectionStabilizer(window_size=3, min_hits=2)
        self.prompt_enhancer = PromptEnhancer()
        self.label_mapper = LabelMapper()
        self.max_active_classes = config.max_active_classes
        self._active_classes: OrderedDict = {}
        self._load_custom_classes(Path(config.custom_classes_path))
        # 更新偵測器的類別（如果有自訂類別）
        if self._active_classes:
            self.update_classes(list(self._active_classes.keys()))
        logger.info("DetectionEngine 已初始化")

    def detect(self, frame: np.ndarray) -> List[DetectionResult]:
        """完整偵測流程"""
        raw_detections = self.detector.detect(frame, conf_threshold=self.config.confidence)
        stable_detections = self.stabilizer.update(raw_detections.detections)
        results = []
        for det in stable_detections:
            resolved_name = self._resolve_alias(det.class_name)
            cn_name = self.label_mapper.get_chinese_name_from_en(resolved_name)
            det.class_name = resolved_name
            det.class_name_cn = cn_name
            results.append(det)
        return results

    def _resolve_alias(self, class_name: str) -> str:
        """解析類別別名"""
        return ALIAS_MAPPING.get(class_name, class_name)

    def _load_custom_classes(self, custom_classes_path: Path):
        """載入自訂類別"""
        if not custom_classes_path.exists():
            return
        import json

        with open(custom_classes_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for cls in data.get("classes", []):
            if cls.get("active"):
                self._active_classes[cls["name_en"]] = cls["name_cn"]
        logger.info(f"已載入 {len(self._active_classes)} 個自訂類別")

    def update_classes(self, classes: List[str]) -> bool:
        """更新偵測類別（動態更新 YOLOE 開放詞彙）"""
        if not classes:
            return False
        return self.detector.update_classes(classes)

    def reset_session(self):
        """重置偵測狀態（新使用者連線時呼叫）"""
        self.stabilizer.reset()
        logger.info("偵測狀態已重置")
