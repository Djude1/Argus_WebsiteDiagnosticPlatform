# ============================================
# ESP32 MJPEG 串流接收器
# ============================================
"""
透過 HTTP MJPEG 協議接收 ESP32 傳來的影像串流
"""

import time
import requests
import numpy as np
import cv2
from typing import Optional, Generator, Tuple
from dataclasses import dataclass
from loguru import logger
import sys

# 設定 loguru
logger.remove()
logger.add(
    sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>"
)


@dataclass
class StreamStats:
    """串流統計資訊"""

    fps: float = 0.0
    frame_count: int = 0
    bytes_received: int = 0
    start_time: float = 0.0
    latency_ms: float = 0.0


class ESP32StreamReceiver:
    """ESP32 MJPEG 串流接收器"""

    def __init__(
        self,
        esp32_ip: str = "",
        port: int = 80,
        stream_path: str = "/stream",
        timeout: int = 10,
        chunk_size: int = 16384,  # 增大 chunk_size 減少讀取次數，降低延遲
        hostname: str = "yollo",
        max_buffer_size: int = 512 * 1024,  # 最大緩衝區大小，防止記憶體溢出
    ):
        """
        初始化 ESP32 串流接收器

        參數:
            esp32_ip: ESP32 的 IP 位址 (備援用，若 mDNS 失敗時使用)
            port: HTTP 埠號
            stream_path: 串流路徑
            timeout: 連線逾時秒數
            chunk_size: 每次讀取的位元組大小（增大可降低延遲）
            hostname: mDNS 主機名 (優先使用)
            max_buffer_size: 最大緩衝區大小
        """
        # 決定使用主機名還是 IP
        # 優先使用 hostname (mDNS)，若未提供則使用 IP
        if hostname:
            self.host = f"{hostname}.local"
        elif esp32_ip:
            self.host = esp32_ip
        else:
            self.host = "yollo.local"  # 預設使用 mDNS

        self.stream_url = f"http://{self.host}:{port}{stream_path}"
        self.snapshot_url = f"http://{self.host}:{port}/snapshot"
        self.status_url = f"http://{self.host}:{port}/status"
        self.timeout = timeout
        self.chunk_size = chunk_size

        self.response: Optional[requests.Response] = None
        self.running = False
        self.stats = StreamStats()
        self.max_buffer_size = max_buffer_size  # 儲存為實例變數

        logger.info(f"ESP32 串流接收器初始化完成: {self.stream_url}")

    def connect(self) -> bool:
        """連接到 ESP32 串流"""
        try:
            logger.info(f"正在連接到 ESP32: {self.stream_url}")
            self.response = requests.get(self.stream_url, stream=True, timeout=self.timeout)
            self.response.raise_for_status()
            self.running = True
            self.stats.start_time = time.time()
            logger.success("ESP32 串流連線成功！")
            return True

        except requests.exceptions.Timeout:
            logger.error("連線逾時，請檢查 ESP32 是否開機且 IP 正確")
            return False
        except requests.exceptions.ConnectionError as e:
            logger.error(f"連線失敗: {e}")
            return False
        except Exception as e:
            logger.error(f"未知錯誤: {e}")
            return False

    def disconnect(self):
        """斷開連線"""
        self.running = False
        if self.response:
            self.response.close()
            self.response = None
        logger.info("已斷開 ESP32 串流連線")

    def _parse_mjpeg(self) -> Generator[np.ndarray, None, None]:
        """解析 MJPEG 串流，產生影像畫面"""
        if not self.response:
            return

        bytes_data = bytes()

        for chunk in self.response.iter_content(chunk_size=self.chunk_size):
            if not self.running:
                break

            bytes_data += chunk
            self.stats.bytes_received += len(chunk)

            # 限制緩衝區大小，防止記憶體溢出
            if len(bytes_data) > self.max_buffer_size:
                bytes_data = bytes_data[-self.max_buffer_size // 2 :]

            # 尋找 JPEG 標記
            # JPEG 檔案開始標記: 0xFFD8
            # JPEG 檔案結束標記: 0xFFD9
            start_marker = bytes_data.find(b"\xff\xd8")
            end_marker = bytes_data.find(b"\xff\xd9")

            if start_marker != -1 and end_marker != -1 and end_marker > start_marker:
                # 提取完整的 JPEG 圖片
                jpg_data = bytes_data[start_marker : end_marker + 2]
                bytes_data = bytes_data[end_marker + 2 :]

                # 解碼 JPEG 為 numpy 陣列
                try:
                    image = cv2.imdecode(np.frombuffer(jpg_data, dtype=np.uint8), cv2.IMREAD_COLOR)

                    if image is not None:
                        self.stats.frame_count += 1
                        yield image

                except Exception as e:
                    logger.warning(f"影像解碼錯誤: {e}")

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        讀取單一畫面

        回傳:
            (success, frame): success 為是否成功，frame 為影像
        """
        if not self.running or not self.response:
            return False, None

        try:
            for frame in self._parse_mjpeg():
                # 更新 FPS 統計
                if self.stats.start_time > 0:
                    elapsed = time.time() - self.stats.start_time
                    self.stats.fps = self.stats.frame_count / elapsed if elapsed > 0 else 0

                return True, frame

        except Exception as e:
            logger.error(f"讀取畫面錯誤: {e}")
            return False, None

        return False, None

    def frames(self) -> Generator[np.ndarray, None, None]:
        """
        產生器函式，持續產生影像畫面

        使用方式:
            for frame in receiver.frames():
                # 處理 frame
        """
        if not self.connect():
            return

        try:
            for frame in self._parse_mjpeg():
                if not self.running:
                    break

                # 更新 FPS 統計
                if self.stats.start_time > 0:
                    elapsed = time.time() - self.stats.start_time
                    self.stats.fps = self.stats.frame_count / elapsed if elapsed > 0 else 0

                yield frame

        except KeyboardInterrupt:
            logger.info("使用者中斷串流")
        finally:
            self.disconnect()

    def get_status(self) -> dict:
        """取得 ESP32 狀態"""
        try:
            response = requests.get(self.status_url, timeout=5)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.warning(f"無法取得 ESP32 狀態: {e}")
        return {}

    def capture_snapshot(self) -> Optional[np.ndarray]:
        """擷取單張快照"""
        try:
            response = requests.get(self.snapshot_url, timeout=5)
            if response.status_code == 200:
                image = cv2.imdecode(
                    np.frombuffer(response.content, dtype=np.uint8), cv2.IMREAD_COLOR
                )
                return image
        except Exception as e:
            logger.error(f"快照擷取失敗: {e}")
        return None

    def get_stats(self) -> StreamStats:
        """取得串流統計資訊"""
        return self.stats


# ============================================
# 測試程式
# ============================================

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    # 載入環境變數
    load_dotenv()

    # 從環境變數取得設定 (優先使用 hostname)
    esp32_hostname = os.getenv("ESP32_HOSTNAME", "yollo")
    esp32_ip = os.getenv("ESP32_IP", "")

    print("=" * 50)
    print("ESP32 串流測試")
    print("=" * 50)
    print(f"ESP32 主機名: {esp32_hostname}")
    print(f"ESP32 IP (備援): {esp32_ip or '未設定'}")
    print("按 'q' 鍵結束")
    print("=" * 50)

    # 建立接收器 (優先使用 hostname)
    receiver = ESP32StreamReceiver(hostname=esp32_hostname, esp32_ip=esp32_ip)

    # 測試串流
    try:
        for frame in receiver.frames():
            # 顯示 FPS
            stats = receiver.get_stats()
            cv2.putText(
                frame,
                f"FPS: {stats.fps:.1f}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2,
            )

            # 顯示畫面
            cv2.imshow("ESP32 Stream Test", frame)

            # 按 'q' 結束
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except Exception as e:
        print(f"錯誤: {e}")
    finally:
        cv2.destroyAllWindows()
