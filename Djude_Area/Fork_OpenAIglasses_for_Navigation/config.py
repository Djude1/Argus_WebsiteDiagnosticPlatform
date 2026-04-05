# config.py
# -*- coding: utf-8 -*-
"""
全域設定檔（集中管理）

規則：
- API 金鑰等機密 → 存放於 .env，此處僅讀取，不提供預設值
- 模型路徑       → 存放於 .env，此處提供相對路徑預設值
- 可調參數       → 此處定義，可透過 .env 環境變數覆寫

用法：
    from config import DASHSCOPE_API_KEY, BLIND_PATH_MODEL, SAMPLE_RATE
"""

import os

# ── 讀取 .env（若存在）───────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 專案根目錄（config.py 所在位置）
_PROJECT_ROOT: str = os.path.dirname(os.path.abspath(__file__))

# ═══════════════════════════════════════════════════════════════════════════════
# API 金鑰（必須在 .env 設定，此處不提供預設值）
# ═══════════════════════════════════════════════════════════════════════════════

DASHSCOPE_API_KEY: str = os.environ.get("DASHSCOPE_API_KEY", "")
OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
GEMINI_API_KEY_2: str = os.environ.get("GEMINI_API_KEY_2", "")
GEMINI_API_KEY_3: str = os.environ.get("GEMINI_API_KEY_3", "")
GEMINI_API_KEY_4: str = os.environ.get("GEMINI_API_KEY_4", "")
GEMINI_API_KEY_5: str = os.environ.get("GEMINI_API_KEY_5", "")
GEMINI_API_KEY_6: str = os.environ.get("GEMINI_API_KEY_6", "")
GEMINI_API_KEY_7: str = os.environ.get("GEMINI_API_KEY_7", "")
GEMINI_API_KEY_8: str = os.environ.get("GEMINI_API_KEY_8", "")
GEMINI_API_KEY_9: str = os.environ.get("GEMINI_API_KEY_9", "")
GEMINI_API_KEY_10: str = os.environ.get("GEMINI_API_KEY_10", "")
GEMINI_API_KEY_11: str = os.environ.get("GEMINI_API_KEY_11", "")
GEMINI_API_KEY_12: str = os.environ.get("GEMINI_API_KEY_12", "")
GEMINI_API_KEY_13: str = os.environ.get("GEMINI_API_KEY_13", "")
GEMINI_API_KEY_14: str = os.environ.get("GEMINI_API_KEY_14", "")
GEMINI_API_KEY_15: str = os.environ.get("GEMINI_API_KEY_15", "")
GEMINI_API_KEY_16: str = os.environ.get("GEMINI_API_KEY_16", "")
GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")

# Google Speech-to-Text 服務帳戶憑證 JSON 路徑
GOOGLE_CREDENTIALS_PATH: str = os.environ.get(
    "GOOGLE_CREDENTIALS_PATH",
    os.path.join(_PROJECT_ROOT, "google_Speech_to_Text.json"),
)

# ═══════════════════════════════════════════════════════════════════════════════
# 模型路徑（預設為相對路徑 model/，可在 .env 覆寫為絕對路徑）
# ═══════════════════════════════════════════════════════════════════════════════

# 盲道分割模型
BLIND_PATH_MODEL: str = os.getenv("BLIND_PATH_MODEL", "model/yolo-seg.pt")
# 障礙物偵測模型（YOLO-E 開放詞彙）
OBSTACLE_MODEL: str = os.getenv("OBSTACLE_MODEL", "model/yoloe-11l-seg.pt")
# YOLO-E 後端預設路徑（與 OBSTACLE_MODEL 共用同一個檔）
YOLOE_MODEL_PATH: str = os.getenv("YOLOE_MODEL_PATH", "model/yoloe-11l-seg.pt")
# 紅綠燈偵測模型
TRAFFICLIGHT_MODEL: str = os.getenv("TRAFFICLIGHT_MODEL", "model/trafficlight.pt")
# 物品識別模型（購物場景）
SHOPPING_MODEL: str = os.getenv("SHOPPING_MODEL", "model/shoppingbest5.pt")
# MediaPipe 手部偵測任務檔
HAND_LANDMARKER_PATH: str = os.getenv("HAND_LANDMARKER_PATH", "model/hand_landmarker.task")

