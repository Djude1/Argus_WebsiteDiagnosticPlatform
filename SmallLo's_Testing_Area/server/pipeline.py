# pipeline.py
# Model chaining orchestrator (Phase 3)
# Pipeline: Frame → YOLO Detection → Context Analysis → Dify Workflow → Response

from models import Detection, DetectionResult, NavigationContext, DifyResponse, PipelineResult
from yolo_detector import YOLODetector
from dify_client import DifyClient, DifyThrottler
import numpy as np

# Object classes considered obstacles for navigation
OBSTACLE_CLASSES = {
    "person", "bicycle", "car", "motorcycle", "bus", "truck",
    "dog", "cat", "chair", "bench", "fire hydrant", "stop sign",
    "pole", "stair",
}

# Object classes related to path features
PATH_CLASSES = {
    "sidewalk_edge", "crosswalk", "road",
}


class ContextAnalyzer:
    """Local rule engine: classifies detections into navigation contexts."""

    def analyze(self, result: DetectionResult) -> NavigationContext:
        obstacles = [d for d in result.detections if d.class_name in OBSTACLE_CLASSES]
        path_features = [d for d in result.detections if d.class_name in PATH_CLASSES]

        danger = self._compute_danger(obstacles)
        path_status = self._compute_path_status(path_features, obstacles)
        summary = self._summarize(obstacles)
        action = self._recommend(danger, path_status)

        return NavigationContext(
            danger_level=danger,
            path_status=path_status,
            obstacle_summary=summary,
            recommended_action=action,
        )

    @staticmethod
    def _compute_danger(obstacles: list) -> str:
        if not obstacles:
            return "low"
        # Large objects close to center = high danger
        for obs in obstacles:
            if obs.area_ratio > 0.15 and 0.3 < obs.center_x < 0.7:
                return "high"
            if obs.area_ratio > 0.08:
                return "medium"
        return "low"

    @staticmethod
    def _compute_path_status(path_features: list, obstacles: list) -> str:
        has_crosswalk = any(p.class_name == "crosswalk" for p in path_features)
        if has_crosswalk:
            return "crosswalk"
        center_obstacles = [o for o in obstacles if 0.3 < o.center_x < 0.7]
        if center_obstacles:
            return "obstructed"
        return "clear"

    @staticmethod
    def _summarize(obstacles: list) -> str:
        if not obstacles:
            return "No obstacles detected"
        names = [o.class_name for o in obstacles]
        unique = list(dict.fromkeys(names))  # preserve order, deduplicate
        return f"Detected: {', '.join(unique)} ({len(obstacles)} total)"

    @staticmethod
    def _recommend(danger: str, path_status: str) -> str:
        if danger == "high":
            return "Stop - obstacle directly ahead"
        if path_status == "crosswalk":
            return "Crosswalk detected - check traffic"
        if path_status == "obstructed":
            return "Path partially obstructed - proceed with caution"
        return "Path clear - continue forward"


class Pipeline:
    """Orchestrator connecting YOLO → Context → Dify → Response."""

    def __init__(
        self,
        detector: YOLODetector,
        dify: DifyClient = None,
        dify_interval: float = 2.0,
    ):
        self.detector = detector
        self.dify = dify
        self.context_analyzer = ContextAnalyzer()
        self.throttler = DifyThrottler(min_interval=dify_interval)
        self._last_dify_response = DifyResponse()

    async def process_frame(self, bgr: np.ndarray) -> PipelineResult:
        """Run the full pipeline on a single frame."""
        # Stage 1: YOLO detection
        detections = self.detector.detect(bgr)

        # Stage 2: Local context analysis
        context = self.context_analyzer.analyze(detections)

        # Stage 3: Dify workflow (throttled)
        dify_response = self._last_dify_response
        if self.dify and self.throttler.should_call(detections):
            dify_response = await self.dify.run_workflow(detections)
            self.throttler.mark_called(detections)
            self._last_dify_response = dify_response

        return PipelineResult(
            detections=detections,
            context=context,
            dify_response=dify_response,
        )
