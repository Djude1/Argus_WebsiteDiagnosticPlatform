# -*- coding: utf-8 -*-
"""
红绿灯检测模块 - 独立工作流版本
基于YOLO模型实时检测红绿灯状态，并通过语音反馈
可以通过语音命令"检测红绿灯"、"停止检测"来控制
"""

import os
import time
import threading
import cv2
import numpy as np
from ultralytics import YOLO
import bridge_io
from audio_player import play_voice_text  # 使用统一的语音播放接口
import logging

logger = logging.getLogger(__name__)

# ========= 配置参数 =========
YOLO_MODEL_PATH = r"C:\Users\Administrator\Desktop\rebuild1002\model\trafficlight.pt"

# ========= 显示参数 =========
CONF_THRESHOLD = 0.25  # 置信度阈值
FONT_SIZE = 20
STROKE_WIDTH = 3

# ========= 语音播报参数 =========
TTS_INTERVAL_SEC = 2.0  # 语音播报间隔（避免频繁播报）
ENABLE_TTS = False  # 【禁用】红绿灯检测模块不播报，由 workflow_crossstreet.py 统一处理

# ========= 线程控制 =========
_detection_thread = None
_stop_event = None
_detection_running = False

# ========= 单帧处理模式（新增）=========
_model = None  # 全局模型实例
_last_tts_ts = 0.0
_last_detected_light = None
_detection_history = []

# ========= 前端配色（BGR） =========
FRONTEND_COLORS = {
    "text": (230, 237, 243),   # 白色文字
    "red": (0, 0, 255),        # 红色
    "yellow": (0, 255, 255),   # 黄色
    "green": (0, 255, 0),      # 绿色
    "muted": (159, 176, 195),  # 灰色
}

# 红绿灯状态到颜色的映射
LIGHT_COLORS = {
    "stop": FRONTEND_COLORS["red"],
    "countdown_go": FRONTEND_COLORS["yellow"],
    "go": FRONTEND_COLORS["green"],
}

# 【修正】红绿灯状态到中文的映射
# 只包含真正的红绿灯类别，排除斑马线(crossing)和空白
LIGHT_NAMES = {
    "stop": "红灯",              # 机动车红灯
    "go": "绿灯",                # 机动车绿灯
    "countdown_go": "黄灯",      # 绿灯倒计时（用黄灯提示）
    "countdown_stop": "红灯",    # 红灯倒计时
}

# 红绿灯状态到语音文件的映射
LIGHT_VOICE_MAP = {
    "stop": "红灯",              # → voice/红灯.WAV
    "go": "绿灯",                # → voice/绿灯.WAV
    "countdown_go": "黄灯",      # → voice/黄灯.WAV（绿灯倒计时用黄灯提示）
    "countdown_stop": "红灯",    # → voice/红灯.WAV
}

# 需要过滤的类别（不检测、不显示）
FILTERED_CLASSES = {
    "crossing",          # 斑马线（不需要）
    "blank",            # 空白
    "countdown_blank"   # 倒计时空白
}

# UI文本管理
_UI_LINE = 0
_UI_H = 0
_UI_TR_LINE = 0
_UI_TOP_MARGIN = 12
_UI_RIGHT_MARGIN = 12
UNIFIED_FONT_PX = 12

def ui_reset_overlay(img_h: int):
    """每帧调用一次，重置叠加行计数"""
    global _UI_LINE, _UI_H, _UI_TR_LINE
    _UI_LINE = 0
    _UI_TR_LINE = 0
    _UI_H = int(img_h)

def _ui_next_y_top(font_size: int) -> int:
    """返回右上角下一行的y坐标"""
    global _UI_TR_LINE
    line_gap = max(4, int(font_size * 0.25))
    y_top = _UI_TOP_MARGIN + (_UI_TR_LINE * (font_size + line_gap))
    _UI_TR_LINE += 1
    return y_top

# ======== 中文文本绘制 ========
_PIL_OK = False
_FONT_PATH = None

