# ============================================
# 訓練資料收集器
# ============================================
"""
收集自定義物品的訓練資料
"""

import cv2
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from loguru import logger
import sys

logger.remove()
logger.add(
    sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>"
)


class DataCollector:
    """訓練資料收集器"""

    def __init__(self, output_dir: str = "data/datasets/raw", class_name: str = "custom_object"):
        """
        初始化資料收集器

        參數:
            output_dir: 輸出目錄
            class_name: 類別名稱
        """
        self.output_dir = Path(output_dir)
        self.class_name = class_name
        self.class_dir = self.output_dir / class_name
        self.class_dir.mkdir(parents=True, exist_ok=True)

        self.collected_count = 0
        self.camera = None

        logger.info(f"資料收集器已初始化: {self.class_dir}")

    def collect_from_webcam(
        self, target_count: int = 100, interval: float = 0.5, preview: bool = True
    ) -> int:
        """
        從 Webcam 收集圖片

        參數:
            target_count: 目標收集數量
            interval: 收集間隔（秒）
            preview: 是否預覽

        回傳:
            實際收集的數量
        """
        cap = cv2.VideoCapture(0)

        if not cap.isOpened():
            logger.error("無法開啟 Webcam")
            return 0

        logger.info(f"開始收集 '{self.class_name}' 圖片")
        logger.info(f"目標數量: {target_count}")
        logger.info("按 'q' 停止收集，按 's' 儲存單張")

        last_save_time = 0
        collected = 0

        try:
            while collected < target_count:
                ret, frame = cap.read()
                if not ret:
                    continue

                current_time = time.time()

                # 顯示預覽
                if preview:
                    display = frame.copy()
                    cv2.putText(
                        display,
                        f"Collected: {collected}/{target_count}",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1,
                        (0, 255, 0),
                        2,
                    )
                    cv2.imshow("Data Collection", display)

                key = cv2.waitKey(1) & 0xFF

                if key == ord("q"):
                    break
                elif key == ord("s") or (current_time - last_save_time >= interval):
                    # 儲存圖片
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    filename = f"{self.class_name}_{timestamp}.jpg"
                    filepath = self.class_dir / filename

                    cv2.imwrite(str(filepath), frame)
                    collected += 1
                    last_save_time = current_time

                    logger.info(f"已儲存: {filename} ({collected}/{target_count})")

        except KeyboardInterrupt:
            logger.info("收集已中斷")
        finally:
            cap.release()
            cv2.destroyAllWindows()

        self.collected_count = collected
        logger.info(f"收集完成: {collected} 張圖片")

        return collected

    def collect_from_esp32(
        self, esp32_ip: str, target_count: int = 100, interval: float = 0.5
    ) -> int:
        """從 ESP32 收集圖片"""
        from camera.esp32_stream import ESP32StreamReceiver

        receiver = ESP32StreamReceiver(esp32_ip=esp32_ip)

        if not receiver.connect():
            logger.error("無法連接到 ESP32")
            return 0

        logger.info(f"開始從 ESP32 收集 '{self.class_name}' 圖片")

        collected = 0
        last_save_time = 0

        try:
            for frame in receiver.frames():
                if collected >= target_count:
                    break

                current_time = time.time()

                if current_time - last_save_time >= interval:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    filename = f"{self.class_name}_{timestamp}.jpg"
                    filepath = self.class_dir / filename

                    cv2.imwrite(str(filepath), frame)
                    collected += 1
                    last_save_time = current_time

                    logger.info(f"已儲存: {filename} ({collected}/{target_count})")

        except KeyboardInterrupt:
            logger.info("收集已中斷")
        finally:
            receiver.disconnect()

        self.collected_count = collected
        return collected


if __name__ == "__main__":
    import time

    print("=" * 50)
    print("訓練資料收集器")
    print("=" * 50)

    class_name = input("請輸入類別名稱 (例如: 100_ntd): ")
    target_count = int(input("請輸入目標數量 (預設 100): ") or "100")

    collector = DataCollector(class_name=class_name)
    collector.collect_from_webcam(target_count=target_count)
