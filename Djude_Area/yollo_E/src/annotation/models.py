# ============================================
# 標註數據模型
# ============================================
"""
定義標註記錄的數據結構
"""

from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import json


class AnnotationStatus(Enum):
    """標註狀態"""

    PENDING = "pending"  # 待標註
    ANNOTATED = "annotated"  # 已標註
    SKIPPED = "skipped"  # 已跳過


@dataclass
class BoundingBox:
    """邊界框"""

    x1: float
    y1: float
    x2: float
    y2: float

    def to_dict(self) -> Dict[str, float]:
        return {"x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2}

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "BoundingBox":
        return cls(x1=data["x1"], y1=data["y1"], x2=data["x2"], y2=data["y2"])


@dataclass
class AnnotationRecord:
    """
    標註記錄

    用於記錄 YOLOE 偵測到的物品資訊，供後台標註使用
    """

    # 基本資訊
    id: str  # 唯一識別碼 (時間戳_類別)
    class_name: str  # 物品類別 (英文)
    class_name_cn: str = ""  # 物品類別 (中文)
    confidence: float = 0.0  # 信心度

    # 邊界框
    bbox: Optional[BoundingBox] = None  # 邊界框

    # 時間資訊
    timestamp: str = ""  # 記錄時間
    session_id: Optional[int] = None  # 會話 ID

    # 圖片資訊
    image_path: Optional[str] = None  # 截圖路徑

    # 標註狀態
    status: AnnotationStatus = AnnotationStatus.PENDING

    # 用戶標註欄位（描述這項物品究竟屬於誰）
    owner: str = ""  # 物品擁有者
    description: str = ""  # 物品描述
    custom_label: str = ""  # 自定義標籤
    notes: str = ""  # 備註

    # 額外資訊
    extra_data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """初始化後處理"""
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return {
            "id": self.id,
            "class_name": self.class_name,
            "class_name_cn": self.class_name_cn,
            "confidence": self.confidence,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "image_path": self.image_path,
            "status": self.status.value,
            "owner": self.owner,
            "description": self.description,
            "custom_label": self.custom_label,
            "notes": self.notes,
            "extra_data": self.extra_data,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AnnotationRecord":
        """從字典創建實例"""
        bbox = None
        if data.get("bbox"):
            bbox = BoundingBox.from_dict(data["bbox"])

        status = AnnotationStatus(data.get("status", "pending"))

        return cls(
            id=data["id"],
            class_name=data["class_name"],
            class_name_cn=data.get("class_name_cn", ""),
            confidence=data.get("confidence", 0.0),
            bbox=bbox,
            timestamp=data.get("timestamp", ""),
            session_id=data.get("session_id"),
            image_path=data.get("image_path"),
            status=status,
            owner=data.get("owner", ""),
            description=data.get("description", ""),
            custom_label=data.get("custom_label", ""),
            notes=data.get("notes", ""),
            extra_data=data.get("extra_data", {}),
        )

    def mark_annotated(
        self, owner: str = "", description: str = "", custom_label: str = "", notes: str = ""
    ):
        """標記為已標註"""
        self.status = AnnotationStatus.ANNOTATED
        if owner:
            self.owner = owner
        if description:
            self.description = description
        if custom_label:
            self.custom_label = custom_label
        if notes:
            self.notes = notes

    def mark_skipped(self):
        """標記為已跳過"""
        self.status = AnnotationStatus.SKIPPED

    def is_pending(self) -> bool:
        """是否待標註"""
        return self.status == AnnotationStatus.PENDING


# ============================================
# 測試程式
# ============================================

if __name__ == "__main__":
    # 建立測試記錄
    record = AnnotationRecord(
        id="20260101_120000_cell_phone",
        class_name="cell phone",
        class_name_cn="手機",
        confidence=0.95,
        bbox=BoundingBox(x1=100, y1=100, x2=200, y2=300),
        session_id=1,
        image_path="data/annotation_images/cell_phone_20260101_120000.jpg",
    )

    print("測試記錄:")
    print(json.dumps(record.to_dict(), indent=2, ensure_ascii=False))

    # 測試標註
    record.mark_annotated(owner="王小明", description="黑色 iPhone 15 Pro", notes="螢幕有裂痕")

    print("\n標註後:")
    print(json.dumps(record.to_dict(), indent=2, ensure_ascii=False))
