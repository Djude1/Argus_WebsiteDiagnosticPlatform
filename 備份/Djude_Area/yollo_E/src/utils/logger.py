# ============================================
# 日誌工具
# ============================================
"""
統一的日誌管理
"""

import sys
from pathlib import Path
from loguru import logger


def setup_logger(
    level: str = "INFO", log_file: str = None, rotation: str = "10 MB", retention: str = "7 days"
):
    """
    設定日誌系統

    參數:
        level: 日誌等級 (DEBUG, INFO, WARNING, ERROR)
        log_file: 日誌檔案路徑
        rotation: 日誌輪替大小
        retention: 日誌保留時間
    """
    # 移除預設處理器
    logger.remove()

    # 主控台輸出
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    # 檔案輸出
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_file,
            level=level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level:8} | {name}:{function}:{line} - {message}",
            rotation=rotation,
            retention=retention,
            encoding="utf-8",
        )

    return logger


def get_logger(name: str = __name__):
    """取得日誌器"""
    return logger.bind(name=name)
