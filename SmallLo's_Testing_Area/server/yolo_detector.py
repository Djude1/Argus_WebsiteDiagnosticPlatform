# yolo_detector.py
# YOLO inference wrapper for obstacle/navigation detection

import time
import cv2
import numpy as np
from pathlib import Path
from models import Detection, DetectionResult

try:
    import torch
    HAS_CUDA = torch.cuda.is_available()
except ImportError:
    HAS_CUDA = False

from ultralytics import YOLO


class YOLODetector:
    """Wraps ultralytics YOLO model for detection and annotation."""

    def __init__(self, model_path: str, confidence: float = 0.25):
        self.confidence = confidence
        self.device = "cuda" if HAS_CUDA else "cpu"

        # Resolve model path
        resolved = Path(model_path)
        if not resolved.is_absolute():
            resolved = Path(__file__).parent / model_path
        resolved = resolved.resolve()

        print(f"[YOLODetector] Loading model from {resolved}")
        print(f"[YOLODetector] Using device: {self.device}")

        self.model = YOLO(str(resolved))
        if HAS_CUDA:
            self.model.to("cuda")

        # Warm-up inference
        print("[YOLODetector] Warming up...")
        test_img = np.zeros((640, 640, 3), dtype=np.uint8)
        self.model.predict(test_img, device=self.device, verbose=False)
        print("[YOLODetector] Ready")

    def detect(self, bgr: np.ndarray) -> DetectionResult:
        """Run YOLO inference on a BGR frame and return structured results."""
        t_start = time.time()

        results = self.model.predict(
            bgr,
            conf=self.confidence,
            device=self.device,
            verbose=False,
        )

        t_end = time.time()
        inference_ms = (t_end - t_start) * 1000

        h, w = bgr.shape[:2]
        frame_area = h * w
        detections = []

        if results and len(results) > 0:
            result = results[0]
            if result.boxes is not None:
                for box in result.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                    conf = float(box.conf[0].cpu().numpy())
                    cls_id = int(box.cls[0].cpu().numpy())
                    cls_name = result.names.get(cls_id, str(cls_id))

                    cx = ((x1 + x2) / 2) / w
                    cy = ((y1 + y2) / 2) / h
                    area = (x2 - x1) * (y2 - y1)
                    area_ratio = area / frame_area if frame_area > 0 else 0

                    detections.append(Detection(
                        class_name=cls_name,
                        confidence=round(conf, 3),
                        bbox=(int(x1), int(y1), int(x2), int(y2)),
                        center_x=round(cx, 3),
                        center_y=round(cy, 3),
                        area_ratio=round(area_ratio, 4),
                    ))

        return DetectionResult(
            timestamp=t_start,
            frame_width=w,
            frame_height=h,
            detections=detections,
            inference_time_ms=round(inference_ms, 1),
        )

    def annotate(self, bgr: np.ndarray, result: DetectionResult) -> np.ndarray:
        """Draw detection boxes and labels on the frame."""
        annotated = bgr.copy()

        for det in result.detections:
            x1, y1, x2, y2 = det.bbox
            label = f"{det.class_name} {det.confidence:.2f}"

            # Draw box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # Draw label background
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(annotated, (x1, y1 - th - 6), (x1 + tw, y1), (0, 255, 0), -1)
            cv2.putText(annotated, label, (x1, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        # Draw stats
        stats = f"Objects: {result.count} | {result.inference_time_ms:.0f}ms"
        cv2.putText(annotated, stats, (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        return annotated
