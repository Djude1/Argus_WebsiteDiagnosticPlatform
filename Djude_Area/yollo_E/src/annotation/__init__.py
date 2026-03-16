# ============================================
# 標註模組
# ============================================
"""
物品標註系統
用於記錄 YOLOE 偵測到的物品並提供後台標註功能
"""

from .annotation_manager import AnnotationManager
from .models import AnnotationRecord, AnnotationStatus

__all__ = ["AnnotationManager", "AnnotationRecord", "AnnotationStatus"]
