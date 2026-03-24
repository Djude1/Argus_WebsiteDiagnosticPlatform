# ============================================
# 資料遷移腳本
# ============================================
"""
將 feedback.jsonl 遷移到 annotations.json 格式

功能：
1. 備份現有 annotations.json
2. 載入 feedback.jsonl
3. 轉換回饋格式為標註格式
4. 複製圖片並加上 feedback_ 前綴
5. 合併轉換後的記錄到 annotations.json
6. 驗證遷移結果
"""

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from loguru import logger

# 專案根目錄
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
FEEDBACK_DIR = DATA_DIR / "feedback"
ANNOTATIONS_DIR = DATA_DIR / "annotations"
ANNOTATION_IMAGES_DIR = ANNOTATIONS_DIR / "annotation_images"

FEEDBACK_JSONL = FEEDBACK_DIR / "feedback.jsonl"
ANNOTATIONS_JSON = ANNOTATIONS_DIR / "annotations.json"


def load_feedback_data() -> List[Dict[str, Any]]:
    """載入 feedback.jsonl 記錄"""
    if not FEEDBACK_JSONL.exists():
        logger.error(f"找不到 feedback.jsonl: {FEEDBACK_JSONL}")
        return []

    records = []
    with open(FEEDBACK_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    logger.info(f"已載入 {len(records)} 筆 feedback 記錄")
    return records


def convert_feedback_to_annotation(feedback_record: Dict[str, Any]) -> Dict[str, Any]:
    """將 feedback 格式轉換為 annotation 格式"""
    # 從 image_path 擷取檔案名稱
    original_image_path = feedback_record.get("image_path", "")
    original_filename = Path(original_image_path).name

    # 生成新 ID 和圖片檔名
    timestamp_str = feedback_record.get("timestamp", "")
    class_name = feedback_record.get("class", "unknown")
    record_id = f"{timestamp_str.replace(':', '').replace('-', '').replace('.', '_')}_{class_name}"

    # 處理時間戳格式
    try:
        dt = datetime.fromisoformat(timestamp_str)
        formatted_timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        formatted_timestamp = timestamp_str

    # 處理 bbox 格式 [x1, y1, x2, y2] -> {x1, y1, x2, y2}
    bbox_list = feedback_record.get("bbox", [0, 0, 0, 0])
    bbox = {
        "x1": float(bbox_list[0]),
        "y1": float(bbox_list[1]),
        "x2": float(bbox_list[2]),
        "y2": float(bbox_list[3])
    }

    # 根據 feedback type 決定 status
    feedback_type = feedback_record.get("type", "confirm")
    if feedback_type == "correct":
        status = "pending"  # 需要確認的改為 pending
    else:
        status = "annotated"

    # 處理 correct_class
    correct_class = feedback_record.get("correct_class")
    description = class_name
    custom_label = class_name
    notes = ""

    if correct_class:
        description = f"{class_name} -> {correct_class}"
        custom_label = correct_class
        notes = f"原本誤判為 {class_name}"

    # 建立 annotation 格式記錄
    annotation = {
        "id": record_id,
        "source": "feedback",
        "type": feedback_type,
        "class_name": class_name,
        "class_name_cn": "",  # feedback.jsonl 沒有中文類名
        "confidence": float(feedback_record.get("confidence", 0.0)),
        "bbox": bbox,
        "timestamp": formatted_timestamp,
        "session_id": "",
        "image_path": f"annotation_images/feedback_{original_filename}",
        "status": status,
        "owner": "",
        "correct_class": correct_class,
        "description": description,
        "custom_label": custom_label,
        "notes": notes,
        "extra_data": {}
    }

    return annotation


def migrate_images(feedback_records: List[Dict[str, Any]]) -> int:
    """複製圖片並加上 feedback_ 前綴"""
    ANNOTATION_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # 確保 feedback 圖片目錄存在
    feedback_images_dir = FEEDBACK_DIR / "images"
    if not feedback_images_dir.exists():
        logger.warning(f"feedback 圖片目錄不存在: {feedback_images_dir}")
        return 0

    copied_count = 0
    for record in feedback_records:
        original_path = record.get("image_path", "")
        if not original_path:
            continue

        original_path = Path(original_path)
        if not original_path.exists():
            logger.warning(f"圖片不存在: {original_path}")
            continue

        dest_filename = f"feedback_{original_path.name}"
        dest_path = ANNOTATION_IMAGES_DIR / dest_filename

        try:
            shutil.copy2(original_path, dest_path)
            copied_count += 1
            logger.debug(f"已複製: {original_path.name} -> {dest_filename}")
        except Exception as e:
            logger.error(f"複製圖片失敗 {original_path}: {e}")

    logger.info(f"已複製 {copied_count} 張圖片")
    return copied_count


def backup_annotations() -> Path:
    """備份現有 annotations.json"""
    if not ANNOTATIONS_JSON.exists():
        logger.info("annotations.json 不存在，略過備份")
        return ANNOTATIONS_JSON

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = ANNOTATIONS_DIR / f"annotations_backup_{timestamp}.json"

    shutil.copy2(ANNOTATIONS_JSON, backup_path)
    logger.info(f"已備份 annotations.json -> {backup_path.name}")
    return backup_path


def load_existing_annotations() -> Dict[str, Any]:
    """載入現有 annotations.json"""
    if ANNOTATIONS_JSON.exists():
        with open(ANNOTATIONS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"version": "2.0", "records": []}


def save_annotations(annotations: Dict[str, Any]):
    """儲存 annotations.json"""
    ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)
    with open(ANNOTATIONS_JSON, "w", encoding="utf-8") as f:
        json.dump(annotations, f, indent=2, ensure_ascii=False)
    logger.info(f"已儲存 annotations.json")


