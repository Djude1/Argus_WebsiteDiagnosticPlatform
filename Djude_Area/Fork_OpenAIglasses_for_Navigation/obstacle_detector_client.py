# app/cloud/obstacle_detector_client.py (新文件)
import logging
import os
import cv2
import numpy as np
import torch
from threading import Semaphore
from contextlib import contextmanager
from ultralytics import YOLO, YOLOE
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# --- GPU/CPU & AMP 配置 (从 blindpath 工作流迁移而来，保持一致) ---
DEVICE = os.getenv("AIGLASS_DEVICE", "cuda:0")
if DEVICE.startswith("cuda") and not torch.cuda.is_available():
    logger.warning(f"AIGLASS_DEVICE={DEVICE} 但未检测到 CUDA，将回退到 CPU")
    DEVICE = "cpu"
IS_CUDA = DEVICE.startswith("cuda")

AMP_POLICY = os.getenv("AIGLASS_AMP", "bf16").lower()
if AMP_POLICY not in ("bf16", "fp16", "off"):
    AMP_POLICY = "bf16"
# YOLOE 的 upsample_nearest2d 不支援 bf16，自動降級至 fp16
if AMP_POLICY == "bf16":
    AMP_POLICY = "fp16"
AMP_DTYPE = torch.bfloat16 if AMP_POLICY == "bf16" else (torch.float16 if AMP_POLICY == "fp16" else None)

# --- GPU 并发限流 (从 blindpath 工作流迁移而来，保持一致) ---
GPU_SLOTS = int(os.getenv("AIGLASS_GPU_SLOTS", "2"))
_gpu_slots = Semaphore(GPU_SLOTS)

try:
    torch.backends.cudnn.benchmark = True
except Exception:
    pass


@contextmanager
def gpu_infer_slot():
    """统一管理 GPU 并发限流 + inference_mode + AMP autocast"""
    with _gpu_slots:
        if IS_CUDA and AMP_POLICY != "off":
            # 新式接口：torch.amp.autocast(device_type='cuda', dtype=...)
            with torch.inference_mode(), torch.amp.autocast(device_type='cuda', dtype=AMP_DTYPE):
                yield
        else:
            with torch.inference_mode():
                yield


