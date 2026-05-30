# workflow_blindpath.py
# -*- coding: utf-8 -*-
"""
盲道导航工作流 - 纯净版
移除了所有 Redis、Celery 依赖，可以直接集成到任何 Python 应用中
"""
import os
import time
import cv2
import numpy as np
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from collections import deque
import torch  # 添加这行
from obstacle_detector_client import ObstacleDetectorClient
from audio_player import play_voice_text  # 新增
from crosswalk_awareness import CrosswalkAwarenessMonitor, split_combined_voice  # 斑马线感知
# 尝试导入 Pillow，用于中文显示
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image, ImageDraw, ImageFont = None, None, None

logger = logging.getLogger(__name__)

# ========== 状态常量定义 ==========
STATE_ONBOARDING = "ONBOARDING"
STATE_NAVIGATING = "NAVIGATING"
STATE_MANEUVERING_TURN = "MANEUVERING_TURN"
STATE_AVOIDING_OBSTACLE = "AVOIDING_OBSTACLE"
STATE_LOCKING_ON = "LOCKING_ON"

# ONBOARDING子步骤
ONBOARDING_STEP_ROTATION = "ROTATION"
ONBOARDING_STEP_TRANSLATION = "TRANSLATION"

# 转向子步骤
MANEUVER_STEP_1_ISSUE_COMMAND = "ISSUE_COMMAND"
MANEUVER_STEP_2_WAIT_FOR_SHIFT = "WAIT_FOR_SHIFT"
MANEUVER_STEP_3_ALIGN_ON_NEW_PATH = "ALIGN_ON_NEW_PATH"

# 颜色定义 (BGR格式)
VIS_COLORS = {
    "blind_path": (0, 255, 0),      # 绿色
    "obstacle": (0, 0, 255),        # 红色
    "crosswalk": (0, 165, 255),     # 橙色
    "centerline": (0, 255, 255),     # 黄色
    "target_point": (255, 0, 0),     # 蓝色
    "turn_point": (128, 0, 128),     # 紫色
    "pulse_effect": (100, 100, 255)  # 淡红色
}

# 障碍物名称映射
_OBSTACLE_NAME_CN = {
    'person': '人',
    'bicycle': '自行车',
    'car': '车',
    'motorcycle': '摩托车',
    'bus': '公交车',
    'truck': '卡车',
    'animal': '动物',
    'scooter': '电瓶车',
    'stroller': '婴儿车',
    'dog': '狗',
}

# 动态类别名称列表
DYNAMIC_CLASS_NAMES = {'person', 'bicycle', 'car', 'motorcycle', 'bus', 'truck', 'animal', 'dog'}

@dataclass
class ProcessingResult:
    """处理结果数据类"""
    guidance_text: str  # 语音引导文本
    visualizations: List[Dict[str, Any]]  # 可视化元素列表
    annotated_image: Optional[np.ndarray] = None  # 标注后的图像
    state_info: Dict[str, Any] = None  # 状态信息
    
    def __post_init__(self):
        if self.state_info is None:
            self.state_info = {}


