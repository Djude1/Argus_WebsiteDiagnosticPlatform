# utils.py
# -*- coding: utf-8 -*-
import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)

# 物品名称映射
ITEM_TO_CLASS_MAP = {
    "红牛": "Red_Bull",
    "AD钙奶": "AD_milk",
    "ad钙奶": "AD_milk",
    "钙奶": "AD_milk",
}

# 英文类别名到中文的映射
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

def extract_english_label(item_cn: str) -> tuple:
    """
    提取中文物品名称对应的英文标签
    :param item_cn: 中文物品名称
    :return: (英文标签, 来源)
    """
    # 先查找本地映射
    if item_cn in ITEM_TO_CLASS_MAP:
        return ITEM_TO_CLASS_MAP[item_cn], "local"
    
    # 如果没有找到，返回原始名称
    return item_cn, "direct"

def _to_cn_obstacle(name: str) -> str:
    """
    将英文障碍物名称转换为中文
    :param name: 英文名称
    :return: 中文名称
    """
    try:
        key = (name or '').strip().lower()
        return _OBSTACLE_NAME_CN.get(key, '障碍物')
    except Exception:
        return '障碍物'

def estimate_global_affine(prev_gray, curr_gray, mask=None):
    """
    估计两帧之间的全局仿射变换
    :param prev_gray: 前一帧灰度图
    :param curr_gray: 当前帧灰度图
    :param mask: 可选的掩码，只在掩码区域内计算
    :return: (仿射矩阵, 内点数)
    """
    try:
        # 提取特征点
        detector = cv2.ORB_create(nfeatures=500)
        kp1, des1 = detector.detectAndCompute(prev_gray, mask)
        kp2, des2 = detector.detectAndCompute(curr_gray, mask)
        
        if des1 is None or des2 is None or len(kp1) < 10 or len(kp2) < 10:
            return np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32), 0
        
        # 匹配特征点
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = matcher.match(des1, des2)
        
        if len(matches) < 4:
            return np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32), 0
        
        # 提取匹配的点对
        src_pts = np.float32([kp1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
        
        # 使用RANSAC估计仿射变换
        M, inliers = cv2.estimateAffinePartial2D(src_pts, dst_pts, method=cv2.RANSAC, 
                                                 ransacReprojThreshold=3.0)
        
        if M is None:
            return np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32), 0
        
        inlier_count = np.sum(inliers) if inliers is not None else 0
        return M, inlier_count
        
    except Exception as e:
        logger.warning(f"estimate_global_affine failed: {e}")
        return np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32), 0

def warp_mask(mask, M, output_shape):
    """
    使用仿射变换对掩码进行变换
    :param mask: 输入掩码
    :param M: 2x3的仿射变换矩阵
    :param output_shape: 输出形状 (width, height)
    :return: 变换后的掩码
    """
    try:
        if mask is None or M is None:
            return None
        
        W, H = output_shape
        warped = cv2.warpAffine(mask, M, (W, H), 
                               flags=cv2.INTER_NEAREST,
                               borderMode=cv2.BORDER_CONSTANT,
                               borderValue=0)
        return warped
        
    except Exception as e:
        logger.warning(f"warp_mask failed: {e}")
        return None

def estimate_translation_flow(prev_gray, curr_gray, mask=None):
    """
    估计两帧之间的平移光流
    :param prev_gray: 前一帧灰度图
    :param curr_gray: 当前帧灰度图
    :param mask: 可选的掩码
    :return: (中位光流幅度, 平移矩阵)
    """
    try:
        # 计算稀疏光流
        corners = cv2.goodFeaturesToTrack(prev_gray, maxCorners=100, 
                                         qualityLevel=0.3, minDistance=7, 
                                         mask=mask)
        
        if corners is None or len(corners) < 10:
            return 0.0, np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)
        
        # 计算光流
        next_pts, status, _ = cv2.calcOpticalFlowPyrLK(prev_gray, curr_gray, 
                                                       corners, None)
        
        # 筛选有效点
        valid_old = corners[status == 1]
        valid_new = next_pts[status == 1]
        
        if len(valid_old) < 5:
            return 0.0, np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)
        
        # 计算位移
        flow_vectors = valid_new - valid_old
        flow_magnitudes = np.linalg.norm(flow_vectors, axis=1)
        median_flow = np.median(flow_magnitudes)
        
        # 估计平均平移
        mean_translation = np.mean(flow_vectors, axis=0)
        M = np.array([[1, 0, mean_translation[0]], 
                      [0, 1, mean_translation[1]]], dtype=np.float32)
        
        return median_flow, M
        
    except Exception as e:
        logger.warning(f"estimate_translation_flow failed: {e}")
        return 0.0, np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)

