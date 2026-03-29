# -*- coding: utf-8 -*-
"""
斑马线感知监控器
基于面积变化的斑马线检测和语音提示
不涉及状态切换，只提供语音引导
"""
import time
import numpy as np
from collections import deque
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class CrosswalkAwarenessMonitor:
    """斑马线感知监控器 - 纯语音提示模块"""
    
    def __init__(self):
        # 面积阈值（固定锚点）
        self.THRESHOLDS = {
            'discover': 0.01,      # 1% - 发现
            'approaching': 0.08,   # 8% - 靠近
            'near': 0.18,          # 18% - 很近
            'arrival': 0.25,       # 25% - 到达（可以过马路）
        }
        
        # 已播报的阈值（避免重复）
        self.broadcasted_thresholds = set()
        
        # 面积历史记录
        self.area_history = deque(maxlen=30)  # 保存最近30帧
        
        # 时间记录
        self.last_broadcast_time = 0
        self.arrival_first_broadcast_time = 0
        
        # 状态标志
        self.in_arrival_state = False  # 是否在"可以过马路"状态
        self.last_position_zone = None  # 上次播报的方位
        
        # 播报间隔配置（可调整参数 - 数值越小播报越频繁）
        # 【参数调整】将所有间隔除以1.5，提高播报频率1.5倍
        self.REPEAT_INTERVALS = {
            'approaching': 6.7,   # 靠近阶段：每6.7秒重复（原10秒÷1.5）
            'near': 3.3,          # 很近阶段：每3.3秒重复（原5秒÷1.5）
            'arrival': 5.3,       # 到达阶段：每5.3秒重复（原8秒÷1.5）
        }
        # 提示：如需调整频率，修改这些数值即可
        # - 数值越小 = 播报越频繁
        # - 数值越大 = 播报越稀疏
        
        # 无遮挡判断阈值
        self.OCCLUSION_THRESHOLD = 0.30  # 重叠>30%认为有遮挡
    
    def process_frame(self, crosswalk_mask, blind_path_mask=None) -> Optional[Dict[str, Any]]:
        """
        处理每帧的斑马线检测
        
        返回：
        {
            'voice_text': 语音文本,
            'priority': 优先级,
            'should_broadcast': 是否应该播报,
            'area': 当前面积,
            'position': 方位描述,
            'visualization': 可视化信息（用于外部绘制）
        }
        或 None（无需播报）
        """
        # 如果没有斑马线，重置状态
        if crosswalk_mask is None:
            self._reset_if_needed()
            return None
        
        # 1. 计算面积
        total_pixels = crosswalk_mask.size
        crosswalk_pixels = np.sum(crosswalk_mask > 0)
        area_ratio = crosswalk_pixels / total_pixels
        
        # 2. 计算中心位置
        y_coords, x_coords = np.where(crosswalk_mask > 0)
        if len(y_coords) == 0:
            return None
        
        center_x_ratio = np.mean(x_coords) / crosswalk_mask.shape[1]
        center_y_ratio = np.mean(y_coords) / crosswalk_mask.shape[0]
        
        # 3. 记录历史
        current_time = time.time()
        self.area_history.append({
            'area': area_ratio,
            'center_x': center_x_ratio,
            'center_y': center_y_ratio,
            'time': current_time
        })
        
        # 4. 检查遮挡
        has_occlusion = self._check_occlusion(crosswalk_mask, blind_path_mask)
        
        # 5. 判断当前阶段和生成语音
        return self._generate_guidance(area_ratio, center_x_ratio, center_y_ratio, 
                                       has_occlusion, current_time)
    
    def _check_occlusion(self, crosswalk_mask, blind_path_mask) -> bool:
        """检查斑马线是否被盲道遮挡"""
        if blind_path_mask is None:
            return False
        
        crosswalk_area = crosswalk_mask > 0
        blind_path_area = blind_path_mask > 0
        
        # 计算重叠
        overlap = np.logical_and(crosswalk_area, blind_path_area)
        overlap_ratio = np.sum(overlap) / max(np.sum(crosswalk_area), 1)
        
        # 重叠超过阈值认为有遮挡
        return overlap_ratio > self.OCCLUSION_THRESHOLD
    
    def _get_position_description(self, center_x_ratio) -> str:
        """获取方位描述（3分法）"""
        if center_x_ratio < 0.40:
            return "在画面左侧"
        elif center_x_ratio < 0.60:
            return "在画面中间"
        else:
            return "在画面右侧"
    
    def _generate_guidance(self, area_ratio, center_x_ratio, center_y_ratio, 
                          has_occlusion, current_time) -> Optional[Dict[str, Any]]:
        """生成引导语音"""
        
        # 检查面积是否稳定（避免抖动）
        if not self._is_area_stable(area_ratio):
            return None
        
        position_desc = self._get_position_description(center_x_ratio)
        
        # 阶段1：发现阶段（0.01-0.08）
        if area_ratio >= self.THRESHOLDS['discover'] and area_ratio < self.THRESHOLDS['approaching']:
            if self.THRESHOLDS['discover'] not in self.broadcasted_thresholds:
                self.broadcasted_thresholds.add(self.THRESHOLDS['discover'])
                return {
                    'voice_text': f"远处发现斑马线,{position_desc}",
                    'priority': 55,  # 提高到55，超过盲道方向指令(50)
                    'should_broadcast': True,
                    'area': area_ratio,
                    'position': position_desc
                }
        
        # 阶段2：靠近阶段（0.08-0.18）
        elif area_ratio >= self.THRESHOLDS['approaching'] and area_ratio < self.THRESHOLDS['near']:
            # 首次播报
            if self.THRESHOLDS['approaching'] not in self.broadcasted_thresholds:
                self.broadcasted_thresholds.add(self.THRESHOLDS['approaching'])
                self.last_broadcast_time = current_time
                self.last_position_zone = position_desc
                return {
                    'voice_text': f"正在靠近斑马线,{position_desc}",
                    'priority': 55,  # 提高到55
                    'should_broadcast': True,
                    'area': area_ratio,
                    'position': position_desc
                }
            # 重复播报（每10秒或方位变化）
            elif (current_time - self.last_broadcast_time >= self.REPEAT_INTERVALS['approaching'] or
                  position_desc != self.last_position_zone):
                self.last_broadcast_time = current_time
                self.last_position_zone = position_desc
                return {
                    'voice_text': f"正在靠近斑马线,{position_desc}",
                    'priority': 55,  # 提高到55
                    'should_broadcast': True,
                    'area': area_ratio,
                    'position': position_desc
                }
        
        # 阶段3：很近阶段（0.18-0.25）
        elif area_ratio >= self.THRESHOLDS['near'] and area_ratio < self.THRESHOLDS['arrival']:
            # 首次播报
            if self.THRESHOLDS['near'] not in self.broadcasted_thresholds:
                self.broadcasted_thresholds.add(self.THRESHOLDS['near'])
                self.last_broadcast_time = current_time
                self.last_position_zone = position_desc
                return {
                    'voice_text': f"接近斑马线,{position_desc}",
                    'priority': 60,
                    'should_broadcast': True,
                    'area': area_ratio,
                    'position': position_desc
                }
            # 重复播报（每5秒或方位变化）
            elif (current_time - self.last_broadcast_time >= self.REPEAT_INTERVALS['near'] or
                  position_desc != self.last_position_zone):
                self.last_broadcast_time = current_time
                self.last_position_zone = position_desc
                return {
                    'voice_text': f"接近斑马线,{position_desc}",
                    'priority': 60,
                    'should_broadcast': True,
                    'area': area_ratio,
                    'position': position_desc
                }
        
        # 阶段4：到达阶段（area ≥ 0.25，无遮挡）
        elif area_ratio >= self.THRESHOLDS['arrival']:
            # 必须无遮挡才能提示过马路
            if has_occlusion:
                # 有遮挡，暂不提示过马路，停留在阶段3
                logger.info(f"[斑马线] 面积达到{area_ratio:.2f}但被遮挡，暂不提示过马路")
                return None
            
            # 首次到达
            if not self.in_arrival_state:
                self.in_arrival_state = True
                self.arrival_first_broadcast_time = current_time
                self.last_broadcast_time = current_time
                logger.info(f"[斑马线] 到达状态：area={area_ratio:.2f}, 无遮挡")
                return {
                    'voice_text': "斑马线到了可以过马路",
                    'priority': 80,
                    'should_broadcast': True,
                    'area': area_ratio,
                    'position': '到达'
                }
            # 重复播报（每8秒）
            elif current_time - self.last_broadcast_time >= self.REPEAT_INTERVALS['arrival']:
                self.last_broadcast_time = current_time
                return {
                    'voice_text': "斑马线到了可以过马路",
                    'priority': 80,
                    'should_broadcast': True,
                    'area': area_ratio,
                    'position': '到达'
                }
            # 超时处理（30秒后自动退出到达状态）
            elif current_time - self.arrival_first_broadcast_time > 30.0:
                logger.info("[斑马线] 到达状态超时30秒，自动退出")
                self.in_arrival_state = False
                return None
        
        # 降级处理：如果从到达状态面积减小
        if self.in_arrival_state and area_ratio < 0.20:
            logger.info(f"[斑马线] 面积降至{area_ratio:.2f}，退出到达状态")
            self.in_arrival_state = False
            # 清除部分已播报标记，允许重新播报
            self.broadcasted_thresholds.discard(self.THRESHOLDS['arrival'])
        
        return None
    
    def _is_area_stable(self, area_ratio, stability_frames=5) -> bool:
        """检查面积是否稳定（避免抖动触发）"""
        if len(self.area_history) < stability_frames:
            return True  # 初始阶段，认为稳定
        
        recent_areas = [h['area'] for h in list(self.area_history)[-stability_frames:]]
        
        # 检查最近N帧是否都在当前面积附近（±20%）
        for recent_area in recent_areas:
            if abs(recent_area - area_ratio) / max(area_ratio, 0.001) > 0.20:
                return False
        
        return True
    
    def _reset_if_needed(self):
        """重置状态（斑马线消失时）"""
        if len(self.area_history) > 0:
            logger.info("[斑马线] 斑马线消失，重置状态")
        
        self.broadcasted_thresholds.clear()
        self.area_history.clear()
        self.in_arrival_state = False
        self.last_position_zone = None
    
    def reset(self):
        """完全重置"""
        self.broadcasted_thresholds.clear()
        self.area_history.clear()
        self.in_arrival_state = False
        self.last_broadcast_time = 0
        self.arrival_first_broadcast_time = 0
        self.last_position_zone = None
        logger.info("[斑马线] 感知监控器已重置")
    
    def is_in_arrival_state(self) -> bool:
        """是否在到达状态（用于外部判断是否暂停盲道语音）"""
        return self.in_arrival_state
    
    def get_current_area(self) -> float:
        """获取当前面积"""
        if len(self.area_history) > 0:
            return self.area_history[-1]['area']
        return 0.0
    
    def get_visualization_data(self, crosswalk_mask, area_ratio, center_x_ratio, center_y_ratio, has_occlusion) -> Dict[str, Any]:
        """
        获取可视化数据
        返回包含所有可视化元素的字典
        """
        if crosswalk_mask is None:
            return {}
        
        # 确定当前阶段（统一使用橙色）
        if area_ratio >= self.THRESHOLDS['arrival']:
            stage = "到达"
            stage_color = "rgba(255, 165, 0, 0.5)"  # 橙色
        elif area_ratio >= self.THRESHOLDS['near']:
            stage = "接近"
            stage_color = "rgba(255, 165, 0, 0.45)"  # 橙色
        elif area_ratio >= self.THRESHOLDS['approaching']:
            stage = "靠近"
            stage_color = "rgba(255, 165, 0, 0.40)"  # 橙色
        else:
            stage = "发现"
            stage_color = "rgba(255, 165, 0, 0.35)"  # 橙色
        
        # 方位描述
        position = self._get_position_description(center_x_ratio)
        
        return {
            'area_ratio': area_ratio,
            'stage': stage,
            'stage_color': stage_color,
            'position': position.replace("在画面", ""),  # 去掉"在画面"前缀
            'center_x_ratio': center_x_ratio,
            'center_y_ratio': center_y_ratio,
            'has_occlusion': has_occlusion,
            'in_arrival': self.in_arrival_state
        }


# 辅助函数
def split_combined_voice(combined_text: str) -> list:
    """
    将组合语音拆分为多个独立语音
    例如："远处发现斑马线,在画面左侧" → ["远处发现斑马线", "在画面左侧"]
    """
    if ',' in combined_text:
        parts = combined_text.split(',')
        return [p.strip() for p in parts if p.strip()]
    return [combined_text]

