# ============================================
# 環境配置管理
# ============================================
"""
從 .env 檔案讀取並管理所有配置參數
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from dataclasses import dataclass, field


# 載入 .env 檔案
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)


@dataclass
class WiFiConfig:
    """WiFi 配置"""

    ssid: str = field(default_factory=lambda: os.getenv("WIFI_SSID", ""))
    password: str = field(default_factory=lambda: os.getenv("WIFI_PASSWORD", ""))


@dataclass
class ESP32Config:
    """ESP32 配置"""

    # mDNS 主機名 (優先使用)
    hostname: str = field(default_factory=lambda: os.getenv("ESP32_HOSTNAME", "yollo"))
    # IP 位址 (備援用，若 mDNS 失敗時使用)
    ip: str = field(default_factory=lambda: os.getenv("ESP32_IP", ""))
    port: int = field(default_factory=lambda: int(os.getenv("ESP32_STREAM_PORT", "80")))
    stream_path: str = field(default_factory=lambda: os.getenv("ESP32_STREAM_PATH", "/stream"))

    @property
    def host(self) -> str:
        """取得連線主機 (優先使用主機名)"""
        # 如果有設定 hostname，使用 mDNS 主機名
        if self.hostname:
            return f"{self.hostname}.local"
        # 否則使用 IP (需手動設定)
        return self.ip if self.ip else "192.168.1.100"

    @property
    def stream_url(self) -> str:
        """取得完整串流 URL"""
        return f"http://{self.host}:{self.port}{self.stream_path}"

    @property
    def snapshot_url(self) -> str:
        """取得快照 URL"""
        return f"http://{self.host}:{self.port}/snapshot"

    @property
    def status_url(self) -> str:
        """取得狀態 URL"""
        return f"http://{self.host}:{self.port}/status"


@dataclass
class ModelConfig:
    """模型配置 - 支援 YOLOE 開放詞彙實例分割模型"""

    # 模型路徑 (相對於專案根目錄)
    model_path: str = field(default_factory=lambda: os.getenv("MODEL_PATH", "yoloe-26s-seg.pt"))
    custom_model_path: str = field(
        default_factory=lambda: os.getenv("CUSTOM_MODEL_PATH", "models/custom/yoloe_custom.pt")
    )
    # 輕量級模型選項
    lightweight_model_path: str = field(
        default_factory=lambda: os.getenv("LIGHTWEIGHT_MODEL_PATH", "yolov8n.pt")
    )
    # 使用輕量級模型 (適合 CPU 或低階 GPU)
    use_lightweight: bool = field(
        default_factory=lambda: os.getenv("USE_LIGHTWEIGHT_MODEL", "false").lower() == "true"
    )
    # 強制使用 CPU (即使有 GPU)
    force_cpu: bool = field(
        default_factory=lambda: os.getenv("FORCE_CPU", "false").lower() == "true"
    )

    confidence_threshold: float = field(
        default_factory=lambda: float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))
    )
    iou_threshold: float = field(default_factory=lambda: float(os.getenv("IOU_THRESHOLD", "0.45")))
    # YOLOE 開放詞彙偵測類別（可自訂任何物品，留空則使用模型內建類別）
    detection_classes: str = field(default_factory=lambda: os.getenv("DETECTION_CLASSES", ""))

    @property
    def full_model_path(self) -> Path:
        """取得完整的模型檔案路徑"""
        path = Path(self.model_path)
        if path.is_absolute():
            return path
        # 相對於專案根目錄 (src 的上一層)
        return Path(__file__).parent.parent / path

    @property
    def full_lightweight_path(self) -> Path:
        """取得完整的輕量級模型檔案路徑"""
        path = Path(self.lightweight_model_path)
        if path.is_absolute():
            return path
        return Path(__file__).parent.parent / path


@dataclass
class DatabaseConfig:
    """資料庫配置"""

    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "data/database/items.db"))

    @property
    def full_path(self) -> Path:
        """取得完整資料庫路徑"""
        return Path(__file__).parent.parent / self.db_path


@dataclass
class CameraConfig:
    """攝影機配置"""

    frame_width: int = field(default_factory=lambda: int(os.getenv("FRAME_WIDTH", "640")))
    frame_height: int = field(default_factory=lambda: int(os.getenv("FRAME_HEIGHT", "480")))
    fps_target: int = field(default_factory=lambda: int(os.getenv("FPS_TARGET", "15")))


@dataclass
class LogConfig:
    """日誌配置"""

    level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    file: str = field(default_factory=lambda: os.getenv("LOG_FILE", "logs/detection.log"))


@dataclass
class Config:
    """主配置類別"""

    wifi: WiFiConfig = field(default_factory=WiFiConfig)
    esp32: ESP32Config = field(default_factory=ESP32Config)
    model: ModelConfig = field(default_factory=ModelConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    log: LogConfig = field(default_factory=LogConfig)

    @classmethod
    def load(cls) -> "Config":
        """載入配置"""
        return cls()

    def validate(self) -> bool:
        """驗證配置是否完整"""
        errors = []

        if not self.wifi.ssid:
            errors.append("WIFI_SSID 未設定")
        if not self.wifi.password:
            errors.append("WIFI_PASSWORD 未設定")

        if errors:
            for error in errors:
                print(f"配置錯誤: {error}")
            return False

        return True


# 全域配置實例
config = Config.load()


# ============================================
# 便捷函式
# ============================================


def get_config() -> Config:
    """取得配置實例"""
    return config


def get_esp32_stream_url() -> str:
    """取得 ESP32 串流 URL"""
    return config.esp32.stream_url


def get_model_path(use_custom: bool = False, use_lightweight: bool = None) -> str:
    """取得模型路徑

    參數:
        use_custom: 使用自訂模型
        use_lightweight: 使用輕量級模型 (None 則根據配置自動判斷)

    回傳:
        模型檔案的完整路徑
    """
    cfg = config.model
    if use_custom:
        path = cfg.custom_model_path
    elif use_lightweight is None:
        path = cfg.lightweight_model_path if cfg.use_lightweight else cfg.model_path
    else:
        path = cfg.lightweight_model_path if use_lightweight else cfg.model_path

    # 轉換為完整路徑
    path_obj = Path(path)
    if path_obj.is_absolute():
        return str(path_obj)
    return str(Path(__file__).parent.parent / path)


def get_device() -> str:
    """取得運算裝置

    回傳:
        "cpu" 如果強制使用 CPU
        "auto" 否則自動判斷
    """
    if config.model.force_cpu:
        return "cpu"
    return "auto"


def get_db_path() -> Path:
    """取得資料庫路徑"""
    return config.database.full_path


if __name__ == "__main__":
    # 測試配置載入
    print("=" * 50)
    print("YOLO 日常物品辨識系統 - 配置資訊")
    print("=" * 50)
    print(f"WiFi SSID: {config.wifi.ssid}")
    print(f"ESP32 主機名: {config.esp32.hostname}")
    print(f"ESP32 IP (備援): {config.esp32.ip or '未設定'}")
    print(f"連線主機: {config.esp32.host}")
    print(f"串流 URL: {config.esp32.stream_url}")
    print(f"模型路徑: {config.model.model_path}")
    print(f"資料庫路徑: {config.database.full_path}")
    print(f"信心度門檻: {config.model.confidence_threshold}")
    print("=" * 50)
