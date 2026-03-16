# ============================================
# SQLAlchemy 資料模型
# ============================================
"""
定義資料庫表格結構
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy 基礎類別"""

    pass


class Item(Base):
    """物品記錄表"""

    __tablename__ = "items"

    # 主鍵
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 物品資訊
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="物品名稱（中文）")
    name_en: Mapped[Optional[str]] = mapped_column(String(100), comment="英文名稱")
    category: Mapped[Optional[str]] = mapped_column(String(50), comment="分類")

    # 辨識資訊
    confidence: Mapped[float] = mapped_column(Float, comment="信心度")
    class_id: Mapped[Optional[int]] = mapped_column(Integer, comment="YOLO 類別 ID")

    # 時間記錄
    first_seen: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="首次辨識時間"
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="最後辨識時間"
    )
    detection_count: Mapped[int] = mapped_column(Integer, default=1, comment="辨識次數")

    # 額外資訊
    image_path: Mapped[Optional[str]] = mapped_column(String(500), comment="儲存的圖片路徑")
    bbox: Mapped[Optional[str]] = mapped_column(String(100), comment="邊界框 (x1,y1,x2,y2)")
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, comment="額外資訊")

    # 關聯
    session_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("detection_sessions.id"))
    session: Mapped[Optional["DetectionSession"]] = relationship(
        "DetectionSession", back_populates="items"
    )

    def __repr__(self) -> str:
        return f"<Item(id={self.id}, name='{self.name}', confidence={self.confidence:.2f})>"

    def to_dict(self) -> dict:
        """轉換為字典"""
        return {
            "id": self.id,
            "name": self.name,
            "name_en": self.name_en,
            "category": self.category,
            "confidence": self.confidence,
            "class_id": self.class_id,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "detection_count": self.detection_count,
            "image_path": self.image_path,
            "extra_data": self.extra_data,
        }


class DetectionSession(Base):
    """辨識會話表"""

    __tablename__ = "detection_sessions"

    # 主鍵
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 會話資訊
    start_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="開始時間")
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="結束時間")

    # 統計資訊
    total_detections: Mapped[int] = mapped_column(Integer, default=0, comment="總偵測次數")
    total_frames: Mapped[int] = mapped_column(Integer, default=0, comment="總幀數")
    avg_fps: Mapped[float] = mapped_column(Float, default=0.0, comment="平均 FPS")

    # 來源資訊
    source: Mapped[str] = mapped_column(
        String(50), default="esp32", comment="影像來源 (esp32/webcam)"
    )
    source_ip: Mapped[Optional[str]] = mapped_column(String(50), comment="ESP32 IP 位址")

    # 關聯
    items: Mapped[List["Item"]] = relationship("Item", back_populates="session")

    def __repr__(self) -> str:
        return f"<DetectionSession(id={self.id}, start={self.start_time}, detections={self.total_detections})>"

    def to_dict(self) -> dict:
        """轉換為字典"""
        return {
            "id": self.id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_detections": self.total_detections,
            "total_frames": self.total_frames,
            "avg_fps": self.avg_fps,
            "source": self.source,
            "source_ip": self.source_ip,
        }


class CustomClass(Base):
    """自定義類別表"""

    __tablename__ = "custom_classes"

    # 主鍵
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 類別資訊
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="類別名稱")
    name_cn: Mapped[Optional[str]] = mapped_column(String(100), comment="中文名稱")
    description: Mapped[Optional[str]] = mapped_column(Text, comment="描述")

    # 訓練狀態
    trained: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已訓練")
    sample_count: Mapped[int] = mapped_column(Integer, default=0, comment="樣本數量")

    # 時間記錄
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="建立時間")
    trained_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="訓練時間")

    # 模型資訊
    model_path: Mapped[Optional[str]] = mapped_column(String(500), comment="模型路徑")
    accuracy: Mapped[Optional[float]] = mapped_column(Float, comment="準確率")

    def __repr__(self) -> str:
        return f"<CustomClass(id={self.id}, name='{self.name}', trained={self.trained})>"

    def to_dict(self) -> dict:
        """轉換為字典"""
        return {
            "id": self.id,
            "name": self.name,
            "name_cn": self.name_cn,
            "description": self.description,
            "trained": self.trained,
            "sample_count": self.sample_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "trained_at": self.trained_at.isoformat() if self.trained_at else None,
            "model_path": self.model_path,
            "accuracy": self.accuracy,
        }


# ============================================
# 測試程式
# ============================================

if __name__ == "__main__":
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    # 建立記憶體資料庫測試
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        # 建立測試會話
        test_session = DetectionSession(source="esp32", source_ip="192.168.1.100")
        session.add(test_session)
        session.commit()

        # 建立測試物品
        test_item = Item(
            name="手機",
            name_en="cell phone",
            category="電子產品",
            confidence=0.95,
            class_id=67,
            session_id=test_session.id,
        )
        session.add(test_item)
        session.commit()

        # 查詢測試
        items = session.query(Item).all()
        for item in items:
            print(item)
            print(item.to_dict())