def _init_font():
    global _PIL_OK, _FONT_PATH
    try:
        from PIL import ImageFont
        _PIL_OK = True
    except Exception:
        _PIL_OK = False
        return
    candidates = [
        r"C:\\Windows\\Fonts\\msyh.ttc",
        r"C:\\Windows\\Fonts\\msyh.ttf",
        r"C:\\Windows\\Fonts\\simhei.ttf",
        r"C:\\Windows\\Fonts\\simfang.ttf",
        r"C:\\Windows\\Fonts\\simsun.ttc",
        r"C:\\Windows\\Fonts\\simsunb.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            _FONT_PATH = p
            return
    _PIL_OK = False

_init_font()

def draw_text_cn(img_bgr, text, xy, font_size=20, color=(255,255,255), ui_hint=True):
    """统一的中文文本绘制"""
    color = (255, 255, 255)
    font_size = int(UNIFIED_FONT_PX)

    H, W = img_bgr.shape[:2]
    y_top = _ui_next_y_top(font_size) if ui_hint else xy[1]
    tw = th = 0
    font_obj = None

    if _PIL_OK and _FONT_PATH:
        try:
            from PIL import Image, ImageDraw, ImageFont
            font_obj = ImageFont.truetype(_FONT_PATH, font_size)
            bbox = ImageDraw.Draw(Image.new('RGB', (1,1))).textbbox((0,0), text, font=font_obj)
            tw = max(1, bbox[2] - bbox[0])
            th = max(1, bbox[3] - bbox[1])
        except Exception:
            pass
    
    if _PIL_OK and _FONT_PATH and font_obj is not None:
        try:
            from PIL import Image, ImageDraw
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)
            draw = ImageDraw.Draw(pil_img)
            if ui_hint:
                x = max(8, W - _UI_RIGHT_MARGIN - tw)
                y = y_top
            else:
                x = xy[0]
                y = xy[1]
            draw.text((x, y), text, fill=color, font=font_obj)
            img_bgr[:] = cv2.cvtColor(np.asarray(pil_img), cv2.COLOR_RGB2BGR)
            return
        except Exception:
            pass
    
    # OpenCV 回退
    if tw <= 0 or th <= 0:
        scale = font_size/24.0
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
    if ui_hint:
        x = max(8, W - _UI_RIGHT_MARGIN - int(tw))
        y_baseline = int(y_top + th)
    else:
        x = xy[0]
        y_baseline = xy[1] + int(th)
    cv2.putText(img_bgr, text, (x, y_baseline), cv2.FONT_HERSHEY_SIMPLEX, font_size/24.0, color, 2, cv2.LINE_AA)