def migrate_feedback_to_annotations() -> Dict[str, Any]:
    """主要遷移函數"""
    logger.info("開始遷移 feedback.jsonl 到 annotations.json")

    # 1. 載入 feedback 資料
    feedback_records = load_feedback_data()
    if not feedback_records:
        logger.warning("沒有 feedback 記錄需要遷移")
        return {"status": "skipped", "message": "沒有 feedback 記錄"}

    # 2. 備份現有 annotations.json
    backup_path = backup_annotations()

    # 3. 轉換 feedback 記錄
    converted_records = []
    for feedback in feedback_records:
        annotation = convert_feedback_to_annotation(feedback)
        converted_records.append(annotation)

    logger.info(f"已轉換 {len(converted_records)} 筆記錄")

    # 4. 複製圖片
    copied_count = migrate_images(feedback_records)

    # 5. 載入並更新 annotations
    existing = load_existing_annotations()
    existing.setdefault("records", [])

    # 合併記錄
    existing["records"].extend(converted_records)
    existing["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing["total_records"] = len(existing["records"])

    # 6. 儲存
    save_annotations(existing)

    # 7. 重命名 feedback.jsonl
    migrated_path = FEEDBACK_JSONL.with_suffix(".jsonl.migrated")
    shutil.move(FEEDBACK_JSONL, migrated_path)
    logger.info(f"已將 feedback.jsonl 重新命名為 {migrated_path.name}")

    return {
        "status": "success",
        "feedback_count": len(feedback_records),
        "images_copied": copied_count,
        "total_annotations": len(existing["records"]),
        "backup_path": str(backup_path),
        "migrated_file": str(migrated_path)
    }


def verify_migration() -> Dict[str, Any]:
    """驗證遷移結果"""
    logger.info("驗證遷移結果...")

    results = {
        "annotations_exists": ANNOTATIONS_JSON.exists(),
        "feedback_jsonl_migrated": FEEDBACK_JSONL.with_suffix(".jsonl.migrated").exists(),
        "feedback_jsonl_original_gone": not FEEDBACK_JSONL.exists(),
        "annotation_images_count": 0,
        "feedback_images_prefix_count": 0,
        "records_count": 0
    }

    # 檢查 annotation_images 目錄
    if ANNOTATION_IMAGES_DIR.exists():
        all_images = list(ANNOTATION_IMAGES_DIR.glob("*"))
        feedback_prefix_images = list(ANNOTATION_IMAGES_DIR.glob("feedback_*"))
        results["annotation_images_count"] = len(all_images)
        results["feedback_images_prefix_count"] = len(feedback_prefix_images)

    # 檢查 annotations.json 記錄數
    if ANNOTATIONS_JSON.exists():
        annotations = load_existing_annotations()
        records = annotations.get("records", [])
        results["records_count"] = len(records)

        # 檢查是否有 source=feedback 的記錄
        feedback_records = [r for r in records if r.get("source") == "feedback"]
        results["feedback_records_count"] = len(feedback_records)

    # 顯示結果
    logger.info("=== 遷移驗證結果 ===")
    for key, value in results.items():
        logger.info(f"  {key}: {value}")

    all_passed = (
        results["annotations_exists"] and
        results["feedback_jsonl_migrated"] and
        not results["feedback_jsonl_original_gone"] and
        results["feedback_images_prefix_count"] > 0
    )

    results["all_passed"] = all_passed

    if all_passed:
        logger.info("遷移驗證通過!")
    else:
        logger.warning("遷移驗證未完全通過，請檢查")

    return results


def main():
    """主程式入口"""
    parser = argparse.ArgumentParser(description="資料遷移腳本：將 feedback.jsonl 遷移到 annotations.json")
    parser.add_argument("--verify", action="store_true", help="只驗證遷移結果，不執行遷移")
    args = parser.parse_args()

    if args.verify:
        results = verify_migration()
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        results = migrate_feedback_to_annotations()
        print(json.dumps(results, indent=2, ensure_ascii=False))

        if results.get("status") == "success":
            print("\n執行驗證...")
            verify_migration()


if __name__ == "__main__":
    main()
