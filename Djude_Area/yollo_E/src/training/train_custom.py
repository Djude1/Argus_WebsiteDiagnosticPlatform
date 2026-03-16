# ============================================
# 自定義模型訓練
# ============================================
"""
使用 Ultralytics YOLO 訓練自定義物品
"""

from pathlib import Path
from typing import Optional, Dict, Any
from loguru import logger
import sys
import yaml

logger.remove()
logger.add(
    sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>"
)


def train_custom_model(
    data_yaml: str,
    base_model: str = "yoloe-26s-seg.pt",
    epochs: int = 100,
    batch_size: int = 16,
    img_size: int = 640,
    device: str = "auto",
    project: str = "runs/train",
    name: str = "custom_exp",
    **kwargs,
) -> Dict[str, Any]:
    """
    訓練自定義 YOLO 模型

    參數:
        data_yaml: 資料集配置檔路徑
        base_model: 基礎模型路徑
        epochs: 訓練輪數
        batch_size: 批次大小
        img_size: 影像大小
        device: 運算裝置
        project: 專案目錄
        name: 實驗名稱
        **kwargs: 其他訓練參數

    回傳:
        訓練結果
    """
    try:
        from ultralytics import YOLO
    except ImportError:
        logger.error("請先安裝 ultralytics: pip install ultralytics")
        return {}

    logger.info("=" * 50)
    logger.info("開始訓練自定義模型")
    logger.info("=" * 50)
    logger.info(f"資料集配置: {data_yaml}")
    logger.info(f"基礎模型: {base_model}")
    logger.info(f"訓練輪數: {epochs}")
    logger.info(f"批次大小: {batch_size}")
    logger.info(f"影像大小: {img_size}")
    logger.info("=" * 50)

    # 載入模型
    model = YOLO(base_model)

    # 開始訓練
    results = model.train(
        data=data_yaml,
        epochs=epochs,
        batch=batch_size,
        imgsz=img_size,
        device=device,
        project=project,
        name=name,
        **kwargs,
    )

    logger.info("訓練完成！")
    logger.info(f"最佳模型: {project}/{name}/weights/best.pt")

    return results


def create_dataset_yaml(output_path: str, train_path: str, val_path: str, class_names: list) -> str:
    """
    建立資料集配置檔

    參數:
        output_path: 輸出路徑
        train_path: 訓練集路徑
        val_path: 驗證集路徑
        class_names: 類別名稱列表

    回傳:
        配置檔路徑
    """
    config = {
        "path": str(Path(output_path).parent),
        "train": train_path,
        "val": val_path,
        "names": {i: name for i, name in enumerate(class_names)},
    }

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

    logger.info(f"已建立資料集配置檔: {output_path}")
    return output_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="訓練自定義 YOLO 模型")
    parser.add_argument("--data", type=str, required=True, help="資料集配置檔路徑")
    parser.add_argument("--model", type=str, default="yoloe-26s-seg.pt", help="基礎模型")
    parser.add_argument("--epochs", type=int, default=100, help="訓練輪數")
    parser.add_argument("--batch", type=int, default=16, help="批次大小")
    parser.add_argument("--img-size", type=int, default=640, help="影像大小")
    parser.add_argument("--device", type=str, default="auto", help="運算裝置")
    parser.add_argument("--name", type=str, default="custom_exp", help="實驗名稱")

    args = parser.parse_args()

    train_custom_model(
        data_yaml=args.data,
        base_model=args.model,
        epochs=args.epochs,
        batch_size=args.batch,
        img_size=args.img_size,
        device=args.device,
        name=args.name,
    )
