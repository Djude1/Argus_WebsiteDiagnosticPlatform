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
from datetime import datetime

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

# 支援直接執行和套件匯入兩種模式
_src_path = Path(__file__).resolve().parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from config import get_config, get_model_path, get_device
from detection.yolo_detector import YOLODetector
from detection.label_mapper import LabelMapper


# ============================================
# 日誌設定 - 終端 + 檔案
# ============================================

# 移除預設處理器
logger.remove()

# 終端輸出 (彩色格式)
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO",
)

# 檔案輸出 - 建立 logs 目錄
log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

log_file = log_dir / f"web_server_{datetime.now().strftime('%Y%m%d')}.log"
logger.add(
    log_file,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
    level="DEBUG",
    rotation="10 MB",
    retention="7 days",
)

logger.info("=" * 60)
logger.info("YOLO 網頁偵測伺服器啟動中...")
logger.info(f"日誌檔案: {log_file}")
logger.info("=" * 60)


class WebDetectionServer:
    """網頁 YOLO 檢測伺服器"""

    def __init__(
        self,
        model_path: str = None,
        confidence: float = 0.5,
        host: str = "0.0.0.0",
        port: int = 8080,
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

        # 新增請求日誌中介軟體
        @self.app.middleware("http")
        async def log_requests(request: Request, call_next):
            """記錄所有 HTTP 請求"""
            start_time = time.time()

            # 記錄請求
            logger.debug(f"請求: {request.method} {request.url.path}")

            try:
                response = await call_next(request)

                # 計算處理時間
                process_time = (time.time() - start_time) * 1000

                # 記錄回應
                status_color = "green" if response.status_code < 400 else "red"
                logger.opt(colors=True).bind(status_color=status_color).log(
                    "INFO",
                    f"回應: {response.status_code} | {process_time:.0f}ms | {request.method} {request.url.path}"
                )

                return response
            except Exception as e:
                process_time = (time.time() - start_time) * 1000
                logger.error(f"請求失敗: {request.method} {request.url.path} | {process_time:.0f}ms | 錯誤: {e}")
                raise

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

        @self.app.post("/api/detect")
        async def detect_endpoint(request: dict):
            """HTTP 物件檢測 API (適用於不支援 WebSocket 的環境)"""
            try:
                # 取得 base64 編碼的影像
                data = request.get("image", "")

                # 解碼 base64
                if data.startswith("data:image"):
                    header, base64_data = data.split(",", 1)
                    image_data = base64.b64decode(base64_data)
                else:
                    image_data = base64.b64decode(data)

                # 轉換為 numpy 陣列
                nparr = np.frombuffer(image_data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if frame is None:
                    return {"error": "無法解析影像"}, 400

                # 執行 YOLO 檢測
                result = await self._detect_frame(frame)

                return result

            except Exception as e:
                logger.error(f"HTTP 檢測錯誤: {e}")
                return {"error": str(e)}, 500

        from pydantic import BaseModel
        from fastapi import Body

        class DetectRequest(BaseModel):
            image: str

        @self.app.post("/api/detect/v2")
        async def detect_endpoint_v2(request: DetectRequest):
            """HTTP 物件檢測 API v2 (使用 Pydantic)"""
            request_start = time.time()
            logger.info("收到檢測請求 (v2)")

            try:
                # 取得 base64 編碼的影像
                data = request.image

                logger.debug(f"收到影像資料，長度: {len(data)} 字元")

                # 解碼 base64
                if data.startswith("data:image"):
                    header, base64_data = data.split(",", 1)
                    image_data = base64.b64decode(base64_data)
                    logger.debug(f"Data URL 格式，編碼方式: {header}")
                else:
                    image_data = base64.b64decode(data)
                    logger.debug("純 base64 格式")

                logger.debug(f"解碼後影像大小: {len(image_data)} bytes")

                # 轉換為 numpy 陣列
                nparr = np.frombuffer(image_data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if frame is None:
                    logger.error("影像解析失敗 - cv2.imdecode 返回 None")
                    return {"error": "無法解析影像"}

                logger.debug(f"影像解析成功: {frame.shape}")

                # 執行 YOLO 檢測
                result = await self._detect_frame(frame)

                process_time = (time.time() - request_start) * 1000
                logger.info(f"檢測完成: {result.get('count', 0)} 個物件 | {process_time:.0f}ms")

                return result

            except ValueError as e:
                logger.error(f"數據驗證錯誤: {e}")
                return {"error": f"數據格式錯誤: {str(e)}"}
            except base64.binascii.Error as e:
                logger.error(f"Base64 解碼錯誤: {e}")
                return {"error": "影像資料格式錯誤 (無效的 base64)"}
            except Exception as e:
                process_time = (time.time() - request_start) * 1000
                logger.error(f"HTTP 檢測錯誤 ({process_time:.0f}ms): {e}")
                import traceback
                logger.error(traceback.format_exc())
                return {"error": str(e)}

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
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

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
        detect_start = time.time()

        if self.detector is None:
            logger.info("初始化 YOLO 檢測器...")
            # 延遲初始化檢測器
            prompt_classes = None
            if self.config.model.detection_classes:
                prompt_classes = [
                    c.strip() for c in self.config.model.detection_classes.split(",") if c.strip()
                ]
            logger.info(f"偵測類別: {prompt_classes or '使用模型內建類別'}")

            self.detector = YOLODetector(
                model_path=self.model_path,
                confidence_threshold=self.confidence,
                device=get_device(),
                prompt_classes=prompt_classes,
                use_fp16=not self.config.model.force_cpu,  # CPU 模式不使用 FP16
            )
            logger.success(f"YOLO 模型已載入: {self.model_path}")
            logger.info(f"運算裝置: {get_device()}")

        logger.debug(f"開始偵測，影像尺寸: {frame.shape}")

        # 計時
        start_time = time.time()

        # 執行檢測
        try:
            result = self.detector.detect(frame)
            detect_time = (time.time() - start_time) * 1000
            logger.debug(f"偵測完成: {result.count} 個物件 | {detect_time:.0f}ms")
        except Exception as e:
            logger.error(f"偵測過程發生錯誤: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # 返回空結果
            return {
                "detections": [],
                "count": 0,
                "fps": 0.0,
                "timestamp": time.time(),
            }

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

        # 每 30 幀記錄一次統計
        if self.frame_count % 30 == 1:
            logger.info(f"統計: 已處理 {self.frame_count} 幀 | FPS: {self.fps:.1f}")

        # 構建結果
        detections = []
        for det in result.detections:
            detections.append({
                "class_name": det.class_name,
                "class_name_cn": det.class_name_cn or det.class_name,
                "confidence": round(det.confidence, 3),
                "bbox": list(det.bbox.to_tuple()) if det.bbox is not None else None,
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

        logger.info("=" * 60)
        logger.info("YOLO 網頁檢測伺服器啟動")
        logger.info("=" * 60)
        logger.info(f"監聽地址: http://{self.host}:{self.port}")
        logger.info(f"模型路徑: {self.model_path}")
        logger.info(f"信心度門檻: {self.confidence}")
        logger.info(f"運算裝置: {get_device()}")
        logger.info(f"日誌檔案: {log_file}")
        logger.info("=" * 60)
        logger.info("可用端點:")
        logger.info("  GET  /health              - 健康檢查")
        logger.info("  GET  /                    - 主頁面")
        logger.info("  POST /api/detect/v2      - 物件檢測 API (推薦)")
        logger.info("  WS   /ws/video            - 影像串流")
        logger.info("  WS   /ws/result           - 結果串流")
        logger.info("=" * 60)
        logger.info("伺服器啟動中... 按 CTRL+C 停止")
        logger.info("")

        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            log_level="warning",  # 降低 uvicorn 自有日誌，使用我們的自訂日誌
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
        default=8080,
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
