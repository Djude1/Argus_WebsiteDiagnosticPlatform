# -*- coding: utf-8 -*-
"""
过马路工作流（简化版 - 仅斑马线检测，但保留导航功能）
- 直连版本，无 Celery/Redis
- 仅检测斑马线，无交通灯检测
- 保留斑马线导航功能（角度、偏移计算）
- 保留可视化（引导线、目标点等）
- 每帧都进行分割；若该帧分割失败，则用上一帧从掩码打点的光流特征点追踪，重建掩码保持位置，直到下一次分割检出
"""
import torch
import os
import time
import logging
import numpy as np
import cv2
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
# 【移除】from audio_player import play_voice_text - 不在工作流内部播放音频

# 可选：用于更精致的数据面板（与 blindpath 一致）
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image, ImageDraw, ImageFont = None, None, None

# 可选：自动启用障碍物检测（与 blindpath 一致）
try:
    from obstacle_detector_client import ObstacleDetectorClient
except Exception:
    ObstacleDetectorClient = None

# 红绿灯检测模块
try:
    import trafficlight_detection
    TRAFFIC_LIGHT_AVAILABLE = True
except Exception:
    TRAFFIC_LIGHT_AVAILABLE = False
    trafficlight_detection = None

logger = logging.getLogger(__name__)

# ========== 状态常量 ==========
STATE_SEEKING = "SEEKING_CROSSWALK"      # 寻找并对准远处的斑马线
STATE_WAIT_LIGHT = "WAIT_TRAFFIC_LIGHT"  # 等待红绿灯判定
STATE_CROSSING = "CROSSING"              # 正在过马路

# ========== 配置参数 ==========
CROSSWALK_MIN_CONF = float(os.getenv('CROSSWALK_MIN_CONF', '0.3'))
CROSSWALK_MIN_AREA = int(os.getenv('CROSSWALK_MIN_AREA', '5000'))
BLIND_MIN_CONF = float(os.getenv('BLIND_MIN_CONF', '0.34'))  # 盲道最低置信度（更高，防误判）
ANGLE_THRESH_DEG = float(os.getenv('CROSSWALK_ANGLE_THRESH_DEG', '5.0'))  # 默认阈值略放宽
OFFSET_THRESH = float(os.getenv('CROSSWALK_OFFSET_THRESH', '0.08'))        # 默认阈值略放宽

# 远距离对准阈值（更宽松，避免过于敏感）
SEEKING_ANGLE_THRESH_DEG = 15.0  # 远距离角度阈值（更宽松）
SEEKING_OFFSET_THRESH = 0.20     # 远距离偏移阈值（更宽松）

# 远距离对准阈值（判定"很近"的条件，更严格）
CROSSWALK_NEAR_AREA_RATIO = 0.30  # 斑马线占画面30%认为"很近"（提高）
CROSSWALK_NEAR_BOTTOM_RATIO = 0.80  # 斑马线底部超过画面80%认为"很近"（提高）
CROSSWALK_NEAR_MIN_HEIGHT_RATIO = 0.35  # 斑马线高度占画面35%以上（新增条件）

# 红绿灯判定参数
GREEN_LIGHT_STABLE_FRAMES = 5  # 绿灯稳定帧数

# 类别ID绑定（与训练集对应）
CW_ID = int(os.getenv("AIGLASS_SEG_CW_ID", "0"))  # 斑马线
BP_ID = int(os.getenv("AIGLASS_SEG_BP_ID", "1"))  # 盲道

# 斑马线与盲道的同义名集合
_CW = {'zebra_crossing', 'zebra crossing', 'zebra', 'crosswalk', 'road_crossing', 'road crossing'}
_BP = {'blind_path', 'tactile_paving', 'tactile paving', 'blind path'}

# 盲道"真伪判定"阈值
BP_VALID_IOU_THR = 0.40  # 与斑马线 IoU 超过此值，判为"混淆"，不当盲道

# 追踪/打点参数
INNER_OFFSET_PX_LOCK = 5
EDGE_DILATE_PX = 2
LK_PARAMS = dict(
    winSize=(21, 21),
    maxLevel=3,
    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 12, 0.03)
)
FEATURE_PARAMS = dict(
    maxCorners=600,
    qualityLevel=0.001,
    minDistance=5,
    blockSize=7
)

# 时序平滑与保活
MASK_EMA_ALPHA = 0.6   # EMA 平滑权重
TRACK_MIN_POINTS = 30  # 追踪最少特征点阈值
TRACK_RESEED_EVERY = 12  # 每隔 N 帧在成功分割时重播种一次特征点

# 可视化颜色（BGR）
VIS_COLORS = {
    "crosswalk": (0, 165, 255),   # 橙色
    "centerline": (255, 255, 0),  # 青色 - 引导中心线
    "target_point": (255, 0, 255), # 粉色 - 引导目标点
    "hint": (0, 255, 255),        # 黄色
    "stripes": (0, 128, 255),     # 橙蓝 - 条纹线段
    "heading": (0, 0, 255),       # 红色 - 方向箭头
}

@dataclass
class CrossStreetResult:
    """过马路导航结果"""
    annotated_image: Optional[np.ndarray] = None
    guidance_text: str = ""
    visualizations: List[Dict[str, Any]] = None
    should_switch_to_blindpath: bool = False

    def __post_init__(self):
        if self.visualizations is None:
            self.visualizations = []

# ========== 辅助函数 ==========
def _score_of(d) -> float:
    """兼容不同检测结构，取出置信度；取不到就给 0.0（保守）"""
    for k in ("conf", "confidence", "score", "prob"):
        v = getattr(d, k, None)
        if v is not None:
            try:
                return float(v)
            except Exception:
                break
    return 0.0

def _norm_name(s: str) -> str:
    """标准化名称"""
    return str(s).lower().replace('_', ' ').strip()

def _in_set(name: str, pool: set) -> bool:
    """检查名称是否在集合中"""
    return _norm_name(name) in {_norm_name(x) for x in pool}

def _mask_iou(a: np.ndarray, b: np.ndarray) -> float:
    """计算两个mask的IoU"""
    if a is None or b is None: 
        return 0.0
    ai = a > 0
    bi = b > 0
    inter = np.logical_and(ai, bi).sum()
    union = np.logical_or(ai, bi).sum()
    return float(inter) / float(union + 1e-6)

def _looks_like_blind_path(bp_mask: np.ndarray, cw_mask: np.ndarray, H: int, W: int) -> bool:
    """几何+互斥检查，过滤'横条纹/路牙'伪盲道"""
    if bp_mask is None: 
        return False
    ys, xs = np.where(bp_mask > 0)
    if xs.size < 80:  # 太小的片段直接丢
        return False

    # 计算主轴角度
    pts = np.stack([xs.astype(np.float32), ys.astype(np.float32)], axis=1)
    mean = pts.mean(axis=0)
    cov = np.cov((pts - mean).T)
    eigvals, eigvecs = np.linalg.eig(cov)
    v = eigvecs[:, np.argmax(eigvals)]
    angle_deg = np.degrees(np.arctan2(v[1], v[0]))
    if angle_deg > 90: angle_deg -= 180
    if angle_deg < -90: angle_deg += 180
    
    h = (ys.max() - ys.min() + 1)
    w = (xs.max() - xs.min() + 1)
    aspect = h / float(w + 1e-6)  # 期望盲道"更竖一些"
    iou_cw = _mask_iou(bp_mask, cw_mask)

    # 1) 横向条纹过滤（放宽到 20°，给远端/轻微倾斜更多空间）
    if abs(angle_deg) <= 20.0:
        return False
    # 2) 形状过滤（放宽到 0.52）
    if aspect < 0.52:
        return False
    # 3) 与斑马线高度重叠
    if iou_cw >= BP_VALID_IOU_THR:
        return False
    # 4) 底边窄条（疑似路牙）过滤
    bottom = bp_mask[int(0.88 * H):, :]
    if bottom.sum() > 0:
        bottom_share = bottom.sum() / float((bp_mask > 0).sum() + 1e-6)
        if bottom_share > 0.50 and (w / float(W)) < 0.35:
            return False
    return True

def _cls_of(d):
    """提取检测对象的类别ID"""
    for k in ("cls", "class_id", "category_id"):
        v = getattr(d, k, None)
        if v is not None:
            try:
                return int(v)
            except Exception:
                pass
    return None

