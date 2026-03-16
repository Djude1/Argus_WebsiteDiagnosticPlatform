# ============================================
# 資料庫管理器
# ============================================
"""
管理 SQLite 資料庫操作
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from sqlalchemy import create_engine, desc, and_
from sqlalchemy.orm import Session, sessionmaker
from loguru import logger
import sys

# 設定 loguru
logger.remove()
logger.add(
    sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>"
)

from .models import Base, Item, DetectionSession, CustomClass


class DatabaseManager:
    """資料庫管理器"""

    def __init__(self, db_path: str = "data/database/items.db"):
        """
        初始化資料庫管理器

        參數:
            db_path: 資料庫檔案路徑
        """
        self.db_path = Path(db_path)

        # 確保目錄存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 建立資料庫連線
        self.engine = create_engine(f"sqlite:///{self.db_path}", echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

        # 建立表格
        self._create_tables()

        logger.info(f"資料庫已初始化: {self.db_path}")

    def _create_tables(self):
        """建立所有表格"""
        Base.metadata.create_all(self.engine)
        logger.info("資料庫表格已建立")

    def get_session(self) -> Session:
        """取得資料庫會話"""
        return self.SessionLocal()

    # ============================================
    # 物品操作
    # ============================================

    def add_item(
        self,
        name: str,
        confidence: float,
        name_en: str = None,
        category: str = None,
        class_id: int = None,
        image_path: str = None,
        bbox: str = None,
        metadata: dict = None,
        session_id: int = None,
    ) -> Item:
        """
        新增物品記錄

        參數:
            name: 物品名稱（中文）
            confidence: 信心度
            name_en: 英文名稱
            category: 分類
            class_id: YOLO 類別 ID
            image_path: 圖片路徑
            bbox: 邊界框
            metadata: 額外資訊
            session_id: 會話 ID

        回傳:
            Item: 新增的物品記錄
        """
        with self.get_session() as session:
            item = Item(
                name=name,
                name_en=name_en,
                category=category,
                confidence=confidence,
                class_id=class_id,
                image_path=image_path,
                bbox=bbox,
                metadata=metadata,
                session_id=session_id,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            logger.debug(f"新增物品: {name} (信心度: {confidence:.2f})")
            return item

    def update_item_seen(self, item_id: int) -> bool:
        """更新物品的最後見到時間和計數"""
        with self.get_session() as session:
            item = session.query(Item).filter(Item.id == item_id).first()
            if item:
                item.last_seen = datetime.now()
                item.detection_count += 1
                session.commit()
                return True
            return False

    def get_item_by_id(self, item_id: int) -> Optional[Item]:
        """根據 ID 取得物品"""
        with self.get_session() as session:
            return session.query(Item).filter(Item.id == item_id).first()

    def get_items_by_name(self, name: str) -> List[Item]:
        """根據名稱搜尋物品"""
        with self.get_session() as session:
            return session.query(Item).filter(Item.name.contains(name)).all()

    def get_items_by_category(self, category: str) -> List[Item]:
        """根據分類取得物品"""
        with self.get_session() as session:
            return session.query(Item).filter(Item.category == category).all()

    def get_recent_items(self, limit: int = 50) -> List[Item]:
        """取得最近辨識的物品"""
        with self.get_session() as session:
            return session.query(Item).order_by(desc(Item.last_seen)).limit(limit).all()

    def get_frequent_items(self, limit: int = 20) -> List[Item]:
        """取得最常辨識的物品"""
        with self.get_session() as session:
            return session.query(Item).order_by(desc(Item.detection_count)).limit(limit).all()

    def get_all_items(self) -> List[Item]:
        """取得所有物品"""
        with self.get_session() as session:
            return session.query(Item).all()

    def delete_item(self, item_id: int) -> bool:
        """刪除物品"""
        with self.get_session() as session:
            item = session.query(Item).filter(Item.id == item_id).first()
            if item:
                session.delete(item)
                session.commit()
                logger.info(f"已刪除物品: {item.name}")
                return True
            return False

    # ============================================
    # 會話操作
    # ============================================

    def create_session(self, source: str = "esp32", source_ip: str = None) -> DetectionSession:
        """建立新的辨識會話"""
        with self.get_session() as session:
            detection_session = DetectionSession(source=source, source_ip=source_ip)
            session.add(detection_session)
            session.commit()
            session.refresh(detection_session)
            logger.info(f"建立新會話: ID={detection_session.id}")
            return detection_session

    def end_session(self, session_id: int, total_frames: int = 0, avg_fps: float = 0.0) -> bool:
        """結束辨識會話"""
        with self.get_session() as session:
            detection_session = (
                session.query(DetectionSession).filter(DetectionSession.id == session_id).first()
            )

            if detection_session:
                detection_session.end_time = datetime.now()
                detection_session.total_frames = total_frames
                detection_session.avg_fps = avg_fps
                detection_session.total_detections = (
                    session.query(Item).filter(Item.session_id == session_id).count()
                )
                session.commit()
                logger.info(
                    f"會話已結束: ID={session_id}, 偵測數={detection_session.total_detections}"
                )
                return True
            return False

    def get_session_by_id(self, session_id: int) -> Optional[DetectionSession]:
        """根據 ID 取得會話"""
        with self.get_session() as session:
            return session.query(DetectionSession).filter(DetectionSession.id == session_id).first()

    def get_recent_sessions(self, limit: int = 10) -> List[DetectionSession]:
        """取得最近的會話"""
        with self.get_session() as session:
            return (
                session.query(DetectionSession)
                .order_by(desc(DetectionSession.start_time))
                .limit(limit)
                .all()
            )

    # ============================================
    # 自定義類別操作
    # ============================================

    def add_custom_class(
        self, name: str, name_cn: str = None, description: str = None
    ) -> CustomClass:
        """新增自定義類別"""
        with self.get_session() as session:
            custom_class = CustomClass(name=name, name_cn=name_cn, description=description)
            session.add(custom_class)
            session.commit()
            session.refresh(custom_class)
            logger.info(f"新增自定義類別: {name}")
            return custom_class

    def update_custom_class_trained(
        self, class_id: int, model_path: str, accuracy: float = None, sample_count: int = None
    ) -> bool:
        """更新自定義類別的訓練狀態"""
        with self.get_session() as session:
            custom_class = session.query(CustomClass).filter(CustomClass.id == class_id).first()

            if custom_class:
                custom_class.trained = True
                custom_class.trained_at = datetime.now()
                custom_class.model_path = model_path
                custom_class.accuracy = accuracy
                if sample_count is not None:
                    custom_class.sample_count = sample_count
                session.commit()
                logger.info(f"更新類別訓練狀態: {custom_class.name}")
                return True
            return False

    def get_untrained_classes(self) -> List[CustomClass]:
        """取得未訓練的類別"""
        with self.get_session() as session:
            return session.query(CustomClass).filter(CustomClass.trained == False).all()

    def get_all_custom_classes(self) -> List[CustomClass]:
        """取得所有自定義類別"""
        with self.get_session() as session:
            return session.query(CustomClass).all()

    # ============================================
    # 統計功能
    # ============================================

    def get_statistics(self) -> Dict[str, Any]:
        """取得統計資訊"""
        with self.get_session() as session:
            total_items = session.query(Item).count()
            total_sessions = session.query(DetectionSession).count()
            total_custom_classes = session.query(CustomClass).count()
            trained_classes = session.query(CustomClass).filter(CustomClass.trained == True).count()

            # 按分類統計
            from sqlalchemy import func

            category_stats = (
                session.query(Item.category, func.count(Item.id).label("count"))
                .group_by(Item.category)
                .all()
            )

            return {
                "total_items": total_items,
                "total_sessions": total_sessions,
                "total_custom_classes": total_custom_classes,
                "trained_classes": trained_classes,
                "category_distribution": {cat: count for cat, count in category_stats if cat},
            }

    def clear_all(self):
        """清空所有資料 (慎用!)"""
        with self.get_session() as session:
            session.query(Item).delete()
            session.query(DetectionSession).delete()
            session.query(CustomClass).delete()
            session.commit()
            logger.warning("所有資料已清空")


# ============================================
# 測試程式
# ============================================

if __name__ == "__main__":
    import tempfile
    import os

    # 使用臨時檔案測試
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")

        print("=" * 50)
        print("資料庫管理器測試")
        print("=" * 50)

        # 建立管理器
        db = DatabaseManager(db_path)

        # 建立會話
        session = db.create_session(source="test", source_ip="127.0.0.1")
        print(f"建立會話: ID={session.id}")

        # 新增物品
        item1 = db.add_item(
            name="手機",
            confidence=0.95,
            name_en="cell phone",
            category="電子產品",
            class_id=67,
            session_id=session.id,
        )
        print(f"新增物品: {item1.name}")

        item2 = db.add_item(
            name="水瓶",
            confidence=0.88,
            name_en="bottle",
            category="飲料容器",
            class_id=39,
            session_id=session.id,
        )
        print(f"新增物品: {item2.name}")

        # 更新會話
        db.end_session(session.id, total_frames=100, avg_fps=15.5)

        # 取得統計
        stats = db.get_statistics()
        print("\n統計資訊:")
        for key, value in stats.items():
            print(f"  {key}: {value}")

        # 取得最近物品
        recent = db.get_recent_items()
        print("\n最近物品:")
        for item in recent:
            print(f"  {item.name} (信心度: {item.confidence:.2f})")