def main(headless: bool = True, stop_event=None):
    """
    红绿灯检测主函数
    
    参数:
        headless: 是否无头模式（不显示OpenCV窗口）
        stop_event: threading.Event，用于停止检测
    """
    
    print("[TRAFFIC] 加载 YOLO 红绿灯检测模型...")
    try:
        model = YOLO(YOLO_MODEL_PATH)
        print(f"[TRAFFIC] 模型加载成功: {YOLO_MODEL_PATH}")
    except Exception as e:
        print(f"[TRAFFIC] 模型加载失败: {e}")
        return

    # 获取类别名称
    class_names = model.names if hasattr(model, 'names') else {}
    print(f"[TRAFFIC] 模型类别: {class_names}")

    # 状态跟踪
    last_tts_ts = 0.0
    last_detected_light = None
    fps_hist = []
    
    # 【优化】状态稳定性判断 - 使用多数表决而非连续帧
    detection_history = []  # 保存最近N帧的检测结果
    HISTORY_SIZE = 5        # 保存最近5帧
    MAJORITY_THRESHOLD = 3  # 5帧中至少3帧相同才认为稳定
    
    # 【新增】帧统计
    frame_count = 0
    frame_received_count = 0
    frame_none_count = 0
    last_frame_log_time = time.time()

    print("[TRAFFIC] 等待 ESP32 画面...")

    try:
        while True:
            # 检查停止事件
            if stop_event and stop_event.is_set():
                print("[TRAFFIC] 停止事件触发，退出检测")
                break

            # 【优化】从bridge_io获取原始BGR帧 - 增加超时时间
            frame = bridge_io.wait_raw_bgr(timeout_sec=2.0)  # 从0.5秒增加到2秒
            
            frame_count += 1
            
            if frame is None:
                frame_none_count += 1
                # 每3秒打印一次帧统计
                current_time = time.time()
                if current_time - last_frame_log_time > 3.0:
                    print(f"[TRAFFIC] 帧统计: 总={frame_count}, 收到={frame_received_count}, "
                          f"丢失={frame_none_count}, 丢失率={frame_none_count/frame_count*100:.1f}%")
                    last_frame_log_time = current_time
                
                if headless:
                    cv2.waitKey(1)
                continue
            
            frame_received_count += 1

            # 重置UI叠加
            H, W = frame.shape[:2]
            ui_reset_overlay(H)

            vis = frame.copy()
            t_now = time.time()

            # 【优化】YOLO推理 - 添加计时
            inference_start = time.time()
            results = model(frame, conf=CONF_THRESHOLD, verbose=False)
            inference_time = (time.time() - inference_start) * 1000
            
            # 监控推理时间
            if inference_time > 100:
                print(f"[TRAFFIC] WARNING: 推理耗时 {inference_time:.0f}ms")

            # 处理检测结果
            detected_light = None
            max_conf = 0.0

            if results and len(results) > 0:
                r = results[0]
                if r.boxes is not None and len(r.boxes) > 0:
                    # 【过滤】遍历所有检测框，找到置信度最高的红绿灯（排除斑马线）
                    for box in r.boxes:
                        cls_id = int(box.cls[0])
                        conf = float(box.conf[0])
                        class_name = class_names.get(cls_id, f"class_{cls_id}")
                        class_name_lower = class_name.lower()
                        
                        # 跳过不需要的类别
                        if class_name_lower in FILTERED_CLASSES:
                            continue
                        
                        if conf > max_conf:
                            max_conf = conf
                            detected_light = class_name_lower

                    # 【过滤】绘制检测框（只绘制红绿灯）
                    for box in r.boxes:
                        cls_id = int(box.cls[0])
                        conf = float(box.conf[0])
                        class_name = class_names.get(cls_id, f"class_{cls_id}")
                        class_name_lower = class_name.lower()
                        
                        # 跳过不需要的类别
                        if class_name_lower in FILTERED_CLASSES:
                            continue
                        
                        # 获取边界框坐标
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        
                        # 确定颜色
                        color = LIGHT_COLORS.get(class_name_lower, FRONTEND_COLORS["text"])
                        
                        # 绘制边界框
                        cv2.rectangle(vis, (x1, y1), (x2, y2), color, STROKE_WIDTH)
                        
                        # 绘制中文标签（使用PIL）
                        label = f"{LIGHT_NAMES.get(class_name.lower(), class_name)}: {conf:.2f}"
                        
                        if _PIL_OK and _FONT_PATH:
                            try:
                                from PIL import Image, ImageDraw, ImageFont
                                # 使用较大的字体绘制标签
                                font_obj = ImageFont.truetype(_FONT_PATH, 20)
                                # 转换为PIL图像
                                img_rgb = cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)
                                pil_img = Image.fromarray(img_rgb)
                                draw = ImageDraw.Draw(pil_img)
                                
                                # 计算文本尺寸
                                bbox = draw.textbbox((0, 0), label, font=font_obj)
                                text_w = bbox[2] - bbox[0]
                                text_h = bbox[3] - bbox[1]
                                
                                # 标签位置
                                label_y = max(y1 - text_h - 8, text_h)
                                
                                # 绘制背景矩形
                                bg_x1 = x1
                                bg_y1 = label_y - text_h - 4
                                bg_x2 = x1 + text_w + 8
                                bg_y2 = label_y + 4
                                cv2.rectangle(vis, (bg_x1, bg_y1), (bg_x2, bg_y2), color, -1)
                                
                                # 重新转换（因为矩形是用OpenCV画的）
                                img_rgb = cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)
                                pil_img = Image.fromarray(img_rgb)
                                draw = ImageDraw.Draw(pil_img)
                                
                                # 【删除】绘制文字
                                # draw.text((x1 + 4, label_y - text_h), label, fill=(0, 0, 0), font=font_obj)
                                
                                # 转换回OpenCV格式
                                vis[:] = cv2.cvtColor(np.asarray(pil_img), cv2.COLOR_RGB2BGR)
                            except Exception as e:
                                # 【删除】PIL失败时的文本标签
                                pass
                        else:
                            # 【删除】文本标签
                            pass

            # 【优化】状态稳定性判断：使用多数表决而非连续帧
            detection_history.append(detected_light)
            if len(detection_history) > HISTORY_SIZE:
                detection_history.pop(0)
            
            # 判断状态是否稳定（多数表决）
            stable_light = None
            if len(detection_history) >= MAJORITY_THRESHOLD:
                # 统计最近N帧中每个状态出现的次数
                valid_detections = [d for d in detection_history if d and d in LIGHT_NAMES]
                if len(valid_detections) >= MAJORITY_THRESHOLD:
                    # 找出现次数最多的状态
                    from collections import Counter
                    counter = Counter(valid_detections)
                    most_common = counter.most_common(1)
                    if most_common and most_common[0][1] >= MAJORITY_THRESHOLD:
                        stable_light = most_common[0][0]
                        # 打印调试信息
                        if frame_received_count % 30 == 0:
                            print(f"[TRAFFIC] 检测历史: {detection_history[-5:]}, 稳定状态: {stable_light}")
            
            # 【禁用语音播报】只检测不播报，由调用者（workflow_crossstreet.py）统一处理语音
            # 只更新状态跟踪
            if stable_light:
                # 状态改变时记录（但不播报）
                if stable_light != last_detected_light:
                    last_detected_light = stable_light
                    print(f"[TRAFFIC] 检测到稳定状态改变: {LIGHT_NAMES[stable_light]}（不播报）")
                    last_tts_ts = t_now
                # 超过间隔时间，更新时间戳（但不播报）
                elif (t_now - last_tts_ts) > TTS_INTERVAL_SEC:
                    print(f"[TRAFFIC] 稳定状态持续: {LIGHT_NAMES[stable_light]}（不播报）")
                    last_tts_ts = t_now

            # 【删除】显示当前检测状态
            # if detected_light and detected_light in LIGHT_NAMES:
            #     status_text = f"检测: {LIGHT_NAMES[detected_light]} ({max_conf:.2f})"
            #     color = LIGHT_COLORS[detected_light]
            # else:
            #     status_text = "检测: 无"
            #     color = FRONTEND_COLORS["muted"]
            # draw_text_cn(vis, status_text, (10, 40), font_size=18, color=color)
            
            # 【删除】显示稳定状态
            # if stable_light:
            #     stable_text = f"稳定状态: {LIGHT_NAMES[stable_light]}"
            #     stable_color = LIGHT_COLORS[stable_light]
            # else:
            #     stable_text = f"稳定状态: 等待中 ({len(detection_history)}/{HISTORY_SIZE})"
            #     stable_color = FRONTEND_COLORS["muted"]
            # draw_text_cn(vis, stable_text, (10, 60), font_size=18, color=stable_color)

            # 【删除】FPS计算和显示
            # fps_hist.append(t_now)
            # if len(fps_hist) > 30:
            #     fps_hist.pop(0)
            # fps = 0.0 if len(fps_hist) < 2 else (len(fps_hist)-1)/(fps_hist[-1]-fps_hist[0])
            # draw_text_cn(vis, f"FPS: {fps:.1f}", (10, 20), font_size=16, color=FRONTEND_COLORS["text"])

            # 发送可视化结果到前端
            bridge_io.send_vis_bgr(vis)

            # 非headless模式下显示窗口
            if not headless:
                cv2.imshow("Traffic Light Detection", vis)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord('q')):
                    break
            else:
                cv2.waitKey(1)

    except Exception as e:
        print(f"[TRAFFIC] 检测过程出错: {e}")
    finally:
        if not headless:
            cv2.destroyAllWindows()
        print("[TRAFFIC] 红绿灯检测已停止")


