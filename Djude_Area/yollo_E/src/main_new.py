#!/usr/bin/env python3
# ============================================
# YOLO 日常物品辨識系統 - 主程式
# ============================================
"""
主程式入口
整合 ESP32 串流、YOLO 辨識、資料庫記錄
"""

import argparse
import signal
import sys
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from loguru import logger

# 設定 loguru
logger.remove()
logger.add(
    sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>"
)

# 支援直接執行和套件匯入兩種模式：
if __name__ == "__main__" and __package__ is None:
    # 直接執行時，添加 src 目錄到路徑
    _src_path = Path(__file__).resolve().parent
    if str(_src_path) not in sys.path:
        sys.path.insert(0, str(_src_path))
    from config import get_config, get_esp32_stream_url, get_model_path, get_db_path
    from camera.esp32_stream import ESP32StreamReceiver
    from camera.webcam_fallback import WebcamReceiver
    from detection.yolo_detector import YOLODetector, FrameDetectionResult
    from detection.label_mapper import LabelMapper
    from database.db_manager import DatabaseManager
    from database.item_logger import ItemLogger, LoggerConfig
    from utils.visualization import draw_detections, draw_fps, draw_info_panel
    from annotation.annotation_manager import AnnotationManager, AnnotationConfig
    from annotation.models import AnnotationRecord, AnnotationStatus
else:
    # 套件匯入模式
    from .config import get_config, get_esp32_stream_url, get_model_path, get_db_path
    from .camera.esp32_stream import ESP32StreamReceiver
    from .camera.webcam_fallback import WebcamReceiver
    from .detection.yolo_detector import YOLODetector, FrameDetectionResult
    from .detection.label_mapper import LabelMapper
    from .database.db_manager import DatabaseManager
    from .database.item_logger import ItemLogger, LoggerConfig
    from .utils.visualization import draw_detections, draw_fps, draw_info_panel
    from .annotation.annotation_manager import AnnotationManager, AnnotationConfig
    from .annotation.models import AnnotationRecord, AnnotationStatus