class BlindPathNavigator:
    """盲道导航处理器 - 无外部依赖版本"""
    
    def __init__(self, yolo_model=None, obstacle_detector=None):
        """
        初始化导航器
        :param yolo_model: YOLO分割模型（可选）
        :param obstacle_detector: 障碍物检测器（可选）
        """
        self.yolo_model = yolo_model
        self.obstacle_detector = obstacle_detector
        
        # 状态变量
        self.current_state = STATE_ONBOARDING
        self.onboarding_step = ONBOARDING_STEP_ROTATION
        self.maneuver_step = MANEUVER_STEP_1_ISSUE_COMMAND
        self.maneuver_target_info = None
        

        # 光流追踪参数
        self.lk_params = dict(
            winSize=(15, 15),
            maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
        )
        
        # 特征检测参数
        self.feature_params = dict(
            maxCorners=100,
            qualityLevel=0.05,
            minDistance=10,
            blockSize=7,
            useHarrisDetector=False,
            k=0.04
        )
        
        # 光流追踪点缓存
        self.flow_points = {}  # {mask_type: points}
        self.flow_grace = {}   # {mask_type: grace_count}
        self.FLOW_GRACE_MAX = 3  # 【修改】从8帧降低到3帧，快速清除光流遗留
        
        # 中心线平滑缓存
        self.centerline_history = []  # 历史中心线数据
        self.centerline_history_max = 5  # 保留最近5帧用于平滑
        
        # 多项式系数平滑缓存
        self.poly_coeffs_history = []  # 历史多项式系数
        self.poly_coeffs_history_max = 8  # 保留最近8帧系数用于平滑

        # 转弯检测追踪器
        self.turn_detection_tracker = {
            'direction': None,
            'consecutive_hits': 0,
            'last_seen_frame': 0,
            'corner_info': None
        }
        
        # 转弯冷却
        self.turn_cooldown_frames = 0
        self.TURN_COOLDOWN_DURATION = 50
        
        # 避障相关
        self.avoidance_plan = None
        self.avoidance_step_index = 0
        self.lock_on_data = None
        
        # 斑马线追踪
        self.crosswalk_tracker = {
            'stage': 'not_detected',
            'consecutive_frames': 0,
            'last_area_ratio': 0.0,
            'last_bottom_y_ratio': 0.0,
            'last_center_x_ratio': 0.5,
            'position_announced': False,
            'alignment_status': 'not_aligned',
            'last_seen_frame': 0,
            'last_angle': 0.0
        }
        
        # 帧计数器
        self.frame_counter = 0
        
        # 直行提示配置 - 支持环境变量
        self.guide_interval = float(os.getenv("AIGLASS_STRAIGHT_INTERVAL", "4.0"))  # 播报间隔（秒）
        self.last_guide_time = 0.0
        self.straight_continuous_mode = os.getenv("AIGLASS_STRAIGHT_CONTINUOUS", "1") == "1"  # 持续播报模式
        self.straight_repeat_limit = int(os.getenv("AIGLASS_STRAIGHT_LIMIT", "2"))  # 限制模式下的最大次数
        self.straight_repeat_count = 0
        
        # 【新增】方向指令持续播报配置
        self.direction_interval = float(os.getenv("AIGLASS_DIRECTION_INTERVAL", "3.0"))  # 方向指令间隔（秒）
        self.last_direction_time = 0.0
        self.last_direction_message = ""
        
        # 打印配置信息
        logger.info(f"[BlindPath] 直行播报配置: 间隔={self.guide_interval}秒, "
                   f"持续模式={self.straight_continuous_mode}, "
                   f"限制次数={self.straight_repeat_limit}")
        logger.info(f"[BlindPath] 方向播报配置: 间隔={self.direction_interval}秒")

        # 缓存变量
        self.prev_gray = None
        self.prev_blind_path_mask = None
        self.prev_crosswalk_mask = None
        self.prev_obstacle_cache = []
        self.last_guidance_message = ""
        self.last_detected_obstacles = []
        self.last_obstacle_detection_frame = 0
        self.last_any_speech_time = 0
        
        # 斑马线准备状态标志
        self.crosswalk_ready_announced = False
        self.crosswalk_ready_time = 0
        
        # 障碍物语音待播报
        self.pending_obstacle_voice = None
        
        # 红绿灯检测
        self.traffic_light_detector = None
        self.init_traffic_light_detector()
        self.traffic_light_history = deque(maxlen=8)  # 用于多数表决
        self.last_traffic_light_state = "unknown"
        self.green_light_announced = False
        
        # 阈值设置
        self.CLASS_CONF_THRESHOLDS = {
            1: 0.20,  # blind_path
            0: 0.30   # crosswalk
        }
        
        # 导航阈值
        # 导航阈值
        self.ONBOARDING_ALIGN_THRESHOLD_RATIO = 0.1
        self.VP_FIT_ERROR_THRESHOLD = 8.0

        self.ONBOARDING_ORIENTATION_THRESHOLD_RAD = np.deg2rad(10)
        self.ONBOARDING_CENTER_OFFSET_THRESHOLD_RATIO = 0.15
        self.NAV_ORIENTATION_THRESHOLD_RAD = np.deg2rad(10)
        self.NAV_CENTER_OFFSET_THRESHOLD_RATIO = 0.15
        self.CURVATURE_PROXY_THRESHOLD = 5e-5
        
        # 斑马线切换阈值
        self.CROSSWALK_SWITCH_AREA_RATIO = 0.22
        self.CROSSWALK_SWITCH_BOTTOM_RATIO = 0.9
        self.CROSSWALK_SWITCH_CONSECUTIVE_FRAMES = 10
        
        # 障碍物检测间隔
        # 障碍物检测优化参数 - 从环境变量读取，支持性能调优
        self.OBSTACLE_DETECTION_INTERVAL = int(os.getenv("AIGLASS_OBS_INTERVAL", "15"))  # 默认每5帧检测一次
        self.OBSTACLE_CACHE_DURATION_FRAMES = int(os.getenv("AIGLASS_OBS_CACHE_FRAMES", "10"))  # 缓存10帧
        
        # 障碍物播报管理
        self.last_obstacle_speech = ""
        self.last_obstacle_speech_time = 0
        self.obstacle_speech_cooldown = 5.0  # 相同障碍物3秒内不重复播报
        
        # 掩码稳定化参数（已禁用光流外推，这些参数不再使用）
        self.MASK_STAB_MIN_AREA = int(os.getenv("AIGLASS_MASK_MIN_AREA", "1500"))
        self.MASK_STAB_KERNEL = int(os.getenv("AIGLASS_MASK_MORPH", "3"))
        self.MASK_MISS_TTL = 0  # 【修改为0】禁用光流外推，完全实时
        self.blind_miss_ttl = 0
        self.cross_miss_ttl = 0
        
        # 光流跟踪参数
        self.flow_iou_threshold = 0.3  # IoU低于此值时重新初始化光流点
        
        # 【新增】盲道YOLO检测间隔
        self.BLINDPATH_DETECTION_INTERVAL = int(os.getenv("AIGLASS_BLINDPATH_INTERVAL", "8"))  # 每2帧检测一次
        self.last_blindpath_detection_frame = 0
        self.last_blindpath_mask = None
        self.last_crosswalk_mask = None
        
        # 【新增】斑马线感知监控器
        self.crosswalk_monitor = CrosswalkAwarenessMonitor()
        logger.info("[BlindPath] 斑马线感知监控器已初始化")
        logger.info(f"[BlindPath] 盲道检测间隔: 每{self.BLINDPATH_DETECTION_INTERVAL}帧")
    
    def init_traffic_light_detector(self):
        """初始化红绿灯检测器"""
        try:
            # 首先尝试使用 YOLO 模型检测红绿灯
            self.traffic_light_yolo = None
            # 如果你有专门的红绿灯模型，在这里加载
            # self.traffic_light_yolo = YOLO('path/to/traffic_light_model.pt')
        except Exception as e:
            logger.info(f"未加载红绿灯YOLO模型: {e}")
    
    def detect_traffic_light(self, image: np.ndarray) -> str:
        """检测红绿灯状态
        返回: 'red', 'green', 'yellow', 'unknown'
        """
        # 模拟模式（用于测试）
        if os.getenv("AIGLASS_SIMULATE_TRAFFIC_LIGHT", "0") == "1":
            # 根据帧数模拟红绿灯变化
            cycle = (self.frame_counter // 100) % 3
            if cycle == 0:
                return "red"
            elif cycle == 1:
                return "yellow"
            else:
                return "green"
        
        # 如果有 YOLO 模型，优先使用
        if self.traffic_light_yolo:
            try:
                results = self.traffic_light_yolo.predict(image, verbose=False, conf=0.3)
                # TODO: 解析 YOLO 结果，判断红绿灯颜色
                pass
            except:
                pass
        
        # 使用 HSV 颜色检测作为后备方案
        return self._detect_traffic_light_by_color(image)
    
    def _detect_traffic_light_by_color(self, image: np.ndarray) -> str:
        """基于 HSV 颜色空间检测红绿灯"""
        h, w = image.shape[:2]
        # 检测图像上半部分和中间部分（红绿灯可能在不同高度）
        roi = image[:int(h * 0.7), :]  # 扩大检测范围到70%
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        
        # 提高亮度的图像用于检测（有助于检测较暗的红绿灯）
        hsv_bright = hsv.copy()
        hsv_bright[:, :, 2] = cv2.add(hsv_bright[:, :, 2], 30)  # 增加亮度
        
        # 定义颜色范围（优化后的参数）
        # 红色（两个范围，因为红色在 HSV 中跨越 0 度）
        lower_red1 = np.array([0, 120, 100])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([170, 120, 100])
        upper_red2 = np.array([180, 255, 255])
        
        # 绿色（调整为更宽的范围以适应不同灯光）
        lower_green = np.array([40, 60, 60])
        upper_green = np.array([90, 255, 255])
        
        # 黄色
        lower_yellow = np.array([15, 100, 100])
        upper_yellow = np.array([40, 255, 255])
        
        # 创建掩码（同时在原图和增亮图上检测）
        mask_red1 = cv2.inRange(hsv, lower_red1, upper_red1)
        mask_red2 = cv2.inRange(hsv, lower_red2, upper_red2)
        mask_red1_bright = cv2.inRange(hsv_bright, lower_red1, upper_red1)
        mask_red2_bright = cv2.inRange(hsv_bright, lower_red2, upper_red2)
        mask_red = cv2.bitwise_or(cv2.bitwise_or(mask_red1, mask_red2), 
                                 cv2.bitwise_or(mask_red1_bright, mask_red2_bright))
        
        mask_green = cv2.bitwise_or(cv2.inRange(hsv, lower_green, upper_green),
                                   cv2.inRange(hsv_bright, lower_green, upper_green))
        mask_yellow = cv2.bitwise_or(cv2.inRange(hsv, lower_yellow, upper_yellow),
                                    cv2.inRange(hsv_bright, lower_yellow, upper_yellow))
        
        # 形态学操作去噪
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask_red = cv2.morphologyEx(mask_red, cv2.MORPH_OPEN, kernel)
        mask_green = cv2.morphologyEx(mask_green, cv2.MORPH_OPEN, kernel)
        mask_yellow = cv2.morphologyEx(mask_yellow, cv2.MORPH_OPEN, kernel)
        
        # 计算每种颜色的面积
        area_red = cv2.countNonZero(mask_red)
        area_green = cv2.countNonZero(mask_green)
        area_yellow = cv2.countNonZero(mask_yellow)
        
        # 设置最小面积阈值（降低阈值使检测更敏感）
        min_area = 30  # 进一步降低阈值
        
        # 添加更详细的调试信息
        if hasattr(self, 'frame_counter') and self.frame_counter % 30 == 0:
            logger.info(f"[HSV检测] 红:{area_red}, 绿:{area_green}, 黄:{area_yellow}")
            # 保存调试图像
            if os.getenv("AIGLASS_DEBUG_TRAFFIC_LIGHT", "0") == "1":
                debug_dir = "traffic_light_debug"
                os.makedirs(debug_dir, exist_ok=True)
                cv2.imwrite(f"{debug_dir}/frame_{self.frame_counter}_roi.jpg", roi)
                cv2.imwrite(f"{debug_dir}/frame_{self.frame_counter}_red.jpg", mask_red)
                cv2.imwrite(f"{debug_dir}/frame_{self.frame_counter}_green.jpg", mask_green)
                cv2.imwrite(f"{debug_dir}/frame_{self.frame_counter}_yellow.jpg", mask_yellow)
        
        # 判断颜色（优先级：绿 > 红 > 黄）
        if area_green > min_area and area_green > area_red * 0.8:  # 绿灯优先
            return "green"
        elif area_red > min_area and area_red > area_green:
            return "red"
        elif area_yellow > min_area:
            return "yellow"
        else:
            return "unknown"
    
    def _get_voice_priority(self, guidance_text):
        """获取语音指令的优先级
        优先级：障碍物(100) > 转向/平移(50) > 保持直行(10)
        """
        if not guidance_text:
            return 0
        
        # 障碍物播报 - 最高优先级
        obstacle_keywords = ['前方有', '左侧有', '右侧有', '停一下', '注意避让', '障碍物']
        for keyword in obstacle_keywords:
            if keyword in guidance_text:
                return 100
        
        # 转向和平移 - 中等优先级  
        direction_keywords = ['左转', '右转', '左移', '右移', '向左', '向右', '平移', '微调']
        for keyword in direction_keywords:
            if keyword in guidance_text:
                return 50
        
        # 保持直行 - 最低优先级
        if '保持直行' in guidance_text or '继续前进' in guidance_text or '方向正确' in guidance_text:
            return 10
        
        # 其他指令 - 默认中等优先级
        return 30

    def process_frame(self, image: np.ndarray) -> ProcessingResult:
        """
        处理单帧图像
        :param image: BGR格式的图像
        :return: 处理结果
        """
        self.frame_counter += 1
        
        # 更新冷却期
        if self.turn_cooldown_frames > 0:
            self.turn_cooldown_frames -= 1
        
        image_height, image_width = image.shape[:2]
        image_center_x = image_width / 2
        
        # 转换为灰度图
        curr_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # 可视化元素列表
        frame_visualizations = []
        guidance_text = ""
        
        # 1. 【修改为实时检测】每帧都进行YOLO检测，不使用缓存
        blind_path_mask, crosswalk_mask = self._detect_path_and_crosswalk(image)
        
        # 【调试】检查YOLO检测结果
        if self.frame_counter % 30 == 0:  # 每30帧打印一次
            has_blind = blind_path_mask is not None and np.sum(blind_path_mask > 0) > 0
            has_cross = crosswalk_mask is not None and np.sum(crosswalk_mask > 0) > 0
            logger.info(f"[YOLO检测] Frame={self.frame_counter}, 盲道={'有' if has_blind else '无'}, "
                       f"斑马线={'有' if has_cross else '无'}")
            if has_cross:
                cross_area = np.sum(crosswalk_mask > 0) / crosswalk_mask.size
                logger.info(f"[YOLO检测] 斑马线原始面积: {cross_area*100:.2f}%")
        
        # 【修改】保留斑马线检测结果，用于斑马线感知
        # crosswalk_mask = None  # 不再强制设为None
        
        # 2. 【禁用掩码稳定化和光流外推】直接使用实时检测结果
        # 不再使用光流外推，完全实时更新：有就是有，没有就是没有
        # blind_path_mask 和 crosswalk_mask 直接使用上面检测的结果
        crosswalk_mask_before_stabilize = crosswalk_mask
        
        # 【调试】检查稳定化后的结果
        if self.frame_counter % 30 == 0 and crosswalk_mask_before_stabilize is not None:
            after_stab = crosswalk_mask is not None and np.sum(crosswalk_mask > 0) > 0
            logger.info(f"[掩码稳定化] 斑马线稳定化后: {'有' if after_stab else '无（被过滤）'}")
        
        # 【新增】3. 全程障碍物检测
        # 无论在什么状态下，都进行障碍物检测
        logger.info(f"[Frame {self.frame_counter}] 开始障碍物检测...")
        
        # 使用缓存策略，但确保所有障碍物都被可视化
        if self.frame_counter % self.OBSTACLE_DETECTION_INTERVAL == 0:
            detected_obstacles = self._detect_obstacles(image, blind_path_mask)
            self.last_detected_obstacles = detected_obstacles
            self.last_obstacle_detection_frame = self.frame_counter
            logger.info(f"[Frame {self.frame_counter}] 执行了新的障碍物检测，检测到 {len(detected_obstacles)} 个障碍物")
        else:
            if self.frame_counter - self.last_obstacle_detection_frame < self.OBSTACLE_CACHE_DURATION_FRAMES:
                detected_obstacles = self.last_detected_obstacles
                logger.info(f"[Frame {self.frame_counter}] 使用缓存的障碍物数据，共 {len(detected_obstacles)} 个障碍物")
            else:
                detected_obstacles = []
                logger.info(f"[Frame {self.frame_counter}] 缓存过期，无障碍物数据")
        
        # 添加所有障碍物的可视化（不只是近距离的）
        for i, obs in enumerate(detected_obstacles):
            logger.info(f"  障碍物 {i+1}: {obs.get('name', 'unknown')}, "
                    f"bottom_y_ratio={obs.get('bottom_y_ratio', 0):.2f}, "
                    f"area_ratio={obs.get('area_ratio', 0):.3f}, "
                    f"位置=({obs.get('center_x', 0):.0f}, {obs.get('center_y', 0):.0f})")
            self._add_obstacle_visualization(obs, frame_visualizations)
        
        # 【新增】检查近距离障碍物并设置语音
        self._check_and_set_obstacle_voice(detected_obstacles)
        
        # 【新增】斑马线感知处理
        # 先检查crosswalk_mask状态
        if crosswalk_mask is not None:
            cross_pixels = np.sum(crosswalk_mask > 0)
            if cross_pixels > 0:
                logger.info(f"[斑马线] 传入monitor: pixels={cross_pixels}, area={cross_pixels/crosswalk_mask.size*100:.2f}%")
            else:
                logger.info(f"[斑马线] crosswalk_mask全为0，无斑马线")
        else:
            if self.frame_counter % 30 == 0:
                logger.info(f"[斑马线] crosswalk_mask为None")
        
        crosswalk_guidance = self.crosswalk_monitor.process_frame(crosswalk_mask, blind_path_mask)
        if crosswalk_guidance:
            logger.info(f"[斑马线感知] 检测结果: area={crosswalk_guidance.get('area', 0):.3f}, "
                       f"should_broadcast={crosswalk_guidance.get('should_broadcast', False)}, "
                       f"voice={crosswalk_guidance.get('voice_text', 'None')}")
        if crosswalk_guidance and crosswalk_guidance['should_broadcast']:
            # 将斑马线语音加入待播报列表（通过pending机制）
            if not hasattr(self, 'pending_crosswalk_voice'):
                self.pending_crosswalk_voice = None
            self.pending_crosswalk_voice = crosswalk_guidance
            logger.info(f"[斑马线语音] 已设置待播报语音: {crosswalk_guidance['voice_text']}, 优先级{crosswalk_guidance['priority']}")
        
        # 【新增】添加斑马线可视化
        if crosswalk_mask is not None:
            # 计算可视化数据
            total_pixels = crosswalk_mask.size
            crosswalk_pixels = np.sum(crosswalk_mask > 0)
            area_ratio = crosswalk_pixels / total_pixels
            
            y_coords, x_coords = np.where(crosswalk_mask > 0)
            if len(y_coords) > 0:
                center_x_ratio = np.mean(x_coords) / crosswalk_mask.shape[1]
                center_y_ratio = np.mean(y_coords) / crosswalk_mask.shape[0]
                has_occlusion = self.crosswalk_monitor._check_occlusion(crosswalk_mask, blind_path_mask)
                
                # 获取可视化数据
                viz_data = self.crosswalk_monitor.get_visualization_data(
                    crosswalk_mask, area_ratio, center_x_ratio, center_y_ratio, has_occlusion
                )
                
                # 添加斑马线mask可视化
                self._add_mask_visualization(crosswalk_mask, frame_visualizations, 
                                            "crosswalk_mask", viz_data['stage_color'])
                
                # 添加斑马线检测信息可视化
                self._add_crosswalk_info_visualization(viz_data, image_height, image_width, 
                                                      frame_visualizations)
        
        # 【已禁用】4. 更新斑马线追踪器 - 盲道导航不再跳转到斑马线
        # self._update_crosswalk_tracker(crosswalk_mask, image_height, image_width)
        
        # 5. 添加路径可视化
        # 【恢复】盲道mask可视化
        self._add_mask_visualization(blind_path_mask, frame_visualizations, "blind_path_mask", "rgba(0, 255, 0, 0.4)")
        # 【斑马线可视化由crosswalk_monitor处理，不在这里添加】
        

        # 【已禁用】5. 根据状态执行不同的导航逻辑 - 盲道导航不再处理斑马线
        current_stage = 'not_detected'  # 固定为不检测斑马线
        # current_stage = self.crosswalk_tracker['stage']  # 已禁用
        
        # 直接进行盲道导航，不检查斑马线状态
        if False:  # current_stage == 'ready':
            # 检查是否已经播报过准备提示
            if not hasattr(self, 'crosswalk_ready_announced'):
                self.crosswalk_ready_announced = False
                self.crosswalk_ready_time = 0
            
            current_time = time.time()
            
            # 检测红绿灯
            traffic_light_color = self.detect_traffic_light(image)
            self.traffic_light_history.append(traffic_light_color)
            
            # 调试信息
            if self.frame_counter % 30 == 0:  # 每30帧打印一次
                logger.info(f"[红绿灯检测] 当前颜色: {traffic_light_color}, 历史: {list(self.traffic_light_history)}")
            
            # 多数表决，获得稳定的红绿灯状态
            if len(self.traffic_light_history) >= 3:
                color_counts = {}
                for color in self.traffic_light_history:
                    color_counts[color] = color_counts.get(color, 0) + 1
                # 获取出现次数最多的颜色
                stable_color = max(color_counts.items(), key=lambda x: x[1])[0]
            else:
                stable_color = "unknown"
            
            # 添加红绿灯状态可视化
            self._add_traffic_light_visualization(
                stable_color, frame_visualizations, image_height, image_width
            )
            
            # 决定语音播报
            if not self.crosswalk_ready_announced:
                guidance_text = "已对准, 准备切换过马路模式。"
                self.crosswalk_ready_announced = True
                self.crosswalk_ready_time = current_time
            elif stable_color == "green" and not self.green_light_announced:
                guidance_text = "绿灯稳定，开始通行。"
                self.green_light_announced = True
            elif stable_color == "red":
                # 红灯时定期提醒
                if current_time - self.crosswalk_ready_time > 5.0:
                    guidance_text = "正在等待绿灯…"
                    self.crosswalk_ready_time = current_time
                else:
                    guidance_text = ""
            else:
                guidance_text = ""
            
            # 添加状态信息
            frame_visualizations.append({
                "type": "data_panel",
                "data": {
                    "状态": "等待过马路",
                    "红绿灯": stable_color,
                    "检测历史": len(self.traffic_light_history)
                },
                "position": (25, image_height - 120)
            })
            
        elif False:  # current_stage == 'approaching':
            guidance_text = self._handle_crosswalk_approaching(
                frame_visualizations, image_height, image_width, image
            )
            
        # elif current_stage in ['far', 'not_detected']:
        else:  # 总是执行盲道导航
            # 【已禁用】斑马线提示
            # if current_stage == 'far' and not self.crosswalk_tracker['position_announced']:
            #     guidance_text = "远处发现斑马线，继续直行。"
            #     self.crosswalk_tracker['position_announced'] = True
            
            if blind_path_mask is None:
                guidance_text = ""
                # 【移除左上角文字，改为右上角数据面板】
                frame_visualizations.append({
                    "type": "data_panel",
                    "data": {
                        "状态": "等待盲道识别"
                    },
                    "position": (image_width - 180, 20)
                })
            else:
                guidance_text = self._execute_state_machine(
                    blind_path_mask, image, frame_visualizations,
                    image_height, image_width, curr_gray
                )
        
        # 6. 更新缓存
        self.prev_gray = curr_gray
        if blind_path_mask is not None:
            self.prev_blind_path_mask = blind_path_mask.copy()
        if crosswalk_mask is not None:
            self.prev_crosswalk_mask = crosswalk_mask.copy()
        
        # 【改进】语音优先级管理系统
        current_time = time.time()
        
        # 收集所有可能的语音指令
        voice_candidates = []
        
        # 1. 添加主要导航语音
        if guidance_text:
            voice_candidates.append({
                'text': guidance_text,
                'priority': self._get_voice_priority(guidance_text),
                'source': 'navigation'
            })
        
        # 2. 检查是否有障碍物语音（独立检查，确保最高优先级）
        if hasattr(self, 'pending_obstacle_voice'):
            if self.pending_obstacle_voice:
                voice_candidates.append({
                    'text': self.pending_obstacle_voice,
                    'priority': 100,  # 障碍物始终最高优先级
                    'source': 'obstacle'
                })
                self.pending_obstacle_voice = None  # 清除已处理的障碍物语音
        
        # 【新增】检查是否有斑马线语音
        if hasattr(self, 'pending_crosswalk_voice'):
            if self.pending_crosswalk_voice:
                voice_candidates.append({
                    'text': self.pending_crosswalk_voice['voice_text'],
                    'priority': self.pending_crosswalk_voice['priority'],
                    'source': 'crosswalk'
                })
                self.pending_crosswalk_voice = None  # 清除已处理的斑马线语音
        
        # 3. 选择优先级最高的语音
        if voice_candidates:
            # 按优先级排序，取最高的
            voice_candidates.sort(key=lambda x: x['priority'], reverse=True)
            selected_voice = voice_candidates[0]
            final_guidance_text = selected_voice['text']
            
            # 全局播报冷却（避免任何语音重叠）
            MIN_SPEECH_INTERVAL = 1.2  # 任意两条语音间隔至少0.8秒
            if hasattr(self, 'last_any_speech_time'):
                if current_time - self.last_any_speech_time < MIN_SPEECH_INTERVAL:
                    final_guidance_text = ""  # 太快了，跳过这次播报
            
            # 特殊处理保持直行的节流
            if final_guidance_text == "保持直行":
                if self.straight_continuous_mode:
                    # 持续播报模式：只检查时间间隔
                    if current_time - self.last_guide_time >= self.guide_interval:
                        self.last_guide_time = current_time
                        self.straight_repeat_count += 1
                        self.last_any_speech_time = current_time
                    else:
                        final_guidance_text = ""
                else:
                    # 原有的限制模式
                    if (current_time - self.last_guide_time >= self.guide_interval) and \
                       (self.straight_repeat_count < self.straight_repeat_limit):
                        self.last_guide_time = current_time
                        self.straight_repeat_count += 1
                        self.last_any_speech_time = current_time
                    else:
                        final_guidance_text = ""
            elif final_guidance_text and selected_voice['source'] != 'obstacle':
                # 【修改】非直行、非障碍物指令 - 支持方向指令持续播报
                # 判断是否是方向指令
                direction_keywords = ["左转", "右转", "左移", "右移", "向左", "向右", "平移", "微调"]
                is_direction = any(keyword in final_guidance_text for keyword in direction_keywords)
                
                if is_direction:
                    # 方向指令：支持持续播报
                    if final_guidance_text == self.last_direction_message:
                        # 同一个方向指令，检查时间间隔
                        if current_time - self.last_direction_time >= self.direction_interval:
                            self.last_direction_time = current_time
                            self.last_any_speech_time = current_time
                            self.straight_repeat_count = 0
                        else:
                            final_guidance_text = ""  # 时间间隔不够，跳过
                    else:
                        # 新的方向指令，立即播报
                        self.last_direction_message = final_guidance_text
                        self.last_direction_time = current_time
                        self.last_any_speech_time = current_time
                        self.straight_repeat_count = 0
                else:
                    # 其他指令：只播报一次
                    if final_guidance_text != self.last_guidance_message:
                        self.last_guidance_message = final_guidance_text
                        self.straight_repeat_count = 0
                        self.last_any_speech_time = current_time
                    else:
                        final_guidance_text = ""
            elif final_guidance_text and selected_voice['source'] == 'obstacle':
                # 障碍物语音总是播报
                self.last_any_speech_time = current_time
            elif final_guidance_text and selected_voice['source'] == 'crosswalk':
                # 斑马线语音总是播报（不受重复检查限制）
                self.last_any_speech_time = current_time
                
            # 播报选中的语音
            if final_guidance_text:
                try:
                    # 【优化】组合语音只播第一部分，避免队列积压
                    if selected_voice.get('source') == 'crosswalk' and ',' in final_guidance_text:
                        voice_parts = split_combined_voice(final_guidance_text)
                        logger.info(f"[斑马线语音] 组合播报检测到{len(voice_parts)}部分，只播第一部分保持实时")
                        # 只播放第一部分，后续部分丢弃以保持实时性
                        if voice_parts:
                            play_voice_text(voice_parts[0])
                            logger.info(f"[语音播报] 优先级{selected_voice['priority']}: {voice_parts[0]}")
                    else:
                        play_voice_text(final_guidance_text)
                        logger.info(f"[语音播报] 优先级{selected_voice['priority']}: {final_guidance_text}")
                except Exception as e:
                    logger.error(f"[语音播报] 播放失败: {e}")
        else:
            final_guidance_text = ""
        
        # 7. 生成标注图像
        annotated_image = None

        if frame_visualizations:
            annotated_image = self._draw_visualizations(image.copy(), frame_visualizations)
        else:
            annotated_image = image.copy()
        
        # 添加底部指令按钮（显示当前实际播报的语音）
        current_instruction = final_guidance_text if final_guidance_text else "等待中..."
        annotated_image = self._draw_command_button(annotated_image, current_instruction)
        
        # 8. 返回结果
        return ProcessingResult(
            guidance_text=guidance_text,
            visualizations=frame_visualizations,
            annotated_image=annotated_image,
            state_info={
                "state": self.current_state,
                "crosswalk_stage": current_stage,
                "frame_count": self.frame_counter
            }
        )
    
    def _detect_path_and_crosswalk(self, image: np.ndarray) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """检测盲道和斑马线"""
        if self.yolo_model is None:
            # 【新增】没有模型时返回模拟数据用于测试
            logger.warning("YOLO模型未加载，返回模拟数据")
            h, w = image.shape[:2]
            # 创建一个模拟的盲道掩码（垂直居中的条带）
            blind_path_mask = np.zeros((h, w), dtype=np.uint8)
            # 在图像中央创建一个宽度为图像宽度20%的垂直条带
            strip_width = int(w * 0.2)
            strip_left = (w - strip_width) // 2
            blind_path_mask[int(h*0.3):, strip_left:strip_left+strip_width] = 255
            return blind_path_mask, None
        
        blind_path_mask = None
        crosswalk_mask = None
        
        try:
            min_conf = min(self.CLASS_CONF_THRESHOLDS.values())
            results = self.yolo_model.predict(image, verbose=False, conf=min_conf, classes=[0, 1])
            
            if (results and results[0] and results[0].masks is not None and 
                results[0].boxes is not None and len(results[0].masks.data) > 0):
                
                for mask_tensor, conf_tensor, cls_tensor in zip(
                    results[0].masks.data, results[0].boxes.conf, results[0].boxes.cls
                ):
                    class_id = int(cls_tensor.item())
                    confidence = float(conf_tensor.item())
                    threshold = self.CLASS_CONF_THRESHOLDS.get(class_id, 1.0)
                    
                    if confidence >= threshold:
                        current_mask = self._tensor_to_mask(mask_tensor, image.shape[1], image.shape[0])
                        
                        if class_id == 1:  # 盲道
                            if blind_path_mask is None:
                                blind_path_mask = current_mask
                            else:
                                blind_path_mask = cv2.bitwise_or(blind_path_mask, current_mask)
                        elif class_id == 0:  # 斑马线
                            if crosswalk_mask is None:
                                crosswalk_mask = current_mask
                            else:
                                crosswalk_mask = cv2.bitwise_or(crosswalk_mask, current_mask)
        except Exception as e:
            logger.error(f"YOLO检测失败: {e}")
            # 【新增】检测失败时也返回模拟数据
            h, w = image.shape[:2]
            blind_path_mask = np.zeros((h, w), dtype=np.uint8)
            strip_width = int(w * 0.2)
            strip_left = (w - strip_width) // 2
            blind_path_mask[int(h*0.3):, strip_left:strip_left+strip_width] = 255
        
        return blind_path_mask, crosswalk_mask
    
    def _tensor_to_mask(self, mask_tensor, out_w: int, out_h: int, binarize: bool = True) -> np.ndarray:
        """将张量掩码转换为numpy数组"""
        try:
            import torch
            
            if not isinstance(mask_tensor, torch.Tensor):
                arr = np.asarray(mask_tensor)
                if arr.dtype != np.uint8:
                    arr = (arr > 0.5).astype(np.uint8) * 255 if binarize else (arr * 255.0).astype(np.uint8)
                mask_u8 = arr
            else:
                if mask_tensor.dtype in (torch.bfloat16, torch.float16):
                    mask_tensor = mask_tensor.to(torch.float32)
                
                if mask_tensor.ndim > 2:
                    mask_tensor = mask_tensor.squeeze()
                
                if binarize:
                    mask_tensor = (mask_tensor > 0.5).to(torch.uint8).mul_(255)
                    mask_u8 = mask_tensor.cpu().numpy()
                else:
                    mask_u8 = (mask_tensor.mul(255).clamp_(0, 255).to(torch.uint8)).cpu().numpy()
            
            if mask_u8.ndim == 3:
                mask_u8 = mask_u8.squeeze(-1)
            
            if mask_u8.shape[1] != out_w or mask_u8.shape[0] != out_h:
                mask_u8 = cv2.resize(mask_u8, (out_w, out_h), interpolation=cv2.INTER_NEAREST)
            
            return mask_u8
        except ImportError:
            # 如果没有torch，返回空掩码
            return np.zeros((out_h, out_w), dtype=np.uint8)
    
    def _stabilize_mask(self, prev_gray, curr_gray, raw_mask, prev_stable_mask, mask_type):
        """稳定化掩码 - 使用 Lucas-Kanade 光流"""
        if mask_type == 'blind_path':
            ttl = self.blind_miss_ttl
            min_area = self.MASK_STAB_MIN_AREA
        else:  # crosswalk
            ttl = self.cross_miss_ttl
            min_area = self.MASK_STAB_MIN_AREA
        
        # 调用新的光流稳定化方法
        stable_mask = self._stabilize_seg_mask(
            prev_gray, curr_gray, raw_mask, prev_stable_mask,
            (curr_gray.shape[1], curr_gray.shape[0]) if curr_gray is not None else (640, 480),
            min_area_px=min_area,
            morph_kernel=self.MASK_STAB_KERNEL,
            mask_type=mask_type
        )
        
        if stable_mask is not None:
            # 重置TTL
            if mask_type == 'blind_path':
                self.blind_miss_ttl = self.MASK_MISS_TTL
            else:
                self.cross_miss_ttl = self.MASK_MISS_TTL
            return stable_mask
        else:
            # 减少TTL
            if mask_type == 'blind_path':
                self.blind_miss_ttl = max(0, self.blind_miss_ttl - 1)
            else:
                self.cross_miss_ttl = max(0, self.cross_miss_ttl - 1)
            return None
    
    def _stabilize_seg_mask(self, prev_gray, curr_gray, curr_mask, prev_stable_mask, 
                          image_wh, min_area_px=1500, morph_kernel=3, iou_high_thr=0.4, mask_type='', 
                          fast_clear=True):
        """使用 Lucas-Kanade 光流的掩码稳定化实现"""
        W, H = image_wh
        
        def _binarize(mask):
            if mask is None:
                return None
            if mask.dtype != np.uint8:
                mask = mask.astype(np.uint8)
            mask = (mask > 0).astype(np.uint8) * 255
            return mask
        
        def _morph_smooth(mask, kernel_size):
            if mask is None:
                return None
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, 
                                         (max(1, kernel_size), max(1, kernel_size)))
            sm = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=1)
            sm = cv2.morphologyEx(sm, cv2.MORPH_OPEN, k, iterations=1)
            return sm
        
        curr_mask_b = _binarize(curr_mask)
        prev_mask_b = _binarize(prev_stable_mask)
        
        # 如果没有历史数据，直接返回当前掩码
        if prev_mask_b is None or prev_gray is None or curr_gray is None:
            return _morph_smooth(curr_mask_b, morph_kernel) if curr_mask_b is not None else None
        
        # 当前帧有检测结果
        if curr_mask_b is not None and np.sum(curr_mask_b > 0) >= min_area_px:
            # 计算与上一帧的IoU
            if prev_mask_b is not None:
                inter = np.logical_and(curr_mask_b > 0, prev_mask_b > 0).sum()
                union = np.logical_or(curr_mask_b > 0, prev_mask_b > 0).sum()
                iou = float(inter) / float(union) if union > 0 else 0.0
                
                # IoU足够高，说明检测稳定，直接使用当前结果
                if iou >= iou_high_thr:
                    return _morph_smooth(curr_mask_b, morph_kernel)
                
                # IoU较低但仍有重叠，进行加权融合
                elif iou > 0.1:
                    # 使用光流预测的掩码
                    flow_mask = self._predict_mask_with_flow(prev_mask_b, prev_gray, curr_gray)
                    if flow_mask is not None:
                        # 根据IoU动态调整权重
                        # IoU越低，越依赖光流；IoU越高，越依赖当前检测
                        w_curr = min(0.9, 0.4 + iou)  # IoU=0.1时w_curr=0.5, IoU=0.5时w_curr=0.9
                        w_flow = 1.0 - w_curr
                        
                        fused = (w_curr * curr_mask_b.astype(np.float32) + 
                                w_flow * flow_mask.astype(np.float32))
                        fused_bin = (fused >= 128).astype(np.uint8) * 255
                        
                        # 重新初始化光流点（如果IoU过低）
                        if iou < self.flow_iou_threshold:
                            self.flow_points['blind_path'] = None
                        
                        return _morph_smooth(fused_bin, morph_kernel)
            
            # 没有历史或IoU太低，使用当前检测
            return _morph_smooth(curr_mask_b, morph_kernel)
        
        # 当前帧没有检测结果，尝试使用光流外推
        else:
            # 获取对应的TTL
            if mask_type == 'blind_path':
                ttl = self.blind_miss_ttl
            else:
                ttl = self.cross_miss_ttl
            
            # 【修改】当前帧无检测结果，快速清除
            if fast_clear and ttl <= 1:
                # TTL耗尽，立即返回None，不使用光流
                return None
                
            if prev_mask_b is not None and np.sum(prev_mask_b > 0) >= min_area_px and ttl > 0:
                # 使用光流预测
                flow_mask = self._predict_mask_with_flow(prev_mask_b, prev_gray, curr_gray)
                if flow_mask is not None and np.sum(flow_mask > 0) >= min_area_px * 0.5:
                    return _morph_smooth(flow_mask, morph_kernel)
            
            # 光流失败或超过TTL
            return None
    
    def _predict_mask_with_flow(self, prev_mask, prev_gray, curr_gray):
        """使用Lucas-Kanade光流预测掩码位置（改进版）"""
        try:
            # 方法1：尝试使用凸包方法（参考yolomedia）
            if hasattr(self, 'flow_points') and 'blind_path' in self.flow_points:
                p0 = self.flow_points['blind_path']
                if p0 is not None and len(p0) >= 5:
                    # 计算光流
                    p1, st, err = cv2.calcOpticalFlowPyrLK(prev_gray, curr_gray, p0, None, **self.lk_params)
                    
                    if p1 is not None and st is not None:
                        good_new = p1[st == 1]
                        if len(good_new) >= 5:
                            # 更新光流点
                            self.flow_points['blind_path'] = good_new.reshape(-1, 1, 2)
                            
                            # 生成凸包掩码
                            hull = cv2.convexHull(good_new.reshape(-1, 1, 2))
                            poly = hull.reshape(-1, 2)
                            
                            if len(poly) >= 3:
                                H, W = curr_gray.shape[:2]
                                flow_mask = np.zeros((H, W), dtype=np.uint8)
                                cv2.fillPoly(flow_mask, [poly.astype(np.int32)], 255)
                                return flow_mask
            
            # 方法2：边缘特征点方法（原有方法，作为备选）
            edge_mask = self._get_edge_mask(prev_mask, offset=10)
            
            # 检测特征点
            p0 = cv2.goodFeaturesToTrack(prev_gray, mask=edge_mask, **self.feature_params)
            if p0 is None or len(p0) < 8:
                return None
            
            # 保存特征点供下次使用
            self.flow_points['blind_path'] = p0
            
            # 计算光流
            p1, st, err = cv2.calcOpticalFlowPyrLK(prev_gray, curr_gray, p0, None, **self.lk_params)
            
            if p1 is None or st is None:
                return None
            
            # 只保留成功追踪的点
            good_new = p1[st == 1]
            good_old = p0[st == 1]
            
            if len(good_new) < 5:
                return None
            
            # 估计变换矩阵（使用RANSAC提高鲁棒性）
            M, inliers = cv2.estimateAffinePartial2D(good_old, good_new, method=cv2.RANSAC, ransacReprojThreshold=5.0)
            
            if M is None:
                return None
            
            # 应用变换
            H, W = curr_gray.shape[:2]
            flow_mask = cv2.warpAffine(prev_mask, M, (W, H), 
                                    flags=cv2.INTER_NEAREST,
                                    borderMode=cv2.BORDER_CONSTANT,
                                    borderValue=0)
            
            return flow_mask
            
        except Exception as e:
            logger.debug(f"光流预测失败: {e}")
            return None
            
    
    def _get_edge_mask(self, mask, offset=10):
        """获取掩码的内边缘区域，用于特征点检测"""
        if mask is None:
            return None
        
        # 腐蚀得到内部掩码
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (offset*2, offset*2))
        inner = cv2.erode(mask, kernel, iterations=1)
        
        # 边缘 = 原始 - 内部
        edge = cv2.subtract(mask, inner)
        
        # 稍微膨胀边缘区域
        kernel_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        edge = cv2.dilate(edge, kernel_small, iterations=1)
        
        return edge

    def _smooth_centerline(self, centerline_data):
        """平滑中心线数据，减少抖动"""
        if centerline_data is None or len(centerline_data) < 5:
            return centerline_data
        
        # 保存到历史记录
        self.centerline_history.append(centerline_data.copy())
        if len(self.centerline_history) > self.centerline_history_max:
            self.centerline_history.pop(0)
        
        # 如果历史记录不足，返回轻度平滑的当前帧数据
        if len(self.centerline_history) < 3:
            # 对当前帧进行空间平滑
            smoothed_data = centerline_data.copy()
            # 使用滑动窗口平均
            window_size = 5
            for i in range(len(smoothed_data)):
                start_idx = max(0, i - window_size // 2)
                end_idx = min(len(smoothed_data), i + window_size // 2 + 1)
                window = smoothed_data[start_idx:end_idx]
                if len(window) > 0:
                    smoothed_data[i, 1] = np.mean(window[:, 1])  # 平滑x坐标
                    smoothed_data[i, 2] = np.mean(window[:, 2])  # 平滑宽度
            return smoothed_data
        
        # 时间平滑：使用历史帧的加权平均
        smoothed_data = centerline_data.copy()
        
        # 为每个y坐标找到历史帧中对应的数据
        for i, (y, x, width) in enumerate(centerline_data):
            x_values = [x]
            width_values = [width]
            weights = [1.0]  # 当前帧权重最高
            
            # 从历史帧中查找相近y坐标的数据
            for hist_idx, hist_data in enumerate(self.centerline_history[-3:-1]):  # 使用最近的2帧历史
                # 找到最接近的y坐标
                y_diffs = np.abs(hist_data[:, 0] - y)
                if len(y_diffs) > 0:
                    closest_idx = np.argmin(y_diffs)
                    if y_diffs[closest_idx] < 10:  # y坐标差异小于10像素
                        x_values.append(hist_data[closest_idx, 1])
                        width_values.append(hist_data[closest_idx, 2])
                        # 历史帧权重递减
                        weights.append(0.5 ** (len(self.centerline_history) - hist_idx - 1))
            
            # 加权平均
            if len(x_values) > 1:
                weights = np.array(weights)
                weights = weights / np.sum(weights)
                smoothed_data[i, 1] = np.sum(np.array(x_values) * weights)
                smoothed_data[i, 2] = np.sum(np.array(width_values) * weights)
        
        # 空间平滑：对结果再进行一次滑动窗口平均
        window_size = 3
        final_data = smoothed_data.copy()
        for i in range(len(final_data)):
            start_idx = max(0, i - window_size // 2)
            end_idx = min(len(final_data), i + window_size // 2 + 1)
            window = smoothed_data[start_idx:end_idx]
            if len(window) > 0:
                final_data[i, 1] = np.mean(window[:, 1])
                final_data[i, 2] = np.mean(window[:, 2])
        
        return final_data

    def _estimate_affine(self, prev_gray, curr_gray, mask=None):
        """使用光流估计仿射变换（备用方法）"""
        try:
            # 提取特征点
            if mask is not None:
                p0 = cv2.goodFeaturesToTrack(prev_gray, mask=mask, **self.feature_params)
            else:
                p0 = cv2.goodFeaturesToTrack(prev_gray, **self.feature_params)
            
            if p0 is None or len(p0) < 4:
                return np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)
            
            # 计算光流
            p1, st, err = cv2.calcOpticalFlowPyrLK(prev_gray, curr_gray, p0, None, **self.lk_params)
            
            if p1 is None or st is None:
                return np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)
            
            # 只保留好的点
            good_new = p1[st == 1].reshape(-1, 2)
            good_old = p0[st == 1].reshape(-1, 2)
            
            if len(good_new) < 4:
                return np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)
            
            # 估计仿射变换
            M, _ = cv2.estimateAffinePartial2D(good_old, good_new, method=cv2.RANSAC)
            
            if M is None:
                return np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)
            
            return M
            
        except Exception as e:
            logger.debug(f"仿射估计失败: {e}")
            return np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)
    
    def _warp_mask(self, mask, M, output_shape):
        """应用仿射变换"""
        try:
            W, H = output_shape
            warped = cv2.warpAffine(mask, M, (W, H), 
                                   flags=cv2.INTER_NEAREST,
                                   borderMode=cv2.BORDER_CONSTANT,
                                   borderValue=0)
            return warped
        except:
            return None
    
    def _add_mask_visualization(self, mask, visualizations, viz_type, color, add_outline=True):
        """添加掩码可视化（增加描边）"""
        if mask is None:
            return
        
        try:
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                main_contour = max(contours, key=cv2.contourArea)
                points = main_contour.squeeze(1)[::5].tolist()
                
                # 添加填充
                visualizations.append({
                    "type": viz_type,
                    "points": points,
                    "color": color
                })
                
                # 添加描边（盲道不添加描边）
                if add_outline and viz_type != "blind_path_mask":
                    visualizations.append({
                        "type": "outline",
                        "points": points,
                        "color": "rgba(255, 255, 255, 0.8)",  # 白色描边
                        "thickness": 3
                    })
        except:
            pass

    
    def _update_crosswalk_tracker(self, crosswalk_mask, image_height, image_width):
        """更新斑马线追踪器"""
        if crosswalk_mask is not None:
            self.crosswalk_tracker['consecutive_frames'] += 1
            self.crosswalk_tracker['last_seen_frame'] = self.frame_counter
            
            # 计算关键指标
            total_area = image_height * image_width
            area_ratio = np.sum(crosswalk_mask > 0) / total_area
            y_coords, x_coords = np.where(crosswalk_mask > 0)
            
            if len(y_coords) > 0:
                bottom_y_ratio = np.max(y_coords) / image_height
                center_x_ratio = np.mean(x_coords) / image_width
                
                self.crosswalk_tracker['last_area_ratio'] = area_ratio
                self.crosswalk_tracker['last_bottom_y_ratio'] = bottom_y_ratio
                self.crosswalk_tracker['last_center_x_ratio'] = center_x_ratio
                
                # 计算角度
                try:
                    contours, _ = cv2.findContours(crosswalk_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    if contours:
                        main_contour = max(contours, key=cv2.contourArea)
                        rect = cv2.minAreaRect(main_contour)
                        angle = rect[-1]
                        w, h = rect[1]
                        if w < h:
                            angle += 90
                        self.crosswalk_tracker['last_angle'] = angle
                except:
                    self.crosswalk_tracker['last_angle'] = 0.0
                
                # 状态切换
                is_ready_to_switch = (
                    area_ratio >= self.CROSSWALK_SWITCH_AREA_RATIO and
                    bottom_y_ratio >= self.CROSSWALK_SWITCH_BOTTOM_RATIO or
                    (self.crosswalk_tracker['consecutive_frames'] >= self.CROSSWALK_SWITCH_CONSECUTIVE_FRAMES 
                     and area_ratio > 0.18)
                )
                
                if is_ready_to_switch and self.crosswalk_tracker['alignment_status'] == 'aligned':
                    if self.crosswalk_tracker['stage'] != 'ready':
                        self.crosswalk_tracker['stage'] = 'ready'
                elif area_ratio > 0.07 or bottom_y_ratio > 0.75:
                    if self.crosswalk_tracker['stage'] in ['far', 'not_detected']:
                        self.crosswalk_tracker['stage'] = 'approaching'
                elif area_ratio > 0.01:
                    if self.crosswalk_tracker['stage'] == 'not_detected':
                        self.crosswalk_tracker['stage'] = 'far'
        else:
            # 丢失检测
            if self.frame_counter - self.crosswalk_tracker['last_seen_frame'] > 15:
                self.crosswalk_tracker['stage'] = 'not_detected'
                self.crosswalk_tracker['consecutive_frames'] = 0
                self.crosswalk_tracker['position_announced'] = False
                self.crosswalk_tracker['alignment_status'] = 'not_aligned'
                # 重置准备状态标志
                if hasattr(self, 'crosswalk_ready_announced'):
                    self.crosswalk_ready_announced = False
                    self.crosswalk_ready_time = 0
                if hasattr(self, 'traffic_light_history'):
                    self.traffic_light_history.clear()
                    self.green_light_announced = False
    
    def _handle_crosswalk_approaching(self, frame_visualizations, image_height, image_width, image):
        """处理接近斑马线的情况"""
        # 障碍物检测
        if self.obstacle_detector and self.frame_counter % self.OBSTACLE_DETECTION_INTERVAL == 0:
            detected_obstacles = self._detect_obstacles(image)
            self.last_detected_obstacles = detected_obstacles
            self.last_obstacle_detection_frame = self.frame_counter
        
        # 添加障碍物可视化
        for obs in self.last_detected_obstacles:
            self._add_obstacle_visualization(obs, frame_visualizations)
        
        # 优先检查近距离障碍物（提高阈值，只有非常近才报警）
        NEAR_DISTANCE_Y_THRESHOLD = 0.75  # 提高到0.75
        NEAR_DISTANCE_AREA_THRESHOLD = 0.12  # 提高到0.12
        near_obstacles = [
            obs for obs in self.last_detected_obstacles
            if (obs.get('bottom_y_ratio', 0) > NEAR_DISTANCE_Y_THRESHOLD or
                obs.get('area_ratio', 0) > NEAR_DISTANCE_AREA_THRESHOLD)
        ]
        
        # 如果有近距离障碍物，应用相同的播报逻辑
        if near_obstacles:
            main_obstacle = near_obstacles[0]
            obstacle_name = main_obstacle.get('name', '')
            current_time = time.time()
            
            # 检查是否需要播报（避免重复）
            should_announce = False
            if obstacle_name != self.last_obstacle_speech:
                should_announce = True
                self.last_obstacle_speech = obstacle_name
                self.last_obstacle_speech_time = current_time
            elif current_time - self.last_obstacle_speech_time > self.obstacle_speech_cooldown:
                should_announce = True
                self.last_obstacle_speech_time = current_time
            
            if should_announce:
                return self._speech_for_obstacle(obstacle_name)
        else:
            # 没有障碍物时清空记录
            self.last_obstacle_speech = ""
        
        # 对准逻辑
        if self.crosswalk_tracker['alignment_status'] == 'not_aligned':
            guidance_text = "正在接近斑马线，为您对准方向。"
            self.crosswalk_tracker['alignment_status'] = 'aligning'
        else:
            angle = self.crosswalk_tracker['last_angle']
            center_x_ratio = self.crosswalk_tracker['last_center_x_ratio']
            
            ANGLE_ALIGN_THRESHOLD = 15
            POSITION_ALIGN_THRESHOLD = 0.25
            
            if abs(angle) > ANGLE_ALIGN_THRESHOLD:
                guidance_text = "右转" if angle < 0 else "左转"
            elif abs(center_x_ratio - 0.5) > (POSITION_ALIGN_THRESHOLD / 2):
                guidance_text = "右移" if center_x_ratio < 0.5 else "左移"
            else:
                self.crosswalk_tracker['alignment_status'] = 'aligned'
                guidance_text = "斑马线已对准，继续前行。"
        
        # 添加数据面板
        data_for_panel = {
            "状态": "对准斑马线",
            "引导": guidance_text,
            "角度": f"{self.crosswalk_tracker['last_angle']:.1f}°",
            "偏移": f"{(self.crosswalk_tracker['last_center_x_ratio'] - 0.5):.2f}"
        }
        frame_visualizations.append({
            "type": "data_panel",
            "data": data_for_panel,
            "position": (25, image_height - 75)
        })
        
        return guidance_text
    
    def _execute_state_machine(self, mask, image, frame_visualizations, 
                              image_height, image_width, curr_gray):
        """执行状态机逻辑"""
        if self.current_state == STATE_ONBOARDING:
            return self._handle_onboarding(mask, image, frame_visualizations, 
                                         image_height, image_width)
        elif self.current_state == STATE_NAVIGATING:
            return self._handle_navigating(mask, image, frame_visualizations,
                                         image_height, image_width, curr_gray)
        elif self.current_state == STATE_MANEUVERING_TURN:
            return self._handle_maneuvering_turn(mask, image, frame_visualizations,
                                               image_height, image_width)
        elif self.current_state == STATE_LOCKING_ON:
            return self._handle_locking_on(frame_visualizations)
        elif self.current_state == STATE_AVOIDING_OBSTACLE:
            return self._handle_avoiding_obstacle(mask, image, frame_visualizations,
                                                image_height, image_width)
        
        return ""
    
    def _handle_onboarding(self, mask, image, frame_visualizations, image_height, image_width):
        """处理上盲道状态"""
        image_center_x = image_width / 2
        vp_features = self._get_vanishing_point_features(mask)
        
        if vp_features and vp_features['fit_error'] < self.VP_FIT_ERROR_THRESHOLD:
            # 使用灭点法
            VP, L_center = vp_features["VP"], vp_features["L_center"]
            
            if self.onboarding_step == ONBOARDING_STEP_ROTATION:
                if abs(VP[0] - image_center_x) < (image_width * self.ONBOARDING_ALIGN_THRESHOLD_RATIO):
                    guidance_text = "方向已对正！现在校准位置。"
                    self.onboarding_step = ONBOARDING_STEP_TRANSLATION
                else:
                    guidance_text = "请向左转动。" if VP[0] < image_center_x else "请向右转动。"
                
                angle_error_px = VP[0] - image_center_x
                self._add_data_panel(frame_visualizations, {
                    "状态": "上盲道 (方向)",
                    "引导": guidance_text,
                    "角度": f"{angle_error_px:.1f}px",
                    "偏移": "待校准"
                }, (25, image_height - 75))
                
            elif self.onboarding_step == ONBOARDING_STEP_TRANSLATION:
                L_center_bottom_x = self._calculate_line_x_at_y(L_center, image_height - 1)
                
                if L_center_bottom_x:
                    center_offset_pixels = L_center_bottom_x - image_center_x
                    center_offset_ratio = abs(center_offset_pixels) / image_width
                    
                    if center_offset_ratio < self.ONBOARDING_CENTER_OFFSET_THRESHOLD_RATIO:
                        guidance_text = "校准完成！您已在盲道上，开始前行。"
                        self.current_state = STATE_NAVIGATING
                    else:
                        guidance_text = "请向左平移。" if L_center_bottom_x < image_center_x else "请向右平移。"
                    
                    self._add_data_panel(frame_visualizations, {
                        "状态": "上盲道 (位置)",
                        "引导": guidance_text,
                        "角度": "已对准",
                        "偏移": f"{center_offset_ratio * 100:.1f}%"
                    }, (25, image_height - 75))
                else:
                    guidance_text = "请向前移动，让盲道更清晰。"
        else:
            # 使用像素域方法
            pixel_features = self._get_pixel_domain_features(mask, image.shape)
            if not pixel_features:
                return ""
            self._add_navigation_info_visualization(pixel_features, image_height, image_width, frame_visualizations)
            guidance_text = self._handle_pixel_domain_onboarding(
                pixel_features, image_height, image_width, frame_visualizations
            )
        
        return guidance_text
    
    def _handle_navigating(self, mask, image, frame_visualizations, 
                          image_height, image_width, curr_gray):
        """处理常规导航状态"""
        image_center_x = image_width / 2
        
        # 提取路径特征
        features = self._get_pixel_domain_features(mask, image.shape)
        if not features:
            return "路径特征提取失败"
        self._add_navigation_info_visualization(features, image_height, image_width, frame_visualizations)
        
        # 转弯检测
        if self.turn_cooldown_frames == 0:
            corner_info = self._detect_sharp_corner(features['centerline_data'])
            if corner_info:
                self._update_turn_tracker(corner_info)
                
                if self.turn_detection_tracker['consecutive_hits'] >= 3:
                    stable_corner_info = self.turn_detection_tracker['corner_info']
                    corner_y = stable_corner_info['corner_point_pixel'][1]
                    turn_trigger_y_threshold = image_height * 0.65
                    
                    if corner_y > turn_trigger_y_threshold:
                        # 触发转弯
                        direction_text = '右' if self.turn_detection_tracker['direction'] == 'right' else '左'
                        self.current_state = STATE_MANEUVERING_TURN
                        self.maneuver_target_info = stable_corner_info
                        self.maneuver_step = MANEUVER_STEP_1_ISSUE_COMMAND
                        self._reset_turn_tracker()
                        # 不再播报"到达转弯处"，直接返回空字符串，让后续逻辑处理
                        return ""
                    else:
                        # 不再预告转弯，继续常规导航
                        pass
        
        # 优先级1：障碍物检测（最高优先级）
        obstacles = self._check_obstacles(image, mask, frame_visualizations)
        if obstacles:
            # 获取主要障碍物
            main_obstacle = obstacles[0]
            obstacle_name = main_obstacle.get('name', '')
            current_time = time.time()
            
            # 检查是否需要播报（避免重复）
            should_announce = False
            if obstacle_name != self.last_obstacle_speech:
                # 不同障碍物，立即播报
                should_announce = True
                self.last_obstacle_speech = obstacle_name
                self.last_obstacle_speech_time = current_time
            elif current_time - self.last_obstacle_speech_time > self.obstacle_speech_cooldown:
                # 同一障碍物但超过冷却时间，再次播报
                should_announce = True
                self.last_obstacle_speech_time = current_time
            
            if should_announce:
                # 不进入完整的避障流程，只是警告
                # 设置待播报的障碍物语音，而不是直接返回
                self.pending_obstacle_voice = self._speech_for_obstacle(obstacle_name)
            # 如果不需要播报，继续常规导航
        else:
            # 没有障碍物，清空记录
            self.last_obstacle_speech = ""
            self.pending_obstacle_voice = None
        
        # 优先级2：常规导航（左移/右移/左转/右转 > 直行）
        return self._generate_navigation_guidance(
            features, image_height, image_width, frame_visualizations
        )
    
    def _handle_maneuvering_turn(self, mask, image, frame_visualizations,
                                image_height, image_width):
        """处理转弯状态"""
        features = self._get_pixel_domain_features(mask, image.shape)
        if not features:
            return "丢失路径，重新搜索。"
        self._add_navigation_info_visualization(features, image_height, image_width, frame_visualizations)
        if self.maneuver_step == MANEUVER_STEP_1_ISSUE_COMMAND:
            direction_text = '右' if self.maneuver_target_info['direction'] == 'right' else '左'
            guidance_text = f"请向{direction_text}平移。"
            
            poly_func = features['poly_func']
            y_check = image_height * 0.7
            self.maneuver_target_info['old_path_center_x'] = poly_func(y_check)
            
            self.maneuver_step = MANEUVER_STEP_2_WAIT_FOR_SHIFT
            
            self._add_data_panel(frame_visualizations, {
                "状态": "处理转弯",
                "引导": guidance_text,
                "步骤": "发出指令",
                "方向": direction_text
            }, (25, image_height - 75))
            
            return guidance_text
            
        elif self.maneuver_step == MANEUVER_STEP_2_WAIT_FOR_SHIFT:
            old_path_x = self.maneuver_target_info.get('old_path_center_x')
            if old_path_x is None:
                self.maneuver_step = MANEUVER_STEP_1_ISSUE_COMMAND
                return ""
            
            poly_func = features['poly_func']
            y_check = image_height * 0.7
            current_path_x = poly_func(y_check)
            shift_distance = abs(current_path_x - old_path_x)
            
            centerline_data = features['centerline_data']
            width_at_check_y = self._get_width_at_y(centerline_data, y_check)
            
            if shift_distance > (width_at_check_y * 0.5):
                guidance_text = "检测到已移动，开始对准新方向。"
                self.maneuver_step = MANEUVER_STEP_3_ALIGN_ON_NEW_PATH
            else:
                direction_text = '右' if self.maneuver_target_info['direction'] == 'right' else '左'
                guidance_text = f"请继续向{direction_text}平移。"
            
            self._add_data_panel(frame_visualizations, {
                "状态": "处理转弯",
                "引导": guidance_text,
                "步骤": "等待平移",
                "偏移量": f"{shift_distance:.1f}px"
            }, (25, image_height - 75))
            
            return guidance_text
            
        elif self.maneuver_step == MANEUVER_STEP_3_ALIGN_ON_NEW_PATH:
            poly_func = features['poly_func']
            y_check = image_height * 0.5
            current_path_x_at_center = poly_func(y_check)
            
            pixel_error = current_path_x_at_center - image_width / 2
            center_offset_ratio = abs(pixel_error) / image_width
            
            if center_offset_ratio < self.NAV_CENTER_OFFSET_THRESHOLD_RATIO:
                guidance_text = "已对准新路径，请向前直行。"
                self.current_state = STATE_NAVIGATING
                self.maneuver_target_info = None
                self.turn_cooldown_frames = self.TURN_COOLDOWN_DURATION
            else:
                move_direction = "右" if pixel_error > 0 else "左"
                guidance_text = f"请向{move_direction}微调，对准盲道。"
            
            self._add_data_panel(frame_visualizations, {
                "状态": "处理转弯",
                "引导": guidance_text,
                "步骤": "对准新路径",
                "误差": f"{center_offset_ratio * 100:.1f}%"
            }, (25, image_height - 75))
            
            return guidance_text
    
    def _handle_locking_on(self, frame_visualizations):
        """处理锁定状态"""
        if not self.lock_on_data:
            self.current_state = STATE_NAVIGATING
            return ""
        
        main_obstacle = self.lock_on_data['main_obstacle']
        
        # 添加脉冲特效
        self._add_obstacle_visualization(main_obstacle, frame_visualizations, pulse_effect=True)
        
        # 检查时间
        if time.time() - self.lock_on_data['start_time'] > 0.7:
            self.avoidance_plan = self.lock_on_data['avoidance_plan']
            self.avoidance_step_index = 0
            self.current_state = STATE_AVOIDING_OBSTACLE
            self.lock_on_data = None
        
        return ""
    
    def _handle_avoiding_obstacle(self, mask, image, frame_visualizations,
                                 image_height, image_width):
        """处理避障状态"""
        if not self.avoidance_plan or self.avoidance_step_index >= len(self.avoidance_plan):
            self.current_state = STATE_NAVIGATING
            self.avoidance_plan = None
            return "避让完成，已回到盲道。"
        
        step = self.avoidance_plan[self.avoidance_step_index]
        
        if step['type'] == 'sidestep_clear':
            direction = step['direction']
            
            if self.obstacle_detector:
                final_obstacles = self._detect_obstacles(image, mask)
            else:
                final_obstacles = []
            
            if final_obstacles:
                guidance_text = f"路径被挡住，请向{'右' if direction == 'right' else '左'}侧平移。"
            else:
                guidance_text = "好的，请停下侧移。"
                self.avoidance_step_index += 1
            
            self._add_data_panel(frame_visualizations, {
                "状态": "避障中",
                "引导": guidance_text,
                "步骤": "侧向移出",
                "方向": direction
            }, (25, image_height - 75))
            
            return guidance_text
            
        elif step['type'] == 'forward_pass':
            # 简化处理，直接进入下一步
            self.avoidance_step_index += 1
            return "向前直行几步越过障碍物。然后说‘好了’。"
            
        elif step['type'] == 'sidestep_return':
            direction = step['direction']
            features = self._get_pixel_domain_features(mask, image.shape)
            
            if not features:
                return f"没看到盲道，请向{'右' if direction == 'right' else '左'}侧小幅移动。"
            
            poly_func = features['poly_func']
            y_target = image_height * 0.5
            x_target = poly_func(y_target)
            
            center_offset_pixels = x_target - image_width / 2
            center_offset_ratio = abs(center_offset_pixels) / image_width
            
            if center_offset_ratio < self.NAV_CENTER_OFFSET_THRESHOLD_RATIO:
                guidance_text = "已回到盲道。"
                self.avoidance_step_index += 1
            else:
                guidance_text = "向右平移，对准盲道" if center_offset_pixels > 0 else "向左平移，对准盲道"
            
            self._add_data_panel(frame_visualizations, {
                "状态": "避障中",
                "引导": guidance_text,
                "步骤": "回归盲道",
                "偏移": f"{center_offset_ratio * 100:.1f}%"
            }, (25, image_height - 75))
            
            return guidance_text
    
    # ========== 辅助方法 ==========
    
    def _get_vanishing_point_features(self, mask):
        """提取灭点特征"""
        try:
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours: 
                return None
            main_contour = max(contours, key=cv2.contourArea)
            if cv2.contourArea(main_contour) < 5000: 
                return None
            
            rect = cv2.minAreaRect(main_contour)
            center, _, angle = rect
            angle_rad = np.deg2rad(angle)
            R = np.array([[np.cos(angle_rad), -np.sin(angle_rad)], 
                          [np.sin(angle_rad), np.cos(angle_rad)]])
            points_transformed = np.dot(main_contour.squeeze(1) - center, R)
            left_points = main_contour.squeeze(1)[points_transformed[:, 0] < 0]
            right_points = main_contour.squeeze(1)[points_transformed[:, 0] >= 0]
            
            if len(left_points) < 20 or len(right_points) < 20: 
                return None
            
            [vx_l, vy_l, x_l, y_l] = cv2.fitLine(left_points, cv2.DIST_L2, 0, 0.01, 0.01)
            [vx_r, vy_r, x_r, y_r] = cv2.fitLine(right_points, cv2.DIST_L2, 0, 0.01, 0.01)
            
            a1, b1, c1 = vy_l, -vx_l, vx_l * y_l - vy_l * x_l
            a2, b2, c2 = vy_r, -vx_r, vx_r * y_r - vy_r * x_r
            determinant = a1 * b2 - a2 * b1
            
            if abs(determinant) < 1e-6: 
                return None
            
            vp_x = (b1 * c2 - b2 * c1) / determinant
            vp_y = (a2 * c1 - a1 * c2) / determinant
            L_center = ((vx_l + vx_r) / 2, (vy_l + vy_r) / 2, (x_l + x_r) / 2, (y_l + y_r) / 2)
            
            total_dist = 0
            for pt in left_points: 
                total_dist += abs((pt[0] - x_l) * vy_l - (pt[1] - y_l) * vx_l)
            for pt in right_points: 
                total_dist += abs((pt[0] - x_r) * vx_r - (pt[1] - y_r) * vy_r)
            fit_error = total_dist / (len(left_points) + len(right_points))
            
            return {"VP": (vp_x, vp_y), "L_center": L_center, "fit_error": fit_error}
        except:
            return None
    
    def _get_pixel_domain_features(self, mask, image_shape):
        """提取像素域特征"""
        try:
            height, width = image_shape[:2]
            
            centerline_data = []
            for y in range(height - 1, int(height * 0.3), -5):
                row = mask[y, :]
                x_pixels = np.where(row > 0)[0]
                if x_pixels.size > 10:
                    x_min, x_max = x_pixels[0], x_pixels[-1]
                    path_width = x_max - x_min
                    center_x = (x_min + x_max) / 2
                    centerline_data.append([y, center_x, path_width])
            
            if len(centerline_data) < 20: 
                return None
            
            data = np.array(centerline_data)
            
            # 应用中心线平滑
            data = self._smooth_centerline(data)
            
            # 检测急转弯
            sharp_turn_index = self._find_sharp_turn(data)
            if sharp_turn_index is not None:
                cutoff_index = int(sharp_turn_index * 0.6)
                if cutoff_index >= 10:
                    data = data[:cutoff_index]
            
            y_coords, x_coords, widths = data[:, 0], data[:, 1], data[:, 2]
            weights = widths
            
            # 原始多项式拟合
            coeffs_raw = np.polyfit(y_coords, x_coords, 2, w=weights)
            
            # 【新增】对多项式系数进行时间平滑
            self.poly_coeffs_history.append(coeffs_raw.copy())
            if len(self.poly_coeffs_history) > self.poly_coeffs_history_max:
                self.poly_coeffs_history.pop(0)
            
            # 使用指数加权移动平均平滑系数
            if len(self.poly_coeffs_history) >= 3:
                # 权重：最近的帧权重更高
                weights_time = np.array([0.7 ** (len(self.poly_coeffs_history) - i - 1) 
                                        for i in range(len(self.poly_coeffs_history))])
                weights_time = weights_time / np.sum(weights_time)
                
                # 加权平均系数
                coeffs = np.zeros_like(coeffs_raw)
                for i, hist_coeffs in enumerate(self.poly_coeffs_history):
                    coeffs += hist_coeffs * weights_time[i]
            else:
                coeffs = coeffs_raw
            
            poly_func = np.poly1d(coeffs)
            
            curvature_proxy = abs(coeffs[0])
            tangent_slope = 2 * coeffs[0] * height + coeffs[1]
            tangent_angle_rad = np.arctan(tangent_slope)
            
            return {
                "poly_func": poly_func,
                "curvature_proxy": curvature_proxy,
                "tangent_angle_rad": tangent_angle_rad,
                "centerline_data": np.array(centerline_data)
            }
        except Exception as e:
            logger.warning(f"Pixel domain feature calculation failed: {e}")
            return None
    
    def _find_sharp_turn(self, data):
        """查找急转弯点"""
        window_size = 5
        angle_threshold = 30
        
        for i in range(len(data) - 2 * window_size):
            front_window = data[i:i + window_size]
            back_window = data[i + window_size:i + 2 * window_size]
            
            front_dir = [front_window[-1, 1] - front_window[0, 1],
                        front_window[-1, 0] - front_window[0, 0]]
            back_dir = [back_window[-1, 1] - back_window[0, 1],
                       back_window[-1, 0] - back_window[0, 0]]
            
            angle1 = np.arctan2(front_dir[1], front_dir[0])
            angle2 = np.arctan2(back_dir[1], back_dir[0])
            angle_diff = abs(np.degrees(angle2 - angle1))
            
            if angle_diff > 180:
                angle_diff = 360 - angle_diff
            
            if angle_diff > angle_threshold:
                return i + window_size
        
        return None
    
    def _detect_sharp_corner(self, centerline_data, angle_threshold_deg=45):
        """检测急转弯"""
        try:
            if len(centerline_data) < 15: 
                return None
            points_in_range = np.array(centerline_data)
            num_points = len(points_in_range)
            
            window_size = max(5, int(num_points * 0.15))
            best_turn_info = None
            max_angle_diff = 0
            
            for i in range(0, num_points - 2 * window_size, 2):
                front_segment = points_in_range[i:i + window_size]
                back_segment = points_in_range[i + window_size:i + 2 * window_size]
                
                if len(front_segment) < 3 or len(back_segment) < 3:
                    continue
                
                front_y = front_segment[:, 0]
                front_x = front_segment[:, 1]
                front_coeffs = np.polyfit(front_y, front_x, 1)
                front_slope = front_coeffs[0]
                
                back_y = back_segment[:, 0]
                back_x = back_segment[:, 1]
                back_coeffs = np.polyfit(back_y, back_x, 1)
                back_slope = back_coeffs[0]
                
                front_angle = np.arctan(front_slope)
                back_angle = np.arctan(back_slope)
                
                angle_diff_rad = back_angle - front_angle
                angle_diff_deg = abs(np.degrees(angle_diff_rad))
                
                if angle_diff_deg > max_angle_diff and angle_diff_deg > angle_threshold_deg:
                    max_angle_diff = angle_diff_deg
                    corner_point_idx = i + window_size
                    corner_point = points_in_range[corner_point_idx]
                    
                    direction = "right" if angle_diff_rad > 0 else "left"
                    
                    post_turn_segment = points_in_range[
                        corner_point_idx:min(corner_point_idx + window_size * 2, num_points)]
                    if len(post_turn_segment) > 0:
                        post_turn_center_x = np.mean(post_turn_segment[:, 1])
                    else:
                        post_turn_center_x = corner_point[1]
                    
                    best_turn_info = {
                        "corner_point_pixel": (corner_point[1], corner_point[0]),
                        "turn_angle": max_angle_diff,
                        "direction": direction,
                        "post_turn_center_x": post_turn_center_x,
                        "corner_point_idx": corner_point_idx
                    }
            
            return best_turn_info
        
        except Exception as e:
            logger.warning(f"Corner detection error: {e}")
            return None
    
    def _update_turn_tracker(self, corner_info):
        """更新转弯追踪器"""
        detected_direction = corner_info['direction']
        
        if detected_direction == self.turn_detection_tracker['direction']:
            self.turn_detection_tracker['consecutive_hits'] += 1
        else:
            self.turn_detection_tracker['direction'] = detected_direction
            self.turn_detection_tracker['consecutive_hits'] = 1
        
        self.turn_detection_tracker['last_seen_frame'] = self.frame_counter
        self.turn_detection_tracker['corner_info'] = corner_info
    
    def _reset_turn_tracker(self):
        """重置转弯追踪器"""
        self.turn_detection_tracker = {
            'direction': None,
            'consecutive_hits': 0,
            'last_seen_frame': 0,
            'corner_info': None
        }
    
    def _calculate_line_x_at_y(self, line_params, y_target):
        """计算直线在特定y坐标的x值"""
        vx, vy, x0, y0 = line_params
        if abs(vy) < 1e-6:
            return None
        t = (y_target - y0) / vy
        x = x0 + t * vx
        return x
    
    def _get_width_at_y(self, centerline_data, y_target):
        """获取特定y坐标的路径宽度"""
        ys = centerline_data[:, 0]
        ws = centerline_data[:, 2]
        idx = np.abs(ys - y_target).argmin()
        return ws[idx]
    
    def _detect_obstacles(self, image, path_mask=None):
        """检测障碍物"""
        logger.info(f"[_detect_obstacles] 开始执行，Frame={self.frame_counter}, obstacle_detector={'已加载' if self.obstacle_detector else '未加载'}")
        
        if self.obstacle_detector is None:
            logger.warning("[_detect_obstacles] 障碍物检测器未加载！")
            return []
        
        # 【新增】打印白名单类别（只在第一次调用时打印）
        if not hasattr(self, '_classes_printed'):
            self._classes_printed = True
            if hasattr(self.obstacle_detector, 'WHITELIST_CLASSES'):
                logger.info("[_detect_obstacles] ===== 障碍物检测白名单类别 =====")
                for idx, name in enumerate(self.obstacle_detector.WHITELIST_CLASSES):
                    logger.info(f"  - 类别 {idx}: {name}")
                logger.info(f"[_detect_obstacles] 总共 {len(self.obstacle_detector.WHITELIST_CLASSES)} 个类别")
        
        try:
            # 【关键修改】使用 ObstacleDetectorClient 的 detect() 方法
            # 它会自动处理 YOLO-E 的文本提示设置、检测和基本过滤
            logger.info(f"[_detect_obstacles] 调用ObstacleDetectorClient.detect()... image.shape={image.shape}")
            detected_obstacles = self.obstacle_detector.detect(image, path_mask=path_mask)
            
            logger.info(f"[_detect_obstacles] ObstacleDetectorClient 返回 {len(detected_obstacles)} 个物体")
            
            # ObstacleDetectorClient 已经返回了正确格式的数据，包括：
            # - name: 物体名称
            # - mask: 分割掩码
            # - area: 面积
            # - area_ratio: 面积比例
            # - center_x, center_y: 中心坐标
            # - bottom_y_ratio: 底部Y比例
            
            # 补充一些可能缺失但后续代码需要的字段
            H, W = image.shape[:2]
            for i, obj in enumerate(detected_obstacles):
                # 添加用于可视化的边界框坐标
                if 'mask' in obj and obj['mask'] is not None:
                    y_coords, x_coords = np.where(obj['mask'] > 0)
                    if len(y_coords) > 0 and len(x_coords) > 0:
                        x1, y1 = int(np.min(x_coords)), int(np.min(y_coords))
                        x2, y2 = int(np.max(x_coords)), int(np.max(y_coords))
                        obj['box_coords'] = (x1, y1, x2, y2)
                        
                        # 补充可能缺失的字段
                        if 'y_position_ratio' not in obj:
                            obj['y_position_ratio'] = obj.get('center_y', 0) / H
                        if 'label' not in obj:
                            obj['label'] = obj.get('name', 'unknown')
                        if 'center' not in obj:
                            obj['center'] = (obj.get('center_x', 0), obj.get('center_y', 0))
                        # 添加一个假的置信度（如果需要的话）
                        if 'confidence' not in obj:
                            obj['confidence'] = 0.5  # ObstacleDetectorClient 已经过滤了低置信度的
                
                # 详细的日志输出
                logger.info(f"[_detect_obstacles] 物体 {i+1}/{len(detected_obstacles)}: ")
                logger.info(f"  - 类别: {obj.get('name', 'unknown')}")
                logger.info(f"  - 面积: {obj.get('area', 0)} pixels ({obj.get('area_ratio', 0):.3f} of image)")
                logger.info(f"  - 中心点: ({obj.get('center_x', 0):.1f}, {obj.get('center_y', 0):.1f})")
                logger.info(f"  - bottom_y_ratio: {obj.get('bottom_y_ratio', 0):.3f} (是否近距离: {'是' if obj.get('bottom_y_ratio', 0) > 0.7 else '否'})")
                logger.info(f"  - area_ratio: {obj.get('area_ratio', 0):.3f} (是否过大: {'是' if obj.get('area_ratio', 0) > 0.1 else '否'})")
            
            # 【注意】ObstacleDetectorClient 已经做了以下过滤：
            # 1. 尺寸过滤（太大的物体，面积超过70%的会被过滤）
            # 2. 置信度过滤（根据环境变量 AIGLASS_OBS_CONF，默认0.25）
            # 3. 如果提供了 path_mask，会做路径相关的空间过滤：
            #    - 要求与路径有至少100像素的交集
            #    - 要求交集占物体面积的至少1%
            # 所以这里不需要再做额外的过滤
            
            logger.info(f"[_detect_obstacles] ===== 最终结果: 返回 {len(detected_obstacles)} 个障碍物 =====")
            for idx, obj in enumerate(detected_obstacles):
                logger.info(f"  {idx+1}. {obj.get('name', 'unknown')} - 位置:({obj.get('center_x', 0):.0f},{obj.get('center_y', 0):.0f}) "
                        f"bottom_y_ratio:{obj.get('bottom_y_ratio', 0):.2f} area_ratio:{obj.get('area_ratio', 0):.3f}")
            
            return detected_obstacles
            
        except Exception as e:
            logger.error(f"[_detect_obstacles] 障碍物检测失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _check_and_set_obstacle_voice(self, obstacles):
        """检查障碍物并设置待播报的语音"""
        if not obstacles:
            self.last_obstacle_speech = ""
            self.pending_obstacle_voice = None
            return
        
        # 筛选近距离障碍物（提高阈值，只有非常近才报警）
        NEAR_DISTANCE_Y_THRESHOLD = 0.75  # 提高到0.75，障碍物底部必须在画面下方75%以下
        NEAR_DISTANCE_AREA_THRESHOLD = 0.12  # 提高到0.12，障碍物必须占画面12%以上
        
        near_obstacles = []
        for obs in obstacles:
            if (obs.get('bottom_y_ratio', 0) > NEAR_DISTANCE_Y_THRESHOLD or
                obs.get('area_ratio', 0) > NEAR_DISTANCE_AREA_THRESHOLD):
                near_obstacles.append(obs)
        
        if near_obstacles:
            # 获取最主要的障碍物（面积最大）
            main_obstacle = max(near_obstacles, key=lambda x: x.get('area_ratio', 0))
            obstacle_name = main_obstacle.get('name', '')
            current_time = time.time()
            
            # 检查是否需要播报
            should_announce = False
            if obstacle_name != self.last_obstacle_speech:
                # 不同障碍物，立即播报
                should_announce = True
                self.last_obstacle_speech = obstacle_name
                self.last_obstacle_speech_time = current_time
            elif current_time - self.last_obstacle_speech_time > self.obstacle_speech_cooldown:
                # 同一障碍物但超过冷却时间，再次播报
                should_announce = True
                self.last_obstacle_speech_time = current_time
            
            if should_announce:
                self.pending_obstacle_voice = self._speech_for_obstacle(obstacle_name)
        else:
            # 没有近距离障碍物
            self.last_obstacle_speech = ""
            self.pending_obstacle_voice = None

    def _check_obstacles(self, image, mask, frame_visualizations):
        """检查并处理障碍物"""
        # 使用缓存策略
        if self.frame_counter % self.OBSTACLE_DETECTION_INTERVAL == 0:
            final_obstacles = self._detect_obstacles(image, mask)
            # 【新增】稳定化障碍物，避免重复叠加
            if hasattr(self, 'prev_gray') and self.prev_gray is not None:
                curr_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                final_obstacles = self._stabilize_obstacle_list(
                    final_obstacles, 
                    self.last_detected_obstacles,
                    self.prev_gray,
                    curr_gray,
                    image.shape[:2]
                )
            self.last_detected_obstacles = final_obstacles
            self.last_obstacle_detection_frame = self.frame_counter
        else:
            if self.frame_counter - self.last_obstacle_detection_frame < self.OBSTACLE_CACHE_DURATION_FRAMES:
                final_obstacles = self.last_detected_obstacles
            else:
                final_obstacles = []
        
        # 添加可视化
        for obs in final_obstacles:
            self._add_obstacle_visualization(obs, frame_visualizations)
        
        # 筛选近距离障碍物（提高阈值，只有非常近才报警）
        NEAR_DISTANCE_Y_THRESHOLD = 0.75  # 提高到0.75，障碍物底部必须在画面下方75%以下
        NEAR_DISTANCE_AREA_THRESHOLD = 0.12  # 提高到0.12，障碍物必须占画面12%以上
        
        near_obstacles = [
            obs for obs in final_obstacles
            if (obs.get('bottom_y_ratio', 0) > NEAR_DISTANCE_Y_THRESHOLD or
                obs.get('area_ratio', 0) > NEAR_DISTANCE_AREA_THRESHOLD)
        ]
        
        return near_obstacles
    
    def _plan_avoidance(self, obstacle_info, image_width):
        """规划避障路径"""
        obstacle_center_x = obstacle_info['center_x']
        image_center_x = image_width / 2
        
        if obstacle_center_x < image_center_x:
            turn_direction = 'right'
        else:
            turn_direction = 'left'
        
        plan = [
            {'type': 'sidestep_clear', 'direction': turn_direction},
            {'type': 'forward_pass'},
            {'type': 'sidestep_return', 'direction': 'left' if turn_direction == 'right' else 'right'}
        ]
        return plan
    
    def _generate_navigation_guidance(self, features, image_height, image_width, frame_visualizations):
        """生成导航指引"""
        poly_func = features['poly_func']
        is_curve = features['curvature_proxy'] > self.CURVATURE_PROXY_THRESHOLD
        lookahead_ratio = 0.6 if is_curve else 0.4
        y_target = image_height * lookahead_ratio
        x_target = poly_func(y_target)
        
        # 添加中心线可视化
        plot_y = np.arange(int(image_height * 0.3), image_height, 5).astype(int)
        plot_x = poly_func(plot_y).astype(int)
        centerline_points = np.vstack((plot_x, plot_y)).T.tolist()
        frame_visualizations.append({
            "type": "polyline",
            "points": centerline_points,
            "color": "yellow",
            "width": 2
        })
        
        # 添加目标点
        frame_visualizations.append({
            "type": "circle",
            "center": [int(x_target), int(y_target)],
            "radius": 10,
            "color": "red"
        })
        
        # 计算导航指令（优先级：转向/平移 > 直行）
        center_offset_pixels = x_target - image_width / 2
        center_offset_ratio = abs(center_offset_pixels) / image_width
        orientation_error_rad = features['tangent_angle_rad']
        
        # 先检查是否需要转向（左转/右转）
        if orientation_error_rad > self.NAV_ORIENTATION_THRESHOLD_RAD:
            guidance_text = "左转"
        elif orientation_error_rad < -self.NAV_ORIENTATION_THRESHOLD_RAD:
            guidance_text = "右转"
        # 再检查是否需要平移（左移/右移）
        elif center_offset_ratio > self.NAV_CENTER_OFFSET_THRESHOLD_RATIO:
            guidance_text = "右移" if center_offset_pixels > 0 else "左移"
        # 最后才是直行
        else:
            guidance_text = "保持直行"
        
        # 添加数据面板
        self._add_data_panel(frame_visualizations, {
            "状态": "常规导航",
            "引导": guidance_text,
            "朝向": f"{np.degrees(orientation_error_rad):.1f}°",
            "偏移": f"{center_offset_ratio * 100:.1f}%"
        }, (25, image_height - 75))
        
        return guidance_text
    
    def _handle_pixel_domain_onboarding(self, pixel_features, image_height, image_width, frame_visualizations):
        """处理像素域的上盲道引导"""
        image_center_x = image_width / 2
        orientation_error_rad = pixel_features['tangent_angle_rad']
        poly_func = pixel_features['poly_func']
        
        y_bottom = image_height - 1
        x_target_bottom = poly_func(y_bottom)
        center_offset_pixels = x_target_bottom - image_center_x
        center_offset_ratio = abs(center_offset_pixels) / image_width
        
        if self.onboarding_step == ONBOARDING_STEP_ROTATION:
            if abs(orientation_error_rad) < self.ONBOARDING_ORIENTATION_THRESHOLD_RAD:
                guidance_text = "方向已对正！现在校准位置。"
                self.onboarding_step = ONBOARDING_STEP_TRANSLATION
            else:
                guidance_text = "请向左转动。" if orientation_error_rad > 0.1 else "请向右转动。"
            
            self._add_data_panel(frame_visualizations, {
                "状态": "上盲道 (方向)",
                "引导": guidance_text,
                "角度": f"{np.degrees(orientation_error_rad):.1f}°",
                "偏移": "待校准"
            }, (25, image_height - 75))
            self._add_navigation_info_visualization(pixel_features, image_height, image_width, frame_visualizations)
    
            return guidance_text
            
        elif self.onboarding_step == ONBOARDING_STEP_TRANSLATION:
            if center_offset_ratio < self.ONBOARDING_CENTER_OFFSET_THRESHOLD_RATIO:
                guidance_text = "校准完成！您已在盲道上，开始前行。"
                self.current_state = STATE_NAVIGATING
            else:
                guidance_text = "请向右平移。" if center_offset_pixels > 0 else "请向左平移。"
            
            self._add_data_panel(frame_visualizations, {
                "状态": "上盲道 (位置)",
                "引导": guidance_text,
                "角度": "已对准",
                "偏移": f"{center_offset_ratio * 100:.1f}%"
            }, (25, image_height - 75))
        
        return guidance_text
    
    def _add_obstacle_visualization(self, obstacle, visualizations, pulse_effect=False):
        """添加障碍物可视化（简化版：仅边框，近红远黄）"""
        try:
            # 计算障碍物危险等级
            bottom_y_ratio = obstacle.get('bottom_y_ratio', 0)
            area_ratio = obstacle.get('area_ratio', 0)
            
            # 判断是否为近距离障碍物
            is_near = bottom_y_ratio > 0.7 or area_ratio > 0.1  # 近距离障碍物
            
            # 添加 mask 边框可视化（如果有）
            if 'mask' in obstacle and obstacle['mask'] is not None:
                mask = obstacle['mask']
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                if contours:
                    # 找到最大的轮廓
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

    def _add_navigation_info_visualization(self, features, image_height, image_width, frame_visualizations):
        """添加导航计算信息的可视化"""
        if not features:
            return
        
        try:
            # 获取计算结果
            poly_func = features.get('poly_func')
            curvature_proxy = features.get('curvature_proxy', 0)
            tangent_angle_rad = features.get('tangent_angle_rad', 0)
            tangent_angle_deg = np.degrees(tangent_angle_rad)
            
            # 绘制切线方向
            if poly_func:
                # 在画面底部计算切线
                y_bottom = image_height - 50
                x_bottom = poly_func(y_bottom)
                
                # 计算切线的终点
                tangent_length = 100
                dx = tangent_length * np.cos(tangent_angle_rad)
                dy = tangent_length * np.sin(tangent_angle_rad)
                
                # 【新增】绘制基准虚线（垂直向上）
                baseline_length = 80
                frame_visualizations.append({
                    "type": "dashed_line",
                    "start": [int(x_bottom), int(y_bottom)],
                    "end": [int(x_bottom), int(y_bottom - baseline_length)],
                    "color": "rgba(255, 255, 255, 0.6)",  # 白色虚线
                    "thickness": 2
                })
                
                # 添加切线可视化
                frame_visualizations.append({
                    "type": "arrow",
                    "start": [int(x_bottom), int(y_bottom)],
                    "end": [int(x_bottom + dx), int(y_bottom - dy)],  # 注意Y轴方向
                    "color": "rgba(0, 255, 255, 0.8)",  # 青色
                    "thickness": 3,
                    "tip_length": 0.3
                })
                
                # 【新增】绘制夹角弧线标识
                arc_radius = 40
                # 基准线角度是-90度（向上），切线角度是tangent_angle_deg
                # OpenCV中角度是从右侧水平线逆时针测量
                start_angle = -90  # 基准线（垂直向上）
                end_angle = -90 + tangent_angle_deg  # 切线角度
                frame_visualizations.append({
                    "type": "angle_arc",
                    "center": [int(x_bottom), int(y_bottom)],
                    "radius": arc_radius,
                    "start_angle": start_angle,
                    "end_angle": end_angle,
                    "color": "rgba(255, 200, 0, 0.8)",  # 橙黄色
                    "thickness": 2
                })
                
                # 添加角度文字（文字大小减半）
                frame_visualizations.append({
                    "type": "text_with_bg",
                    "text": f"角度: {tangent_angle_deg:.1f}°",
                    "position": [int(x_bottom + 10), int(y_bottom - 30)],
                    "font_scale": 0.3,  # 从0.6减半到0.3
                    "color": "rgba(255, 255, 255, 1.0)",
                    "bg_color": "rgba(0, 0, 0, 0.7)"
                })
            
            # 添加曲率信息（文字大小减半）
            if curvature_proxy > 0.00001:
                curve_text = "弯道" if curvature_proxy > 0.00005 else "缓弯"
                frame_visualizations.append({
                    "type": "text_with_bg",
                    "text": f"{curve_text}: {curvature_proxy:.2e}",
                    "position": [20, 100],
                    "font_scale": 0.25,  # 从0.5减半到0.25
                    "color": "rgba(255, 255, 0, 1.0)",
                    "bg_color": "rgba(0, 0, 0, 0.7)"
                })
                
            # 显示中心线数据点
            if 'centerline_data' in features:
                centerline_data = features['centerline_data']
                # 在画面中部显示路径宽度
                mid_idx = len(centerline_data) // 2
                if mid_idx < len(centerline_data):
                    y, x, width = centerline_data[mid_idx]
                    # 绘制宽度指示线（改为双向箭头）
                    frame_visualizations.append({
                        "type": "double_arrow",  # 新增双向箭头类型
                        "start": [int(x - width/2), int(y)],
                        "end": [int(x + width/2), int(y)],
                        "color": "rgba(0, 255, 0, 0.8)",
                        "thickness": 2,
                        "tip_length": 0.15
                    })
                    # 添加宽度文字（文字大小减半）
                    frame_visualizations.append({
                        "type": "text_with_bg",
                        "text": f"宽度: {width:.0f}px",
                        "position": [int(x - 30), int(y - 10)],
                        "font_scale": 0.25,  # 从0.5减半到0.25
                        "color": "rgba(255, 255, 255, 1.0)",
                        "bg_color": "rgba(0, 0, 0, 0.7)"
                    })
        except Exception as e:
            logger.error(f"添加导航信息可视化失败: {e}")

    def _add_data_panel(self, visualizations, data, position):
        """添加数据面板"""
        visualizations.append({
            "type": "data_panel",
            "data": data,
            "position": position
        })
    
    def _add_crosswalk_info_visualization(self, viz_data, image_height, image_width, visualizations):
        """添加斑马线检测信息的精美可视化"""
        try:
            # 1. 绘制斑马线中心点标识（大十字）
            center_x = int(viz_data['center_x_ratio'] * image_width)
            center_y = int(viz_data['center_y_ratio'] * image_height)
            
            cross_size = 20 if viz_data['in_arrival'] else 15  # 减小尺寸
            cross_color = "rgba(255, 100, 0, 1.0)" if viz_data['in_arrival'] else "rgba(0, 200, 255, 0.8)"
            
            # 水平线
            visualizations.append({
                "type": "line",
                "start": [center_x - cross_size, center_y],
                "end": [center_x + cross_size, center_y],
                "color": cross_color,
                "thickness": 2  # 减细
            })
            # 垂直线
            visualizations.append({
                "type": "line",
                "start": [center_x, center_y - cross_size],
                "end": [center_x, center_y + cross_size],
                "color": cross_color,
                "thickness": 2  # 减细
            })
            
            # 2. 绘制指向斑马线的箭头（从画面中心指向斑马线中心）
            screen_center_x = image_width // 2
            screen_center_y = image_height // 2
            
            # 只在斑马线不在画面中心时绘制箭头
            distance = np.sqrt((center_x - screen_center_x)**2 + (center_y - screen_center_y)**2)
            if distance > 80:  # 提高到80像素才画箭头（减少干扰）
                visualizations.append({
                    "type": "arrow",
                    "start": [screen_center_x, screen_center_y],
                    "end": [center_x, center_y],
                    "color": "rgba(255, 150, 0, 0.6)",  # 降低透明度
                    "thickness": 2,  # 减细
                    "tip_length": 0.15  # 减小箭头
                })
            
            # 3. 添加信息面板（右上角）
            panel_x = image_width - 180
            panel_y = 20
            
            # 准备面板数据
            panel_data = {
                "斑马线": viz_data['stage'],
                "面积": f"{viz_data['area_ratio']*100:.1f}%",
                "方位": viz_data['position'],
            }
            
            if viz_data['has_occlusion']:
                panel_data["状态"] = "被遮挡"
            elif viz_data['in_arrival']:
                panel_data["状态"] = "可过马路"
            
            visualizations.append({
                "type": "data_panel",
                "data": panel_data,
                "position": (panel_x, panel_y)
            })
            
            # 4. 添加面积进度条（视觉化面积大小）
            bar_width = 150
            bar_height = 20
            bar_x = image_width - bar_width - 20
            bar_y = panel_y + 90
            
            # 背景框
            visualizations.append({
                "type": "rectangle",
                "top_left": (bar_x, bar_y),
                "bottom_right": (bar_x + bar_width, bar_y + bar_height),
                "color": "rgba(50, 50, 50, 0.7)",
                "filled": True
            })
            
            # 进度填充（0-100%，但最多显示到arrival阈值0.25对应100%）
            progress = min(viz_data['area_ratio'] / 0.25, 1.0)
            fill_width = int(bar_width * progress)
            
            # 根据阶段选择颜色
            if viz_data['in_arrival']:
                fill_color = "rgba(0, 255, 100, 0.8)"  # 绿色（可过马路）
            elif viz_data['area_ratio'] >= 0.18:
                fill_color = "rgba(255, 200, 0, 0.8)"  # 黄色（接近）
            elif viz_data['area_ratio'] >= 0.08:
                fill_color = "rgba(0, 200, 255, 0.8)"  # 青色（靠近）
            else:
                fill_color = "rgba(100, 150, 255, 0.8)"  # 蓝色（发现）
            
            visualizations.append({
                "type": "rectangle",
                "top_left": (bar_x + 2, bar_y + 2),
                "bottom_right": (bar_x + fill_width - 2, bar_y + bar_height - 2),
                "color": fill_color,
                "filled": True
            })
            
            # 进度条标签（使用中文文本，字体减小）
            visualizations.append({
                "type": "text_with_bg",
                "text": f"接近度: {int(progress * 100)}%",
                "position": [bar_x, bar_y - 18],
                "font_scale": 0.25,  # 减小字体
                "color": "rgba(255, 255, 255, 1.0)",
                "bg_color": "rgba(0, 0, 0, 0.7)"
            })
            
        except Exception as e:
            logger.error(f"添加斑马线可视化失败: {e}")
    
    def _add_traffic_light_visualization(self, color, visualizations, image_height, image_width):
        """添加红绿灯状态可视化"""
        # 在右上角绘制红绿灯指示器
        x = image_width - 100
        y = 50
        
        # 背景框
        visualizations.append({
            "type": "rectangle",
            "top_left": (x - 40, y - 40),
            "bottom_right": (x + 40, y + 100),
            "color": "rgba(0, 0, 0, 0.5)",
            "filled": True
        })
        
        # 三个圆形灯
        colors = {
            "red": [(255, 0, 0), (50, 0, 0), (50, 0, 0)],
            "yellow": [(50, 50, 0), (255, 255, 0), (50, 50, 0)],
            "green": [(0, 50, 0), (0, 50, 0), (0, 255, 0)],
            "unknown": [(50, 50, 50), (50, 50, 50), (50, 50, 50)]
        }
        
        light_colors = colors.get(color, colors["unknown"])
        positions = [y - 20, y + 20, y + 60]
        
        for i, (pos_y, light_color) in enumerate(zip(positions, light_colors)):
            # 外圈
            visualizations.append({
                "type": "circle",
                "center": [x, pos_y],
                "radius": 18,
                "color": f"rgba(100, 100, 100, 1.0)",
                "thickness": 2
            })
            # 内圈（灯的颜色）
            visualizations.append({
                "type": "circle",
                "center": [x, pos_y],
                "radius": 15,
                "color": f"rgba({light_color[0]}, {light_color[1]}, {light_color[2]}, 1.0)",
                "filled": True
            })
        
        # 标签
        visualizations.append({
            "type": "text_with_bg",
            "text": f"信号灯: {color}",
            "position": [x - 35, y + 90],
            "font_scale": 0.5,
            "color": "rgba(255, 255, 255, 1.0)",
            "bg_color": "rgba(0, 0, 0, 0.7)"
        })
    
    def _to_cn_obstacle(self, name: str) -> str:
        """转换障碍物名称为中文"""
        try:
            key = (name or '').strip().lower()
            return _OBSTACLE_NAME_CN.get(key, '障碍物')
        except:
            return '障碍物'

    def _speech_for_obstacle(self, name: str) -> str:
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

    def _draw_command_button(self, image, text):
        """绘制底部中央的指令按钮（与斑马线模式统一）"""
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
            
            if PIL_AVAILABLE and 'font' in locals() and font:
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
    
    def _parse_color(self, color_str):
        """解析颜色字符串，返回BGR格式"""
        try:
            if color_str.startswith('rgba('):
                values = color_str[5:-1].split(',')
                r, g, b = int(values[0]), int(values[1]), int(values[2])
                return (b, g, r)  # OpenCV 使用 BGR 格式
            elif color_str == 'yellow':
                return (0, 255, 255)
            elif color_str == 'red':
                return (0, 0, 255)
            else:
                return (0, 0, 255)  # 默认红色
        except:
            return (0, 0, 255)

    def _draw_data_panel_no_bg(self, image, data, position=(15, 15)):
        """绘制数据面板（无黑底版本）"""
        if not PIL_AVAILABLE:
            return image
        
        try:
            pil_img = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_img, "RGBA")
            
            env_scale = float(os.getenv("AIGLASS_PANEL_SCALE", "0.7"))
            base_font_size = max(10, int(round(14 * env_scale)))
            
            # 尝试多种字体，确保中文显示
            font = None
            font_paths = [
                "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
                "C:/Windows/Fonts/simhei.ttf",    # 黑体
                "C:/Windows/Fonts/simsun.ttc",    # 宋体
                "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",  # Linux
                "/System/Library/Fonts/PingFang.ttc",  # macOS
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
            
            # 绘制文本，使用描边效果
            y_offset = position[1]
            for key, value in data.items():
                text = f"{key}: {value}"
                
                # 绘制黑色描边（8个方向）
                for dx in [-1, 0, 1]:
                    for dy in [-1, 0, 1]:
                        if dx != 0 or dy != 0:
                            draw.text((position[0] + dx, y_offset + dy), text, 
                                    font=font, fill=(0, 0, 0, 255))
                
                # 绘制白色文字
                draw.text((position[0], y_offset), text, font=font, fill=(255, 255, 255, 255))
                y_offset += base_font_size + 5
            
            return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        
        except Exception as e:
            logger.warning(f"绘制数据面板失败: {e}")
            return image


    def _draw_visualizations(self, image, viz_elements):
        """增强的可视化绘制方法"""
        if not viz_elements:
            return image
        
        # 获取当前时间用于动画效果
        current_time = time.time()
        
        # 分离不同类型的元素
        panel_elements = [v for v in viz_elements if v.get("type") == "data_panel"]
        standard_elements = [v for v in viz_elements if v.get("type") != "data_panel"]
        
        # 第一遍：绘制填充（半透明效果）
        for element in standard_elements:
            elem_type = element.get("type")
            
            if elem_type in ['blind_path_mask', 'obstacle_mask', 'crosswalk_mask']:
                points = np.array(element.get("points", []), dtype=np.int32)
                if points.size > 0:
                    color = self._parse_color(element.get("color", "rgba(255, 255, 255, 0.5)"))
                    
                    # 处理脉冲效果
                    if element.get("effect") == "pulse":
                        pulse_speed = element.get("pulse_speed", 1.0)
                        alpha = 0.3 + 0.3 * np.sin(current_time * pulse_speed * 2 * np.pi)
                    else:
                        alpha = 0.4
                    
                    # 获取多边形的边界框
                    x, y, w, h = cv2.boundingRect(points)
                    
                    # 确保边界框在图像范围内
                    x = max(0, x)
                    y = max(0, y)
                    w = min(w, image.shape[1] - x)
                    h = min(h, image.shape[0] - y)
                    
                    if w > 0 and h > 0:
                        # 创建一个二值掩码，只在多边形内部为1
                        binary_mask = np.zeros((h, w), dtype=np.uint8)
                        local_points = points - np.array([x, y])
                        cv2.fillPoly(binary_mask, [local_points], 255)
                        
                        # 只在多边形内部进行颜色混合
                        local_region = image[y:y+h, x:x+w].copy()
                        
                        # 创建彩色覆盖层
                        color_overlay = np.zeros((h, w, 3), dtype=np.uint8)
                        color_overlay[:] = color
                        
                        # 使用二值掩码进行混合
                        for c in range(3):
                            local_region[:, :, c] = np.where(
                                binary_mask > 0,
                                (1 - alpha) * local_region[:, :, c] + alpha * color_overlay[:, :, c],
                                local_region[:, :, c]
                            )
                        
                        # 将混合后的局部区域放回原图
                        image[y:y+h, x:x+w] = local_region
        
        # 第二遍：绘制轮廓和其他元素
        for element in standard_elements:
            elem_type = element.get("type")
            
            # 【新增】绘制直线
            if elem_type == 'line':
                start = tuple(element.get("start", (0, 0)))
                end = tuple(element.get("end", (100, 100)))
                color = self._parse_color(element.get("color", "rgba(255, 255, 255, 1.0)"))
                thickness = element.get("thickness", 2)
                cv2.line(image, start, end, color, thickness)
            
            # 绘制轮廓/描边
            elif elem_type == 'outline':
                points = np.array(element.get("points", []), dtype=np.int32)
                if points.size > 0:
                    color = self._parse_color(element.get("color", "rgba(255, 255, 255, 1.0)"))
                    thickness = element.get("thickness", 3)
                    cv2.polylines(image, [points], isClosed=True, color=color, thickness=thickness)
            
            # 绘制折线
            elif elem_type == 'polyline':
                points = np.array(element.get("points", []), dtype=np.int32)
                if points.size > 0:
                    color = self._parse_color(element.get("color", "rgba(255, 255, 0, 1.0)"))
                    thickness = element.get("width", 2)
                    cv2.polylines(image, [points], isClosed=False, color=color, thickness=thickness)
            
            # 绘制圆形
            elif elem_type == 'circle':
                center = tuple(element.get("center", (0, 0)))
                radius = element.get("radius", 10)
                color = self._parse_color(element.get("color", "rgba(255, 0, 0, 1.0)"))
                thickness = element.get("thickness", -1 if element.get("filled", True) else 2)
                cv2.circle(image, center, radius, color, thickness)
            
            # 绘制矩形
            elif elem_type == 'rectangle':
                top_left = tuple(element.get("top_left", (0, 0)))
                bottom_right = tuple(element.get("bottom_right", (100, 100)))
                color = self._parse_color(element.get("color", "rgba(0, 0, 0, 0.5)"))
                thickness = -1 if element.get("filled", True) else 2
                cv2.rectangle(image, top_left, bottom_right, color, thickness)
            
            # 绘制箭头
            elif elem_type == 'arrow':
                start = tuple(element.get("start", (0, 0)))
                end = tuple(element.get("end", (100, 100)))
                color = self._parse_color(element.get("color", "rgba(0, 255, 255, 1.0)"))
                thickness = element.get("thickness", 2)
                tip_length = element.get("tip_length", 0.3)
                cv2.arrowedLine(image, start, end, color, thickness, tipLength=tip_length)
            
            # 【新增】绘制双向箭头
            elif elem_type == 'double_arrow':
                start = tuple(element.get("start", (0, 0)))
                end = tuple(element.get("end", (100, 100)))
                color = self._parse_color(element.get("color", "rgba(0, 255, 0, 0.8)"))
                thickness = element.get("thickness", 2)
                tip_length = element.get("tip_length", 0.15)
                # 绘制中间的线
                cv2.line(image, start, end, color, thickness)
                # 绘制两端的箭头
                # 计算箭头方向向量
                dx = end[0] - start[0]
                dy = end[1] - start[1]
                length = np.sqrt(dx*dx + dy*dy)
                if length > 0:
                    # 单位方向向量
                    ux, uy = dx/length, dy/length
                    # 箭头长度
                    arrow_len = length * tip_length
                    # 左端箭头
                    tip1_x = int(start[0] + arrow_len * ux)
                    tip1_y = int(start[1] + arrow_len * uy)
                    # 绘制左端箭头（指向左）
                    angle = np.arctan2(dy, dx)
                    arrow_angle = 30 * np.pi / 180  # 箭头角度
                    p1 = (int(start[0] + arrow_len * np.cos(angle - arrow_angle)),
                          int(start[1] + arrow_len * np.sin(angle - arrow_angle)))
                    p2 = (int(start[0] + arrow_len * np.cos(angle + arrow_angle)),
                          int(start[1] + arrow_len * np.sin(angle + arrow_angle)))
                    cv2.line(image, start, p1, color, thickness)
                    cv2.line(image, start, p2, color, thickness)
                    # 右端箭头（指向右）
                    p3 = (int(end[0] - arrow_len * np.cos(angle - arrow_angle)),
                          int(end[1] - arrow_len * np.sin(angle - arrow_angle)))
                    p4 = (int(end[0] - arrow_len * np.cos(angle + arrow_angle)),
                          int(end[1] - arrow_len * np.sin(angle + arrow_angle)))
                    cv2.line(image, end, p3, color, thickness)
                    cv2.line(image, end, p4, color, thickness)
            
            # 【新增】绘制虚线
            elif elem_type == 'dashed_line':
                start = np.array(element.get("start", (0, 0)))
                end = np.array(element.get("end", (100, 100)))
                color = self._parse_color(element.get("color", "rgba(255, 255, 255, 0.6)"))
                thickness = element.get("thickness", 2)
                dash_length = 10
                gap_length = 5
                # 计算总长度和方向
                total_vec = end - start
                total_len = np.linalg.norm(total_vec)
                if total_len > 0:
                    unit_vec = total_vec / total_len
                    # 绘制虚线段
                    current_len = 0
                    while current_len < total_len:
                        seg_start = start + unit_vec * current_len
                        seg_end = start + unit_vec * min(current_len + dash_length, total_len)
                        cv2.line(image, tuple(seg_start.astype(int)), tuple(seg_end.astype(int)), color, thickness)
                        current_len += dash_length + gap_length
            
            # 【新增】绘制角度弧线
            elif elem_type == 'angle_arc':
                center = tuple(element.get("center", (100, 100)))
                radius = element.get("radius", 40)
                start_angle = element.get("start_angle", -90)
                end_angle = element.get("end_angle", 0)
                color = self._parse_color(element.get("color", "rgba(255, 200, 0, 0.8)"))
                thickness = element.get("thickness", 2)
                # OpenCV的ellipse函数：startAngle和endAngle是从右侧水平线开始顺时针测量
                # 需要转换：我们的角度是从右侧水平线逆时针（数学标准）
                # OpenCV需要的是从右侧水平线顺时针
                cv2_start = -end_angle  # 转换为OpenCV格式
                cv2_end = -start_angle
                # 确保角度范围正确
                if cv2_start > cv2_end:
                    cv2_start, cv2_end = cv2_end, cv2_start
                cv2.ellipse(image, center, (radius, radius), 0, cv2_start, cv2_end, color, thickness)
            
            # 【修改】绘制带背景的文本（使用中文支持）
            elif elem_type == 'text_with_bg':
                text = element.get("text", "")
                pos = element.get("position", [10, 30])
                font_scale = element.get("font_scale", 0.6)
                color = self._parse_color(element.get("color", "rgba(255, 255, 255, 1.0)"))
                
                # 使用新的中文文本绘制函数
                image = self._draw_chinese_text(image, text, tuple(pos), 
                                              font_scale=font_scale, 
                                              color=color,
                                              stroke_color=(0, 0, 0),
                                              stroke_width=1)
            
            # 绘制警告图标
            elif elem_type == 'warning_icon':
                pos = element.get("position", (100, 100))
                level = element.get("level", "info")
                text = element.get("text", "")
                flash = element.get("flash", False)
                
                # 根据级别选择颜色
                if level == "danger":
                    icon_color = (0, 0, 255)  # 红色
                    text_color = (255, 255, 255)
                elif level == "warning":
                    icon_color = (0, 165, 255)  # 橙色
                    text_color = (255, 255, 255)
                else:
                    icon_color = (0, 255, 255)  # 黄色
                    text_color = (0, 0, 0)
                
                # 闪烁效果
                if flash:
                    alpha = 0.5 + 0.5 * np.sin(current_time * 4 * np.pi)
                    icon_color = tuple(int(c * alpha) for c in icon_color)
                
                # 绘制三角形警告图标
                triangle = np.array([
                    [pos[0], pos[1] - 20],
                    [pos[0] - 15, pos[1]],
                    [pos[0] + 15, pos[1]]
                ], np.int32)
                cv2.fillPoly(image, [triangle], icon_color)
                cv2.polylines(image, [triangle], True, (255, 255, 255), 2)
                
                # 绘制感叹号
                cv2.putText(image, "!", (pos[0] - 5, pos[1] - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                # 绘制文本标签（使用中文支持）
                if text:
                    font_scale = 0.5
                    # 使用新的中文文本绘制函数
                    text_pos = (pos[0] - 20, pos[1] + 20)  # 简化位置计算
                    image = self._draw_chinese_text(image, text, text_pos,
                                                  font_scale=font_scale,
                                                  color=text_color,
                                                  stroke_color=(0, 0, 0),
                                                  stroke_width=1)
            
            # 普通文本
            elif elem_type == 'text':
                text = element.get("text", "")
                pos = tuple(element.get("pos", (10, 30)))
                # 使用中文文本绘制函数
                image = self._draw_chinese_text(image, text, pos,
                                              font_scale=0.7,
                                              color=(255, 255, 255),
                                              stroke_color=(0, 0, 0),
                                              stroke_width=1)
        
        # 【修改】绘制数据面板（使用无黑底版本）
        if PIL_AVAILABLE:
            for panel in panel_elements:
                image = self._draw_data_panel_no_bg(image, panel["data"], panel["position"])
        else:
            # 如果没有PIL，也使用描边效果
            for panel in panel_elements:
                y_offset = panel["position"][1]
                for key, value in panel["data"].items():
                    text = f"{key}: {value}"
                    # 绘制文字描边
                    for dx in [-1, 0, 1]:
                        for dy in [-1, 0, 1]:
                            if dx != 0 or dy != 0:
                                cv2.putText(image, text, (panel["position"][0] + dx, y_offset + dy), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3)
                    # 绘制白色文字
                    cv2.putText(image, text, (panel["position"][0], y_offset), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
                    y_offset += 25
        
        return image


    
    def _draw_chinese_text(self, image, text, position, font_scale=0.6, color=(255, 255, 255), 
                         stroke_color=(0, 0, 0), stroke_width=1):
        """绘制中文文本，使用微软雅黑字体，白字黑边"""
        if not PIL_AVAILABLE:
            # 如果没有PIL，回退到cv2.putText（会显示问号）
            cv2.putText(image, text, position, cv2.FONT_HERSHEY_SIMPLEX, 
                       font_scale, color, 2)
            return image
        
        try:
            # 转换为PIL图像
            pil_img = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_img)
            
            # 计算字体大小（基于font_scale）
            base_size = 24  # 基准字体大小
            font_size = int(base_size * font_scale / 0.6)
            
            # 尝试加载微软雅黑字体
            font = None
            font_paths = [
                "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
                "C:/Windows/Fonts/msyh.ttf",      # 微软雅黑旧版
                "C:/Windows/Fonts/simhei.ttf",    # 黑体
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",  # Linux
                "/System/Library/Fonts/PingFang.ttc",  # macOS
            ]
            
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        font = ImageFont.truetype(font_path, font_size)
                        break
                    except:
                        continue
            
            if font is None:
                font = ImageFont.load_default()
            
            # 将OpenCV的BGR颜色转换为RGB
            rgb_color = (color[2], color[1], color[0])
            rgb_stroke = (stroke_color[2], stroke_color[1], stroke_color[0])
            
            # 绘制文本（带描边效果）
            x, y = position
            # 绘制描边
            draw.text((x, y), text, font=font, fill=rgb_stroke, 
                     stroke_width=stroke_width, stroke_fill=rgb_stroke)
            # 绘制主文本
            draw.text((x, y), text, font=font, fill=rgb_color)
            
            # 转换回OpenCV格式
            return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            
        except Exception as e:
            logger.warning(f"绘制中文文本失败: {e}")
            # 回退到cv2.putText
            cv2.putText(image, text, position, cv2.FONT_HERSHEY_SIMPLEX, 
                       font_scale, color, 2)
            return image

    def _draw_data_panel(self, image, data, position=(15, 15)):
        """绘制数据面板（需要Pillow）"""
        if not PIL_AVAILABLE:
            return image
        
        try:
            pil_img = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_img, "RGBA")
            
            env_scale = float(os.getenv("AIGLASS_PANEL_SCALE", "0.65"))
            base_font_size = max(8, int(round(16 * env_scale)))
            padding = max(4, int(round(8 * env_scale)))
            
            # 尝试加载微软雅黑字体
            font = None
            font_paths = [
                "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
                "C:/Windows/Fonts/msyh.ttf",      # 微软雅黑旧版
                "C:/Windows/Fonts/simhei.ttf",    # 黑体
            ]
            
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        font = ImageFont.truetype(font_path, base_font_size)
                        break
                    except:
                        continue
            
            if font is None:
                font = ImageFont.load_default()
            
            text_lines = [f"{key}: {value}" for key, value in data.items()]
            text_to_draw = "\n".join(text_lines)
            
            bbox = draw.textbbox(position, text_to_draw, font=font)
            text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            
            bg_rect = [
                (position[0] - padding, position[1] - padding),
                (position[0] + text_w + padding, position[1] + text_h + padding)
            ]
            draw.rectangle(bg_rect, fill=(0, 0, 0, 128))
            draw.text(position, text_to_draw, font=font, fill=(255, 255, 255, 255))
            
            return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        
        except Exception:
            return image
    
    def reset(self):
        """重置导航器状态"""
        self.current_state = STATE_ONBOARDING
        self.onboarding_step = ONBOARDING_STEP_ROTATION
        self.maneuver_step = MANEUVER_STEP_1_ISSUE_COMMAND
        self.maneuver_target_info = None
        self.turn_detection_tracker = {
            'direction': None,
            'consecutive_hits': 0,
            'last_seen_frame': 0,
            'corner_info': None
        }
        self.turn_cooldown_frames = 0
        self.avoidance_plan = None
        self.avoidance_step_index = 0
        self.lock_on_data = None
        
        # 重置光流和平滑相关
        self.flow_points = {}
        self.flow_grace = {}
        self.centerline_history = []
        self.blind_miss_ttl = 0
        self.cross_miss_ttl = 0
        
        # 重置语音相关
        self.pending_obstacle_voice = None
        self.last_obstacle_speech = ""
        self.last_obstacle_speech_time = 0
        
        # 重置多项式系数历史
        self.poly_coeffs_history = []
        self.crosswalk_tracker = {
            'stage': 'not_detected',
            'consecutive_frames': 0,
            'last_area_ratio': 0.0,
            'last_bottom_y_ratio': 0.0,
            'last_center_x_ratio': 0.5,
            'position_announced': False,
            'alignment_status': 'not_aligned',
            'last_seen_frame': 0,
            'last_angle': 0.0
        }
        self.frame_counter = 0
        self.prev_gray = None
        self.prev_blind_path_mask = None
        self.prev_crosswalk_mask = None
        self.prev_obstacle_cache = []
        self.last_guidance_message = ""
        self.last_detected_obstacles = []
        self.last_obstacle_detection_frame = 0
        self.last_obstacle_speech = ""
        self.last_obstacle_speech_time = 0
        self.last_any_speech_time = 0
        self.crosswalk_ready_announced = False
        self.crosswalk_ready_time = 0
        self.traffic_light_history.clear()
        self.last_traffic_light_state = "unknown"
        self.green_light_announced = False
    
    def _stabilize_obstacle_list(self, obstacles, prev_obstacles, prev_gray, curr_gray, 
                                image_shape, threshold=0.5):
        """稳定障碍物检测结果，避免重复叠加"""
        if not obstacles or prev_gray is None or curr_gray is None:
            return obstacles
        
        H, W = image_shape
        stabilized = []
        used_prev = set()  # 记录已使用的历史障碍物
        
        # 对每个当前检测到的障碍物
        for curr_obs in obstacles:
            if 'mask' not in curr_obs or curr_obs['mask'] is None:
                stabilized.append(curr_obs)
                continue
                
            curr_mask = curr_obs['mask']
            best_match = None
            best_iou = 0
            best_idx = -1
            
            # 寻找最佳匹配的历史障碍物
            if prev_obstacles:
                for idx, prev_obs in enumerate(prev_obstacles):
                    if idx in used_prev or 'mask' not in prev_obs:
                        continue
                    
                    # 使用光流预测历史障碍物的新位置
                    flow_mask = self._predict_mask_with_flow(prev_obs['mask'], prev_gray, curr_gray)
                    if flow_mask is None:
                        flow_mask = prev_obs['mask']
                    
                    # 计算IoU
                    inter = np.logical_and(curr_mask > 0, flow_mask > 0).sum()
                    union = np.logical_or(curr_mask > 0, flow_mask > 0).sum()
                    iou = float(inter) / float(union) if union > 0 else 0.0
                    
                    if iou > best_iou and iou > threshold:
                        best_iou = iou
                        best_match = flow_mask
                        best_idx = idx
            
            # 如果找到匹配，融合结果
            if best_match is not None and best_idx >= 0:
                used_prev.add(best_idx)
                # 融合当前检测和光流预测，提高稳定性
                fused_mask = ((0.8 * curr_mask + 0.2 * best_match) > 128).astype(np.uint8) * 255
                curr_obs['mask'] = fused_mask
                # 更新派生属性
                self._update_obstacle_properties(curr_obs, H, W)
            
            stabilized.append(curr_obs)
        
        return stabilized
  
    def _speech_for_obstacle(self, name: str) -> str:
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

    def _update_obstacle_properties(self, obs, H, W):
        """更新障碍物的派生属性"""
        if 'mask' not in obs or obs['mask'] is None:
            return
        
        mask = obs['mask']
        y_coords, x_coords = np.where(mask > 0)
        
        if len(y_coords) > 0:
            obs['area'] = len(y_coords)
            obs['center_x'] = float(np.mean(x_coords))
            obs['center_y'] = float(np.mean(y_coords))
            obs['y_position_ratio'] = obs['center_y'] / H
            obs['area_ratio'] = obs['area'] / (H * W)
            obs['bottom_y_ratio'] = np.max(y_coords) / H
            
            # 更新边界框
            x1, y1 = int(np.min(x_coords)), int(np.min(y_coords))
            x2, y2 = int(np.max(x_coords)), int(np.max(y_coords))
            obs['box_coords'] = (x1, y1, x2, y2)