def start_detection():
    """启动红绿灯检测（在后台线程中运行）"""
    global _detection_thread, _stop_event, _detection_running
    
    if _detection_running:
        print("[TRAFFIC] 红绿灯检测已在运行中")
        return False
    
    _stop_event = threading.Event()
    _detection_thread = threading.Thread(
        target=main,
        args=(True, _stop_event),  # headless=True, stop_event
        daemon=True,
        name="TrafficLightDetection"
    )
    _detection_thread.start()
    _detection_running = True
    print("[TRAFFIC] 红绿灯检测已启动（后台线程）")
    return True

def stop_detection():
    """停止红绿灯检测"""
    global _detection_thread, _stop_event, _detection_running
    
    if not _detection_running:
        print("[TRAFFIC] 红绿灯检测未运行")
        return False
    
    print("[TRAFFIC] 正在停止红绿灯检测...")
    if _stop_event:
        _stop_event.set()
    
    if _detection_thread:
        _detection_thread.join(timeout=2.0)
        _detection_thread = None
    
    _stop_event = None
    _detection_running = False
    print("[TRAFFIC] 红绿灯检测已停止")
    return True

def is_detection_running():
    """检查红绿灯检测是否正在运行"""
    return _detection_running

def init_model():
    """初始化YOLO模型（单帧处理模式）"""
    global _model
    if _model is not None:
        print("[TRAFFIC] 模型已加载")
        return True
    
    try:
        print("[TRAFFIC] 加载 YOLO 红绿灯检测模型...")
        _model = YOLO(YOLO_MODEL_PATH)
        print(f"[TRAFFIC] 模型加载成功: {YOLO_MODEL_PATH}")
        class_names = _model.names if hasattr(_model, 'names') else {}
        print(f"[TRAFFIC] 模型类别: {class_names}")
        return True
    except Exception as e:
        print(f"[TRAFFIC] 模型加载失败: {e}")
        _model = None
        return False

