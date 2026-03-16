# ============================================
# 標註管理器
# ============================================
"""
管理物品標註記錄的讀取、寫入和查詢
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from dataclasses import dataclass
from loguru import logger
import sys
import cv2
import numpy as np

# 設定 loguru
logger.remove()
logger.add(
    sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>"
)

from .models import AnnotationRecord, AnnotationStatus, BoundingBox

# 使用 TYPE_CHECKING 避免運行時循環導入
if TYPE_CHECKING:
    from detection.yolo_detector import DetectionResult


@dataclass
class AnnotationConfig:
    """標註管理器配置"""

    annotation_file: str = "data/annotations/annotations.json"
    image_dir: str = "data/annotation_images"
    auto_save: bool = True


class AnnotationManager:
    """
    標註管理器

    負責管理物品標註記錄的讀取、寫入、查詢等操作
    """

    def __init__(self, config: AnnotationConfig = None):
        """
        初始化標註管理器

        參數:
            config: 標註管理器配置
        """
        self.config = config or AnnotationConfig()
        self.annotations: Dict[str, AnnotationRecord] = {}

        # 確保目錄存在
        Path(self.config.annotation_file).parent.mkdir(parents=True, exist_ok=True)
        Path(self.config.image_dir).mkdir(parents=True, exist_ok=True)

        # 載入現有記錄
        self._load_annotations()

        logger.info(f"標註管理器已初始化，現有記錄: {len(self.annotations)} 筆")

    def _load_annotations(self):
        """從 JSON 檔案載入標註記錄"""
        file_path = Path(self.config.annotation_file)

        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                for record_data in data.get("records", []):
                    record = AnnotationRecord.from_dict(record_data)
                    self.annotations[record.id] = record

                logger.info(f"已載入 {len(self.annotations)} 筆標註記錄")
            except Exception as e:
                logger.error(f"載入標註記錄失敗: {e}")
                self.annotations = {}

    def _save_annotations(self):
        """將標註記錄儲存到 JSON 檔案"""
        file_path = Path(self.config.annotation_file)

        try:
            data = {
                "version": "1.0",
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_records": len(self.annotations),
                "records": [record.to_dict() for record in self.annotations.values()],
            }

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug(f"已儲存 {len(self.annotations)} 筆標註記錄")
        except Exception as e:
            logger.error(f"儲存標註記錄失敗: {e}")

    def add_detection(
        self,
        detection: "DetectionResult",
        frame: Optional[np.ndarray] = None,
        session_id: Optional[int] = None,
    ) -> AnnotationRecord:
        """
        添加偵測結果到標註記錄

        參數:
            detection: 偵測結果
            frame: 原始影像（用於儲存截圖）
            session_id: 會話 ID

        回傳:
            新增的標註記錄
        """
        # 生成唯一 ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        record_id = f"{timestamp}_{detection.class_name}"

        # 儲存截圖
        image_path = None
        if frame is not None:
            image_path = self._save_crop_image(detection, frame, record_id)

        # 建立記錄
        bbox = BoundingBox(
            x1=detection.bbox.x1, y1=detection.bbox.y1, x2=detection.bbox.x2, y2=detection.bbox.y2
        )

        record = AnnotationRecord(
            id=record_id,
            class_name=detection.class_name,
            class_name_cn=detection.class_name_cn,
            confidence=detection.confidence,
            bbox=bbox,
            session_id=session_id,
            image_path=image_path,
        )

        self.annotations[record_id] = record

        # 自動儲存
        if self.config.auto_save:
            self._save_annotations()

        logger.info(
            f"新增標註記錄: {record_id} ({detection.class_name_cn or detection.class_name})"
        )

        return record

    def add_detections(
        self,
        detections: List["DetectionResult"],
        frame: np.ndarray = None,
        session_id: Optional[int] = None,
    ) -> List[AnnotationRecord]:
        """
        批次添加偵測結果

        參數:
            detections: 偵測結果列表
            frame: 原始影像
            session_id: 會話 ID

        回傳:
            新增的標註記錄列表
        """
        records = []

        for detection in detections:
            record = self.add_detection(detection, frame, session_id)
            records.append(record)

        return records

    def _save_crop_image(
        self, detection: "DetectionResult", frame: np.ndarray, record_id: str
    ) -> Optional[str]:
        """儲存偵測區域截圖"""
        try:
            # 取得邊界框座標
            x1, y1, x2, y2 = detection.bbox.to_tuple()

            # 確保座標在範圍內
            h, w = frame.shape[:2]
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(w, x2)
            y2 = min(h, y2)

            if x2 > x1 and y2 > y1:
                # 裁切偵測區域
                crop = frame[y1:y2, x1:x2]

                # 儲存圖片
                filename = f"{record_id}.jpg"
                filepath = Path(self.config.image_dir) / filename
                cv2.imwrite(str(filepath), crop)

                return str(filepath)
        except Exception as e:
            logger.error(f"儲存截圖失敗: {e}")

        return None

    def get_record(self, record_id: str) -> Optional[AnnotationRecord]:
        """取得指定記錄"""
        return self.annotations.get(record_id)

    def get_all_records(self) -> List[AnnotationRecord]:
        """取得所有記錄"""
        return list(self.annotations.values())

    def get_pending_records(self) -> List[AnnotationRecord]:
        """取得待標註的記錄"""
        return [r for r in self.annotations.values() if r.is_pending()]

    def get_annotated_records(self) -> List[AnnotationRecord]:
        """取得已標註的記錄"""
        return [r for r in self.annotations.values() if r.status == AnnotationStatus.ANNOTATED]

    def get_records_by_class(self, class_name: str) -> List[AnnotationRecord]:
        """根據類別取得記錄"""
        return [r for r in self.annotations.values() if r.class_name == class_name]

    def get_records_by_owner(self, owner: str) -> List[AnnotationRecord]:
        """根據擁有者取得記錄"""
        return [r for r in self.annotations.values() if r.owner == owner]

    def update_annotation(
        self,
        record_id: str,
        owner: str = None,
        description: str = None,
        custom_label: str = None,
        notes: str = None,
        status: AnnotationStatus = None,
    ) -> bool:
        """
        更新標註資訊

        參數:
            record_id: 記錄 ID
            owner: 擁有者
            description: 描述
            custom_label: 自定義標籤
            notes: 備註
            status: 狀態

        回傳:
            是否更新成功
        """
        record = self.annotations.get(record_id)
        if not record:
            logger.warning(f"找不到記錄: {record_id}")
            return False

        if owner is not None:
            record.owner = owner
        if description is not None:
            record.description = description
        if custom_label is not None:
            record.custom_label = custom_label
        if notes is not None:
            record.notes = notes
        if status is not None:
            record.status = status

        if self.config.auto_save:
            self._save_annotations()

        logger.info(f"已更新標註: {record_id}")
        return True

    def mark_annotated(
        self,
        record_id: str,
        owner: str = "",
        description: str = "",
        custom_label: str = "",
        notes: str = "",
    ) -> bool:
        """標記記錄為已標註"""
        record = self.annotations.get(record_id)
        if not record:
            return False

        record.mark_annotated(owner, description, custom_label, notes)

        if self.config.auto_save:
            self._save_annotations()

        return True

    def mark_skipped(self, record_id: str) -> bool:
        """標記記錄為已跳過"""
        record = self.annotations.get(record_id)
        if not record:
            return False

        record.mark_skipped()

        if self.config.auto_save:
            self._save_annotations()

        return True

    def delete_record(self, record_id: str) -> bool:
        """刪除記錄"""
        if record_id in self.annotations:
            del self.annotations[record_id]

            if self.config.auto_save:
                self._save_annotations()

            logger.info(f"已刪除記錄: {record_id}")
            return True

        return False

    def get_statistics(self) -> Dict[str, Any]:
        """取得統計資訊"""
        total = len(self.annotations)
        pending = len(self.get_pending_records())
        annotated = len(self.get_annotated_records())
        skipped = sum(1 for r in self.annotations.values() if r.status == AnnotationStatus.SKIPPED)

        # 按類別統計
        class_stats: Dict[str, int] = {}
        for record in self.annotations.values():
            class_name = record.class_name_cn or record.class_name
            class_stats[class_name] = class_stats.get(class_name, 0) + 1

        # 按擁有者統計
        owner_stats: Dict[str, int] = {}
        for record in self.annotations.values():
            if record.owner:
                owner_stats[record.owner] = owner_stats.get(record.owner, 0) + 1

        return {
            "total": total,
            "pending": pending,
            "annotated": annotated,
            "skipped": skipped,
            "by_class": class_stats,
            "by_owner": owner_stats,
        }

    def export_to_csv(self, output_path: str) -> bool:
        """匯出為 CSV 格式"""
        import csv

        try:
            with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)

                # 寫入標題
                writer.writerow(
                    [
                        "ID",
                        "類別",
                        "中文名稱",
                        "信心度",
                        "時間",
                        "狀態",
                        "擁有者",
                        "描述",
                        "自定義標籤",
                        "備註",
                        "圖片路徑",
                    ]
                )

                # 寫入資料
                for record in self.annotations.values():
                    writer.writerow(
                        [
                            record.id,
                            record.class_name,
                            record.class_name_cn,
                            f"{record.confidence:.2f}",
                            record.timestamp,
                            record.status.value,
                            record.owner,
                            record.description,
                            record.custom_label,
                            record.notes,
                            record.image_path or "",
                        ]
                    )

            logger.info(f"已匯出 CSV: {output_path}")
            return True
        except Exception as e:
            logger.error(f"匯出 CSV 失敗: {e}")
            return False

    def reload_annotations(self) -> int:
        """
        重新載入標註記錄（用於即時更新）

        回傳:
            載入的記錄數量
        """
        self.annotations.clear()
        self._load_annotations()
        return len(self.annotations)

    def get_custom_label_for_class(self, class_name: str) -> Optional[str]:
        """
        根據類別名稱取得自定義標籤

        查找該類別中最新且有 custom_label 的記錄，
        返回其 custom_label。

        參數:
            class_name: 類別名稱（英文，如 "bottle", "cup"）

        回傳:
            自定義標籤，如果沒有則返回 None
        """
        # 找出該類別所有有 custom_label 的記錄
        matching_records = []
        for record in self.annotations.values():
            if record.class_name == class_name and record.custom_label:
                matching_records.append(record)

        if not matching_records:
            return None

        # 按時間排序，返回最新的 custom_label
        matching_records.sort(key=lambda r: r.timestamp, reverse=True)
        return matching_records[0].custom_label

    def get_all_custom_labels(self) -> Dict[str, str]:
        """
        取得所有類別的自定義標籤對應表

        回傳:
            字典 {class_name: custom_label}
        """
        labels = {}
        for record in self.annotations.values():
            if record.custom_label and record.class_name:
                # 如果該類別還沒有標籤，或是這筆記錄較新，則更新
                if record.class_name not in labels:
                    labels[record.class_name] = record.custom_label
                else:
                    # 比較時間，保留較新的
                    existing_record = next(
                        (
                            r
                            for r in self.annotations.values()
                            if r.class_name == record.class_name
                            and r.custom_label == labels[record.class_name]
                        ),
                        None,
                    )
                    if existing_record and record.timestamp > existing_record.timestamp:
                        labels[record.class_name] = record.custom_label

        return labels

    def get_label_history(self) -> List[Dict[str, str]]:
        """
        取得所有曾經使用過的標籤對（中文 -> 英文）

        從 description（中文）和 custom_label（英文）中提取歷史標籤對，
        用於下拉式選單顯示。

        回傳:
            列表 [{"cn": "手機", "en": "phone"}, ...]
        """
        label_pairs: Dict[str, Dict[str, str]] = {}  # 用中文作為 key 去重

        for record in self.annotations.values():
            # description 是中文物品名稱，custom_label 是英文標籤
            cn_label = record.description.strip() if record.description else ""
            en_label = record.custom_label.strip() if record.custom_label else ""

            # 兩者都有值才加入
            if cn_label and en_label:
                if cn_label not in label_pairs:
                    label_pairs[cn_label] = {"cn": cn_label, "en": en_label}

        # 轉換為列表並按中文排序
        result = list(label_pairs.values())
        result.sort(key=lambda x: x["cn"])

        return result

    def get_unique_descriptions(self) -> List[str]:
        """
        取得所有不重複的 description（中文物品名稱）

        回傳:
            不重複的中文物品名稱列表
        """
        descriptions = set()
        for record in self.annotations.values():
            if record.description and record.description.strip():
                descriptions.add(record.description.strip())
        return sorted(list(descriptions))


# ============================================
# 測試程式
# ============================================

if __name__ == "__main__":
    import tempfile
    import os
    from detection.yolo_detector import BoundingBox as DetBBox, DetectionResult

    # 使用臨時目錄測試
    with tempfile.TemporaryDirectory() as tmpdir:
        config = AnnotationConfig(
            annotation_file=os.path.join(tmpdir, "annotations.json"),
            image_dir=os.path.join(tmpdir, "images"),
        )

        manager = AnnotationManager(config)

        print("=" * 50)
        print("標註管理器測試")
        print("=" * 50)

        # 模擬偵測結果
        detection = DetectionResult(
            bbox=DetBBox(x1=100, y1=100, x2=200, y2=300),
            confidence=0.95,
            class_id=67,
            class_name="cell phone",
            class_name_cn="手機",
        )

        # 添加記錄
        record = manager.add_detection(detection, session_id=1)
        print(f"新增記錄: {record.id}")

        # 取得統計
        stats = manager.get_statistics()
        print(f"\n統計: {stats}")

        # 標註
        manager.mark_annotated(record.id, owner="王小明", description="黑色 iPhone 15 Pro")

        # 取得待標註記錄
        pending = manager.get_pending_records()
        print(f"\n待標註: {len(pending)} 筆")

        # 匯出 CSV
        csv_path = os.path.join(tmpdir, "export.csv")
        manager.export_to_csv(csv_path)
        print(f"\n已匯出 CSV: {csv_path}")