class ObstacleDetectorClient:
    def __init__(self, model_path: str = None):
        # 若未傳入路徑，從 config 讀取預設值
        if model_path is None:
            from config import OBSTACLE_MODEL
            model_path = OBSTACLE_MODEL
        self.model = None
        self.whitelist_embeddings = None
        self.WHITELIST_CLASSES = [
            # 人（視障者最需要閃避）
            'person',
            # 交通工具與動物
            'bicycle', 'car', 'motorcycle', 'bus', 'truck',
            'animal', 'scooter', 'stroller', 'dog',
            # 柱狀障礙物（精簡同義詞，保留高頻詞）
            'pole', 'post', 'bollard', 'utility pole', 'light pole', 'signpost',
            # 路邊常見固定物
            'bench', 'chair', 'potted plant', 'hydrant', 'cone', 'stone', 'box',
            'trash can', 'barrel', 'cart',
            # 阻隔物
            'fence', 'barrier', 'wall', 'gate', 'door',
            # 地面障礙
            'rock', 'tree', 'branch', 'curb',
            'stairs', 'step', 'ramp', 'hole',
            # 行李
            'bag', 'suitcase', 'backpack',
            # 其他
            'table', 'ladder',
            # 通用（捕捉未知障礙物）
            'object', 'obstacle',
        ]
        # 標記模型類型：YOLOE（文字提示）或標準 YOLO（固定類別）
        self.is_yoloe = False

        try:
            logger.info(f"正在載入障礙物模型：{model_path}")
            # 先嘗試以 YOLOE 載入（文字提示型），若失敗則改用標準 YOLO
            try:
                self.model = YOLOE(model_path)
                self.model.to(DEVICE)
                self.model.fuse()
                # 真正的 YOLOE 模型類別名稱為純數字（'0','1','2'...）；
                # 若有具名類別（'person','car'...）代表這是標準 YOLO，強制 fallback。
                class_names = list(self.model.names.values())
                if not all(str(n).isdigit() for n in class_names):
                    raise ValueError(f"具名類別模型，非 YOLOE（{class_names[:3]}...）")
                # 嘗試預計算文字特徵，若成功代表確實是 YOLOE 模型
                logger.info("正在為 YOLOE 預計算白名單文字特徵...")
                if IS_CUDA and AMP_DTYPE is not None:
                    with torch.inference_mode(), torch.amp.autocast(device_type='cuda', dtype=AMP_DTYPE):
                        self.whitelist_embeddings = self.model.get_text_pe(self.WHITELIST_CLASSES)
                else:
                    self.whitelist_embeddings = self.model.get_text_pe(self.WHITELIST_CLASSES)
                self.is_yoloe = True
                logger.info(f"YOLOE 模型載入成功，設備: {DEVICE}")
            except Exception as yoloe_err:
                # 非 YOLOE 模型，改用標準 YOLO segmentation
                logger.info(f"非 YOLOE 模型（{yoloe_err}），改用標準 YOLO 載入...")
                self.model = YOLO(model_path)
                self.model.to(DEVICE)
                self.is_yoloe = False
                # 將固定類別與白名單取交集，僅保留障礙物相關類別
                model_classes = set(self.model.names.values()) if hasattr(self.model, 'names') else set()
                whitelist_lower = {w.lower() for w in self.WHITELIST_CLASSES}
                matched = [c for c in model_classes if c.lower() in whitelist_lower]
                logger.info(f"標準 YOLO 模型載入成功，全部類別: {list(self.model.names.values())}")
                logger.info(f"與白名單匹配的障礙物類別: {matched}")
        except Exception as e:
            logger.error(f"障礙物模型載入失敗: {e}", exc_info=True)
            raise
    @staticmethod
    def tensor_to_numpy_mask(mask_tensor):
        """安全地將各種型別的張量轉換為 numpy 遮罩（目前未使用，保留供未來使用）"""
        if mask_tensor.dtype in (torch.bfloat16, torch.float16):
            mask_tensor = mask_tensor.float()
        mask = mask_tensor.cpu().numpy()
        if mask.max() <= 1.0:
            mask = (mask > 0.5).astype(np.uint8) * 255
        else:
            mask = mask.astype(np.uint8)
        return mask
    def detect(self, image: np.ndarray, path_mask: np.ndarray = None) -> List[Dict[str, Any]]:
        """
        利用白名单作为提示词寻找障碍物。
        如果提供了 path_mask，则执行与路径相关的空间过滤。
        如果 path_mask 为 None，则进行全局检测。
        """
        if self.model is None:
            return []

        H, W = image.shape[:2]

        # YOLOE 需要先設定類別提示詞；標準 YOLO 直接推理
        if self.is_yoloe:
            try:
                self.model.set_classes(self.WHITELIST_CLASSES, self.whitelist_embeddings)
            except Exception as e:
                logger.error(f"設定 YOLOE 提示詞失敗: {e}")
                return []

        conf_thr = float(os.getenv("AIGLASS_OBS_CONF", "0.25"))
        with gpu_infer_slot():
            results = self.model.predict(image, verbose=False, conf=conf_thr)

        if not (results and results[0].masks):
            return []

        # --- 過濾與後處理 ---
        final_obstacles = []
        num_masks = len(results[0].masks.data)
        num_boxes = len(results[0].boxes.cls) if getattr(results[0].boxes, "cls", None) is not None else 0
        # 白名單集合只建一次，避免在 loop 內重複建立
        whitelist_lower = {w.lower() for w in self.WHITELIST_CLASSES}

        for i, mask_tensor in enumerate(results[0].masks.data):
            if i >= num_boxes: continue

            # 【修复】处理 BFloat16 类型的掩码
            # 先转换为 float32，避免 numpy 不支持 BFloat16 的问题
            if mask_tensor.dtype == torch.bfloat16:
                mask_tensor = mask_tensor.float()
            
            # 转换为 numpy 数组
            mask = mask_tensor.cpu().numpy()
            
            # 处理概率掩码（值在0-1之间）或二值掩码
            if mask.max() <= 1.0:
                # 概率掩码，需要二值化
                mask = (mask > 0.5).astype(np.uint8) * 255
            else:
                # 已经是二值掩码
                mask = mask.astype(np.uint8)
            
            mask = cv2.resize(mask, (W, H), interpolation=cv2.INTER_NEAREST)
            area = np.sum(mask > 0)

            # 尺寸过滤：太大的物体（如整片地面）通常是误识别
            if (area / (H * W)) > 0.7: continue

            # 空间过滤：如果提供了 path_mask，则只保留路径上的障碍物
            if path_mask is not None:
                intersection_area = np.sum(cv2.bitwise_and(mask, path_mask) > 0)
                # 與路徑有任何重疊即保留（降低門檻：從 100px 改為 30px）
                if intersection_area < 30:
                    continue

            cls_id = int(results[0].boxes.cls[i])
            class_names_map = results[0].names
            class_name = "Unknown"
            if isinstance(class_names_map, dict):
                class_name = class_names_map.get(cls_id, "Unknown")
            elif isinstance(class_names_map, list) and 0 <= cls_id < len(class_names_map):
                class_name = class_names_map[cls_id]

            # 標準 YOLO：過濾不在白名單內的類別（僅保留障礙物相關）
            if not self.is_yoloe and class_name.lower() not in whitelist_lower:
                continue

            # 计算距离指标
            y_coords, x_coords = np.where(mask > 0)
            if len(y_coords) == 0: continue

            conf_val = float(results[0].boxes.conf[i]) if results[0].boxes.conf is not None else 0.5
            final_obstacles.append({
                'name': class_name.strip(),
                'confidence': conf_val,
                'mask': mask,
                'area': area,
                'area_ratio': area / (H * W),
                'center_x': np.mean(x_coords),
                'center_y': np.mean(y_coords),
                'bottom_y_ratio': np.max(y_coords) / H
            })

        return final_obstacles