def process_single_frame(image: np.ndarray, ui_broadcast_callback=None) -> dict:
    """
    处理单帧图像（主线程模式，避免掉帧）
    参数：
        image: 输入图像
        ui_broadcast_callback: 前端广播回调函数（用于显示红绿灯状态）
    返回：{'vis_image': 可视化图像, 'detected_light': 检测到的灯, 'stable_light': 稳定状态}
    """
    global _model, _last_tts_ts, _last_detected_light, _detection_history
    
    if _model is None:
        if not init_model():
            return {'vis_image': image, 'detected_light': None, 'stable_light': None}
    
    vis = image.copy()
    t_now = time.time()
    
    # YOLO推理
    results = _model(image, conf=CONF_THRESHOLD, verbose=False)
    
    # 处理检测结果
    detected_light = None
    max_conf = 0.0
    class_names = _model.names if hasattr(_model, 'names') else {}
    
    if results and len(results) > 0:
        r = results[0]
        if r.boxes is not None and len(r.boxes) > 0:
            # 遍历所有检测框，找到置信度最高的红绿灯（过滤掉crossing等）
            for box in r.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                class_name = class_names.get(cls_id, f"class_{cls_id}")
                class_name_lower = class_name.lower()
                
                # 【过滤】跳过不需要的类别（斑马线、空白等）
                if class_name_lower in FILTERED_CLASSES:
                    continue
                
                if conf > max_conf:
                    max_conf = conf
                    detected_light = class_name_lower
            
            # 绘制检测框（只绘制红绿灯，不绘制斑马线）
            for box in r.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                class_name = class_names.get(cls_id, f"class_{cls_id}")
                class_name_lower = class_name.lower()
                
                # 【过滤】跳过不需要的类别
                if class_name_lower in FILTERED_CLASSES:
                    continue
                
                # 获取边界框坐标
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                
                # 确定颜色
                color = LIGHT_COLORS.get(class_name_lower, FRONTEND_COLORS["text"])
                
                # 绘制边界框
                cv2.rectangle(vis, (x1, y1), (x2, y2), color, STROKE_WIDTH)
    
    # 【放宽】状态稳定性判断（多数表决） - 降低要求
    _detection_history.append(detected_light)
    if len(_detection_history) > 5:
        _detection_history.pop(0)
    
    stable_light = None
    if len(_detection_history) >= 2:  # 从3帧降低到2帧
        from collections import Counter
        valid_detections = [d for d in _detection_history if d and d in LIGHT_NAMES]
        if len(valid_detections) >= 2:  # 从3帧降低到2帧
            counter = Counter(valid_detections)
            most_common = counter.most_common(1)
            if most_common and most_common[0][1] >= 2:  # 从3次降低到2次
                stable_light = most_common[0][0]
    
    # 【调试】打印检测结果（已禁用）
    # print(f"[TRAFFIC-DEBUG] detected={detected_light}, stable={stable_light}, history={_detection_history}")
    
    # 【禁用语音播报】只检测不播报，由 workflow_crossstreet.py 统一处理语音
    # 只更新状态跟踪，不调用 play_voice_text
    if stable_light:
        # 更新状态跟踪（用于检测状态变化）
        if stable_light != _last_detected_light:
            _last_detected_light = stable_light
            print(f"[TRAFFIC] 检测到稳定状态改变: {LIGHT_NAMES[stable_light]}（不播报）")
            _last_tts_ts = t_now
        elif (t_now - _last_tts_ts) > TTS_INTERVAL_SEC:
            # 超过间隔时间，更新时间戳（但不播报）
            print(f"[TRAFFIC] 稳定状态持续: {LIGHT_NAMES[stable_light]}（不播报）")
            _last_tts_ts = t_now
    
    # 【删除】状态文本显示
    # if detected_light and detected_light in LIGHT_NAMES:
    #     status_text = f"{LIGHT_NAMES[detected_light]} ({max_conf:.2f})"
    # else:
    #     status_text = "无检测"
    # 
    # if stable_light:
    #     stable_text = f"稳定: {LIGHT_NAMES[stable_light]}"
    # else:
    #     stable_text = f"等待稳定 ({len(_detection_history)}/5)"
    # 
    # # 添加简单的文本显示
    # cv2.putText(vis, status_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    # cv2.putText(vis, stable_text, (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    
    return {
        'vis_image': vis,
        'detected_light': detected_light,
        'stable_light': stable_light
    }

def reset_detection_state():
    """重置检测状态"""
    global _last_tts_ts, _last_detected_light, _detection_history
    _last_tts_ts = 0.0
    _last_detected_light = None
    _detection_history = []
    print("[TRAFFIC] 检测状态已重置")

if __name__ == "__main__":
    main(headless=False)



