# ============================================
# 本地 Webcam 備援接收器
# ============================================
"""
當 ESP32 不可用時，使用本地 Webcam 作為影像來源
"""

import cv2
import numpy as np
from typing import Optional, Tuple, Generator
from dataclasses import dataclass
from loguru import logger
import sys

# 設定 loguru
logger.remove()
logger.add(
    sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>"
)


@dataclass
class WebcamStats:
    """Webcam 統計資訊"""

    fps: float = 0.0
    frame_count: int = 0
    width: int = 0
    height: int = 0


class WebcamReceiver:
    """本地 Webcam 接收器"""

    def __init__(
        self,
        camera_index: int = 0,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        buffer_skip: bool = True,  # 啟用緩衝區跳過，減少延遲
    ):
        """
        初始化 Webcam 接收器

        參數:
            camera_index: 攝影機索引 (0 = 預設攝影機)
            width: 影像寬度
            height: 影像高度
            fps: 目標幀率
            buffer_skip: 是否跳過緩衝區中的舊畫面（減少延遲）
        """
        self.camera_index = camera_index
        self.target_width = width
        self.target_height = height
        self.target_fps = fps
        self.buffer_skip = buffer_skip

        self.cap: Optional[cv2.VideoCapture] = None
        self.running = False
        self.stats = WebcamStats()

        logger.info(f"Webcam 接收器初始化完成 (索引: {camera_index})")

    def connect(self) -> bool:
        """連接到 Webcam"""
        try:
            logger.info(f"正在連接到 Webcam (索引: {self.camera_index})...")
            self.cap = cv2.VideoCapture(self.camera_index)

            if not self.cap.isOpened():
                logger.error("無法開啟 Webcam")
                return False

            # 設定解析度
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.target_width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.target_height)
            self.cap.set(cv2.CAP_PROP_FPS, self.target_fps)

            # 取得實際設定值
            self.stats.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.stats.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = self.cap.get(cv2.CAP_PROP_FPS)

            self.running = True
            logger.success(f"Webcam 連線成功！")
            logger.info(f"解析度: {self.stats.width}x{self.stats.height}, FPS: {actual_fps}")
            return True

        except Exception as e:
            logger.error(f"Webcam 連線失敗: {e}")
            return False

    def disconnect(self):
        """斷開連線"""
        self.running = False
        if self.cap:
            self.cap.release()
            self.cap = None
        logger.info("已斷開 Webcam 連線")

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        讀取單一畫面

        回傳:
            (success, frame): success 為是否成功，frame 為影像
        """
        if not self.running or not self.cap:
            return False, None

        # 如果啟用緩衝區跳過，讀取多次以獲取最新畫面
        if self.buffer_skip:
            # 跳過緩衝區中的舊畫面，最多跳過 5 次
            for _ in range(5):
                ret, frame = self.cap.read()
                if not ret:
                    continue
                # 檢查是否還有更多畫面在緩衝區
                if self.cap.get(cv2.CAP_PROP_POS_FRAMES) == 0:
                    break
            # 最後一次讀取確保拿到最新畫面
            ret, frame = self.cap.read()
        else:
            ret, frame = self.cap.read()

        if ret:
            self.stats.frame_count += 1
            return True, frame

        return False, None

    def frames(self) -> Generator[np.ndarray, None, None]:
        """
        產生器函式，持續產生影像畫面

        使用方式:
            for frame in webcam.frames():
                # 處理 frame
        """
        if not self.connect():
            return

        try:
            import time

            start_time = time.time()

            while self.running:
                ret, frame = self.cap.read()

                if not ret:
                    logger.warning("無法讀取畫面")
                    break

                self.stats.frame_count += 1

                # 更新 FPS
                elapsed = time.time() - start_time
                self.stats.fps = self.stats.frame_count / elapsed if elapsed > 0 else 0

                yield frame

        except KeyboardInterrupt:
            logger.info("使用者中斷串流")
        finally:
            self.disconnect()

    def get_stats(self) -> WebcamStats:
        """取得統計資訊"""
        return self.stats

    def set_resolution(self, width: int, height: int):
        """設定解析度"""
        if self.cap:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self.stats.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.stats.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            logger.info(f"解析度已設定為: {self.stats.width}x{self.stats.height}")


# ============================================
# 測試程式
# ============================================

if __name__ == "__main__":
    print("=" * 50)
    print("Webcam 測試")
    print("=" * 50)
    print("按 'q' 鍵結束")
    print("=" * 50)

    # 建立接收器
    webcam = WebcamReceiver(camera_index=0, width=640, height=480)

    # 測試串流
    try:
        for frame in webcam.frames():
            # 顯示 FPS
            stats = webcam.get_stats()
            cv2.putText(
                frame,
                f"FPS: {stats.fps:.1f}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2,
            )

            # 顯示解析度
            cv2.putText(
                frame,
                f"{stats.width}x{stats.height}",
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )

            # 顯示畫面
            cv2.imshow("Webcam Test", frame)

            # 按 'q' 結束
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except Exception as e:
        print(f"錯誤: {e}")
    finally:
        cv2.destroyAllWindows()
