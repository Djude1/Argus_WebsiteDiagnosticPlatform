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
import ipaddress
import json
import ssl
import sys
import time
from pathlib import Path
from typing import Optional, Set, Tuple
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
from detection.label_mapper import LabelMapper, EN_TO_CN_MAPPING, CN_TO_EN_MAPPING
from detection.detection_logger import DetectionLogger
from detection.stabilizer import DetectionStabilizer, filter_false_positives
from detection.feedback import FeedbackManager
from detection.yolo_detector import FrameDetectionResult


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


# ============================================
# SSL 證書生成 (自簽名)
# ============================================

def generate_self_signed_cert(cert_dir: Path) -> Tuple[Path, Path]:
    """生成自簽名 SSL 證書

    Args:
        cert_dir: 證書存放目錄

    Returns:
        (cert_file, key_file) 證書和金鑰檔案路徑
    """
    cert_file = cert_dir / "server.crt"
    key_file = cert_dir / "server.key"

    # 如果證書已存在，直接返回
    if cert_file.exists() and key_file.exists():
        logger.info(f"使用現有 SSL 證書: {cert_file}")
        return cert_file, key_file

    cert_dir.mkdir(parents=True, exist_ok=True)

    logger.info("生成自簽名 SSL 證書...")

    # 創建自簽名證書
    from cryptography import x509
    from cryptography.x509.oid import NameOID, ExtensionOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    import datetime

    # 生成私鑰
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # 建立證書主體
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "TW"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Taiwan"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Taipei"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "YOLO Detection"),
        x509.NameAttribute(NameOID.COMMON_NAME, "yollo.local"),
    ])

    # SAN (Subject Alternative Names) - 支援多種訪問方式
    san_list = [
        # DNS 名稱
        x509.DNSName("localhost"),
        x509.DNSName("*.local"),
        x509.DNSName("yollo.local"),
        # 本地迴環
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        x509.IPAddress(ipaddress.IPv4Address("0.0.0.0")),
    ]

    # 添加 Tailscale IP 範圍 (100.64.0.0/10)
    # 添加一些常見的 Tailscale IP
    try:
        for i in range(256):
            san_list.append(x509.IPAddress(ipaddress.IPv4Address(f"100.64.{i}.1")))
            san_list.append(x509.IPAddress(ipaddress.IPv4Address(f"100.65.{i}.1")))
    except Exception:
        pass  # 如果添加太多 SAN 失敗，跳過

    # 建立證書 (有效期 10 年)
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.utcnow()
    ).not_valid_after(
        datetime.datetime.utcnow() + datetime.timedelta(days=3650)
    ).add_extension(
        x509.SubjectAlternativeName(san_list),
        critical=False,
    ).sign(private_key, hashes.SHA256())

    # 寫入證書檔案
    with open(cert_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    # 寫入私鑰檔案
    with open(key_file, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))

    logger.success(f"SSL 證書已生成: {cert_file}")
    logger.info(f"私鑰已生成: {key_file}")
    logger.warning("此證書為自簽名，瀏覽器會顯示安全警告，這是正常的")

    return cert_file, key_file


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

        # 偵測結果記錄器
        self.detection_logger = DetectionLogger()

        # 偵測穩定化
        self.stabilizer = DetectionStabilizer(
            window_size=self.config.model.stabilizer_window_size,
            min_hits=self.config.model.stabilizer_min_hits,
        )

        # 用戶反饋管理器
        self.feedback_manager = FeedbackManager(
            default_threshold=self.confidence,
        )

        # 記錄信心度門檻
        self.record_confidence = self.config.model.record_confidence_threshold

        # 自訂類別檔案路徑
        self._custom_classes_path = Path(__file__).parent.parent / "data" / "custom_classes.json"

        # 連接的客戶端
        self.video_clients: Set[WebSocket] = set()
        self.result_clients: Set[WebSocket] = set()

        # 並發保護與會話管理
        self._detection_lock = asyncio.Lock()  # 防止並發偵測
        self._last_request_time = 0  # 上次請求時間（用於檢測新使用者）

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

        # 新增請求日誌與防快取中介軟體
        @self.app.middleware("http")
        async def log_requests(request: Request, call_next):
            """記錄所有 HTTP 請求，並為靜態檔案加上防快取 header"""
            start_time = time.time()

            # 記錄請求
            logger.debug(f"請求: {request.method} {request.url.path}")

            try:
                response = await call_next(request)

                # 計算處理時間
                process_time = (time.time() - start_time) * 1000

                # 靜態檔案加上防快取 header（開發階段避免瀏覽器快取舊版）
                if request.url.path.startswith("/static/"):
                    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                    response.headers["Pragma"] = "no-cache"
                    response.headers["Expires"] = "0"

                # 記錄回應
                logger.opt(colors=True).log(
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
        from typing import List as TypingList

        class DetectRequest(BaseModel):
            image: str

        class AddClassRequest(BaseModel):
            name_cn: str
            name_en: str = ""

        class RemoveClassRequest(BaseModel):
            name_en: str

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

        # ============================================
        # 類別管理 API
        # ============================================

        @self.app.get("/api/classes")
        async def get_classes():
            """取得目前所有偵測類別（含 .env 預設 + 使用者自訂）"""
            env_classes = self._get_env_classes()
            custom = self._load_custom_classes()
            custom_names = [c["name_en"] for c in custom]

            # 合併列表，標記來源
            all_classes = []
            for name in env_classes:
                cn = self.label_mapper.get_chinese_name_from_en(name)
                all_classes.append({
                    "name_en": name,
                    "name_cn": cn,
                    "source": "default",
                })
            for c in custom:
                # 避免重複
                if c["name_en"] not in env_classes:
                    all_classes.append({
                        "name_en": c["name_en"],
                        "name_cn": c.get("name_cn", ""),
                        "source": "custom",
                    })

            return {
                "classes": all_classes,
                "total": len(all_classes),
                "default_count": len(env_classes),
                "custom_count": len(custom),
            }

        @self.app.post("/api/classes")
        async def add_class(request: AddClassRequest):
            """註冊新的偵測類別"""
            name_cn = request.name_cn.strip()
            name_en = request.name_en.strip().lower()

            if not name_cn:
                return {"error": "中文名稱不可為空"}

            # 自動查找英文名稱（若使用者未提供）
            if not name_en:
                name_en = self.label_mapper.get_english_name_from_cn(name_cn)
                if name_en == name_cn:
                    # 找不到對應，使用中文名稱作為模型輸入（CLIP 可處理）
                    name_en = name_cn

            # 載入現有自訂類別
            custom = self._load_custom_classes()
            existing_names = [c["name_en"] for c in custom]

            # 檢查是否已存在
            env_classes = self._get_env_classes()
            if name_en in env_classes:
                return {"error": f"'{name_en}' 已在預設類別中", "exists": True}
            if name_en in existing_names:
                return {"error": f"'{name_en}' 已在自訂類別中", "exists": True}

            # 新增
            custom.append({
                "name_en": name_en,
                "name_cn": name_cn,
                "added_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
            self._save_custom_classes(custom)

            # 動態更新偵測器類別
            self._reload_detector_classes()

            # 同步更新 label_mapper 的映射表
            if name_cn:
                EN_TO_CN_MAPPING[name_en] = name_cn
                CN_TO_EN_MAPPING[name_cn] = name_en

            logger.info(f"新增自訂偵測類別: {name_en} ({name_cn})")

            return {
                "success": True,
                "class": {"name_en": name_en, "name_cn": name_cn},
                "message": f"已新增 '{name_cn or name_en}'，偵測器已更新",
            }

        @self.app.delete("/api/classes")
        async def remove_class(request: RemoveClassRequest):
            """移除自訂偵測類別"""
            name_en = request.name_en.strip().lower()

            custom = self._load_custom_classes()
            original_len = len(custom)
            custom = [c for c in custom if c["name_en"] != name_en]

            if len(custom) == original_len:
                return {"error": f"找不到自訂類別 '{name_en}'"}

            self._save_custom_classes(custom)
            self._reload_detector_classes()

            logger.info(f"移除自訂偵測類別: {name_en}")

            return {
                "success": True,
                "message": f"已移除 '{name_en}'，偵測器已更新",
            }

        # ============================================
        # 反饋 API
        # ============================================

        class FeedbackRequest(BaseModel):
            type: str  # "confirm" | "correct" | "false_positive"
            class_name: str
            confidence: float = 0.0
            bbox: Optional[TypingList[int]] = None
            correct_class: Optional[str] = None
            image: Optional[str] = None  # base64 截圖

        @self.app.post("/api/feedback")
        async def submit_feedback(request: FeedbackRequest):
            """提交偵測反饋"""
            if request.type not in ("confirm", "correct", "false_positive"):
                return {"error": "無效的反饋類型"}

            result = self.feedback_manager.record_feedback(
                feedback_type=request.type,
                class_name=request.class_name,
                confidence=request.confidence,
                bbox=request.bbox,
                correct_class=request.correct_class,
                image_base64=request.image,
            )

            # 如果是 correct 且正確類別是新的，同時新增類別
            if request.type == "correct" and request.correct_class:
                correct_name = request.correct_class.strip()

                # 自動偵測中文輸入，轉換為英文名稱
                has_cjk = any('\u4e00' <= ch <= '\u9fff' for ch in correct_name)
                if has_cjk:
                    en_name = self.label_mapper.get_english_name_from_cn(correct_name)
                    logger.info(f"中文類別名稱轉換: {correct_name} → {en_name}")
                    correct_name = en_name

                correct_name = correct_name.lower()

                env_classes = self._get_env_classes()
                custom = self._load_custom_classes()
                existing = env_classes + [c["name_en"] for c in custom]
                if correct_name not in existing:
                    # 自動查找中文名稱
                    name_cn = self.label_mapper.get_chinese_name_from_en(correct_name)
                    if name_cn == correct_name:
                        name_cn = ""  # 找不到對應就留空
                    custom.append({
                        "name_en": correct_name,
                        "name_cn": name_cn,
                        "added_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    })
                    self._save_custom_classes(custom)
                    self._reload_detector_classes()

            # 每 20 筆反饋重新計算門檻
            stats = self.feedback_manager.get_stats()
            if stats["total"] > 0 and stats["total"] % 20 == 0:
                self.feedback_manager.recalculate_thresholds()

            return result

        @self.app.get("/api/feedback/stats")
        async def get_feedback_stats():
            """取得反饋統計"""
            return self.feedback_manager.get_stats()

        # ============================================
        # 偵測記錄 API
        # ============================================

        @self.app.get("/api/logs/stats")
        async def get_log_stats():
            """取得今日偵測統計"""
            return self.detection_logger.get_today_stats()

        @self.app.get("/api/logs/history")
        async def get_log_history():
            """列出所有歷史記錄檔"""
            return {"files": self.detection_logger.get_history_files()}

    # ============================================
    # 自訂類別管理
    # ============================================

    def _get_env_classes(self) -> list:
        """從 .env 取得預設偵測類別"""
        classes_str = self.config.model.detection_classes
        if not classes_str:
            return []
        return [c.strip() for c in classes_str.split(",") if c.strip()]

    def _load_custom_classes(self) -> list:
        """讀取自訂類別檔案"""
        try:
            if self._custom_classes_path.exists():
                with open(self._custom_classes_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("classes", [])
        except Exception as e:
            logger.error(f"讀取自訂類別失敗: {e}")
        return []

    def _save_custom_classes(self, classes: list):
        """儲存自訂類別檔案"""
        try:
            self._custom_classes_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._custom_classes_path, "w", encoding="utf-8") as f:
                json.dump({
                    "description": "使用者自行註冊的偵測類別（透過網頁介面新增）",
                    "classes": classes,
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"儲存自訂類別失敗: {e}")

    def _get_all_classes(self) -> list:
        """取得所有偵測類別（.env 預設 + 使用者自訂）"""
        env_classes = self._get_env_classes()
        custom = self._load_custom_classes()
        custom_names = [c["name_en"] for c in custom]
        # 合併，避免重複
        all_classes = list(env_classes)
        for name in custom_names:
            if name not in all_classes:
                all_classes.append(name)
        return all_classes

    def _reload_detector_classes(self):
        """重新載入偵測器的偵測類別"""
        if self.detector is None:
            return
        all_classes = self._get_all_classes()
        if all_classes:
            self.detector.update_classes(all_classes)
            logger.info(f"偵測器類別已更新（共 {len(all_classes)} 個）")

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
        """執行 YOLO 檢測（帶並發保護與會話管理）"""
        # 檢查是否為新使用者（超過 5 秒無請求 → 重置 stabilizer）
        current_time = time.time()
        if current_time - self._last_request_time > 5 and self._last_request_time > 0:
            logger.info("檢測到新使用者連線，重置偵測穩定化狀態")
            self.stabilizer.reset()
        self._last_request_time = current_time

        # 使用鎖防止並發偵測（GPU 資源有限，序列處理更穩定）
        async with self._detection_lock:
            return await self._do_detect(frame)

    async def _do_detect(self, frame: np.ndarray) -> dict:
        """實際執行 YOLO 檢測"""
        detect_start = time.time()

        if self.detector is None:
            logger.info("初始化 YOLO 檢測器...")
            # 合併 .env 預設類別 + 使用者自訂類別
            all_classes = self._get_all_classes()
            prompt_classes = all_classes if all_classes else None
            logger.info(f"偵測類別（共 {len(all_classes)} 個）: {prompt_classes or '使用模型內建類別'}")

            self.detector = YOLODetector(
                model_path=self.model_path,
                confidence_threshold=self.confidence,
                iou_threshold=self.config.model.iou_threshold,
                device=get_device(),
                prompt_classes=prompt_classes,
                use_fp16=not self.config.model.force_cpu,  # CPU 模式不使用 FP16
                imgsz=self.config.model.detection_imgsz,  # 新增
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
            return {
                "detections": [],
                "count": 0,
                "fps": 0.0,
                "timestamp": time.time(),
            }

        # === 新增：假正例過濾 ===
        filtered_detections = filter_false_positives(result.detections, frame.shape)

        # === 新增：時序穩定化 ===
        stable_detections = self.stabilizer.update(filtered_detections)

        # 為每個 detection 設置中文標籤（改用 stable_detections）
        for detection in stable_detections:
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

        # 構建結果（改用 stable_detections）
        detections = []
        for det in stable_detections:
            detections.append({
                "class_name": det.class_name,
                "class_name_cn": det.class_name_cn or det.class_name,
                "confidence": round(det.confidence, 3),
                "bbox": list(det.bbox.to_tuple()) if det.bbox is not None else None,
            })

        # === 新增：雙路輸出 — 記錄門檻 ===
        if detections:
            high_conf_detections = [
                d for d in detections if d["confidence"] >= self.record_confidence
            ]
            if high_conf_detections:
                self.detection_logger.log(
                    detections=high_conf_detections,
                    fps=result.fps,
                    frame_count=self.frame_count,
                )

        # 建立穩定結果的 FrameDetectionResult 給繪製用
        # （FrameDetectionResult 已在頂部 imports 匯入）
        stable_result = FrameDetectionResult(
            detections=stable_detections,
            inference_time_ms=result.inference_time_ms,
            fps=result.fps,
            frame_shape=result.frame_shape,
        )
        annotated_frame = self.detector.draw_detections(frame, stable_result)

        # 將處理後的畫面編碼為 base64
        _, buffer = cv2.imencode('.jpg', annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        annotated_base64 = base64.b64encode(buffer).decode('utf-8')

        return {
            "detections": detections,
            "count": len(detections),
            "fps": round(result.fps, 1),
            "timestamp": time.time(),
            "annotated_frame": annotated_base64,
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

    def run(self, ssl_certfile: Optional[Path] = None, ssl_keyfile: Optional[Path] = None):
        """啟動伺服器

        Args:
            ssl_certfile: SSL 證書檔案路徑 (如提供則啟用 HTTPS)
            ssl_keyfile: SSL 私鑰檔案路徑
        """
        import uvicorn

        is_https = ssl_certfile is not None and ssl_keyfile is not None
        protocol = "https" if is_https else "http"

        logger.info("=" * 60)
        logger.info("YOLO 網頁檢測伺服器啟動")
        logger.info("=" * 60)
        logger.info(f"監聽地址: {protocol}://{self.host}:{self.port}")
        if is_https:
            logger.info(f"SSL 證書: {ssl_certfile}")
            logger.info(f"SSL 私鑰: {ssl_keyfile}")
        logger.info(f"模型路徑: {self.model_path}")
        logger.info(f"信心度門檻: {self.confidence}")
        logger.info(f"運算裝置: {get_device()}")
        logger.info(f"日誌檔案: {log_file}")
        logger.info("=" * 60)
        logger.info("可用端點:")
        logger.info(f"  GET  /health              - 健康檢查")
        logger.info(f"  GET  /                    - 主頁面")
        logger.info(f"  POST /api/detect/v2      - 物件檢測 API (推薦)")
        logger.info(f"  WS   /ws/video            - 影像串流 ({'WSS' if is_https else 'WS'})")
        logger.info(f"  WS   /ws/result           - 結果串流 ({'WSS' if is_https else 'WS'})")
        logger.info("=" * 60)

        if is_https:
            logger.info("HTTPS 模式已啟用")
            logger.info("適用於 Cloudflare Tunnel、Dev Tunnel 等公網服務")
            logger.warning("首次訪問時瀏覽器會顯示安全警告 (自簽名證書)")
            logger.warning("這是正常的，請點擊「繼續訪問」或「接受風險」")
        else:
            logger.info("HTTP 模式")
            logger.warning("如需 Cloudflare Tunnel/Dev Tunnel，請使用 --ssl 參數啟用 HTTPS")
        logger.info("=" * 60)
        logger.info("伺服器啟動中... 按 CTRL+C 停止")
        logger.info("")

        # SSL 配置
        ssl_config = {}
        if is_https:
            ssl_config = {
                "ssl_keyfile": str(ssl_keyfile),
                "ssl_certfile": str(ssl_certfile),
            }

        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            log_level="warning",
            **ssl_config,
        )


def main():
    """主程式入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="YOLO 網頁檢測伺服器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python -m src.web_server                    # HTTP 模式 (localhost:8080)
  python -m src.web_server --ssl              # HTTPS 模式 (自動生成證書)
  python -m src.web_server --ssl --port 8443  # HTTPS 模式 (自訂端口)
  python -m src.web_server --host 0.0.0.0     # 允許外部訪問

HTTPS 模式說明:
  --ssl 參數會自動生成自簽名證書，適用於:
  - Cloudflare Tunnel
  - VS Code Dev Tunnel
  - 其他公網隧道服務

  證書存儲位置: certs/server.crt, certs/server.key
        """,
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
        default=None,  # 改為 None（原為 0.5），從 config 讀取
        help="信心度門檻 (0.0 - 1.0)，預設使用 .env 設定",
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
        help="伺服器端口 (HTTP: 8080, HTTPS: 建議 8443)",
    )

    parser.add_argument(
        "--ssl",
        action="store_true",
        help="啟用 HTTPS 模式 (自動生成自簽名證書)",
    )

    parser.add_argument(
        "--cert-file",
        type=str,
        default=None,
        help="SSL 證書檔案路徑 (與 --ssl 同時使用時覆蓋自動生成)",
    )

    parser.add_argument(
        "--key-file",
        type=str,
        default=None,
        help="SSL 私鑰檔案路徑 (與 --ssl 同時使用時覆蓋自動生成)",
    )

    args = parser.parse_args()

    confidence = args.confidence if args.confidence is not None else get_config().model.confidence_threshold
    server = WebDetectionServer(
        model_path=args.model,
        confidence=confidence,
        host=args.host,
        port=args.port,
    )

    # 處理 SSL/HTTPS
    ssl_certfile = None
    ssl_keyfile = None

    if args.ssl:
        cert_dir = Path(__file__).parent.parent / "certs"

        if args.cert_file and args.key_file:
            # 使用指定的證書
            ssl_certfile = Path(args.cert_file)
            ssl_keyfile = Path(args.key_file)
            logger.info(f"使用指定的 SSL 證書: {ssl_certfile}")
        else:
            # 自動生成證書
            try:
                ssl_certfile, ssl_keyfile = generate_self_signed_cert(cert_dir)
            except ImportError:
                logger.error("生成 SSL 證書需要 'cryptography' 套件")
                logger.info("請安裝: pip install cryptography")
                logger.info("或使用 --cert-file 和 --key-file 指定現有證書")
                sys.exit(1)
            except Exception as e:
                logger.error(f"生成 SSL 證書失敗: {e}")
                sys.exit(1)

    server.run(ssl_certfile=ssl_certfile, ssl_keyfile=ssl_keyfile)


if __name__ == "__main__":
    main()