class CrossStreetNavigator:
    """简化版过马路导航器 - 仅斑马线检测但保留导航（每帧分割 + 失败用光流保活）"""

    def __init__(self, seg_model=None, coco_model=None, obs_model=None, device_id: str = "esp32"):
        self.seg_model = seg_model
        self.device_id = device_id
        self.frame_counter = 0
        self.last_guidance = ""
        self.crosswalk_detected = False
        self.last_guide_time = 0
        self.guide_interval = 3.0  # 语音引导间隔（秒）

        # —— 状态机 ——
        self.state = STATE_SEEKING           # 当前状态
        self.green_light_counter = 0         # 绿灯稳定帧计数
        self.last_traffic_light = None       # 上一帧检测到的红绿灯
        self.last_seeking_guidance = ""      # 上一次SEEKING状态的引导文本（用于节流）
        self.last_waiting_light_time = 0     # 上次播报"正在等待绿灯"的时间
        self.crossing_end_announced = False  # 是否已播报"过马路结束"（CROSSING状态用）
        self.last_crosswalk_seen_time = 0    # 上次检测到斑马线的时间
        self.last_blindpath_announce_time = 0  # 上次播报盲道提示的时间（用于节流重复播报）

        # —— 时序/追踪状态 ——
        self.prev_mask = None            # 上一帧稳定后的二值掩码
        self.prev_mask_float = None      # 掩码 EMA 浮点缓冲
        self.prev_mask_ts = 0.0          # 最近一次掩码更新时间
        self.old_gray = None             # 上一帧灰度图（供 LK）
        self.p0 = None                   # 上一帧特征点（N,1,2）
        self.last_seed_frame = 0         # 上次播种特征点的帧号

        # —— 避障（与 blindpath 一致） ——
        self.obstacle_detector = obs_model
        self.prev_gray = None
        self.last_detected_obstacles = []
        self.last_obstacle_detection_frame = 0
        self.OBSTACLE_DETECTION_INTERVAL = int(os.getenv("AIGLASS_OBS_INTERVAL", "15"))
        self.OBSTACLE_CACHE_DURATION_FRAMES = int(os.getenv("AIGLASS_OBS_CACHE_FRAMES", "0"))
        
        # 【新增】斑马线检测间隔配置
        self.CROSSWALK_DETECTION_INTERVAL = int(os.getenv("AIGLASS_CROSSWALK_INTERVAL", "4"))  # 每4帧检测一次
        self.last_crosswalk_detection_frame = 0
        self.last_detected_crosswalk_mask = None
        self.last_detected_blindpath_mask = None

        # 自动启用障碍物检测（若未传入 obs_model）
        if self.obstacle_detector is None and os.getenv("AIGLASS_OBS_AUTO", "1") != "0":
            try:
                if ObstacleDetectorClient is not None:
                    model_path = os.getenv("AIGLASS_OBS_MODEL", "model/yoloe-11l-seg.pt")
                    self.obstacle_detector = ObstacleDetectorClient(model_path)
                    logger.info("[CROSS_STREET] 障碍物检测器已自动加载")
                else:
                    logger.warning("[CROSS_STREET] 未找到 ObstacleDetectorClient，跳过自动加载")
            except Exception as e:
                logger.warning(f"[CROSS_STREET] 自动加载障碍物检测器失败: {e}")

        # 如果模型有 predict 方法但没有 detect 方法，进行包装
        if self.seg_model and hasattr(self.seg_model, 'predict') and not hasattr(self.seg_model, 'detect'):
            logger.info("[CROSS_STREET] 包装 YOLO 模型")
            self.seg_model = YOLOModelWrapper(self.seg_model)
        
        # 【新增】打印检测间隔配置
        logger.info(f"[CROSS_STREET] 斑马线检测间隔: 每{self.CROSSWALK_DETECTION_INTERVAL}帧")

        # 确保模型在 GPU 上
        if self.seg_model and torch.cuda.is_available():
            try:
                if hasattr(self.seg_model, 'model') and hasattr(self.seg_model.model, 'to'):
                    self.seg_model.model.to('cuda')
                elif hasattr(self.seg_model, 'to'):
                    self.seg_model.to('cuda')
                logger.info("[CROSS_STREET] 模型已移至 GPU")
            except Exception as e:
                logger.warning(f"[CROSS_STREET] 无法将模型移至 GPU: {e}")

    def reset(self):
        """重置状态"""
        self.frame_counter = 0
        self.last_guidance = ""
        self.crosswalk_detected = False
        self.last_guide_time = 0
        # 状态机
        self.state = STATE_SEEKING
        self.green_light_counter = 0
        self.last_traffic_light = None
        self.last_seeking_guidance = ""
        self.last_waiting_light_time = 0
        self.crossing_end_announced = False
        self.last_crosswalk_seen_time = 0
        self.last_blindpath_announce_time = 0
        # 追踪
        self.prev_mask = None
        self.prev_mask_float = None
        self.prev_mask_ts = 0.0
        self.old_gray = None
        self.p0 = None
        self.last_seed_frame = 0
        # 避障缓存
        self.prev_gray = None
        self.last_detected_obstacles = []
        self.last_obstacle_detection_frame = 0
        # 重置红绿灯检测状态
        if TRAFFIC_LIGHT_AVAILABLE and trafficlight_detection:
            trafficlight_detection.reset_detection_state()
        logger.info("[CROSS_STREET] 导航器已重置")

    # —— 打点/追踪辅助 ——
    @staticmethod
    def _inner_offset_edge(mask_bin: np.ndarray, offset_px=5, edge_dilate_px=2) -> np.ndarray:
        """对二值掩码做内收后提边缘，便于在目标内部打光流特征点"""
        if offset_px > 0:
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*offset_px+1, 2*offset_px+1))
            eroded = cv2.erode(mask_bin.astype(np.uint8), k, iterations=1)
        else:
            eroded = mask_bin.astype(np.uint8)
        edges = cv2.Canny(eroded*255, 50, 150)
        if edge_dilate_px > 0:
            k2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*edge_dilate_px+1, 2*edge_dilate_px+1))
            edges = cv2.dilate(edges, k2, iterations=1)
        return edges  # uint8 0/255

    @staticmethod
    def _hull_mask_from_points(points: np.ndarray, shape_hw: tuple) -> Optional[np.ndarray]:
        """从一组点的凸包生成二值掩码"""
        if points is None or len(points) < 3:
            return None
        H, W = shape_hw
        pts = points.reshape(-1, 2).astype(np.float32)
        hull = cv2.convexHull(pts.reshape(-1,1,2))
        poly = hull.reshape(-1, 2).astype(np.int32)
        mask = np.zeros((H, W), dtype=np.uint8)
        cv2.fillPoly(mask, [poly], 1)
        return mask

    def _seed_points_from_mask(self, gray: np.ndarray, mask_bin: np.ndarray) -> Optional[np.ndarray]:
        """基于掩码的内收边界，播种 LK 光流特征点"""
        edge_mask = self._inner_offset_edge(mask_bin, offset_px=INNER_OFFSET_PX_LOCK, edge_dilate_px=EDGE_DILATE_PX)
        try:
            pts = cv2.goodFeaturesToTrack(gray, mask=edge_mask, **FEATURE_PARAMS)
            return pts
        except Exception as e:
            logger.warning(f"[CROSS_STREET] goodFeaturesToTrack 失败: {e}")
            return None

    @staticmethod
    def _ensure_binary_mask(mask: np.ndarray, shape_hw: tuple) -> np.ndarray:
        """阈值化并调整尺寸到图像大小，返回二值 0/1 uint8"""
        H, W = shape_hw
        if mask.dtype != np.uint8:
            mask = (mask > 0.5).astype(np.uint8)
        if mask.shape[:2] != (H, W):
            mask = cv2.resize(mask, (W, H), interpolation=cv2.INTER_NEAREST)
        return (mask > 0).astype(np.uint8)

    def _postprocess_mask(self, mask_bin: np.ndarray) -> np.ndarray:
        """形态学净化 + 移除小碎片，缓解毛边与噪点"""
        try:
            m = (mask_bin > 0).astype(np.uint8)
            H, W = m.shape[:2]
            # 轻度开闭操作，去毛刺并填补细小空洞
            k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
            m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k_open, iterations=1)
            m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k_close, iterations=1)
            # 移除过小连通域
            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
            if num_labels > 1:
                areas = stats[1:, cv2.CC_STAT_AREA]
                keep_area = max(int(0.003 * H * W), 1500)  # 约 0.3% 画面或 1500 px
                keep_labels = np.where(areas >= keep_area)[0] + 1
                m2 = np.zeros_like(m)
                for lbl in keep_labels:
                    m2[labels == lbl] = 1
                if m2.sum() > 0:
                    m = m2
            return (m > 0).astype(np.uint8)
        except Exception:
            return (mask_bin > 0).astype(np.uint8)

    @staticmethod
    def _largest_contour(mask_bin: np.ndarray):
        cts, _ = cv2.findContours((mask_bin>0).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cts:
            return None
        return max(cts, key=cv2.contourArea)


    def _mask_center(self, mask: np.ndarray):
        """用图像矩计算掩码质心；失败返回 None"""
        M = cv2.moments((mask > 0).astype(np.uint8))
        if abs(M["m00"]) < 1e-6:
            return None
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
        return (cx, cy)
    
    def _is_crosswalk_near(self, mask: np.ndarray, h: int, w: int) -> bool:
        """判断斑马线是否"很近"（到用户跟前）- 更严格的判定条件"""
        if mask is None:
            return False
        area = int(mask.sum())
        area_ratio = float(area) / float(h * w)
        
        # 获取底部位置和高度
        ys = np.where(mask > 0)[0]
        if ys.size == 0:
            return False
        top_y = int(ys.min())
        bottom_y = int(ys.max())
        mask_height = bottom_y - top_y + 1
        height_ratio = float(mask_height) / float(h)
        bottom_ratio = float(bottom_y) / float(h)
        
        # 需要同时满足多个条件（AND逻辑，更严格）：
        # 1. 面积足够大
        # 2. 底部位置足够低
        # 3. 高度占比足够大（防止只是因为抬头导致的误判）
        is_near = (area_ratio >= CROSSWALK_NEAR_AREA_RATIO and 
                   bottom_ratio >= CROSSWALK_NEAR_BOTTOM_RATIO and
                   height_ratio >= CROSSWALK_NEAR_MIN_HEIGHT_RATIO)
        return is_near
    
    def _is_crosswalk_almost_done(self, mask: np.ndarray, h: int, w: int) -> bool:
        """判断斑马线是否"快消失"（斑马线在画面底部且面积很小）- 更严格的判定"""
        if mask is None:
            return False
        area = int(mask.sum())
        area_ratio = float(area) / float(h * w)
        
        ys = np.where(mask > 0)[0]
        if ys.size == 0:
            return False
        
        # 计算斑马线的顶部和底部位置
        top_y = int(ys.min())
        bottom_y = int(ys.max())
        
        top_ratio = float(top_y) / float(h)
        bottom_ratio = float(bottom_y) / float(h)
        
        # 更严格的判断条件（避免过早触发）：
        # 1. 顶部已经过了画面70%（>0.7），说明斑马线主要在画面最下方
        # 2. 底部接近画面底部（>0.85）
        # 3. 面积很小（<0.08），说明快消失了
        is_almost_done = (top_ratio > 0.7 and bottom_ratio > 0.85 and area_ratio < 0.08)
        return is_almost_done
    
    def _compute_远_distance_alignment(self, mask: np.ndarray, h: int, w: int) -> tuple:
        """计算远距离对准的角度和偏移（基于mask几何，不依赖条纹）"""
        ys, xs = np.where(mask > 0)
        if xs.size < 50:
            return 0.0, 0.0
        
        # 使用PCA计算主方向
        pts = np.stack([xs.astype(np.float32), ys.astype(np.float32)], axis=1)
        mean = pts.mean(axis=0)
        cov = np.cov((pts - mean).T)
        eigvals, eigvecs = np.linalg.eig(cov)
        v = eigvecs[:, np.argmax(eigvals)]
        
        # 计算角度（相对水平）
        angle = np.degrees(np.arctan2(v[1], v[0]))
        if angle > 90: angle -= 180
        if angle < -90: angle += 180
        
        # 计算水平偏移（质心相对画面中心）
        cx = float(mean[0])
        offset = (cx - (w / 2.0)) / max(1.0, w / 2.0)
        
        return float(angle), float(offset)

    def _draw_line_vertical_angle(self, image, center, angle_deg, length_ratio=0.7, color=(255, 255, 0), thickness=3):
        """
        以“竖直方向”为0°基准，angle_deg>0 表示左偏，<0 表示右偏。
        在 center 处画一条通过点的直线。
        """
        H, W = image.shape[:2]
        half_len = int(0.5 * length_ratio * min(H, W))
        rad = np.radians(angle_deg)
        # 竖直基准: 向上的单位向量(0, -1)
        # 旋转 angle 后的方向向量 = (sin, -cos)
        vx = np.sin(rad);
        vy = -np.cos(rad)
        x0, y0 = center
        p1 = (int(x0 - vx * half_len), int(y0 - vy * half_len))
        p2 = (int(x0 + vx * half_len), int(y0 + vy * half_len))
        cv2.line(image, p1, p2, color, thickness)

    def _draw_dashed_line_vertical_angle(self, image, center, angle_deg, length_ratio=0.7,
                                         dash=12, gap=8, color=(255, 255, 255), thickness=2):
        """同样以竖直为0°，画 through center 的虚线。"""
        H, W = image.shape[:2]
        half_len = int(0.5 * length_ratio * min(H, W))
        rad = np.radians(angle_deg)
        vx = np.sin(rad);
        vy = -np.cos(rad)
        x0, y0 = center
        x1, y1 = int(x0 - vx * half_len), int(y0 - vy * half_len)
        x2, y2 = int(x0 + vx * half_len), int(y0 + vy * half_len)

        # 沿整条线分段画虚线
        total_len = int(np.hypot(x2 - x1, y2 - y1))
        if total_len <= 0: return
        dx = (x2 - x1) / total_len
        dy = (y2 - y1) / total_len
        s = 0
        while s < total_len:
            e = min(s + dash, total_len)
            xa, ya = int(x1 + dx * s), int(y1 + dy * s)
            xb, yb = int(x1 + dx * e), int(y1 + dy * e)
            cv2.line(image, (xa, ya), (xb, yb), color, thickness)
            s += (dash + gap)

    def _offset_from_centerline(self, center_pt, angle_vertical_deg, width, height, y_ratio=0.75) -> float:
        """
        基于“青色法线中央直线”计算左右偏移：
        - angle_vertical_deg: 以“竖直方向为0°”的角（与 _draw_line_vertical_angle 相同坐标系）
        - center_pt: 掩码质心 (cx, cy)
        - y_ratio: 预瞄行高度（相对图像高度的比例），默认0.75（底部偏下更稳定）
        返回：归一化偏移（右为正，左为负），与原 offset 含义一致。
        """
        if center_pt is None:
            return 0.0
        x0, y0 = center_pt
        rad = np.radians(angle_vertical_deg)
        # 与 _draw_line_vertical_angle 完全一致的方向向量定义
        vx = np.sin(rad)
        vy = -np.cos(rad)

        # 取预瞄行的 y
        y_target = float(int(height * y_ratio))

        # 若法线几乎水平（极少出现），避免除0
        if abs(vy) < 1e-6:
            x_at = float(x0)
        else:
            t = (y_target - float(y0)) / vy
            x_at = float(x0) + t * vx

        x_at = float(np.clip(x_at, 0, width - 1))
        # 与旧 offset 定义一致：相对画面中心的归一化水平偏移（右正左负）
        return float((x_at - (width / 2.0)) / max(1.0, width / 2.0))

    def _compute_angle_and_offset(self, mask: np.ndarray) -> tuple:
        """计算斑马线的角度和偏移（PCA 回退用）"""
        H, W = mask.shape[:2]
        ys, xs = np.where(mask > 0)
        if xs.size < 50:
            return 0.0, 0.0

        # 使用PCA计算主方向
        pts = np.stack([xs.astype(np.float32), ys.astype(np.float32)], axis=1)
        mean = pts.mean(axis=0)
        cov = np.cov((pts - mean).T)
        eigvals, eigvecs = np.linalg.eig(cov)
        v = eigvecs[:, np.argmax(eigvals)]

        # 计算角度
        angle = np.degrees(np.arctan2(v[1], v[0]))
        if angle > 90: angle -= 180
        if angle < -90: angle += 180

        # 计算水平偏移
        cx = float(mean[0])
        offset = (cx - (W / 2.0)) / max(1.0, W / 2.0)

        return float(angle), float(offset)

    def _estimate_angle_by_stripes(self, mask: np.ndarray, gray: np.ndarray) -> Optional[Dict[str, Any]]:
        """
        基于掩码内条纹（霍夫线）估计角度和可视化（放宽参数 + 鲁棒聚类）:
        返回 dict: {
          'angle_deg': float,       # 相对竖直方向偏角（[-45,45]），正=左偏，负=右偏
          'lines': List[(x1,y1,x2,y2)],  # 选中的条纹线段（图像坐标）
          'confidence': float,      # [0,1] 加权圆均值合力强度
          'count': int              # 线段数量
        }
        """
        try:
            H, W = mask.shape[:2]
            roi_top = int(0.45 * H)  # 关注下半部分，稳定性更好
            m_roi = (mask[roi_top:H, :] > 0).astype(np.uint8)
            g_roi = gray[roi_top:H, :]

            # 放宽边缘阈值
            g_blur = cv2.GaussianBlur(g_roi, (5, 5), 0)
            edges = cv2.Canny(g_blur, 50, 150)
            edges = cv2.bitwise_and(edges, edges, mask=m_roi * 255)

            # 放宽霍夫参数
            lines = cv2.HoughLinesP(
                edges,
                rho=1,
                theta=np.pi / 180,
                threshold=max(30, int(0.03 * W)),
                minLineLength=int(0.15 * W),
                maxLineGap=20
            )
            if lines is None:
                return None

            angles, weights = [], []
            all_lines = []
            for x1, y1, x2, y2 in lines.reshape(-1, 4):
                dx, dy = x2 - x1, y2 - y1
                length = float(np.hypot(dx, dy))
                if length < 8:
                    continue
                ang = float(np.degrees(np.arctan2(dy, dx)))  # 相对 x 轴
                if ang > 90: ang -= 180
                if ang < -90: ang += 180
                # 放宽角度接受范围
                if abs(ang) > 65:
                    continue
                # 底部越近权重越大
                ymid = (y1 + y2) * 0.5 + roi_top
                w = length * (0.5 + 0.5 * (ymid / max(1.0, H)))
                angles.append(ang)
                weights.append(w)
                all_lines.append((int(x1), int(y1 + roi_top), int(x2), int(y2 + roi_top)))

            if len(angles) < 5:
                return None

            # 角度鲁棒聚类：加权中位数 + MAD 剔除离群
            angs = np.array(angles, dtype=np.float32)
            wts = np.array(weights, dtype=np.float32)

            # 加权中位数
            sort_idx = np.argsort(angs)
            angs_sorted = angs[sort_idx]
            wts_sorted = wts[sort_idx]
            cum = np.cumsum(wts_sorted)
            med_idx = np.searchsorted(cum, cum[-1] * 0.5)
            med = float(angs_sorted[min(max(med_idx, 0), len(angs_sorted) - 1)])

            # MAD（围绕中位数的绝对偏差中位数），阈值更宽
            dev = np.abs(angs - med)
            mad = float(np.median(dev) + 1e-6)
            deg_thr = max(12.0, 2.8 * mad)  # 适度放宽
            keep = dev <= deg_thr

            if keep.sum() >= 3:
                angs_keep = angs[keep]
                wts_keep = wts[keep]
                lines_keep = [all_lines[i] for i, k in enumerate(keep) if k]
            else:
                angs_keep = angs
                wts_keep = wts
                lines_keep = all_lines

            # 加权圆均值
            ang_rad = np.radians(angs_keep)
            C = float(np.sum(wts_keep * np.cos(ang_rad)))
            S = float(np.sum(wts_keep * np.sin(ang_rad)))
            norm = float(np.sum(wts_keep) + 1e-6)
            if abs(C) < 1e-6 and abs(S) < 1e-6:
                return None
            mean = float(np.degrees(np.arctan2(S, C)))
            confidence = float(np.hypot(C, S) / norm)

            return {
                "angle_deg": mean,
                "lines": lines_keep,
                "confidence": confidence,
                "count": len(lines_keep),
            }
        except Exception:
            return None

    def _get_crosswalk_guidance_features(self, mask: np.ndarray, image_shape: tuple) -> dict:
        """计算斑马线引导特征（鲁棒中心线 + 目标点 + 角度/偏移）"""
        try:
            height, width = image_shape[:2]
            min_run_px = max(12, int(width * 0.02))
            centerline_rows = []

            # 自底向上扫描，按最大连续区段取左右边界的中点，忽略零散噪点
            for y in range(height - 1, int(height * 0.4), -5):
                row = mask[y, :]
                xs = np.where(row > 0)[0]
                if xs.size <= min_run_px:
                    continue
                splits = np.where(np.diff(xs) > 1)[0] + 1
                segments = np.split(xs, splits) if xs.size else []
                if not segments:
                    continue
                seg = max(segments, key=lambda s: (s[-1] - s[0] + 1))
                if seg.size == 0 or (seg[-1] - seg[0] + 1) < min_run_px:
                    continue
                center_x = 0.5 * (seg[0] + seg[-1])
                centerline_rows.append([y, center_x])

            if len(centerline_rows) < 10:
                return None

            data = np.array(centerline_rows, dtype=np.float32)
            y_coords, x_coords = data[:, 0], data[:, 1]

            # 初始加权（底部更重要）
            w_base = y_coords / float(height)
            coeffs = np.polyfit(y_coords, x_coords, 2, w=w_base)
            poly = np.poly1d(coeffs)

            # 一次鲁棒再加权（抑制弯折/异常点）
            res = x_coords - poly(y_coords)
            mad = np.median(np.abs(res - np.median(res))) + 1e-6
            c = 2.5 * mad
            w_robust = 1.0 / (1.0 + (res / c) ** 2)
            w_total = w_base * w_robust
            coeffs = np.polyfit(y_coords, x_coords, 2, w=w_total)
            poly = np.poly1d(coeffs)

            # 目标点与绘制点
            lookahead_y = int(height * 0.6)
            target_x = float(poly(lookahead_y))
            plot_y = np.arange(int(height * 0.4), height, 5).astype(int)
            plot_x = poly(plot_y).astype(int)
            centerline_points = np.vstack((plot_x, plot_y)).T.tolist()

            # 角度（基于 x(y) 的导数）与水平偏移
            dpoly = np.polyder(poly)
            dx_dy = float(dpoly(lookahead_y))
            angle_deg = float(np.degrees(np.arctan(dx_dy)))
            offset = float((target_x - (width / 2.0)) / max(1.0, width / 2.0))

            # 截断目标点范围
            tx = int(np.clip(target_x, 0, width - 1))
            return {
                "target_point": (tx, lookahead_y),
                "centerline_points": centerline_points,
                "angle_deg": angle_deg,
                "offset": offset,
            }
        except Exception:
            return None

    # —— 障碍物：光流辅助方法（与 blindpath 一致） ——
    def _get_edge_mask(self, mask, offset=10):
        """获取掩码的内边缘区域，用于特征点检测"""
        if mask is None:
            return None
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (offset*2, offset*2))
        inner = cv2.erode(mask, kernel, iterations=1)
        edge = cv2.subtract(mask, inner)
        kernel_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        edge = cv2.dilate(edge, kernel_small, iterations=1)
        return edge

    def _predict_mask_with_flow(self, prev_mask, prev_gray, curr_gray):
        """使用 Lucas-Kanade 光流预测掩码位置（与 blindpath 一致）"""
        try:
            edge_mask = self._get_edge_mask(prev_mask, offset=10)
            p0 = cv2.goodFeaturesToTrack(prev_gray, mask=edge_mask, **FEATURE_PARAMS)
            if p0 is None or len(p0) < 8:
                return None
            p1, st, err = cv2.calcOpticalFlowPyrLK(prev_gray, curr_gray, p0, None, **LK_PARAMS)
            if p1 is None or st is None:
                return None
            good_new = p1[st == 1]
            good_old = p0[st == 1]
            if len(good_new) < 5:
                return None
            M, inliers = cv2.estimateAffinePartial2D(good_old, good_new, method=cv2.RANSAC, ransacReprojThreshold=5.0)
            if M is None:
                return None
            H, W = curr_gray.shape[:2]
            flow_mask = cv2.warpAffine(prev_mask, M, (W, H),
                                       flags=cv2.INTER_NEAREST,
                                       borderMode=cv2.BORDER_CONSTANT,
                                       borderValue=0)
            return flow_mask
        except Exception:
            return None

    # —— 障碍物：检测与可视化（与 blindpath 一致） ——
    def _detect_obstacles(self, image, path_mask=None):
        """检测障碍物，调用 ObstacleDetectorClient.detect（与 blindpath 同步）"""
        logger.info(f"[_detect_obstacles] 开始执行，Frame={self.frame_counter}, obstacle_detector={'已加载' if self.obstacle_detector else '未加载'}")
        if self.obstacle_detector is None:
            logger.warning("[_detect_obstacles] 障碍物检测器未加载！")
            return []

        try:
            logger.info(f"[_detect_obstacles] 调用ObstacleDetectorClient.detect()... image.shape={image.shape}")
            detected_obstacles = self.obstacle_detector.detect(image, path_mask=path_mask)
            logger.info(f"[_detect_obstacles] 返回 {len(detected_obstacles)} 个物体")

            # 补充派生字段
            H, W = image.shape[:2]
            for i, obj in enumerate(detected_obstacles):
                if 'mask' in obj and obj['mask'] is not None:
                    y_coords, x_coords = np.where(obj['mask'] > 0)
                    if len(y_coords) > 0 and len(x_coords) > 0:
                        x1, y1 = int(np.min(x_coords)), int(np.min(y_coords))
                        x2, y2 = int(np.max(x_coords)), int(np.max(y_coords))
                        obj['box_coords'] = (x1, y1, x2, y2)
                        if 'y_position_ratio' not in obj:
                            obj['y_position_ratio'] = obj.get('center_y', 0) / H
                        if 'label' not in obj:
                            obj['label'] = obj.get('name', 'unknown')
                        if 'center' not in obj:
                            obj['center'] = (obj.get('center_x', 0), obj.get('center_y', 0))
                        if 'confidence' not in obj:
                            obj['confidence'] = 0.5
            return detected_obstacles
        except Exception as e:
            logger.error(f"[_detect_obstacles] 障碍物检测失败: {e}", exc_info=True)
            return []

    def _stabilize_obstacle_list(self, obstacles, prev_obstacles, prev_gray, curr_gray, image_shape, threshold=0.5):
        """稳定障碍物检测结果，避免重复叠加（与 blindpath 一致）"""
        if not obstacles or prev_gray is None or curr_gray is None:
            return obstacles

        H, W = image_shape
        stabilized = []
        used_prev = set()
        for curr_obs in obstacles:
            if 'mask' not in curr_obs or curr_obs['mask'] is None:
                stabilized.append(curr_obs)
                continue
            curr_mask = curr_obs['mask']
            best_match = None
            best_iou = 0
            best_idx = -1

            if prev_obstacles:
                for idx, prev_obs in enumerate(prev_obstacles):
                    if idx in used_prev or 'mask' not in prev_obs:
                        continue
                    flow_mask = self._predict_mask_with_flow(prev_obs['mask'], prev_gray, curr_gray)
                    if flow_mask is None:
                        flow_mask = prev_obs['mask']
                    inter = np.logical_and(curr_mask > 0, flow_mask > 0).sum()
                    union = np.logical_or(curr_mask > 0, flow_mask > 0).sum()
                    iou = float(inter) / float(union) if union > 0 else 0.0
                    if iou > best_iou and iou > threshold:
                        best_iou = iou
                        best_match = flow_mask
                        best_idx = idx

            if best_match is not None and best_idx >= 0:
                used_prev.add(best_idx)
                fused_mask = ((0.8 * curr_mask + 0.2 * best_match) > 128).astype(np.uint8) * 255
                curr_obs['mask'] = fused_mask
                self._update_obstacle_properties(curr_obs, H, W)
            stabilized.append(curr_obs)
        return stabilized

    def _update_obstacle_properties(self, obs, H, W):
        """更新障碍物的派生属性"""
        if 'mask' not in obs or obs['mask'] is None:
            return
        mask = obs['mask']
        y_coords, x_coords = np.where(mask > 0)
        if len(y_coords) > 0:
            obs['area'] = int(len(y_coords))
            obs['center_x'] = float(np.mean(x_coords))
            obs['center_y'] = float(np.mean(y_coords))
            obs['y_position_ratio'] = obs['center_y'] / H
            obs['area_ratio'] = obs['area'] / float(H * W)
            obs['bottom_y_ratio'] = np.max(y_coords) / float(H)
            x1, y1 = int(np.min(x_coords)), int(np.min(y_coords))
            x2, y2 = int(np.max(x_coords)), int(np.max(y_coords))
            obs['box_coords'] = (x1, y1, x2, y2)

    # —— 可视化通用方法（与 blindpath 一致） ——
    def _parse_color(self, color_str):
        """解析颜色字符串，返回BGR格式"""
        try:
            if isinstance(color_str, tuple) and len(color_str) == 3:
                return color_str
            if color_str.startswith('rgba('):
                values = color_str[5:-1].split(',')
                r, g, b = int(values[0]), int(values[1]), int(values[2])
                return (b, g, r)  # OpenCV: BGR
            elif color_str == 'yellow':
                return (0, 255, 255)
            elif color_str == 'red':
                return (0, 0, 255)
            else:
                return (0, 0, 255)
        except:
            return (0, 0, 255)

    def _add_obstacle_visualization(self, obstacle, visualizations, pulse_effect=False):
        """添加障碍物可视化（简化版：仅边框，近红远黄）"""
        try:
            bottom_y_ratio = obstacle.get('bottom_y_ratio', 0)
            area_ratio = obstacle.get('area_ratio', 0)
            is_near = bottom_y_ratio > 0.7 or area_ratio > 0.1

            if 'mask' in obstacle and obstacle['mask'] is not None:
                mask = obstacle['mask']
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if contours:
                    max_contour = max(contours, key=cv2.contourArea)
                    points = max_contour.squeeze(1)[::5].tolist()
                    
                    # 根据距离选择边框颜色：近距离红色，远距离黄色
                    if is_near:
                        outline_color = "rgba(255, 0, 0, 1.0)"  # 红色
                        thickness = 3
                    else:
                        outline_color = "rgba(255, 255, 0, 0.8)"  # 黄色
                        thickness = 2

                    # 只添加边框，不添加填充和文字
                    visualizations.append({
                        "type": "outline",
                        "points": points,
                        "color": outline_color,
                        "thickness": thickness
                    })
        except Exception as e:
            logger.error(f"[_add_obstacle_visualization] 添加障碍物可视化失败: {e}")

    def _draw_command_button(self, image, text):
        """绘制底部中央的指令按钮（类似yolomedia风格）"""
        try:
            H, W = image.shape[:2]
            full_text = f"当前指令：{text if text else '—'}"
            
            # 按钮参数
            font_px = 14
            pad_x, pad_y = 14, 8
            bottom_margin = 28
            
            # 计算文字尺寸
            if PIL_AVAILABLE:
                try:
                    from PIL import Image as PILImage, ImageDraw, ImageFont
                    # 尝试加载中文字体
                    font = None
                    for font_path in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"]:
                        if os.path.exists(font_path):
                            try:
                                font = ImageFont.truetype(font_path, font_px)
                                break
                            except:
                                continue
                    if font:
                        bbox = ImageDraw.Draw(PILImage.new('RGB', (1, 1))).textbbox((0, 0), full_text, font=font)
                        tw = max(1, bbox[2] - bbox[0])
                        th = max(1, bbox[3] - bbox[1])
                    else:
                        scale = font_px / 24.0
                        (tw, th), _ = cv2.getTextSize(full_text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
                except:
                    scale = font_px / 24.0
                    (tw, th), _ = cv2.getTextSize(full_text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
            else:
                scale = font_px / 24.0
                (tw, th), _ = cv2.getTextSize(full_text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
            
            # 计算按钮位置（底部居中）
            bw = tw + pad_x * 2
            bh = th + pad_y * 2
            radius = max(10, bh // 2)
            
            cx = W // 2
            left = max(8, cx - bw // 2)
            top = H - bottom_margin - bh
            right = min(W - 8, left + bw)
            bottom = top + bh
            
            # 绘制半透明圆角背景
            overlay = image.copy()
            bg_color = (26, 32, 41)  # 深色背景
            border_color = (60, 76, 102)  # 边框
            
            # 圆角矩形（中间+两个圆）
            cv2.rectangle(overlay, (left + radius, top), (right - radius, bottom), bg_color, -1)
            cv2.circle(overlay, (left + radius, (top + bottom) // 2), radius, bg_color, -1)
            cv2.circle(overlay, (right - radius, (top + bottom) // 2), radius, bg_color, -1)
            
            # 混合半透明
            cv2.addWeighted(overlay, 0.75, image, 0.25, 0, image)
            
            # 绘制边框
            cv2.rectangle(image, (left + radius, top), (right - radius, bottom), border_color, 1)
            cv2.circle(image, (left + radius, (top + bottom) // 2), radius, border_color, 1)
            cv2.circle(image, (right - radius, (top + bottom) // 2), radius, border_color, 1)
            
            # 绘制文字
            text_x = left + pad_x
            text_y = top + pad_y + th
            
            if PIL_AVAILABLE and font:
                # 使用PIL绘制中文
                pil_img = PILImage.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
                draw = ImageDraw.Draw(pil_img)
                draw.text((text_x, top + pad_y), full_text, font=font, fill=(255, 255, 255))
                image = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            else:
                # 使用OpenCV绘制
                cv2.putText(image, full_text, (text_x, text_y), 
                           cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), 1)
            
            return image
        except Exception as e:
            logger.error(f"绘制指令按钮失败: {e}")
            return image
    
    def _draw_data_panel_no_bg(self, image, data, position=(15, 15)):
        """绘制数据面板（无黑底，描边文字），与 blindpath 一致"""
        if not PIL_AVAILABLE:
            return image
        try:
            pil_img = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_img, "RGBA")
            env_scale = float(os.getenv("AIGLASS_PANEL_SCALE", "0.7"))
            base_font_size = max(10, int(round(14 * env_scale)))
            font = None
            font_paths = [
                "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/simhei.ttf",
                "C:/Windows/Fonts/simsun.ttc",
                "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
                "/System/Library/Fonts/PingFang.ttc",
            ]
            for font_path in font_paths:
                try:
                    if os.path.exists(font_path):
                        font = ImageFont.truetype(font_path, base_font_size)
                        break
                except:
                    continue
            if font is None:
                font = ImageFont.load_default()

            y_offset = position[1]
            for key, value in data.items():
                text = f"{key}: {value}"
                for dx in [-1, 0, 1]:
                    for dy in [-1, 0, 1]:
                        if dx != 0 or dy != 0:
                            draw.text((position[0] + dx, y_offset + dy), text,
                                      font=font, fill=(0, 0, 0, 255))
                draw.text((position[0], y_offset), text, font=font, fill=(255, 255, 255, 255))
                y_offset += base_font_size + 5
            return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        except Exception as e:
            logger.warning(f"绘制数据面板失败: {e}")
            return image

    def _draw_visualizations(self, image, viz_elements):
        """增强的可视化绘制方法（与 blindpath 一致）"""
        if not viz_elements:
            return image
        current_time = time.time()
        panel_elements = [v for v in viz_elements if v.get("type") == "data_panel"]
        standard_elements = [v for v in viz_elements if v.get("type") != "data_panel"]

        # 第一遍：半透明填充
        for element in standard_elements:
            elem_type = element.get("type")
            if elem_type in ['blind_path_mask', 'obstacle_mask', 'crosswalk_mask']:
                points = np.array(element.get("points", []), dtype=np.int32)
                if points.size > 0:
                    color = self._parse_color(element.get("color", "rgba(255, 255, 255, 0.5)"))
                    if element.get("effect") == "pulse":
                        pulse_speed = element.get("pulse_speed", 1.0)
                        alpha = 0.3 + 0.3 * np.sin(current_time * pulse_speed * 2 * np.pi)
                    else:
                        alpha = 0.4
                    x, y, w, h = cv2.boundingRect(points)
                    x = max(0, x); y = max(0, y)
                    w = min(w, image.shape[1] - x)
                    h = min(h, image.shape[0] - y)
                    if w > 0 and h > 0:
                        binary_mask = np.zeros((h, w), dtype=np.uint8)
                        local_points = points - np.array([x, y])
                        cv2.fillPoly(binary_mask, [local_points], 255)
                        local_region = image[y:y+h, x:x+w].copy()
                        color_overlay = np.zeros((h, w, 3), dtype=np.uint8)
                        color_overlay[:] = color
                        for c in range(3):
                            local_region[:, :, c] = np.where(
                                binary_mask > 0,
                                (1 - alpha) * local_region[:, :, c] + alpha * color_overlay[:, :, c],
                                local_region[:, :, c]
                            )
                        image[y:y+h, x:x+w] = local_region

        # 第二遍：轮廓和元素
        for element in standard_elements:
            elem_type = element.get("type")
            if elem_type == 'outline':
                points = np.array(element.get("points", []), dtype=np.int32)
                if points.size > 0:
                    color = self._parse_color(element.get("color", "rgba(255, 255, 255, 1.0)"))
                    thickness = element.get("thickness", 3)
                    cv2.polylines(image, [points], isClosed=True, color=color, thickness=thickness)
            elif elem_type == 'polyline':
                points = np.array(element.get("points", []), dtype=np.int32)
                if points.size > 0:
                    color = self._parse_color(element.get("color", "rgba(255, 255, 0, 1.0)"))
                    thickness = element.get("width", 2)
                    cv2.polylines(image, [points], isClosed=False, color=color, thickness=thickness)
            elif elem_type == 'circle':
                center = tuple(element.get("center", (0, 0)))
                radius = element.get("radius", 10)
                color = self._parse_color(element.get("color", "rgba(255, 0, 0, 1.0)"))
                thickness = -1 if element.get("filled", True) else 2
                cv2.circle(image, center, radius, color, thickness)
            elif elem_type == 'arrow':
                start = tuple(element.get("start", (0, 0)))
                end = tuple(element.get("end", (100, 100)))
                color = self._parse_color(element.get("color", "rgba(0, 255, 255, 1.0)"))
                thickness = element.get("thickness", 2)
                tip_length = element.get("tip_length", 0.3)
                cv2.arrowedLine(image, start, end, color, thickness, tipLength=tip_length)
            elif elem_type == 'text_with_bg':
                text = element.get("text", "")
                pos = element.get("position", [10, 30])
                font_scale = element.get("font_scale", 0.6)
                color = self._parse_color(element.get("color", "rgba(255, 255, 255, 1.0)"))
                for dx in [-1, 0, 1]:
                    for dy in [-1, 0, 1]:
                        if dx != 0 or dy != 0:
                            cv2.putText(image, text, (pos[0] + dx, pos[1] + dy),
                                        cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), 3)
                cv2.putText(image, text, tuple(pos), cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, 2)
            elif elem_type == 'warning_icon':
                pos = element.get("position", (100, 100))
                level = element.get("level", "info")
                text = element.get("text", "")
                flash = element.get("flash", False)
                if level == "danger":
                    icon_color = (0, 0, 255)
                    text_color = (255, 255, 255)
                elif level == "warning":
                    icon_color = (0, 165, 255)
                    text_color = (255, 255, 255)
                else:
                    icon_color = (0, 255, 255)
                    text_color = (0, 0, 0)
                if flash:
                    alpha = 0.5 + 0.5 * np.sin(current_time * 4 * np.pi)
                    icon_color = tuple(int(c * alpha) for c in icon_color)
                triangle = np.array([
                    [pos[0], pos[1] - 20],
                    [pos[0] - 15, pos[1]],
                    [pos[0] + 15, pos[1]]
                ], np.int32)
                cv2.fillPoly(image, [triangle], icon_color)
                cv2.polylines(image, [triangle], True, (255, 255, 255), 2)
                cv2.putText(image, "!", (pos[0] - 5, pos[1] - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                if text:
                    font_scale = 0.5
                    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
                    text_pos = (pos[0] - tw // 2, pos[1] + 20)
                    for dx in [-1, 0, 1]:
                        for dy in [-1, 0, 1]:
                            if dx != 0 or dy != 0:
                                cv2.putText(image, text, (text_pos[0] + dx, text_pos[1] + dy),
                                            cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), 2)
                    cv2.putText(image, text, text_pos, cv2.FONT_HERSHEY_SIMPLEX, font_scale, text_color, 1)
            elif elem_type == 'text':
                text = element.get("text", "")
                pos = tuple(element.get("pos", (10, 30)))
                cv2.putText(image, text, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        # 数据面板
        if PIL_AVAILABLE:
            for panel in panel_elements:
                image = self._draw_data_panel_no_bg(image, panel["data"], panel["position"])
        else:
            for panel in panel_elements:
                y_offset = panel["position"][1]
                for key, value in panel["data"].items():
                    text = f"{key}: {value}"
                    for dx in [-1, 0, 1]:
                        for dy in [-1, 0, 1]:
                            if dx != 0 or dy != 0:
                                cv2.putText(image, text, (panel["position"][0] + dx, y_offset + dy),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3)
                    cv2.putText(image, text, (panel["position"][0], y_offset),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
                    y_offset += 25
        return image

    def _speech_for_obstacle(self, name: str) -> str:
        """生成障碍物语音提示"""
        k = (name or '').strip().lower()
        if k == 'person': return "前方有人，注意避让。"
        if k == 'car': return "前方有车，注意避让。"
        if k == 'bicycle': return "前方有自行车，停一下。"
        if k == 'motorcycle': return "前方有摩托车，停一下。"
        if k == 'bus': return "前方有公交车，停一下。"
        if k == 'truck': return "前方有卡车，停一下。"
        if k == 'scooter': return "前方有电瓶车，停一下。"
        if k == 'stroller': return "前方有婴儿车，停一下。"
        if k == 'dog': return "前方有狗，停一下。"
        if k == 'animal': return "前方有动物，停一下。"
        return "前方有障碍物，注意避让。"

    def process_frame(self, bgr_image: np.ndarray) -> CrossStreetResult:
        """处理单帧图像（每帧分割；若失败，用光流追踪上一帧掩码保持可视化与导航）"""
        self.frame_counter += 1
        current_time = time.time()

        try:
            annotated = bgr_image.copy()
            h, w = bgr_image.shape[:2]
            frame_visualizations = []

            # 当前灰度图供 LK 与避障稳定使用
            gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)

            # ========== 1) 间隔执行分割（每4帧检测一次） ==========
            crosswalk_mask = None
            blindpath_mask = None
            det_area = 0

            # 【新增】检测间隔逻辑
            if self.seg_model and self.frame_counter % self.CROSSWALK_DETECTION_INTERVAL == 0:
                # 执行新的检测
                # 使用较低的基础阈值获取所有候选
                base_thr = min(CROSSWALK_MIN_CONF, BLIND_MIN_CONF)
                detections = self.seg_model.detect(bgr_image, confidence_threshold=base_thr) or []
                
                # 按类别ID和名称分拣
                raw_cw, raw_bp = [], []
                for det in detections:
                    if not hasattr(det, 'mask') or det.mask is None:
                        continue
                    
                    cid = _cls_of(det)
                    name = str(getattr(det, "name", "")).lower()
                    
                    # 斑马线：ID匹配或名称匹配
                    if (cid == CW_ID) or _in_set(name, _CW):
                        raw_cw.append(det)
                    # 盲道：ID匹配或名称匹配
                    elif (cid == BP_ID) or _in_set(name, _BP):
                        raw_bp.append(det)
                
                # 二次阈值过滤
                cw_list = [d for d in raw_cw if _score_of(d) >= CROSSWALK_MIN_CONF]
                bp_list = [d for d in raw_bp if _score_of(d) >= BLIND_MIN_CONF]
                
                # 合并斑马线mask
                if cw_list:
                    cw_masks = []
                    for det in cw_list:
                        mask = det.mask
                        if mask.shape != (h, w):
                            mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
                        mask_bin = (mask > 0.5).astype(np.uint8)
                        cw_masks.append(mask_bin)
                    if cw_masks:
                        crosswalk_mask = np.maximum.reduce(cw_masks)
                        det_area = int(crosswalk_mask.sum())
                        if det_area < CROSSWALK_MIN_AREA:
                            crosswalk_mask = None
                            det_area = 0
                
                # 合并盲道mask
                if bp_list:
                    bp_masks = []
                    for det in bp_list:
                        mask = det.mask
                        if mask.shape != (h, w):
                            mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
                        mask_bin = (mask > 0.5).astype(np.uint8)
                        bp_masks.append(mask_bin)
                    if bp_masks:
                        blindpath_mask = np.maximum.reduce(bp_masks)
                
                # 去交叠：从斑马线mask中移除盲道区域
                if crosswalk_mask is not None and blindpath_mask is not None:
                    crosswalk_mask = crosswalk_mask.copy()
                    crosswalk_mask[blindpath_mask > 0] = 0
                
                # 盲道真伪判定
                if blindpath_mask is not None:
                    if not _looks_like_blind_path(blindpath_mask, crosswalk_mask, h, w):
                        blindpath_mask = None
                
                # 【新增】保存检测结果到缓存
                self.last_detected_crosswalk_mask = crosswalk_mask
                self.last_detected_blindpath_mask = blindpath_mask
                self.last_crosswalk_detection_frame = self.frame_counter
            
            else:
                # 【新增】使用缓存的检测结果
                crosswalk_mask = self.last_detected_crosswalk_mask
                blindpath_mask = self.last_detected_blindpath_mask

            # ========== 2) 分割失败 → 用上一帧特征点光流追踪重建 ==========
            used_tracking = False
            if crosswalk_mask is None:
                if self.old_gray is not None and self.p0 is not None and len(self.p0) >= TRACK_MIN_POINTS:
                    try:
                        p1, st, err = cv2.calcOpticalFlowPyrLK(self.old_gray, gray, self.p0, None, **LK_PARAMS)
                        if p1 is not None and st is not None:
                            good_new = p1[st == 1]
                            if good_new is not None and len(good_new) >= TRACK_MIN_POINTS:
                                tracked_mask = self._hull_mask_from_points(good_new, (h, w))
                                if tracked_mask is not None and int(tracked_mask.sum()) >= (0.3 * (self.prev_mask.sum() if self.prev_mask is not None else 1)):
                                    crosswalk_mask = tracked_mask
                                    used_tracking = True
                                    self.p0 = good_new.reshape(-1, 1, 2)
                                else:
                                    self.p0 = None
                                    self.old_gray = None
                    except Exception as e:
                        logger.warning(f"[CROSS_STREET] LK 光流失败: {e}")
                        self.p0 = None
                        self.old_gray = None

            # ========== 3) EMA 平滑（减少抖动） + 形态学净化 ==========
            if crosswalk_mask is not None:
                m = crosswalk_mask.astype(np.float32)
                if self.prev_mask_float is not None and self.prev_mask_float.shape == m.shape:
                    self.prev_mask_float = MASK_EMA_ALPHA * m + (1.0 - MASK_EMA_ALPHA) * self.prev_mask_float
                else:
                    self.prev_mask_float = m
                crosswalk_mask = (self.prev_mask_float > 0.5).astype(np.uint8)
                crosswalk_mask = self._postprocess_mask(crosswalk_mask)
                self.prev_mask = crosswalk_mask
                self.prev_mask_ts = current_time

            # ========== 4) 若分割成功（或追踪成功）→ 播种/更新特征点 ==========
            if crosswalk_mask is not None:
                need_seed = (self.p0 is None or len(self.p0) < TRACK_MIN_POINTS or
                             (self.frame_counter - self.last_seed_frame) >= TRACK_RESEED_EVERY)
                if need_seed:
                    pts = self._seed_points_from_mask(gray, crosswalk_mask)
                    if pts is not None and len(pts) >= TRACK_MIN_POINTS:
                        self.p0 = pts
                        self.old_gray = gray.copy()
                        self.last_seed_frame = self.frame_counter
                else:
                    self.old_gray = gray.copy()
            else:
                self.crosswalk_detected = False
                self.p0 = None
                self.old_gray = None

            # ========== 4.5) 障碍物检测与可视化（与 blindpath 一致） ==========
            # 使用 crosswalk_mask 作为 path_mask，若无则全局检测
            detected_obstacles = []
            if self.obstacle_detector is not None:
                if self.frame_counter % self.OBSTACLE_DETECTION_INTERVAL == 0:
                    detected_obstacles = self._detect_obstacles(bgr_image, path_mask=crosswalk_mask)
                    # 稳定化
                    if self.prev_gray is not None:
                        detected_obstacles = self._stabilize_obstacle_list(
                            detected_obstacles,
                            self.last_detected_obstacles,
                            self.prev_gray,
                            gray,
                            bgr_image.shape[:2]
                        )
                    self.last_detected_obstacles = detected_obstacles
                    self.last_obstacle_detection_frame = self.frame_counter
                else:
                    if self.frame_counter - self.last_obstacle_detection_frame < self.OBSTACLE_CACHE_DURATION_FRAMES:
                        detected_obstacles = self.last_detected_obstacles
                    else:
                        detected_obstacles = []
                # 可视化所有障碍物
                for obs in detected_obstacles:
                    self._add_obstacle_visualization(obs, frame_visualizations)

            # ========== 5) 状态机 + 可视化与导航指令 ==========
            guidance_text = ""
            
            # 先绘制盲道（绿色mask，无黑底）
            if blindpath_mask is not None:
                # 只在掩码区域混合绿色，避免黑底
                mask_area = (blindpath_mask > 0).astype(bool)
                green_color = np.array([0, 255, 0], dtype=np.float32)  # BGR
                # 在掩码区域内混合颜色
                for c in range(3):
                    annotated[:, :, c] = np.where(
                        mask_area,
                        (annotated[:, :, c] * 0.7 + green_color[c] * 0.3).astype(np.uint8),
                        annotated[:, :, c]
                    )
                # 绘制盲道边框
                bp_ct = self._largest_contour(blindpath_mask)
                if bp_ct is not None:
                    cv2.drawContours(annotated, [bp_ct], -1, (0, 255, 0), 2)
            
            # 绘制斑马线（橙色mask，无描边，与盲道模式颜色一致）
            if crosswalk_mask is not None:
                self.crosswalk_detected = True
                # 使用与盲道模式相同的橙色：BGR(0, 165, 255)，只在掩码区域混合
                mask_area = (crosswalk_mask > 0).astype(bool)
                orange_color = np.array([0, 165, 255], dtype=np.float32)  # BGR
                # 在掩码区域内混合颜色
                for c in range(3):
                    annotated[:, :, c] = np.where(
                        mask_area,
                        (annotated[:, :, c] * 0.7 + orange_color[c] * 0.3).astype(np.uint8),
                        annotated[:, :, c]
                    )
            
            # ===== 状态机逻辑 =====
            if self.state == STATE_SEEKING:
                # 阶段1：寻找并对准远处的斑马线
                if crosswalk_mask is not None:
                    is_near = self._is_crosswalk_near(crosswalk_mask, h, w)
                    
                    if is_near:
                        # 斑马线已到跟前，切换到红绿灯判定
                        self.state = STATE_WAIT_LIGHT
                        guidance_text = "斑马线已在跟前，进入红绿灯判定模式"
                        self.last_seeking_guidance = ""  # 重置节流状态
                    else:
                        # 远距离对准引导（使用更宽松的阈值）
                        angle, offset = self._compute_远_distance_alignment(crosswalk_mask, h, w)
                        
                        # 优先角度，其次方位（使用SEEKING专用的宽松阈值）
                        if abs(angle) >= SEEKING_ANGLE_THRESH_DEG:
                            direction = "左转一点" if angle > 0 else "右转一点"
                        elif abs(offset) >= SEEKING_OFFSET_THRESH:
                            direction = "向右平移" if offset > 0 else "向左平移"
                        else:
                            direction = "保持直行"
                        
                        # 【移除左上角文字，改为右上角数据面板】
                        # 添加右上角数据面板
                        frame_visualizations.append({
                            "type": "data_panel",
                            "data": {
                                "状态": "对准斑马线",
                                "角度": f"{angle:.1f}°",
                                "偏移": f"{offset:.2f}"
                            },
                            "position": (w - 180, 20)
                        })
                        
                        # 节流：只有当引导文本改变或超过时间间隔时才播报
                        if current_time - self.last_guide_time > self.guide_interval:
                            if direction != self.last_seeking_guidance:
                                guidance_text = direction
                                self.last_seeking_guidance = direction
                            elif current_time - self.last_guide_time > self.guide_interval * 2:
                                # 超过2倍间隔，重复播报
                                guidance_text = direction
                else:
                    # 【移除左上角文字，改为右上角数据面板】
                    frame_visualizations.append({
                        "type": "data_panel",
                        "data": {
                            "状态": "寻找斑马线"
                        },
                        "position": (w - 180, 20)
                    })
                    self.last_seeking_guidance = ""  # 没有斑马线时重置
            
            elif self.state == STATE_WAIT_LIGHT:
                # 阶段2：红绿灯判定
                # 【移除左上角文字，稍后添加右上角数据面板】
                
                if TRAFFIC_LIGHT_AVAILABLE and trafficlight_detection:
                    try:
                        # 传入annotated（已包含斑马线和盲道），红绿灯检测在此基础上添加检测框
                        result = trafficlight_detection.process_single_frame(annotated)
                        
                        # 可视化红绿灯检测结果（绘制检测框）
                        if result and 'vis_image' in result:
                            vis_img = result['vis_image']
                            if vis_img is not None:
                                # 将红绿灯检测的可视化结果（带斑马线、盲道和检测框）更新到annotated
                                annotated = vis_img
                        
                        if result and 'stable_light' in result:
                            stable_light = result['stable_light']
                            
                            if stable_light == 'go':
                                self.green_light_counter += 1
                                # 【移除左上角文字，改为右上角数据面板】
                                frame_visualizations.append({
                                    "type": "data_panel",
                                    "data": {
                                        "状态": "红绿灯判定",
                                        "检测": f"绿灯 {self.green_light_counter}/{GREEN_LIGHT_STABLE_FRAMES}"
                                    },
                                    "position": (w - 180, 20)
                                })
                                
                                if self.green_light_counter >= GREEN_LIGHT_STABLE_FRAMES:
                                    self.state = STATE_CROSSING
                                    guidance_text = "绿灯稳定，开始通行。"
                                    self.green_light_counter = 0
                                    self.crossing_end_announced = False      # 重置过马路结束标志
                                    self.last_crosswalk_seen_time = current_time  # 初始化斑马线检测时间
                                    self.last_blindpath_announce_time = 0    # 重置盲道播报时间
                                else:
                                    # 检测到绿灯但还不稳定，节流播报
                                    if current_time - self.last_waiting_light_time > 3.0:
                                        guidance_text = "正在等待绿灯…"
                                        self.last_waiting_light_time = current_time
                            else:
                                self.green_light_counter = 0
                                if stable_light in ['stop', 'countdown_stop']:
                                    # 【移除左上角文字，改为右上角数据面板】
                                    frame_visualizations.append({
                                        "type": "data_panel",
                                        "data": {
                                            "状态": "红绿灯判定",
                                            "检测": "红灯，请等待"
                                        },
                                        "position": (w - 180, 20)
                                    })
                                    # 红灯状态播报（节流）
                                    if current_time - self.last_waiting_light_time > 3.0:
                                        guidance_text = "正在等待绿灯…"
                                        self.last_waiting_light_time = current_time
                                else:
                                    # 其他状态（黄灯或未检测到），节流播报
                                    if current_time - self.last_waiting_light_time > 3.0:
                                        guidance_text = "正在等待绿灯…"
                                        self.last_waiting_light_time = current_time
                        else:
                            # 没有检测到稳定的红绿灯，节流播报
                            if current_time - self.last_waiting_light_time > 3.0:
                                guidance_text = "正在等待绿灯…"
                                self.last_waiting_light_time = current_time
                    except Exception as e:
                        logger.warning(f"[CROSS_STREET] 红绿灯检测失败: {e}")
                        if current_time - self.last_waiting_light_time > 3.0:
                            guidance_text = "正在等待绿灯…"
                            self.last_waiting_light_time = current_time
                else:
                    # 无红绿灯模块，直接切换
                    # 【移除左上角文字，改为右上角数据面板】
                    frame_visualizations.append({
                        "type": "data_panel",
                        "data": {
                            "状态": "红绿灯判定",
                            "检测": "模块未加载"
                        },
                        "position": (w - 180, 20)
                    })
                    if current_time - self.last_guide_time > 2.0:
                        self.state = STATE_CROSSING
                        guidance_text = "开始通行"
                        self.crossing_end_announced = False          # 重置过马路结束标志
                        self.last_crosswalk_seen_time = current_time # 初始化斑马线检测时间
                        self.last_blindpath_announce_time = 0        # 重置盲道播报时间
            
            elif self.state == STATE_CROSSING:
                # 阶段3：过马路引导（原有逻辑）
                
                # 【新增】实时红绿灯检测（在CROSSING状态中）
                traffic_light_warning = None  # 用于存储红绿灯警告信息
                if TRAFFIC_LIGHT_AVAILABLE and trafficlight_detection:
                    try:
                        # 传入annotated（已包含斑马线和盲道），红绿灯检测在此基础上添加检测框
                        result = trafficlight_detection.process_single_frame(annotated)
                        
                        # 将红绿灯检测的可视化结果（带斑马线、盲道和检测框）更新到annotated
                        if result and 'vis_image' in result:
                            vis_img = result['vis_image']
                            if vis_img is not None:
                                # 将红绿灯检测框叠加到annotated上（保留斑马线和盲道）
                                annotated = vis_img
                        
                        # 检查稳定状态，如果是绿灯倒计时，播报警告
                        if result and 'stable_light' in result:
                            stable_light = result['stable_light']
                            if stable_light == 'countdown_go':
                                # 绿灯倒计时，播报警告（节流）
                                if current_time - self.last_guide_time > 2.0:
                                    traffic_light_warning = "绿灯快没了"
                    except Exception as e:
                        logger.warning(f"[CROSS_STREET] CROSSING状态红绿灯检测失败: {e}")
                
                if crosswalk_mask is not None:
                    # 更新斑马线检测时间
                    self.last_crosswalk_seen_time = current_time
                    
                    # 检测到斑马线：如果之前误播报了结束，现在重置标志回到正常流程
                    area = int(crosswalk_mask.sum())
                    area_ratio = float(area) / float(h * w)
                    # 如果斑马线面积还比较大（>0.1），说明还在过马路中，重置结束标志
                    if area_ratio > 0.1 and self.crossing_end_announced:
                        self.crossing_end_announced = False
                        self.blindpath_announced = False
                        logger.info("[CROSS_STREET] 检测到斑马线，重置结束标志，回到正常过马路流程")
                    
                    # 【移除左上角文字，改为右上角数据面板】
                    panel_data = {
                        "状态": "正在过马路",
                        "面积": f"{area_ratio:.2f}"
                    }
                    if self.crossing_end_announced:
                        panel_data["提示"] = "已播报结束"
                    frame_visualizations.append({
                        "type": "data_panel",
                        "data": panel_data,
                        "position": (w - 180, 20)
                    })
                    
                    # 使用"斑马线横纹法线的中央直线"来推导偏移（offset 初值仍给 0，后面根据青色法线更新）
                    angle_deg, offset = 0.0, 0.0

                    # 角度：优先使用条纹霍夫线估计；失败回退 PCA
                    angle_source = "条纹"
                    stripes = self._estimate_angle_by_stripes(crosswalk_mask, gray)
                    if stripes and ("angle_deg" in stripes):
                        angle_deg = -float(stripes["angle_deg"])
                        for (x1, y1, x2, y2) in stripes.get("lines", []):
                            cv2.line(annotated, (x1, y1), (x2, y2), VIS_COLORS["stripes"], 2)
                        # 可视化方向箭头（底部中心，表示偏角相对竖直）
                        cx, cy = int(w * 0.5), int(h * 0.85)
                        length = int(60)
                        rad = np.radians(angle_deg)
                        dx = int(length * np.sin(rad))
                        dy = int(length * np.cos(rad))
                        cv2.arrowedLine(annotated, (cx, cy), (cx + dx, cy - dy), VIS_COLORS["heading"], 3, tipLength=0.25)
                    else:
                        angle_source = "PCA"
                        angle_deg, _ = self._compute_angle_and_offset(crosswalk_mask)


                    # === 基于掩码质心 + 条纹法线，绘制"青色法线中央直线" & "白色虚线（与红箭头同向）" ===
                    # === 过中心的两条参考线：青色=法线、白色虚线=与红箭头同向 ===
                    center_pt = self._mask_center(crosswalk_mask)
                    if center_pt is not None and stripes and ("angle_deg" in stripes):
                        # 1) 青色法线：使用"条纹均值角"作为【法线相对竖直】角，保证与橙色条纹垂直
                        angle_blue = float(stripes["angle_deg"])  # ← 关键：不要再取负，不要再加减 90°
                        self._draw_line_vertical_angle(annotated, center_pt, angle_blue,
                                                       length_ratio=0.7,
                                                       color=VIS_COLORS["centerline"], thickness=3)

                        # 2) 白色虚线：过质心的"画面竖直(0°)"——代表用户假定行走朝向
                        angle_white = 0.0
                        self._draw_dashed_line_vertical_angle(annotated, center_pt, angle_white,
                                                              length_ratio=0.7,
                                                              dash=12, gap=8, color=(255, 255, 255), thickness=2)

                        # 3) 角差显示（可选）：青色 vs 白虚线
                        diff = angle_blue - 0.0  # = angle_blue
                        diff = (diff + 180.0) % 360.0 - 180.0  # wrap 到 [-180,180]
                        cv2.putText(annotated, f"{abs(diff):.1f}°",
                                    (min(center_pt[0] + 12, w - 110), max(center_pt[1] - 12, 30)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

                        # === 用青色法线中央直线 计算"左右偏移" ===
                        try:
                            # 注意：_offset_from_centerline 的角度坐标系与 _draw_line_vertical_angle 一致（竖直为0°）
                            offset_new = self._offset_from_centerline(center_pt, angle_blue, w, h, y_ratio=0.75)
                            offset = float(offset_new)
                        except Exception:
                            # 兜底：若计算异常，保持原 offset（默认为0）
                            pass

                    # 导航方向（基础）
                    if abs(angle_deg) >= ANGLE_THRESH_DEG:
                        direction = "左转一点" if angle_deg > 0 else "右转一点"
                    elif abs(offset) >= OFFSET_THRESH:
                        direction = "向右平移" if offset > 0 else "向左平移"
                    else:
                        direction = "保持直行"

                    # 障碍物引导优先级（近距离优先覆盖方向提示）
                    obstacle_override = None
                    if detected_obstacles:
                        NEAR_Y = 0.7
                        NEAR_AREA = 0.1
                        near_list = [o for o in detected_obstacles if (o.get('bottom_y_ratio', 0) > NEAR_Y or o.get('area_ratio', 0) > NEAR_AREA)]
                        if near_list:
                            name = (near_list[0].get('name') or '障碍物')
                            obstacle_override = self._speech_for_obstacle(name)

                    # 【移除左上角调试信息，改为右上角数据面板】
                    # 更新右上角数据面板（合并到已有的面板数据中）
                    src_text = "分割" if not used_tracking else "追踪"
                    # 数据面板在前面已经添加了，这里只记录调试数据
                    # 稍后会统一添加完整的数据面板

                    # 语音输出（节流）
                    if current_time - self.last_guide_time > self.guide_interval:
                        # 检查是否快走完斑马线
                        is_almost_done = self._is_crosswalk_almost_done(crosswalk_mask, h, w)
                        
                        # 调试信息：显示判定条件
                        if self.frame_counter % 30 == 0:
                            ys = np.where(crosswalk_mask > 0)[0]
                            if ys.size > 0:
                                top_y, bottom_y = int(ys.min()), int(ys.max())
                                logger.info(f"[CROSS_STREET] area_ratio={area_ratio:.3f}, top_ratio={top_y/h:.3f}, bottom_ratio={bottom_y/h:.3f}, almost_done={is_almost_done}")
                        
                        # 优先级1：红绿灯警告（绿灯倒计时）
                        if traffic_light_warning:
                            guidance_text = traffic_light_warning
                            self.last_guide_time = current_time
                        # 优先级2：过马路结束提示（斑马线快消失）
                        elif is_almost_done and not self.crossing_end_announced:
                            guidance_text = "过马路结束，准备上人行道。"
                            self.crossing_end_announced = True
                            self.last_guide_time = current_time
                        # 优先级3：盲道提示（过马路结束后检测到盲道，可重复播报但节流4秒）
                        elif self.crossing_end_announced and blindpath_mask is not None:
                            if current_time - self.last_blindpath_announce_time > 4.0:
                                guidance_text = "远处有盲道，继续前行。"
                                self.last_blindpath_announce_time = current_time
                                self.last_guide_time = current_time
                        # 优先级4：障碍物
                        elif obstacle_override:
                            guidance_text = obstacle_override
                            self.last_guide_time = current_time
                        # 优先级5：方向引导
                        else:
                            guidance_text = direction
                            self.last_guide_time = current_time
                else:
                    # CROSSING 阶段但没有检测到斑马线
                    no_crosswalk_duration = current_time - self.last_crosswalk_seen_time
                    # 【移除左上角文字，改为右上角数据面板】
                    frame_visualizations.append({
                        "type": "data_panel",
                        "data": {
                            "状态": "正在过马路",
                            "斑马线": f"未检测到 ({no_crosswalk_duration:.1f}s)"
                        },
                        "position": (w - 180, 20)
                    })
                    
                    # 连续超过10秒没有斑马线，才播报"过马路结束"
                    if no_crosswalk_duration > 10.0:
                        if not self.crossing_end_announced:
                            if current_time - self.last_guide_time > self.guide_interval:
                                # 优先级1：红绿灯警告
                                if traffic_light_warning:
                                    guidance_text = traffic_light_warning
                                    self.last_guide_time = current_time
                                # 优先级2：过马路结束
                                else:
                                    guidance_text = "过马路结束，准备上人行道。"
                                    self.crossing_end_announced = True
                                    self.last_guide_time = current_time
                        # 播报结束后，检测到盲道则重复播报（节流4秒）
                        elif blindpath_mask is not None:
                            if current_time - self.last_blindpath_announce_time > 4.0:
                                guidance_text = "远处有盲道，继续前行。"
                                self.last_blindpath_announce_time = current_time
                                self.last_guide_time = current_time

            # 【移除帧信息】
            # 添加底部指令按钮（显示当前状态或引导内容）
            if guidance_text:
                current_instruction = guidance_text
            elif self.state == STATE_SEEKING:
                current_instruction = self.last_seeking_guidance if self.last_seeking_guidance else "寻找斑马线..."
            elif self.state == STATE_WAIT_LIGHT:
                current_instruction = "等待绿灯..."
            elif self.state == STATE_CROSSING:
                current_instruction = "过马路中..."
            else:
                current_instruction = "等待中..."
            annotated = self._draw_command_button(annotated, current_instruction)

            # 统一渲染障碍物等可视化图层（blindpath 风格）
            if frame_visualizations:
                annotated = self._draw_visualizations(annotated, frame_visualizations)

            # 【修改】不在工作流内部播放音频，由app_main统一处理
            # 直接返回guidance_text给上层调用者（app_main）来播放

            # 更新 prev_gray（供障碍物稳定化使用）
            self.prev_gray = gray

            return CrossStreetResult(
                annotated_image=annotated,
                guidance_text=guidance_text,
                visualizations=frame_visualizations,
                should_switch_to_blindpath=False
            )

        except Exception as e:
            logger.error(f"[CROSS_STREET] 处理帧时出错: {e}", exc_info=True)
            return CrossStreetResult(
                annotated_image=bgr_image,
                guidance_text="",
                visualizations=[],
                should_switch_to_blindpath=False
            )

class YOLOModelWrapper:
    """YOLO 模型包装器，将 predict 方法适配为 detect"""

    def __init__(self, yolo_model):
        self.model = yolo_model

    def detect(self, image, confidence_threshold=0.25):
        """使用 predict 方法并转换为 detect 格式"""
        try:
            results = self.model.predict(image, conf=confidence_threshold, verbose=False)
            detections = []
            if results and len(results) > 0:
                result = results[0]
                if hasattr(result, 'masks') and result.masks is not None:
                    for i, mask in enumerate(result.masks.data):
                        if hasattr(result, 'boxes') and result.boxes is not None:
                            cls = int(result.boxes.cls[i].cpu().numpy())
                            conf = float(result.boxes.conf[i].cpu().numpy())
                            class Detection:
                                def __init__(self):
                                    self.cls = cls
                                    self.conf = conf
                                    self.mask = mask.cpu().numpy()
                            detections.append(Detection())
            return detections
        except Exception as e:
            logger.error(f"[YOLO Wrapper] 检测错误: {e}")
            return []