#!/usr/bin/env python3
# ============================================
# YOLO 網頁伺服器 - FastAPI + WebSocket
# ============================================
"""
網頁伺服器模組
提供瀏覽器攝影機串流接收和 YOLO 檢測結果返回
"""

import asyncio
import base64
import json
import sys
import time
from pathlib import Path
from typing import Optional, Set

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

# 支援直接執行和套件匯入兩種模式
_src_path = Path(__file__).resolve().parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from config import get_config, get_model_path
from detection.yolo_detector import YOLODetector
from detection.label_mapper import LabelMapper


class WebDetectionServer:
    """網頁 YOLO 檢測伺服器"""

    def __init__(
        self,
        model_path: str = None,
        confidence: float = 0.5,
        host: str = "0.0.0.0",
        port: int = 8000,
    ):
        self.model_path = model_path or get_model_path()
        self.confidence = confidence
        self.host = host
        self.port = port

        self.config = get_config()
        self.detector: Optional[YOLODetector] = None
        self.label_mapper = LabelMapper()

        # 連接的客戶端
        self.video_clients: Set[WebSocket] = set()
        self.result_clients: Set[WebSocket] = set()

        # 統計資訊
        self.frame_count = 0
        self.start_time = time.time()
        self.fps = 0.0

        # 建立 FastAPI 應用
        self.app = FastAPI(
            title="YOLO 網頁檢測系統",
            description="即時物件辨識網頁介面",
        )

        # CORS 設定
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # 靜態檔案
        static_dir = Path(__file__).parent / "static"
        static_dir.mkdir(parents=True, exist_ok=True)
        self.app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        # 註冊路由
        self._setup_routes()

        logger.info("網頁檢測伺服器初始化完成")

    def _setup_routes(self):
        """設定 API 路由"""

        @self.app.get("/", response_class=HTMLResponse)
        async def index():
            """主頁面"""
            html_path = Path(__file__).parent / "static" / "index.html"
            return HTMLResponse(content=html_path.read_text(encoding="utf-8"), status_code=200)

        @self.app.websocket("/ws/video")
        async def video_endpoint(websocket: WebSocket):
            """接收瀏覽器攝影機串流"""
            await self._handle_video_stream(websocket)

        @self.app.websocket("/ws/result")
        async def result_endpoint(websocket: WebSocket):
            """返回檢測結果給瀏覽器"""
            await self._handle_result_stream(websocket)

        @self.app.get("/health")
        async def health_check():
            """健康檢查"""
            return {"status": "ok", "fps": self.fps, "frame_count": self.frame_count}

    async def _handle_video_stream(self, websocket: WebSocket):
        """處理視頻串流"""
        await websocket.accept()
        self.video_clients.add(websocket)
        logger.info(f"視頻客戶端連接，當前連接數: {len(self.video_clients)}")

        try:
            while True:
                # 接收 base64 編碼的影像
                data = await websocket.receive_text()

                # 解碼 base64
                if data.startswith("data:image"):
                    # 移除 data URL 娰頭
                    header, base64_data = data.split(",", 1)
                    image_data = base64.b64decode(base64_data)
                else:
                    image_data = base64.b64decode(data)

                # 轉換為 numpy 陣列
                nparr = np.frombuffer(image_data, np.uint8)
                frame = cv2.imdecode(nparr)

                if frame is None:
                    continue

                # 執行 YOLO 檢測
                result = await self._detect_frame(frame)

                # 廣播結果給所有結果客戶端
                await self._broadcast_result(result)

        except WebSocketDisconnect:
            logger.info("視頻客戶端斷線")
        except Exception as e:
            logger.error(f"視頻串流錯誤: {e}")
        finally:
            self.video_clients.discard(websocket)
            logger.info(f"視頻客戶端斷開，當前連接數: {len(self.video_clients)}")

    async def _handle_result_stream(self, websocket: WebSocket):
        """處理結果串流"""
        await websocket.accept()
        self.result_clients.add(websocket)
        logger.info(f"結果客戶端連接，當前連接數: {len(self.result_clients)}")

        try:
            # 保持連接，等待伺服器推送結果
            while True:
                await asyncio.sleep(1)

        except WebSocketDisconnect:
            logger.info("結果客戶端斷線")
        finally:
            self.result_clients.discard(websocket)
            logger.info(f"結果客戶端斷開，當前連接數: {len(self.result_clients)}")

    async def _detect_frame(self, frame: np.ndarray) -> dict:
        """執行 YOLO 檢測"""
        if self.detector is None:
            # 延遲初始化檢測器
            prompt_classes = None
            if self.config.model.detection_classes:
                prompt_classes = [
                    c.strip() for c in self.config.model.detection_classes.split(",") if c.strip()
                ]
            self.detector = YOLODetector(
                model_path=self.model_path,
                confidence_threshold=self.confidence,
                device="auto",
                prompt_classes=prompt_classes,
            )
            logger.info(f"YOLO 模型已載入: {self.model_path}")

        # 計時
        start_time = time.time()

        # 執行檢測
        result = self.detector.detect(frame)

        # 為每個 detection 設置中文標籤
        for detection in result.detections:
            if not detection.class_name_cn:
                detection.class_name_cn = self.label_mapper.get_chinese_name_from_en(
                    detection.class_name
                )

        # 更新 FPS
        self.frame_count += 1
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            self.fps = self.frame_count / elapsed

        # 構建結果
        detections = []
        for det in result.detections:
            detections.append({
                "class_name": det.class_name,
                "class_name_cn": det.class_name_cn or det.class_name,
                "confidence": round(det.confidence, 3),
                "bbox": [int(x) for x in det.bbox] if det.bbox is not None else None,
                "mask": det.mask.tolist() if det.mask is not None else None,
            })

        return {
            "detections": detections,
            "count": len(detections),
            "fps": round(result.fps, 1),
            "timestamp": time.time(),
        }

    async def _broadcast_result(self, result: dict):
        """廣播檢測結果給所有客戶端"""
        if not self.result_clients:
            return

        message = json.dumps(result, ensure_ascii=False)

        # 複製集合避免在迭代時修改
        clients = list(self.result_clients)

        for client in clients:
            try:
                await client.send_text(message)
            except Exception as e:
                logger.warning(f"發送結果失敗: {e}")
                self.result_clients.discard(client)

    def run(self):
        """啟動伺服器"""
        import uvicorn

        logger.info("=" * 50)
        logger.info("YOLO 網頁檢測伺服器啟動")
        logger.info("=" * 50)
        logger.info(f"地址: http://{self.host}:{self.port}")
        logger.info(f"模型: {self.model_path}")
        logger.info(f"信心度門檻: {self.confidence}")
        logger.info("=" * 50)

        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
        )


def main():
    """主程式入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="YOLO 網頁檢測伺服器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="模型檔案路徑",
    )

    parser.add_argument(
        "--confidence",
        type=float,
        default=0.5,
        help="信心度門檻 (0.0 - 1.0)",
    )

    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="伺服器地址",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="伺服器端口",
    )

    args = parser.parse_args()

    server = WebDetectionServer(
        model_path=args.model,
        confidence=args.confidence,
        host=args.host,
        port=args.port,
    )

    server.run()


if __name__ == "__main__":
    main()
