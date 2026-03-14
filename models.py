# app/models.py
import os
import logging
import torch
from threading import Semaphore
from contextlib import contextmanager
from typing import List
from app.cloud.obstacle_detector_client import ObstacleDetectorClient
# ==========================================================
# 0. 导入所有需要的模型封装类 (Clients) 和 Ultralytics 基类
# ==========================================================
# 这是过马路工作流使用的封装类
from app.cloud.crosswalk_detector_client import CrosswalkDetector
from app.cloud.coco_perception_client import COCOClient
from obstacle_detector_client import ObstacleDetectorClient

# 这是盲道工作流直接使用的 Ultralytics 类
from ultralytics import YOLO, YOLOE

logger = logging.getLogger(__name__)

# ==========================================================
# 1. 全局设备与并发控制 (统一管理)
# ==========================================================
DEVICE = os.getenv("AIGLASS_DEVICE", "cuda:0")
if DEVICE.startswith("cuda") and not torch.cuda.is_available():
    logger.warning(f"AIGLASS_DEVICE={DEVICE} 但未检测到 CUDA，将回退到 CPU")
    DEVICE = "cpu"
IS_CUDA = DEVICE.startswith("cuda")

# AMP (自动混合精度) 配置
AMP_POLICY = os.getenv("AIGLASS_AMP", "bf16").lower()
AMP_DTYPE = torch.bfloat16 if AMP_POLICY == "bf16" else (
    torch.float16 if AMP_POLICY == "fp16" else None) if IS_CUDA else None

# 🔥 核心：全局唯一的GPU并发信号量，所有工作流共享
GPU_SLOTS = int(os.getenv("AIGLASS_GPU_SLOTS", "2"))
gpu_semaphore = Semaphore(GPU_SLOTS)


# 统一的推理上下文管理器，所有工作流都应使用它来调用模型
@contextmanager
def gpu_infer_slot():
    """
    统一管理：GPU 并发限流 + torch.inference_mode() + AMP autocast
    """
    with gpu_semaphore:
        if IS_CUDA and AMP_POLICY != "off" and AMP_DTYPE is not None:
            with torch.inference_mode(), torch.amp.autocast('cuda', dtype=AMP_DTYPE):
                yield
        else:
            with torch.inference_mode():
                yield


# cuDNN 加速优化
try:
    if IS_CUDA:
        torch.backends.cudnn.benchmark = True
except Exception:
    pass

# ==========================================================
# 2. 全局模型实例定义 (全部初始化为 None)
# ==========================================================

# --- 过马路工作流模型 (通过Client类封装) ---
crosswalk_detector_client: CrosswalkDetector = None
coco_client: COCOClient = None
# ObstacleDetectorClient 将作为所有场景的通用障碍物检测器
obstacle_detector_client: ObstacleDetectorClient = None

# --- 盲道工作流模型 (直接使用Ultralytics类) ---
# 它们主要用于分割和路径规划，与过马路场景的检测逻辑不同
blindpath_seg_model: YOLO = None
# 障碍物检测将复用 obstacle_detector_client，但YOLOE的文本特征需要单独保存
blindpath_whitelist_embeddings = None

# 全局加载状态标志
models_are_loaded = False


# ==========================================================
# 3. 统一的模型加载函数 (由 celery.py 在启动时调用)
# ==========================================================
def init_all_models():
    """
    在Celery Worker进程启动时被调用一次。
    负责加载所有工作流所需的模型到全局变量中。
    """
    global models_are_loaded
    if models_are_loaded:
        return

    logger.info(f"========= 🚀 开始全局模型预加载 (目标设备: {DEVICE}) =========")

    try:
        # --- [1] 加载通用的障碍物检测器 (ObstacleDetectorClient) ---
        global obstacle_detector_client
        logger.info("[1/4] 正在加载通用障碍物检测模型 (ObstacleDetectorClient)...")
        obstacle_detector_client = ObstacleDetectorClient(model_path='models/yoloe-11l-seg.pt')

        # 🔥🔥🔥 【核心修复】在这里添加缺失的设备转移代码 🔥🔥🔥
        if hasattr(obstacle_detector_client, 'model') and obstacle_detector_client.model is not None:
            obstacle_detector_client.model.to(DEVICE)

        logger.info("...通用障碍物检测模型加载成功。")

        # --- [2] 加载过马路专用的模型 (Clients) ---
        global crosswalk_detector_client, coco_client
        logger.info("[2/4] 正在加载过马路分割模型 (CrosswalkDetector)...")
        crosswalk_detector_client = CrosswalkDetector(model_path='models/yolo-seg.pt')
        # 将其内部的YOLO模型移动到指定设备
        if hasattr(crosswalk_detector_client, 'model') and crosswalk_detector_client.model is not None:
            crosswalk_detector_client.model.to(DEVICE)
        logger.info("...过马路分割模型加载成功。")

        logger.info("[3/4] 正在加载通用感知模型 (COCOClient)...")
        coco_client = COCOClient(model_path='models/yolov8l-world.pt')
        # 将其内部的YOLO模型移动到指定设备
        if hasattr(coco_client, 'model') and coco_client.model is not None:
            coco_client.model.to(DEVICE)
        logger.info("...通用感知模型加载成功。")

        # --- [4] 加载盲道专用的模型 ---
        global blindpath_seg_model, blindpath_whitelist_embeddings
        logger.info("[4/4] 正在加载盲道专用分割模型 (YOLO)...")
        blindpath_seg_model = YOLO('models/yolo-seg.pt')
        blindpath_seg_model.to(DEVICE)
        blindpath_seg_model.fuse()
        logger.info("...盲道专用分割模型加载成功。")

        # 为盲道工作流保存其需要的YOLOE文本特征引用
        if obstacle_detector_client:
            blindpath_whitelist_embeddings = obstacle_detector_client.whitelist_embeddings
            logger.info("...已为盲道工作流链接障碍物模型特征。")

        # 所有模型加载完毕
        models_are_loaded = True
        logger.info("========= ✅ 所有模型已成功预加载。Worker准备就绪! =========")

    except Exception as e:
        logger.error(f"模型预加载过程中发生严重错误: {e}", exc_info=True)
        # 抛出异常，这将导致Celery Worker启动失败，这是合理的行为
        # 因为一个没有模型的Worker是无用的，提前暴露问题更好。
        raise