# ═══════════════════════════════════════════════════════════════════════════════
# 外部 API 端點與模型名稱
# ═══════════════════════════════════════════════════════════════════════════════

# Google Gemini（視覺理解與 TTS）
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_BASE_URL: str = os.getenv(
    "GEMINI_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta/models",
)

# ═══════════════════════════════════════════════════════════════════════════════
# 伺服器設定
# ═══════════════════════════════════════════════════════════════════════════════

SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8081"))

# IMU UDP 接收設定
UDP_IP: str = os.getenv("UDP_IP", "0.0.0.0")
UDP_PORT: int = int(os.getenv("UDP_PORT", "12345"))

# ═══════════════════════════════════════════════════════════════════════════════
# 音訊設定
# ═══════════════════════════════════════════════════════════════════════════════

# ESP32 麥克風上傳的 PCM 取樣率
SAMPLE_RATE: int = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
# 每個 chunk 的毫秒數（用於 ASR 分塊）
CHUNK_MS: int = int(os.getenv("AUDIO_CHUNK_MS", "20"))
# ASR 上傳格式
AUDIO_FORMAT: str = os.getenv("AUDIO_FORMAT", "pcm")
# 音訊下行串流採樣率（TTS 播放，ESP32 喇叭）
STREAM_SR: int = int(os.getenv("STREAM_SR", "8000"))

# ═══════════════════════════════════════════════════════════════════════════════
# TTS / 語音播報
# ═══════════════════════════════════════════════════════════════════════════════

# 語音播報最短間隔（秒），避免頻繁播報
TTS_INTERVAL_SEC: float = float(os.getenv("TTS_INTERVAL_SEC", "1.0"))
# 是否啟用 TTS 語音播報
ENABLE_TTS: bool = os.getenv("ENABLE_TTS", "true").lower() == "true"

# ═══════════════════════════════════════════════════════════════════════════════
# 視覺 / 攝影機參數
# ═══════════════════════════════════════════════════════════════════════════════

# 本機攝影機索引（0 = 預設攝影機）
CAM_INDEX: int = int(os.getenv("CAM_INDEX", "0"))
# 全域 YOLO 置信度門檻
CONF_THRESHOLD: float = float(os.getenv("CONF_THRESHOLD", "0.20"))

# 手部偵測輸入縮放比例（0.5 = 長寬各半）
HAND_DOWNSCALE: float = float(os.getenv("HAND_DOWNSCALE", "0.8"))
# 手部偵測抽幀比（1=每幀，2=隔幀）
HAND_FPS_DIV: int = int(os.getenv("HAND_FPS_DIV", "1"))

# 是否輸出效能偵錯資訊（處理時間等）
PERF_DEBUG: bool = os.getenv("PERF_DEBUG", "false").lower() == "true"

# ═══════════════════════════════════════════════════════════════════════════════
# GPU / 推理加速
# ═══════════════════════════════════════════════════════════════════════════════

# 推理裝置（cuda:0 / cpu）
AIGLASS_DEVICE: str = os.getenv("AIGLASS_DEVICE", "cuda:0")
# AMP 混合精度策略（bf16 / fp16 / off）
AIGLASS_AMP: str = os.getenv("AIGLASS_AMP", "bf16")
# GPU 並行推理最大 slot 數
AIGLASS_GPU_SLOTS: int = int(os.getenv("AIGLASS_GPU_SLOTS", "2"))

