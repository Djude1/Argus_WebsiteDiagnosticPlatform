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
from core import DetectionEngine, DataManager, DetectionConfig
from detection.label_mapper import LabelMapper, EN_TO_CN_MAPPING, CN_TO_EN_MAPPING
from detection.detection_logger import DetectionLogger
from detection.yolo_detector import FrameDetectionResult, BoundingBox


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
    from cryptography.x509.oid import NameOID
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
        self.label_mapper = LabelMapper()

        # 自訂類別檔案路徑（需要在 _load_and_apply_aliases 之前）
        self._custom_classes_path = Path(__file__).parent.parent / "data" / "custom_classes.json"

        # 載入自訂別名
        self._load_and_apply_aliases()

        # 偵測結果記錄器
        self.detection_logger = DetectionLogger()

        # 記錄信心度門檻
        self.record_confidence = self.config.model.record_confidence_threshold

        # 初始化 DetectionEngine 和 DataManager
        detection_config = DetectionConfig(
            model_path=self.model_path,
            device=get_device(),
            confidence=self.confidence,
            max_active_classes=self.config.model.max_active_classes,
            custom_classes_path=str(self._custom_classes_path),
        )
        self.engine = DetectionEngine(detection_config)
        self.data_manager = DataManager(Path(__file__).parent.parent / "data")

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

        class ToggleClassRequest(BaseModel):
            name_en: str
            active: bool

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
            """取得目前所有偵測類別（含 .env 預設 + 使用者自訂，含啟用狀態）"""
            env_classes = self._get_env_classes()
            data = self._load_custom_classes_data()
            custom = data.get("classes", [])
            deactivated = data.get("deactivated_defaults", [])
            last_detected = data.get("last_detected", {})
            max_active = self.config.model.max_active_classes

            # 合併列表，標記來源和狀態
            all_classes = []
            active_count = 0
            for name in env_classes:
                cn = self.label_mapper.get_chinese_name_from_en(name)
                is_active = name not in deactivated
                if is_active:
                    active_count += 1
                all_classes.append({
                    "name_en": name,
                    "name_cn": cn,
                    "source": "default",
                    "active": is_active,
                    "last_detected": last_detected.get(name),
                })
            for c in custom:
                if c["name_en"] not in env_classes:
                    is_active = c.get("active", True)
                    if is_active:
                        active_count += 1
                    all_classes.append({
                        "name_en": c["name_en"],
                        "name_cn": c.get("name_cn", ""),
                        "source": "custom",
                        "active": is_active,
                        "last_detected": last_detected.get(c["name_en"]),
                    })

            return {
                "classes": all_classes,
                "total": len(all_classes),
                "active_count": active_count,
                "max_active": max_active,
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
                # 先嘗試中文轉英文
                name_en = self.label_mapper.get_english_name_from_cn(name_cn)
                if name_en == name_cn:
                    name_en = name_cn

            # 檢查是否為已存在類別的別名（防止重複）
            if self.label_mapper.is_alias(name_en):
                canonical = self.label_mapper.resolve_alias(name_en)
                canonical_cn = self.label_mapper.get_chinese_name_from_en(canonical)
                return {
                    "error": "is_alias",
                    "message": f"「{name_cn or name_en}」是「{canonical_cn}」的變體，建議合併",
                    "alias": name_en,
                    "canonical": canonical,
                    "canonical_cn": canonical_cn,
                }

            # 載入完整資料
            data = self._load_custom_classes_data()
            custom = data.get("classes", [])
            existing_names = [c["name_en"] for c in custom]

            # 檢查是否已存在（可能是已停用的，重新啟用即可）
            env_classes = self._get_env_classes()
            deactivated = data.get("deactivated_defaults", [])

            if name_en in env_classes:
                # 如果是已停用的預設類別，重新啟用
                if name_en in deactivated:
                    max_active = self.config.model.max_active_classes
                    active_count = self._get_active_count()
                    if active_count >= max_active:
                        lru = self._get_lru_suggestion()
                        return {
                            "error": "slots_full",
                            "message": f"已達啟用上限（{active_count}/{max_active}），請先停用一個類別",
                            "active_count": active_count,
                            "max_active": max_active,
                            "lru_suggestion": lru,
                        }
                    deactivated.remove(name_en)
                    data["deactivated_defaults"] = deactivated
                    self._save_custom_classes_data(data)
                    self._reload_detector_classes()
                    cn = self.label_mapper.get_chinese_name_from_en(name_en)
                    return {
                        "success": True,
                        "class": {"name_en": name_en, "name_cn": cn},
                        "message": f"已重新啟用 '{cn or name_en}'",
                    }
                return {"error": f"'{name_en}' 已在預設類別中", "exists": True}

            if name_en in existing_names:
                # 如果是已停用的自訂類別，重新啟用
                target = next((c for c in custom if c["name_en"] == name_en), None)
                if target and not target.get("active", True):
                    max_active = self.config.model.max_active_classes
                    active_count = self._get_active_count()
                    if active_count >= max_active:
                        lru = self._get_lru_suggestion()
                        return {
                            "error": "slots_full",
                            "message": f"已達啟用上限（{active_count}/{max_active}），請先停用一個類別",
                            "active_count": active_count,
                            "max_active": max_active,
                            "lru_suggestion": lru,
                        }
                    target["active"] = True
                    self._save_custom_classes_data(data)
                    self._reload_detector_classes()
                    return {
                        "success": True,
                        "class": {"name_en": name_en, "name_cn": target.get("name_cn", "")},
                        "message": f"已重新啟用 '{target.get('name_cn', name_en)}'",
                    }
                return {"error": f"'{name_en}' 已在自訂類別中", "exists": True}

            # 檢查槽位上限
            max_active = self.config.model.max_active_classes
            active_count = self._get_active_count()
            if active_count >= max_active:
                lru = self._get_lru_suggestion()
                return {
                    "error": "slots_full",
                    "message": f"已達啟用上限（{active_count}/{max_active}），請先停用一個類別再新增",
                    "active_count": active_count,
                    "max_active": max_active,
                    "lru_suggestion": lru,
                }

            # 新增
            custom.append({
                "name_en": name_en,
                "name_cn": name_cn,
                "active": True,
                "added_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
            data["classes"] = custom
            self._save_custom_classes_data(data)

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
                "active_count": active_count + 1,
                "max_active": max_active,
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

        @self.app.put("/api/classes/toggle")
        async def toggle_class(request: ToggleClassRequest):
            """啟用或停用偵測類別"""
            name_en = request.name_en.strip().lower()
            want_active = request.active

            env_classes = self._get_env_classes()
            data = self._load_custom_classes_data()
            deactivated = data.get("deactivated_defaults", [])
            custom = data.get("classes", [])

            # 啟用時檢查槽位上限
            if want_active:
                max_active = self.config.model.max_active_classes
                active_count = self._get_active_count()
                if active_count >= max_active:
                    lru = self._get_lru_suggestion()
                    return {
                        "error": "slots_full",
                        "message": f"已達啟用上限（{active_count}/{max_active}），請先停用一個類別",
                        "active_count": active_count,
                        "max_active": max_active,
                        "lru_suggestion": lru,
                    }

            found = False

            # 處理預設類別
            if name_en in env_classes:
                found = True
                if want_active and name_en in deactivated:
                    deactivated.remove(name_en)
                elif not want_active and name_en not in deactivated:
                    deactivated.append(name_en)
                data["deactivated_defaults"] = deactivated

            # 處理自訂類別
            for c in custom:
                if c["name_en"] == name_en:
                    found = True
                    c["active"] = want_active
                    break

            if not found:
                return {"error": f"找不到類別 '{name_en}'"}

            self._save_custom_classes_data(data)
            self._reload_detector_classes()

            status = "啟用" if want_active else "停用"
            cn = self.label_mapper.get_chinese_name_from_en(name_en)
            logger.info(f"類別 {status}: {name_en} ({cn})")

            return {
                "success": True,
                "message": f"已{status} '{cn or name_en}'",
                "active_count": self._get_active_count(),
                "max_active": self.config.model.max_active_classes,
            }

        # ============================================
        # 別名管理 API
        # ============================================

        @self.app.get("/api/aliases")
        async def get_aliases():
            """取得所有別名映射"""
            aliases = self.label_mapper.get_all_aliases()
            # 按正規名稱分組
            grouped = {}
            for alias, canonical in aliases.items():
                if canonical not in grouped:
                    cn = self.label_mapper.get_chinese_name_from_en(canonical)
                    grouped[canonical] = {"name_en": canonical, "name_cn": cn, "aliases": []}
                alias_cn = self.label_mapper.get_chinese_name_from_en(alias)
                grouped[canonical]["aliases"].append({"name_en": alias, "name_cn": alias_cn})
            return {
                "groups": list(grouped.values()),
                "total": len(aliases),
            }

        class AliasRequest(BaseModel):
            alias: str
            canonical: str

        @self.app.post("/api/aliases")
        async def add_alias(request: AliasRequest):
            """新增別名映射"""
            alias = request.alias.strip().lower()
            canonical = request.canonical.strip().lower()

            if not alias or not canonical:
                return {"error": "別名和正規名稱不可為空"}
            if alias == canonical:
                return {"error": "別名不可與正規名稱相同"}

            # 新增別名
            self.label_mapper.add_alias(alias, canonical)

            # 持久化到 custom_classes.json
            data = self._load_custom_classes_data()
            custom_aliases = data.get("aliases", {})
            custom_aliases[alias] = canonical
            data["aliases"] = custom_aliases
            self._save_custom_classes_data(data)

            alias_cn = self.label_mapper.get_chinese_name_from_en(alias)
            canonical_cn = self.label_mapper.get_chinese_name_from_en(canonical)
            logger.info(f"新增別名: {alias}({alias_cn}) → {canonical}({canonical_cn})")

            return {
                "success": True,
                "message": f"已將「{alias_cn or alias}」設為「{canonical_cn or canonical}」的別名",
            }

        @self.app.delete("/api/aliases")
        async def remove_alias(request: AliasRequest):
            """移除別名映射"""
            alias = request.alias.strip().lower()
            self.label_mapper.remove_alias(alias)

            # 持久化
            data = self._load_custom_classes_data()
            custom_aliases = data.get("aliases", {})
            custom_aliases.pop(alias, None)
            data["aliases"] = custom_aliases
            self._save_custom_classes_data(data)

            return {"success": True, "message": f"已移除別名 '{alias}'"}

        @self.app.get("/api/aliases/check")
        async def check_alias(name: str):
            """檢查名稱是否為現有類別的別名或相似物品"""
            name_lower = name.strip().lower()

            # 檢查是否直接是別名
            if self.label_mapper.is_alias(name_lower):
                canonical = self.label_mapper.resolve_alias(name_lower)
                canonical_cn = self.label_mapper.get_chinese_name_from_en(canonical)
                return {
                    "is_alias": True,
                    "canonical": canonical,
                    "canonical_cn": canonical_cn,
                    "message": f"「{name}」是「{canonical_cn or canonical}」的變體",
                }

            return {"is_alias": False}

        # ============================================
        # 變體管理 API（CLIP 提示擴展）
        # ============================================

        class VariantRequest(BaseModel):
            class_name: str
            variants: TypingList[str]

        @self.app.get("/api/variants")
        async def get_variants():
            """取得所有類別的變體描述"""
            data = self._load_custom_classes_data()
            variants = data.get("variants", {})
            # 附加中文名稱
            result = []
            for class_name, var_list in variants.items():
                cn = self.label_mapper.get_chinese_name_from_en(class_name)
                result.append({
                    "name_en": class_name,
                    "name_cn": cn,
                    "variants": var_list,
                })
            return {"classes": result, "total": len(result)}

        @self.app.put("/api/variants")
        async def update_variants(request: VariantRequest):
            """更新類別的變體描述（擴展 CLIP 提示）"""
            class_name = request.class_name.strip().lower()
            new_variants = [v.strip() for v in request.variants if v.strip()]

            # 儲存到 custom_classes.json
            data = self._load_custom_classes_data()
            variants = data.get("variants", {})
            if new_variants:
                variants[class_name] = new_variants
            else:
                variants.pop(class_name, None)
            data["variants"] = variants
            self._save_custom_classes_data(data)

            # 套用到偵測器並重新生成 CLIP 嵌入
            if self.engine.detector:
                self.engine.detector.update_variants(class_name, new_variants)

            cn = self.label_mapper.get_chinese_name_from_en(class_name)
            count = len(new_variants)
            logger.info(f"更新類別變體: {class_name}({cn}) — {count} 個變體")

            return {
                "success": True,
                "message": f"已更新「{cn or class_name}」的變體描述（{count} 個），CLIP 嵌入已重新生成",
                "variants": new_variants,
            }

        @self.app.post("/api/variants/add")
        async def add_variant(request: VariantRequest):
            """為類別新增變體描述"""
            class_name = request.class_name.strip().lower()
            new_variants = [v.strip() for v in request.variants if v.strip()]

            if not new_variants:
                return {"error": "請提供至少一個變體描述"}

            data = self._load_custom_classes_data()
            variants = data.get("variants", {})
            existing = variants.get(class_name, [])
            # 合併去重
            for v in new_variants:
                if v not in existing:
                    existing.append(v)
            variants[class_name] = existing
            data["variants"] = variants
            self._save_custom_classes_data(data)

            # 套用到偵測器
            if self.engine.detector:
                self.engine.detector.update_variants(class_name, existing)

            cn = self.label_mapper.get_chinese_name_from_en(class_name)
            logger.info(f"新增變體: {class_name}({cn}) += {new_variants}")

            return {
                "success": True,
                "message": f"已為「{cn or class_name}」新增 {len(new_variants)} 個變體，CLIP 嵌入已更新",
                "variants": existing,
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

            # 建立偵測結果物件用於 DataManager
            class MockDetection:
                def __init__(self, class_name, confidence, bbox):
                    self.class_name = class_name
                    self.confidence = confidence
                    self.bbox = bbox
                    self.class_name_cn = ""

            # 解碼圖片（如果有的話）
            frame = None
            if request.image:
                try:
                    if request.image.startswith("data:image"):
                        _, base64_data = request.image.split(",", 1)
                        image_data = base64.b64decode(base64_data)
                    else:
                        image_data = base64.b64decode(request.image)
                    nparr = np.frombuffer(image_data, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                except Exception as e:
                    logger.warning(f"無法解碼回饋圖片: {e}")

            # 建立 MockDetection 物件
            if request.bbox and len(request.bbox) == 4:
                mock_bbox = BoundingBox(x1=request.bbox[0], y1=request.bbox[1], x2=request.bbox[2], y2=request.bbox[3])
            else:
                logger.warning(f"bbox 格式無效（長度={len(request.bbox) if request.bbox else 0}），使用全零 bbox")
                mock_bbox = BoundingBox(x1=0, y1=0, x2=0, y2=0)
            detection = MockDetection(
                class_name=request.class_name,
                confidence=request.confidence,
                bbox=mock_bbox,
            )

            # 使用 DataManager 記錄
            result = self.data_manager.record(
                detection=detection,
                frame=frame if frame is not None else np.zeros((1, 1, 3), dtype=np.uint8),
                source="web",
                feedback_type=request.type,
                correct_class=request.correct_class,
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

                # 檢查是否為已有類別的別名，自動歸併
                if self.label_mapper.is_alias(correct_name):
                    canonical = self.label_mapper.resolve_alias(correct_name)
                    logger.info(f"更正別名自動歸併: {correct_name} → {canonical}")
                    canonical_cn = self.label_mapper.get_chinese_name_from_en(canonical)
                    result["alias_resolved"] = {
                        "original": correct_name,
                        "canonical": canonical,
                        "canonical_cn": canonical_cn,
                    }
                    correct_name = canonical

                env_classes = self._get_env_classes()
                data = self._load_custom_classes_data()
                custom = data.get("classes", [])
                existing = env_classes + [c["name_en"] for c in custom]
                if correct_name not in existing:
                    # 檢查槽位上限，超過則以停用狀態新增
                    max_active = self.config.model.max_active_classes
                    active_count = self._get_active_count()
                    is_active = active_count < max_active

                    # 自動查找中文名稱
                    name_cn = self.label_mapper.get_chinese_name_from_en(correct_name)
                    if name_cn == correct_name:
                        name_cn = ""  # 找不到對應就留空
                    custom.append({
                        "name_en": correct_name,
                        "name_cn": name_cn,
                        "active": is_active,
                        "added_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    })
                    data["classes"] = custom
                    self._save_custom_classes_data(data)
                    if is_active:
                        self._reload_detector_classes()
                    else:
                        logger.warning(f"新類別 '{correct_name}' 因槽位已滿，以停用狀態註冊")

            return result

        @self.app.get("/api/feedback/stats")
        async def get_feedback_stats():
            """取得反饋統計"""
            return self.data_manager.get_stats()

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

    def _load_custom_classes_data(self) -> dict:
        """讀取完整自訂類別資料（含 deactivated_defaults 和 last_detected）"""
        try:
            if self._custom_classes_path.exists():
                with open(self._custom_classes_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data
        except Exception as e:
            logger.error(f"讀取自訂類別失敗: {e}")
        return {"classes": [], "deactivated_defaults": [], "last_detected": {}}

    def _load_custom_classes(self) -> list:
        """讀取自訂類別列表（向後相容）"""
        return self._load_custom_classes_data().get("classes", [])

    def _save_custom_classes_data(self, data: dict):
        """儲存完整自訂類別資料"""
        try:
            self._custom_classes_path.parent.mkdir(parents=True, exist_ok=True)
            # 確保必要欄位存在
            if "deactivated_defaults" not in data:
                data["deactivated_defaults"] = []
            if "last_detected" not in data:
                data["last_detected"] = {}
            data["description"] = "使用者自行註冊的偵測類別（透過網頁介面新增）"
            with open(self._custom_classes_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"儲存自訂類別失敗: {e}")

    def _save_custom_classes(self, classes: list):
        """儲存自訂類別列表（向後相容，保留其他欄位）"""
        data = self._load_custom_classes_data()
        data["classes"] = classes
        self._save_custom_classes_data(data)

    def _get_active_count(self) -> int:
        """取得目前啟用中的類別數量"""
        env_classes = self._get_env_classes()
        data = self._load_custom_classes_data()
        deactivated = data.get("deactivated_defaults", [])
        custom = data.get("classes", [])

        # 啟用中的預設類別
        active_defaults = [c for c in env_classes if c not in deactivated]
        # 啟用中的自訂類別
        active_custom = [c for c in custom if c.get("active", True) and c["name_en"] not in env_classes]

        return len(active_defaults) + len(active_custom)

    def _get_lru_suggestion(self) -> Optional[dict]:
        """取得 LRU 建議替換的類別（最久未偵測到的啟用類別）"""
        env_classes = self._get_env_classes()
        data = self._load_custom_classes_data()
        deactivated = data.get("deactivated_defaults", [])
        last_detected = data.get("last_detected", {})
        custom = data.get("classes", [])

        # 收集所有啟用中的類別
        active_classes = []
        for c in env_classes:
            if c not in deactivated:
                active_classes.append({
                    "name_en": c,
                    "name_cn": self.label_mapper.get_chinese_name_from_en(c),
                    "source": "default",
                    "last_detected": last_detected.get(c),
                })
        for c in custom:
            if c.get("active", True) and c["name_en"] not in env_classes:
                active_classes.append({
                    "name_en": c["name_en"],
                    "name_cn": c.get("name_cn", ""),
                    "source": "custom",
                    "last_detected": last_detected.get(c["name_en"]),
                })

        if not active_classes:
            return None

        # 排序：無偵測紀錄的排最前，其次按時間戳由舊到新
        active_classes.sort(key=lambda x: x["last_detected"] or "")
        return active_classes[0]

    def _get_all_classes(self) -> list:
        """取得所有啟用中的偵測類別（.env 預設 + 使用者自訂，排除已停用的）"""
        env_classes = self._get_env_classes()
        data = self._load_custom_classes_data()
        deactivated = data.get("deactivated_defaults", [])
        custom = data.get("classes", [])

        # 啟用中的預設類別
        all_classes = [c for c in env_classes if c not in deactivated]
        # 啟用中的自訂類別
        for c in custom:
            if c.get("active", True) and c["name_en"] not in all_classes:
                all_classes.append(c["name_en"])
        return all_classes

    def _reload_detector_classes(self):
        """重新載入偵測器的偵測類別（含變體）"""
        if self.engine.detector is None:
            return
        # 先載入變體資料到 PromptEnhancer
        self._load_and_apply_variants()
        all_classes = self._get_all_classes()
        if all_classes:
            self.engine.detector.update_classes(all_classes)
            logger.info(f"偵測器類別已更新（共 {len(all_classes)} 個啟用中）")

    def _update_last_detected(self, class_names: list):
        """更新類別的最後偵測時間戳"""
        if not class_names:
            return
        data = self._load_custom_classes_data()
        last_detected = data.get("last_detected", {})
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        for name in class_names:
            last_detected[name] = now
        data["last_detected"] = last_detected
        self._save_custom_classes_data(data)

    def _load_and_apply_aliases(self):
        """從 custom_classes.json 載入自訂別名並套用到 label_mapper"""
        data = self._load_custom_classes_data()
        custom_aliases = data.get("aliases", {})
        if custom_aliases:
            self.label_mapper.load_custom_aliases(custom_aliases)
            logger.info(f"已載入 {len(custom_aliases)} 個自訂別名")

    def _load_and_apply_variants(self):
        """從 custom_classes.json 載入變體資料並套用到偵測器"""
        data = self._load_custom_classes_data()
        variants = data.get("variants", {})
        if variants and self.engine.detector:
            self.engine.detector.load_all_variants(variants)
            logger.info(f"已載入 {len(variants)} 個類別的變體描述")

    def _save_aliases(self, aliases: dict):
        """儲存自訂別名到 custom_classes.json"""
        data = self._load_custom_classes_data()
        data["aliases"] = aliases
        self._save_custom_classes_data(data)

    async def _handle_video_stream(self, websocket: WebSocket):
        """處理視頻串流"""
        await websocket.accept()
        self.engine.reset_session()  # 新連線重置偵測狀態
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
            self.engine.reset_session()
        self._last_request_time = current_time

        # 使用鎖防止並發偵測（GPU 資源有限，序列處理更穩定）
        async with self._detection_lock:
            return await self._do_detect(frame)

    async def _do_detect(self, frame: np.ndarray) -> dict:
        """實際執行 YOLO 檢測"""
        logger.debug(f"開始偵測，影像尺寸: {frame.shape}")

        # 執行檢測（使用 DetectionEngine 的完整流程）
        try:
            detections = self.engine.detect(frame)
            logger.debug(f"偵測完成: {len(detections)} 個物件")
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

        # 更新 FPS
        self.frame_count += 1
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            self.fps = self.frame_count / elapsed

        # 每 30 幀記錄一次統計 + 更新最後偵測時間
        if self.frame_count % 30 == 1:
            logger.info(f"統計: 已處理 {self.frame_count} 幀 | FPS: {self.fps:.1f}")
            # 更新偵測到的類別的最後偵測時間（節流，避免頻繁寫入）
            if detections:
                detected_names = list(set(d.class_name for d in detections))
                self._update_last_detected(detected_names)

        # 構建結果
        detection_results = []
        for det in detections:
            detection_results.append({
                "class_name": det.class_name,
                "class_name_cn": det.class_name_cn or det.class_name,
                "confidence": round(det.confidence, 3),
                "bbox": list(det.bbox.to_tuple()) if det.bbox is not None else None,
            })

        # === 新增：雙路輸出 — 記錄門檻 ===
        if detection_results:
            high_conf_detections = [
                d for d in detection_results if d["confidence"] >= self.record_confidence
            ]
            if high_conf_detections:
                self.detection_logger.log(
                    detections=high_conf_detections,
                    fps=self.fps,
                    frame_count=self.frame_count,
                )

        # 建立 FrameDetectionResult 給繪製用
        stable_result = FrameDetectionResult(
            detections=detections,
            inference_time_ms=0,  # DetectionEngine 內部處理
            fps=self.fps,
            frame_shape=frame.shape,
        )
        if self.engine.detector is not None:
            annotated_frame = self.engine.detector.draw_detections(frame, stable_result)
        else:
            annotated_frame = frame

        # 將處理後的畫面編碼為 base64
        _, buffer = cv2.imencode('.jpg', annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        annotated_base64 = base64.b64encode(buffer).decode('utf-8')

        return {
            "detections": detection_results,
            "count": len(detection_results),
            "fps": round(self.fps, 1),
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
