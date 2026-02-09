from dataclasses import dataclass, field, asdict
from typing import List, Tuple, Optional


@dataclass
class Detection:
    """Single detected object."""
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    center_x: float  # normalized 0-1
    center_y: float  # normalized 0-1
    area_ratio: float  # proportion of frame area


@dataclass
class DetectionResult:
    """Result of a single YOLO inference run."""
    timestamp: float
    frame_width: int
    frame_height: int
    detections: List[Detection] = field(default_factory=list)
    inference_time_ms: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def count(self) -> int:
        return len(self.detections)


@dataclass
class NavigationContext:
    """Local rule-based analysis of detections for navigation (Phase 3)."""
    danger_level: str = "low"  # low / medium / high
    path_status: str = "unknown"  # clear / obstructed / crosswalk
    obstacle_summary: str = ""
    recommended_action: str = ""


@dataclass
class DifyResponse:
    """Response from Dify workflow (Phase 2)."""
    text: str = ""
    workflow_run_id: str = ""
    status: str = ""


@dataclass
class PipelineResult:
    """Combined result from the full pipeline (Phase 3)."""
    detections: Optional[DetectionResult] = None
    context: Optional[NavigationContext] = None
    dify_response: Optional[DifyResponse] = None