# ═══════════════════════════════════════════════════════════════════════════════
# 盲道導航參數
# ═══════════════════════════════════════════════════════════════════════════════

# 掩碼最小面積（小於此值視為雜訊）
AIGLASS_MASK_MIN_AREA: int = int(os.getenv("AIGLASS_MASK_MIN_AREA", "1500"))
# 形態學運算核大小
AIGLASS_MASK_MORPH: int = int(os.getenv("AIGLASS_MASK_MORPH", "3"))
# 資料面板縮放比例
AIGLASS_PANEL_SCALE: float = float(os.getenv("AIGLASS_PANEL_SCALE", "0.65"))
# 直行語音播報間隔（秒）
AIGLASS_STRAIGHT_INTERVAL: float = float(os.getenv("AIGLASS_STRAIGHT_INTERVAL", "4.0"))
# 方向指令語音播報間隔（秒）
AIGLASS_DIRECTION_INTERVAL: float = float(os.getenv("AIGLASS_DIRECTION_INTERVAL", "3.0"))
# 障礙物偵測抽幀間隔（每 N 幀執行一次）
AIGLASS_OBS_INTERVAL: int = int(os.getenv("AIGLASS_OBS_INTERVAL", "15"))
# 障礙物偵測結果快取幀數
AIGLASS_OBS_CACHE_FRAMES: int = int(os.getenv("AIGLASS_OBS_CACHE_FRAMES", "10"))
# 盲道 YOLO 偵測抽幀間隔
AIGLASS_BLINDPATH_INTERVAL: int = int(os.getenv("AIGLASS_BLINDPATH_INTERVAL", "8"))
# 障礙物偵測置信度門檻
AIGLASS_OBS_CONF: float = float(os.getenv("AIGLASS_OBS_CONF", "0.25"))

# ═══════════════════════════════════════════════════════════════════════════════
# 過馬路參數
# ═══════════════════════════════════════════════════════════════════════════════

# 斑馬線偵測最低置信度
CROSSWALK_MIN_CONF: float = float(os.getenv("CROSSWALK_MIN_CONF", "0.3"))
# 斑馬線偵測最小面積（像素）
CROSSWALK_MIN_AREA: int = int(os.getenv("CROSSWALK_MIN_AREA", "5000"))
# 斑馬線對齊角度容許誤差（度）
CROSSWALK_ANGLE_THRESH_DEG: float = float(os.getenv("CROSSWALK_ANGLE_THRESH_DEG", "5.0"))
# 斑馬線對齊偏移容許誤差（相對寬度）
CROSSWALK_OFFSET_THRESH: float = float(os.getenv("CROSSWALK_OFFSET_THRESH", "0.08"))
# 分割模型中斑馬線的類別 ID
AIGLASS_SEG_CW_ID: int = int(os.getenv("AIGLASS_SEG_CW_ID", "0"))
# 分割模型中盲道的類別 ID
AIGLASS_SEG_BP_ID: int = int(os.getenv("AIGLASS_SEG_BP_ID", "1"))


# ═══════════════════════════════════════════════════════════════════════════════
# 音訊目錄路徑
# ═══════════════════════════════════════════════════════════════════════════════

# 系統提示音目錄（music/）
AUDIO_BASE_DIR: str = os.getenv(
    "AUDIO_BASE_DIR",
    os.path.join(_PROJECT_ROOT, "music"),
)
# 語音回應目錄（voice/）
VOICE_DIR: str = os.getenv(
    "VOICE_DIR",
    os.path.join(_PROJECT_ROOT, "voice"),
)

# ═══════════════════════════════════════════════════════════════════════════════
# 語音打斷熱詞
# ═══════════════════════════════════════════════════════════════════════════════

# 觸發全系統重置的熱詞清單（逗號分隔）
INTERRUPT_KEYWORDS: set = set(
    os.getenv("INTERRUPT_KEYWORDS", "停下所有功能,停止所有功能").split(",")
)