def is_stationary_frame(prev_gray, curr_gray, mask=None, threshold=0.35):
    """
    判断用户是否静止
    :param prev_gray: 前一帧灰度图
    :param curr_gray: 当前帧灰度图
    :param mask: 可选的掩码
    :param threshold: 静止判定阈值
    :return: True表示静止，False表示运动
    """
    try:
        median_flow, _ = estimate_translation_flow(prev_gray, curr_gray, mask)
        return median_flow < threshold
    except:
        return False

def compute_approach_metrics(prev_obstacles, curr_obstacles, M, H, W):
    """
    计算障碍物的接近度量
    :param prev_obstacles: 前一帧障碍物列表
    :param curr_obstacles: 当前帧障碍物列表
    :param M: 仿射变换矩阵
    :param H: 图像高度
    :param W: 图像宽度
    :return: 接近度量列表
    """
    metrics = []
    
    for curr_obs in curr_obstacles:
        # 寻找最佳匹配的前一帧障碍物
        best_match = None
        best_iou = 0.0
        
        curr_mask = curr_obs.get('mask')
        if curr_mask is None:
            metrics.append(None)
            continue
        
        for prev_obs in prev_obstacles:
            prev_mask = prev_obs.get('mask')
            if prev_mask is None:
                continue
            
            # 将前一帧掩码变换到当前帧
            warped_prev = warp_mask(prev_mask, M, (W, H))
            if warped_prev is None:
                continue
            
            # 计算IoU
            intersection = np.logical_and(curr_mask > 0, warped_prev > 0).sum()
            union = np.logical_or(curr_mask > 0, warped_prev > 0).sum()
            iou = intersection / union if union > 0 else 0.0
            
            if iou > best_iou:
                best_iou = iou
                best_match = prev_obs
        
        if best_match is None:
            metrics.append(None)
            continue
        
        # 计算度量
        curr_area = curr_obs.get('area', 0)
        prev_area = best_match.get('area', 0)
        area_growth = (curr_area - prev_area) / prev_area if prev_area > 0 else 0.0
        
        curr_bottom_y = curr_obs.get('bottom_y_ratio', 0)
        prev_bottom_y = best_match.get('bottom_y_ratio', 0)
        v_forward = curr_bottom_y - prev_bottom_y
        
        metrics.append({
            'area_growth': area_growth,
            'v_forward': v_forward,
            'iou': best_iou
        })
    
    return metrics

def compute_risk_scores(obstacles, prev_obstacles, M, path_mask, image_shape,
                       stop_th=0.6, avoid_th=0.56):
    """
    计算障碍物的风险评分
    :param obstacles: 当前障碍物列表
    :param prev_obstacles: 前一帧障碍物列表
    :param M: 仿射变换矩阵
    :param path_mask: 路径掩码
    :param image_shape: 图像形状
    :param stop_th: 停止阈值
    :param avoid_th: 避让阈值
    :return: (评分后的障碍物列表, 是否需要停止, 是否需要避让, 可视化元素)
    """
    H, W = image_shape[:2]
    has_stop = False
    has_avoid = False
    risk_vis = []
    
    # 计算接近度量
    metrics = compute_approach_metrics(prev_obstacles, obstacles, M, H, W)
    
    for obs, met in zip(obstacles, metrics):
        risk_score = 0.0
        
        if met is not None:
            # 基于接近速度和面积增长计算风险
            if met['v_forward'] > 0.004:  # 向下移动
                risk_score += 0.3
            if met['area_growth'] > 0.01:  # 面积增长
                risk_score += 0.3
        
        # 基于距离的风险
        bottom_y = obs.get('bottom_y_ratio', 0)
        area_ratio = obs.get('area_ratio', 0)
        
        if bottom_y > 0.8 or area_ratio > 0.15:
            risk_score += 0.3
        
        # 动态物体额外风险
        name_lower = str(obs.get('name', '')).lower()
        if name_lower in DYNAMIC_CLASS_NAMES:
            risk_score *= 1.2
        
        obs['risk_score'] = risk_score
        
        # 更新标志
        if risk_score >= stop_th:
            has_stop = True
        elif risk_score >= avoid_th:
            has_avoid = True
        
        # 添加风险可视化
        if risk_score > 0.3:
            risk_color = "rgba(255, 0, 0, 0.3)" if risk_score >= stop_th else "rgba(255, 165, 0, 0.3)"
            risk_vis.append({
                "type": "risk_indicator",
                "score": risk_score,
                "color": risk_color,
                "position": [int(obs.get('center_x', W/2)), int(obs.get('center_y', H/2))]
            })
    
    return obstacles, has_stop, has_avoid, risk_vis