class YOLODetectionSystem:
    """YOLO 辨識系統主類別"""

    def __init__(
        self,
        source: str = "esp32",
        model_path: str = None,
        use_custom_model: bool = False,
        confidence: float = 0.5,
        save_to_db: bool = True,
        save_images: bool = False,
        display: bool = True,
    ):
        """
        初始化辨識系統

        參數:
            source: 影像來源 ("esp32" 或 "webcam")
            model_path: 模型路徑
            use_custom_model: 是否使用自定義模型
            confidence: 信心度門檻
            save_to_db: 是否儲存到資料庫
            save_images: 是否儲存辨識圖片
            display: 是否顯示影像
        """
        self.source = source
        self.confidence = confidence
        self.save_to_db = save_to_db
        self.save_images = save_images
        self.display = display

        # 載入配置
        self.config = get_config()

        # 設定模型路徑
        if model_path:
            self.model_path = model_path
        else:
            self.model_path = get_model_path(use_custom=use_custom_model)

        # 初始化元件
        self.camera = None
        self.detector = None
        self.label_mapper = LabelMapper()
        self.db_manager = None
        self.item_logger = None

        # 狀態
        self.running = False
        self.frame_count = 0
        self.start_time = None

        logger.info("YOLO 辨識系統初始化中...")

    def initialize(self) -> bool:
        """初始化所有元件"""
        try:
            # 初始化資料庫
            if self.save_to_db:
                self.db_manager = DatabaseManager(str(get_db_path()))
                logger_config = LoggerConfig(
                    save_images=self.save_images, min_confidence=self.confidence, dedup_interval=5.0
                )
                self.item_logger = ItemLogger(self.db_manager, logger_config)
                logger.info("資料庫已初始化")

            # 解析開放詞彙偵測類別 (YOLOE 模型專用)
            prompt_classes = None
            if self.config.model.detection_classes:
                prompt_classes = [
                    c.strip() for c in self.config.model.detection_classes.split(",") if c.strip()
                ]
                logger.info(f"開放詞彙偵測類別: {prompt_classes}")

            # 初始化 YOLO 偵測器
            self.detector = YOLODetector(
                model_path=self.model_path,
                confidence_threshold=self.confidence,
                device="auto",
                prompt_classes=prompt_classes,  # 傳遞開放詞彙類別
            )
            logger.info(f"YOLO 模型已載入: {self.model_path}")

            # 初始化攝影機
            if self.source == "esp32":
                self.camera = ESP32StreamReceiver(
                    esp32_ip=self.config.esp32.ip,
                    port=self.config.esp32.port,
                    stream_path=self.config.esp32.stream_path,
                )
                logger.info(f"ESP32 串流接收器已初始化: {self.config.esp32.stream_url}")
            else:
                self.camera = WebcamReceiver(
                    camera_index=0,
                    width=self.config.camera.frame_width,
                    height=self.config.camera.frame_height,
                )
                logger.info("Webcam 接收器已初始化")

            return True

        except Exception as e:
            logger.error(f"初始化失敗: {e}")
            return False

    def run(self):
        """執行辨識系統"""
        if not self.initialize():
            logger.error("系統初始化失敗，無法啟動")
            return

        logger.info("=" * 50)
        logger.info("YOLO 日常物品辨識系統啟動")
        logger.info("=" * 50)
        logger.info(f"影像來源: {self.source}")
        logger.info(f"模型: {self.model_path}")
        logger.info(f"信心度門檻: {self.confidence}")
        logger.info("按 'q' 鍵結束程式")
        logger.info("=" * 50)

        # 開始辨識會話
        session_id = None
        if self.item_logger:
            session_id = self.item_logger.start_session(
                source=self.source,
                source_ip=self.config.esp32.ip if self.source == "esp32" else None,
            )

        self.running = True
        self.start_time = time.time()
        self.frame_count = 0

        try:
            # 連接攝影機
            if not self.camera.connect():
                logger.error("無法連接到影像來源")
                return

            # 主迴圈
            while self.running:
                # 讀取畫面
                ret, frame = self.camera.read_frame()
                if not ret or frame is None:
                    logger.warning("無法讀取畫面")
                    continue

                self.frame_count += 1

                # 執行 YOLO 辨識
                result = self.detector.detect(frame)

                # 加入中文標籤
                for detection in result.detections:
                    detection.class_name_cn = self.label_mapper.get_chinese_name(
                        detection.class_id, detection.class_name
                    )

                # 記錄到資料庫
                if self.item_logger:
                    self.item_logger.log_frame(result, frame)

                # 顯示結果
                if self.display:
                    # 繪製偵測結果
                    output = self.detector.draw_detections(frame, result, show_label_cn=True)

                    # 顯示資訊面板
                    info = {
                        "FPS": f"{result.fps:.1f}",
                        "Objects": result.count,
                        "Source": self.source,
                    }
                    output = draw_info_panel(output, info, position=(10, 30))

                    cv2.imshow("YOLO Detection", output)

                    # 按鍵處理
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        logger.info("使用者按下 'q' 鍵，結束程式")
                        break
                    elif key == ord("s"):
                        # 儲存當前畫面
                        from .utils.visualization import save_detection_image

                        filepath = save_detection_image(output, "screenshots")
                        logger.info(f"已儲存畫面: {filepath}")

        except KeyboardInterrupt:
            logger.info("收到中斷訊號")
        except Exception as e:
            logger.error(f"執行錯誤: {e}")
        finally:
            self.stop()

    def stop(self):
        """停止系統"""
        self.running = False

        # 計算統計
        if self.start_time and self.frame_count > 0:
            elapsed = time.time() - self.start_time
            avg_fps = self.frame_count / elapsed
        else:
            elapsed = 0
            avg_fps = 0

        # 結束會話
        session_id = (
            getattr(self.item_logger, "current_session", None) if self.item_logger else None
        )
        if session_id:
            self.item_logger.end_session(total_frames=self.frame_count, avg_fps=avg_fps)

        # 清理資源
        if self.camera:
            self.camera.disconnect()

        cv2.destroyAllWindows()

        logger.info("=" * 50)
        logger.info("系統已停止")
        logger.info(f"總幀數: {self.frame_count}")
        logger.info(f"執行時間: {elapsed:.1f} 秒")
        logger.info(f"平均 FPS: {avg_fps:.1f}")
        logger.info("=" * 50)


def main():
    """主程式入口"""
    parser = argparse.ArgumentParser(
        description="YOLO 日常物品辨識系統",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例:
  # 使用 ESP32 串流
  python main.py --source esp32
  
  # 使用本地 Webcam
  python main.py --source webcam
  
  # 使用自定義模型
  python main.py --model models/custom/yoloe_custom.pt
  
  # 不顯示視窗（背景執行）
  python main.py --no-display
        """,
    )

    parser.add_argument(
        "--source",
        type=str,
        default="esp32",
        choices=["esp32", "webcam"],
        help="影像來源 (esp32 或 webcam)",
    )

    parser.add_argument("--model", type=str, default=None, help="模型檔案路徑")

    parser.add_argument("--custom", action="store_true", help="使用自定義訓練的模型")

    parser.add_argument("--confidence", type=float, default=0.5, help="信心度門檻 (0.0 - 1.0)")

    parser.add_argument("--no-db", action="store_true", help="不儲存到資料庫")

    parser.add_argument("--save-images", action="store_true", help="儲存辨識圖片")

    parser.add_argument("--no-display", action="store_true", help="不顯示影像視窗")

    args = parser.parse_args()

    # 建立並執行系統
    system = YOLODetectionSystem(
        source=args.source,
        model_path=args.model,
        use_custom_model=args.custom,
        confidence=args.confidence,
        save_to_db=not args.no_db,
        save_images=args.save_images,
        display=not args.no_display,
    )

    # 設定訊號處理
    def signal_handler(sig, frame):
        logger.info("收到停止訊號")
        system.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 執行系統
    system.run()


if __name__ == "__main__":
    main()
