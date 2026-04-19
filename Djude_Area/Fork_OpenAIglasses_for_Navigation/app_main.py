# app_main.py
# -*- coding: utf-8 -*-
import os
import sys
import time
import json
import asyncio
import base64
import audioop
from typing import Any, Dict, Optional, Tuple, List, Set, Deque
from collections import deque
import re
from qwen_extractor import extract_english_label
from navigation_master import NavigationMaster
from workflow_blindpath import BlindPathNavigator
from workflow_crossstreet import CrossStreetNavigator
import torch
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from starlette.websockets import WebSocketState
import uvicorn
import cv2
import numpy as np
from ultralytics import YOLO
from obstacle_detector_client import ObstacleDetectorClient
import bridge_io
import threading
import yolomedia  # 确保和 app_main.py 同目录，文件名就是 yolomedia.py
# ---- Windows 事件循环策略 ----
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

# ── 從 config.py 讀取所有設定（.env 已在 config.py 中載入）──────────────────
from config import (
    GOOGLE_CREDENTIALS_PATH,
    SAMPLE_RATE,
    UDP_IP,
    UDP_PORT,
    SERVER_HOST,
    SERVER_PORT,
)

# ---- 引入我们的模块 ----
from audio_stream import (
    register_stream_route,         # 挂 /stream.wav
    broadcast_pcm16_realtime,      # 实时向连接分发 16k PCM
    hard_reset_audio,              # 音频+AI 播放总闸
    is_playing_now,
)
from omni_client import stream_chat, generate_text_async
from asr_core import (
    ASRCallback,
    GoogleASR,
    set_current_recognition,
    stop_current_recognition,
    STANDBY_RMS_THRESH,
    preload_speech_client,
)
from audio_player import initialize_audio_system, play_voice_text, play_audio_threadsafe, register_speak_push

# ---- 同步录制器 ----
import sync_recorder

# ---- IMU UDP（設定來自 config.py）----

app = FastAPI()

# CORS：允許 Website 管理後台（任何來源）跨域呼叫 FastAPI
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 後台管理路由（JWT 認證 + 使用者/聯絡人 CRUD + 統計）──
from auth import router as auth_router
app.include_router(auth_router)

# ====== 状态与容器 ======

# ── 靜態檔案（加入 Cache-Control，讓瀏覽器快取避免每次重載）──────────────────
from starlette.staticfiles import StaticFiles as _StaticFiles

class _CachedStaticFiles(_StaticFiles):
    """根據副檔名設定不同快取時間：
      .glb/.gltf  → 7 天（3D模型幾乎不變動）
      .js/.css    → 1 小時
      其他         → 30 分鐘
    """
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if path.endswith(('.glb', '.gltf')):
            response.headers['Cache-Control'] = 'public, max-age=604800'   # 7天
        elif path.endswith(('.js', '.css')):
            response.headers['Cache-Control'] = 'public, max-age=3600'     # 1小時
        else:
            response.headers['Cache-Control'] = 'public, max-age=1800'     # 30分鐘
        return response

app.mount("/static", _CachedStaticFiles(directory="static"), name="static")

ui_clients: Dict[int, WebSocket] = {}
current_partial: str = ""
recent_finals: List[str] = []
RECENT_MAX = 50
last_frames: Deque[Tuple[float, bytes]] = deque(maxlen=10)

camera_viewers: Set[WebSocket] = set()
esp32_camera_ws: Optional[WebSocket] = None
_welcome_played: bool = False  # 歡迎音效只播一次
imu_ws_clients: Set[WebSocket] = set()
esp32_audio_ws: Optional[WebSocket] = None

# ── IDLE/CHAT 短句過濾門檻（字數 < 此值且無關鍵字則丟棄，0 = 不過濾）──────
_idle_filter_min_chars: int = 4   # 預設 4 字，旁路模式課堂轉錄建議設為 1

# ── 說話人聲紋錄製（Enrollment）狀態 ──────────────────────────────────────
_enroll_active:  bool       = False   # 是否正在錄製聲紋
_enroll_buffer:  bytearray  = bytearray()  # 收音緩衝
_enroll_end_ts:  float      = 0.0     # 錄製結束時間戳（monotonic）
_ENROLL_SEC:     float      = 10.0    # 聲紋錄製秒數

# ── 說話人聲紋測試驗證狀態 ────────────────────────────────────────────────
_verify_test_active:  bool      = False   # 是否正在收音測試
_verify_test_buffer:  bytearray = bytearray()  # 測試收音緩衝
_verify_test_end_ts:  float     = 0.0     # 測試結束時間戳
_VERIFY_TEST_SEC:     float     = 3.0     # 測試錄音秒數

# ── 說話人聲紋持續監測模式 ────────────────────────────────────────────────
_verify_continuous:        bool      = False   # 是否啟用持續監測
_verify_continuous_buf:    bytearray = bytearray()  # 滾動收音緩衝
_VERIFY_CONTINUOUS_SEC:    float     = 2.0     # 每幾秒做一次驗證

# ── Speaker 聲紋事件 SSE 廣播隊列 ────────────────────────────────────────────
_speaker_sse_queues: list = []  # 每個 SSE 客戶端一個 asyncio.Queue
_last_rms_push_ts:   float = 0.0  # 限制 RMS 推送頻率（每 0.15 秒一次）

# ── Debug 錄音（收音品質排查）────────────────────────────────────────────────
_debug_rec_active: bool      = False   # 是否正在錄音
_debug_rec_buffer: bytearray = bytearray()  # 收音緩衝
_DEBUG_REC_DIR:    str       = r"D:\GitHub_Project\Fork_OpenAIglasses_for_Navigation\錄音測試"
_server_start_time: float    = time.time()   # 伺服器啟動時間戳（Debug 面板用）

# 【新增】盲道导航相关全局变量
blind_path_navigator = None
navigation_active = False
yolo_seg_model = None
obstacle_detector = None

# 【新增】过马路导航相关全局变量
cross_street_navigator = None
cross_street_active = False
orchestrator = None  # 新增

# 【新增】omni对话状态标志
omni_conversation_active = False  # 标记omni对话是否正在进行
omni_previous_nav_state = None  # 保存omni激活前的导航状态，用于恢复

# 【新增】模型加载函数
def load_navigation_models():
    """加载盲道导航所需的模型"""
    global yolo_seg_model, obstacle_detector

    # ── 共用模型伺服器模式（MODEL_SERVER_PORT 有設定時）──────────────────────
    if os.getenv("MODEL_SERVER_PORT"):
        try:
            from model_client import RemoteYOLO, RemoteObstacleDetector
            yolo_seg_model   = RemoteYOLO("yolo-seg")
            obstacle_detector = RemoteObstacleDetector()
            print(f"[NAVIGATION] 共用模型伺服器模式：localhost:{os.getenv('MODEL_SERVER_PORT')}", flush=True)
        except Exception as e:
            print(f"[NAVIGATION] 無法連接模型伺服器，回退到本機模式: {e}", flush=True)
        return

    try:
        from config import BLIND_PATH_MODEL
        seg_model_path = BLIND_PATH_MODEL
        #print(f"[NAVIGATION] 尝试加载模型: {seg_model_path}")

        if os.path.exists(seg_model_path):
            print("[NAVIGATION] 模型文件存在，开始加载...")
            yolo_seg_model = YOLO(seg_model_path)

            # 强制放到 GPU
            if torch.cuda.is_available():
                yolo_seg_model.to("cuda")
                print(f"[NAVIGATION] 盲道分割模型加载成功并放到GPU: {yolo_seg_model.device}")
            else:
                print("[NAVIGATION] CUDA不可用，模型仍在CPU")

            # 测试模型是否能正常运行
            try:
                test_img = np.zeros((640, 640, 3), dtype=np.uint8)
                results = yolo_seg_model.predict(
                    test_img,
                    device="cuda" if torch.cuda.is_available() else "cpu",
                    verbose=False
                )
                print(f"[NAVIGATION] 模型测试成功，支持的类别数: {len(yolo_seg_model.names) if hasattr(yolo_seg_model, 'names') else '未知'}")
                if hasattr(yolo_seg_model, 'names'):
                    print(f"[NAVIGATION] 模型类别: {yolo_seg_model.names}")
            except Exception as e:
                print(f"[NAVIGATION] 模型测试失败: {e}")
        else:
            print(f"[NAVIGATION] 错误：找不到模型文件: {seg_model_path}")
            print(f"[NAVIGATION] 当前工作目录: {os.getcwd()}")
            print("[NAVIGATION] 请检查文件路径是否正确")
            
        # 【修改开始】使用 ObstacleDetectorClient 替代直接的 YOLO
        from config import OBSTACLE_MODEL
        obstacle_model_path = OBSTACLE_MODEL
        print(f"[NAVIGATION] 尝试加载障碍物检测模型: {obstacle_model_path}")
        
        if os.path.exists(obstacle_model_path):
            print("[NAVIGATION] 障碍物检测模型文件存在，开始加载...")
            try:
                # 使用 ObstacleDetectorClient 封装的 YOLO-E
                obstacle_detector = ObstacleDetectorClient(model_path=obstacle_model_path)
                print("[NAVIGATION] ========== YOLO-E 障碍物检测器加载成功 ==========")
                
                # 检查模型是否成功加载
                if hasattr(obstacle_detector, 'model') and obstacle_detector.model is not None:
                    print("[NAVIGATION] YOLO-E 模型已初始化")
                    print(f"[NAVIGATION] 模型设备: {next(obstacle_detector.model.parameters()).device}")
                else:
                    print("[NAVIGATION] 警告：YOLO-E 模型初始化异常")
                
                # 检查白名单是否成功加载
                if hasattr(obstacle_detector, 'WHITELIST_CLASSES'):
                    print(f"[NAVIGATION] 白名单类别数: {len(obstacle_detector.WHITELIST_CLASSES)}")
                    print(f"[NAVIGATION] 白名单前10个类别: {', '.join(obstacle_detector.WHITELIST_CLASSES[:10])}")
                else:
                    print("[NAVIGATION] 警告：白名单类别未定义")
                
                # 检查文本特征是否成功预计算
                if hasattr(obstacle_detector, 'whitelist_embeddings') and obstacle_detector.whitelist_embeddings is not None:
                    print("[NAVIGATION] YOLO-E 文本特征已预计算")
                    print(f"[NAVIGATION] 文本特征张量形状: {obstacle_detector.whitelist_embeddings.shape if hasattr(obstacle_detector.whitelist_embeddings, 'shape') else '未知'}")
                else:
                    print("[NAVIGATION] 警告：YOLO-E 文本特征未预计算")
                
                # 测试障碍物检测功能
                print("[NAVIGATION] 开始测试 YOLO-E 检测功能...")
                try:
                    test_img = np.zeros((640, 640, 3), dtype=np.uint8)
                    # 在测试图像中画一个白色矩形，模拟一个物体
                    cv2.rectangle(test_img, (200, 200), (400, 400), (255, 255, 255), -1)
                    
                    # 测试检测（不提供 path_mask）
                    test_results = obstacle_detector.detect(test_img)
                    print("[NAVIGATION] YOLO-E 检测测试成功!")
                    print(f"[NAVIGATION] 测试检测结果数: {len(test_results)}")
                    
                    if len(test_results) > 0:
                        print("[NAVIGATION] 测试检测到的物体:")
                        for i, obj in enumerate(test_results):
                            print(f"  - 物体 {i+1}: {obj.get('name', 'unknown')}, "
                                  f"面积比例: {obj.get('area_ratio', 0):.3f}, "
                                  f"位置: ({obj.get('center_x', 0):.0f}, {obj.get('center_y', 0):.0f})")
                except Exception as e:
                    print(f"[NAVIGATION] YOLO-E 检测测试失败: {e}")
                    import traceback
                    traceback.print_exc()
                
                print("[NAVIGATION] ========== YOLO-E 障碍物检测器加载完成 ==========")
                
            except Exception as e:
                print(f"[NAVIGATION] 障碍物检测器加载失败: {e}")
                import traceback
                traceback.print_exc()
                obstacle_detector = None
        else:
            print(f"[NAVIGATION] 警告：找不到障碍物检测模型文件: {obstacle_model_path}")
        
    except Exception as e:
        print(f"[NAVIGATION] 模型加载失败: {e}")
        import traceback
        traceback.print_exc()

# 在程序启动时加载模型
print("[NAVIGATION] 开始加载导航模型...")
load_navigation_models()
print(f"[NAVIGATION] 模型加载完成 - yolo_seg_model: {yolo_seg_model is not None}")

# 【新增】启动同步录制
print("[RECORDER] 同步錄製系統已停用（如需啟用請取消此處的註解）")
# sync_recorder.start_recording()
# print("[RECORDER] 录制系统已启动，将自动保存视频和音频")

print("[RECORDER] 已注册退出处理器 - Ctrl+C时会自动保存录制文件")



# 【新增】预加载红绿灯检测模型（避免进入WAIT_TRAFFIC_LIGHT状态时卡顿）
try:
    import trafficlight_detection
    print("[TRAFFIC_LIGHT] 开始预加载红绿灯检测模型...")
    if trafficlight_detection.init_model():
        print("[TRAFFIC_LIGHT] 红绿灯检测模型预加载成功")
        # 执行一次测试推理，完全预热模型
        try:
            test_img = np.zeros((640, 640, 3), dtype=np.uint8)
            _ = trafficlight_detection.process_single_frame(test_img)
            print("[TRAFFIC_LIGHT] 模型预热完成")
        except Exception as e:
            print(f"[TRAFFIC_LIGHT] 模型预热失败: {e}")
    else:
        print("[TRAFFIC_LIGHT] 红绿灯检测模型预加载失败")
except Exception as e:
    print(f"[TRAFFIC_LIGHT] 红绿灯模型预加载出错: {e}")

# ============== 关键：系统级"硬重置"总闸 =================
interrupt_lock = asyncio.Lock()

# ============== YOLO媒体线程管理 =================
yolomedia_thread: Optional[threading.Thread] = None
yolomedia_stop_event = threading.Event()
yolomedia_running = False
yolomedia_sending_frames = False  # 新增：标记YOLO是否已经开始发送处理后的帧

# 方位播報模式："clock"（時鐘，預設）或 "cardinal"（前後左右）
# 使用者可在 APP 設定頁切換，透過 /api/settings/position_mode 儲存
_position_mode: str = "clock"

# 物品名称到YOLO类别的映射
ITEM_TO_CLASS_MAP = {
    "红牛": "Red_Bull",
    "AD钙奶": "AD_milk",
    "ad钙奶": "AD_milk",
    "钙奶": "AD_milk",
}

async def ui_broadcast_raw(msg: str):
    dead = []
    for k, ws in list(ui_clients.items()):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(k)
    for k in dead:
        ui_clients.pop(k, None)


async def ui_broadcast_partial(text: str):
    global current_partial
    current_partial = text
    await ui_broadcast_raw("PARTIAL:" + text)
    # 同步推送到聲紋 Dashboard SSE（即時顯示辨識中文字）
    if text and text.strip() and _speaker_sse_queues:
        asyncio.create_task(_speaker_event_push({
            "type": "asr_partial", "text": text, "ts": time.time(),
        }))

async def ui_broadcast_final(text: str):
    global current_partial, recent_finals
    current_partial = ""
    recent_finals.append(text)
    if len(recent_finals) > RECENT_MAX:
        recent_finals = recent_finals[-RECENT_MAX:]
    await ui_broadcast_raw("FINAL:" + text)
    print(f"[ASR/AI FINAL] {text}", flush=True)
    # 同步推送到聲紋 Dashboard SSE（顯示最終辨識結果）
    if text and _speaker_sse_queues:
        asyncio.create_task(_speaker_event_push({
            "type": "asr_final", "text": text, "ts": time.time(),
        }))

async def full_system_reset(reason: str = ""):
    """
    回到刚启动后的状态：
    1) 停播 + 取消AI任务 + 清空串流佇列（hard_reset_audio）
    2) 停止 ASR 实时识别流（关键）
    3) 清 UI 状态
    4) 清最近相机帧（避免把旧帧又拼进下一轮）
    5) 告知 ESP32：RESET（可选）
    """
    # 1) 音频&AI
    await hard_reset_audio(reason or "full_system_reset")

    # 2) ASR
    await stop_current_recognition()

    # 3) UI
    global current_partial, recent_finals
    current_partial = ""
    recent_finals = []

    # 4) 相机帧
    try:
        last_frames.clear()
    except Exception:
        pass

    # 5) 通知 ESP32
    try:
        if esp32_audio_ws and (esp32_audio_ws.client_state == WebSocketState.CONNECTED):
            await esp32_audio_ws.send_text("RESET")
    except Exception:
        pass

    print("[SYSTEM] full reset done.", flush=True)

# ========= 启动/停止 YOLO 媒体处理 =========
def start_yolomedia_with_target(target_name: str, position_mode: str = "clock"):
    """启动yolomedia线程，搜索指定物品"""
    global yolomedia_thread, yolomedia_stop_event, yolomedia_running, yolomedia_sending_frames

    # 如果已经在运行，先停止
    if yolomedia_running:
        stop_yolomedia()

    # 查找对应的YOLO类别
    yolo_class = ITEM_TO_CLASS_MAP.get(target_name, target_name)
    print(f"[YOLOMEDIA] Starting with target: {target_name} -> YOLO class: {yolo_class}", flush=True)
    print(f"[YOLOMEDIA] Available mappings: {ITEM_TO_CLASS_MAP}", flush=True)
    print(f"[YOLOMEDIA] position_mode: {position_mode}", flush=True)

    yolomedia_stop_event.clear()
    yolomedia_running = True
    yolomedia_sending_frames = False  # 重置发送帧状态

    def _run():
        try:
            # 傳遞目標類別名、停止事件與方位模式
            yolomedia.main(
                headless=True,
                prompt_name=yolo_class,
                stop_event=yolomedia_stop_event,
                position_mode=position_mode,
            )
        except Exception as e:
            print(f"[YOLOMEDIA] worker stopped: {e}", flush=True)
        finally:
            global yolomedia_running, yolomedia_sending_frames
            yolomedia_running = False
            yolomedia_sending_frames = False

    yolomedia_thread = threading.Thread(target=_run, daemon=True)
    yolomedia_thread.start()
    print(f"[YOLOMEDIA] background worker started for: {yolo_class}（正在初始化，暂时显示原始画面）", flush=True)

def stop_yolomedia():
    """停止yolomedia线程"""
    global yolomedia_thread, yolomedia_stop_event, yolomedia_running, yolomedia_sending_frames
    
    if yolomedia_running:
        print("[YOLOMEDIA] Stopping worker...", flush=True)
        yolomedia_stop_event.set()
        
        # 等待线程结束（最多等5秒）
        if yolomedia_thread and yolomedia_thread.is_alive():
            yolomedia_thread.join(timeout=5.0)
        
        yolomedia_running = False
        yolomedia_sending_frames = False
        
        # 【新增】如果orchestrator在找物品模式，结束时不自动恢复（由命令控制）
        # 只清理标志位即可
        print("[YOLOMEDIA] Worker stopped, 等待状态切换.", flush=True)

# ========= 自定义的 start_ai_with_text，支持识别特殊命令 =========
async def start_ai_with_text_custom(user_text: str):
    """扩展版的AI启动函数，支持识别特殊命令"""
    global navigation_active, blind_path_navigator, cross_street_active, cross_street_navigator, orchestrator

    # ── 使用說明書（任何模式下均可觸發）──────────────────────────────────
    if "眼鏡使用說明書" in user_text or "使用說明書" in user_text:
        await ui_broadcast_final("[系統] 播放使用說明")
        play_audio_threadsafe("使用說明書")
        return

    # 【修改】在导航模式和红绿灯检测模式下，只有特定词才进入omni对话
    if orchestrator:
        current_state = orchestrator.get_state()
        # 如果在导航模式或红绿灯检测模式（非CHAT模式）
        if current_state not in ["CHAT", "IDLE"]:
            # 检查是否是允许的对话触发词
            allowed_keywords = ["帮我看", "帮我看下", "帮我看一下", "帮我找",
                                "帮我找下", "帮我找一下", "找一下", "看看", "识别一下",
                                "幫我看", "幫我看下", "幫我找", "識別一下"]
            is_allowed_query = any(keyword in user_text for keyword in allowed_keywords)
            
            # 检查是否是导航控制命令
            nav_control_keywords = ["开始过马路", "过马路结束", "开始导航", "开启导航", "盲道导航", "停止导航", "结束导航",
                                   "检测红绿灯", "看红绿灯", "停止检测", "停止红绿灯",
                                   "開始過馬路", "過馬路結束", "開始導航", "開啟導航", "停止導航", "結束導航",
                                   "檢測紅綠燈", "看紅綠燈", "停止檢測", "停止紅綠燈"]
            is_nav_control = any(keyword in user_text for keyword in nav_control_keywords)
            
            # 如果既不是允许的查询，也不是导航控制命令，则丢弃
            if not is_allowed_query and not is_nav_control:
                mode_name = "红绿灯检测" if current_state == "TRAFFIC_LIGHT_DETECTION" else "导航"
                print(f"[{mode_name}模式] 丢弃非对话语音: {user_text}")
                return  # 直接丢弃，不进入omni
    
    # 【修改】检查是否是过马路相关命令 - 使用orchestrator控制
    if "开始过马路" in user_text or "帮我过马路" in user_text or \
       "開始過馬路" in user_text or "幫我過馬路" in user_text:
        # 【新增】如果正在找物品，先停止
        if yolomedia_running:
            stop_yolomedia()
            print("[ITEM_SEARCH] 从找物品模式切换到过马路")
        
        if orchestrator:
            orchestrator.start_crossing()
            print(f"[CROSS_STREET] 过马路模式已启动，状态: {orchestrator.get_state()}")
            # 播放启动语音并广播到UI
            play_voice_text("過馬路模式已啟動")
            await ui_broadcast_final("[系统] 过马路模式已启动")
            await ui_broadcast_raw(f"NAV_STATE:{orchestrator.get_state()}")
        else:
            print("[CROSS_STREET] 警告：导航统领器未初始化！")
            play_voice_text("啟動過馬路模式失敗，請稍後重試")
            await ui_broadcast_final("[系统] 导航系统未就绪")
        return

    if "过马路结束" in user_text or "结束过马路" in user_text or \
       "過馬路結束" in user_text or "結束過馬路" in user_text:
        if orchestrator:
            orchestrator.stop_navigation()
            print(f"[CROSS_STREET] 导航已停止，状态: {orchestrator.get_state()}")
            # 播放停止语音并广播到UI
            play_voice_text("已停止導航")
            await ui_broadcast_final("[系统] 过马路模式已停止")
            await ui_broadcast_raw(f"NAV_STATE:{orchestrator.get_state()}")
        # else: orchestrator 未初始化，靜默返回
        return
    
    # 【修改】检查是否是红绿灯检测命令 - 实现与盲道导航互斥
    if "检测红绿灯" in user_text or "看红绿灯" in user_text or \
       "檢測紅綠燈" in user_text or "看紅綠燈" in user_text:
        try:
            import trafficlight_detection
            
            # 切换orchestrator到红绿灯检测模式（暂停盲道导航）
            if orchestrator:
                orchestrator.start_traffic_light_detection()
                print(f"[TRAFFIC] 切换到红绿灯检测模式，状态: {orchestrator.get_state()}")
            
            # 【改进】使用主线程模式而不是独立线程，避免掉帧
            success = trafficlight_detection.init_model()  # 只初始化模型，不启动线程
            trafficlight_detection.reset_detection_state()  # 重置状态
            
            if success:
                await ui_broadcast_final("[系统] 红绿灯检测已启动")
                if orchestrator:
                    await ui_broadcast_raw(f"NAV_STATE:{orchestrator.get_state()}")
            else:
                await ui_broadcast_final("[系统] 红绿灯模型加载失败")
        except Exception as e:
            print(f"[TRAFFIC] 启动红绿灯检测失败: {e}")
            await ui_broadcast_final(f"[系统] 启动失败: {e}")
        return

    if "停止检测" in user_text or "停止红绿灯" in user_text or \
       "停止檢測" in user_text or "停止紅綠燈" in user_text:
        try:
            # 恢复到对话模式
            if orchestrator:
                orchestrator.stop_navigation()  # 回到CHAT模式
                print(f"[TRAFFIC] 红绿灯检测停止，恢复到{orchestrator.get_state()}模式")
                await ui_broadcast_raw(f"NAV_STATE:{orchestrator.get_state()}")

            await ui_broadcast_final("[系统] 红绿灯检测已停止")
        except Exception as e:
            print(f"[TRAFFIC] 停止红绿灯检测失败: {e}")
            await ui_broadcast_final(f"[系统] 停止失败: {e}")
        return
    
    # 【修改】检查是否是导航相关命令 - 使用orchestrator控制
    if "开始导航" in user_text or "开启导航" in user_text or "盲道导航" in user_text or "帮我导航" in user_text or \
       "開始導航" in user_text or "開啟導航" in user_text or "幫我導航" in user_text or "忙導航" in user_text:
        # 【新增】如果正在找物品，先停止
        if yolomedia_running:
            stop_yolomedia()
            print("[ITEM_SEARCH] 从找物品模式切换到盲道导航")
        
        if orchestrator:
            orchestrator.start_blind_path_navigation()
            print(f"[NAVIGATION] 盲道导航已启动，状态: {orchestrator.get_state()}")
            # 播放啟動語音並廣播到 UI
            play_voice_text("盲道導航已開始")
            await ui_broadcast_final("[系统] 盲道导航已启动")
            await ui_broadcast_raw(f"NAV_STATE:{orchestrator.get_state()}")
        else:
            print("[NAVIGATION] 警告：导航统领器未初始化！")
            play_voice_text("導航系統尚未就緒，請稍後重試。")
            await ui_broadcast_final("[系统] 导航系统未就绪")
        return

    if "停止导航" in user_text or "结束导航" in user_text or \
       "停止導航" in user_text or "結束導航" in user_text:
        if orchestrator:
            orchestrator.stop_navigation()
            print(f"[NAVIGATION] 导航已停止，状态: {orchestrator.get_state()}")
            await ui_broadcast_final("[系统] 盲道导航已停止")
            await ui_broadcast_raw(f"NAV_STATE:{orchestrator.get_state()}")
        # else: orchestrator 未初始化，導航本就未運行，靜默返回（不廣播雜訊）
        return

    nav_cmd_keywords = ["开始过马路", "过马路结束", "开始导航", "开启导航", "盲道导航", "停止导航", "结束导航", "立即通过", "现在通过", "继续",
                       "開始過馬路", "過馬路結束", "開始導航", "開啟導航", "忙導航", "停止導航", "結束導航", "立即通過", "現在通過"]
    if any(k in user_text for k in nav_cmd_keywords):
        if orchestrator:
            orchestrator.on_voice_command(user_text)
            await ui_broadcast_final("[系统] 导航模式已更新")
            await ui_broadcast_raw(f"NAV_STATE:{orchestrator.get_state()}")
        else:
            await ui_broadcast_final("[系统] 导航统领器未初始化")
        return    

    # 检查是否是"帮我找/识别一下xxx"的命令
    # 扩展正则表达式，支持更多关键词
    find_pattern = r"(?:^\s*(?:帮我|幫我))?\s*找一下\s*(.+?)(?:。|！|？|$)"
    match = re.search(find_pattern, user_text)
        
    if match:
        # 提取中文物品名称
        item_cn = match.group(1).strip()
        if item_cn:
            # 【新增】用本地映射 + Qwen 提取英文类名
            label_en, src = extract_english_label(item_cn)
            print(f"[COMMAND] Finder request: '{item_cn}' -> '{label_en}' (src={src})", flush=True)

            # 【新增】切换到找物品模式（暂停导航）
            if orchestrator:
                orchestrator.start_item_search()
                print(f"[ITEM_SEARCH] 已切换到找物品模式，状态: {orchestrator.get_state()}")
                await ui_broadcast_raw(f"NAV_STATE:{orchestrator.get_state()}")
            
            # 【关键】把英文类名传给 yolomedia（它会在找不到类时自动切 YOLOE）
            start_yolomedia_with_target(label_en, position_mode=_position_mode)

            # 给前端/语音来个确认反馈
            try:
                await ui_broadcast_final(f"[找物品] 正在寻找 {item_cn}...")
            except Exception:
                pass

            return
    
    # 检查是否是"找到了"的命令
    if "找到了" in user_text or "拿到了" in user_text:
        print("[COMMAND] Found command detected", flush=True)
        # 停止yolomedia
        stop_yolomedia()
        
        # 【新增】停止找物品模式，恢复之前的导航状态
        if orchestrator:
            orchestrator.stop_item_search(restore_nav=True)
            current_state = orchestrator.get_state()
            print(f"[ITEM_SEARCH] 找物品结束，当前状态: {current_state}")
            await ui_broadcast_raw(f"NAV_STATE:{current_state}")

            # 根据恢复的状态给出反馈
            if current_state in ["BLINDPATH_NAV", "SEEKING_CROSSWALK", "WAIT_TRAFFIC_LIGHT", "CROSSING", "SEEKING_NEXT_BLINDPATH"]:
                await ui_broadcast_final("[找物品] 已找到物品，继续导航。")
            else:
                await ui_broadcast_final("[找物品] 已找到物品。")
        else:
            await ui_broadcast_final("[找物品] 已找到物品。")
        
        return

    # 【修改】omni对话开始时，切换到CHAT模式
    global omni_conversation_active, omni_previous_nav_state
    omni_conversation_active = True
    
    # 保存当前导航状态并切换到CHAT模式
    if orchestrator:
        current_state = orchestrator.get_state()
        # 只有在导航模式下才需要保存和切换
        if current_state not in ["CHAT", "IDLE"]:
            omni_previous_nav_state = current_state
            orchestrator.force_state("CHAT")
            print(f"[OMNI] 对话开始，从{current_state}切换到CHAT模式")
        else:
            omni_previous_nav_state = None
            print(f"[OMNI] 对话开始（当前已在{current_state}模式）")
    
    # 如果不是特殊命令，执行原有的AI对话逻辑
    # 但如果yolomedia正在运行，暂时不处理普通对话
    if yolomedia_running:
        print("[AI] YOLO media is running, skipping normal AI response", flush=True)
        return

    # IDLE/CHAT 模式下防止環境雜訊誤觸發：
    # 文字必須 >= IDLE_FILTER_MIN_CHARS 字，或包含明確的對話觸發關鍵字
    # 旁路模式下通常用於課堂轉錄等情境，可透過 /api/set_param?name=idle_filter_min_chars&value=1 放寬
    _CHAT_TRIGGER_KEYWORDS = [
        "帮我", "幫我", "看看", "看一下", "前面", "什么", "什麼",
        "有没有", "有沒有", "告訴", "告诉", "描述", "識別", "识别",
        "找", "開始", "开始", "導航", "导航", "過馬路", "过马路",
        "說明書", "使用說明", "紅綠燈", "红绿灯",
    ]
    keyword_hits = [kw for kw in _CHAT_TRIGGER_KEYWORDS if kw in user_text]
    if len(user_text) < _idle_filter_min_chars and len(keyword_hits) < 2:
        print(
            f"[IDLE過濾] 過短語音丟棄（{len(user_text)}字，命中關鍵字 {len(keyword_hits)} 個）: '{user_text}'",
            flush=True,
        )
        return
    if keyword_hits:
        print(f"[IDLE過濾] 關鍵字命中 {len(keyword_hits)} 個 {keyword_hits}，通過", flush=True)

    # 原有的AI对话逻辑
    await start_ai_with_text(user_text)

# ========= Omni 播放启动 =========
async def start_ai_with_text(user_text: str):
    """硬重置后，开启新的 AI 语音输出。"""
    async def _runner():
        txt_buf: List[str] = []
        rate_state = None

        # 組裝（多幀圖像 + 文本）
        # 從 last_frames 取最多 3 幀（平均分佈），讓 Gemini 有時間序列上下文
        content_list = []
        if last_frames:
            try:
                frames = list(last_frames)  # deque → list（索引 0 最舊，-1 最新）
                n = len(frames)
                if n >= 3:
                    indices = [0, n // 2, n - 1]
                elif n == 2:
                    indices = [0, 1]
                else:
                    indices = [0]
                for idx in indices:
                    _, jpeg_bytes = frames[idx]
                    img_b64 = base64.b64encode(jpeg_bytes).decode("ascii")
                    content_list.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
                    })
            except Exception:
                pass
        content_list.append({"type": "text", "text": user_text})

        try:
            async for piece in stream_chat(content_list, voice="Cherry", audio_format="wav"):
                # 文本增量（仅 UI）
                if piece.text_delta:
                    txt_buf.append(piece.text_delta)
                    try:
                        await ui_broadcast_partial("[AI] " + "".join(txt_buf))
                    except Exception:
                        pass

                # 音频分片：Omni 返回 24k (PCM16) 的 wav audio.data（Base64）；下行需要 8k PCM16
                if piece.audio_b64:
                    try:
                        pcm24 = base64.b64decode(piece.audio_b64)
                    except Exception:
                        pcm24 = b""
                    if pcm24:
                        # 24k → 8k (使用ratecv保证音调和速度不变)
                        pcm8k, rate_state = audioop.ratecv(pcm24, 2, 1, 24000, 8000, rate_state)
                        pcm8k = audioop.mul(pcm8k, 2, 0.60)
                        if pcm8k:
                            await broadcast_pcm16_realtime(pcm8k)

        except asyncio.CancelledError:
            # 被新一轮打断
            raise
        except Exception as e:
            try:
                await ui_broadcast_final(f"[AI] 发生错误：{e}")
            except Exception:
                pass
        finally:
            # 【修改】标记omni对话结束，恢复之前的导航模式
            global omni_conversation_active, omni_previous_nav_state
            omni_conversation_active = False
            
            # 恢复之前的导航状态
            # 播放結束對話音效
            play_audio_threadsafe("結束對話")

            if orchestrator and omni_previous_nav_state:
                orchestrator.force_state(omni_previous_nav_state)
                print(f"[OMNI] 对话结束，恢复到{omni_previous_nav_state}模式")
                omni_previous_nav_state = None
            else:
                print("[OMNI] 对话结束（无需恢复导航状态）")
            
            # 不斷開串流連線，讓 APP 保持長連線，避免重連延遲丟失音訊

            final_text = ("".join(txt_buf)).strip() or "（空响应）"
            try:
                await ui_broadcast_final("[AI] " + final_text)
            except Exception:
                pass

    # 真正启动前先硬重置，保证**绝无**旧音频残留
    await hard_reset_audio("start_ai_with_text")
    loop = asyncio.get_running_loop()
    from audio_stream import __dict__ as _as_dict
    # 设置模块内的 current_ai_task
    task = loop.create_task(_runner())
    _as_dict["current_ai_task"] = task

# ---------- 页面 / 健康 ----------
@app.get("/", response_class=HTMLResponse)
def root():
    with open(os.path.join("templates", "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/speaker", response_class=HTMLResponse)
def speaker_page():
    """說話人聲紋管理 Dashboard"""
    with open(os.path.join("templates", "speaker.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/api/health", response_class=PlainTextResponse)
def health():
    return "OK"

# ── 說話人聲紋管理 API ───────────────────────────────────────────────────────

@app.post("/api/enroll_speaker")
async def enroll_speaker():
    """
    開始錄製說話人聲紋（10 秒）。
    使用方式：對著 ESP32 麥克風正常說話，完成後自動建立聲紋。
    建立成功後說話人驗證立即生效。
    """
    global _enroll_active, _enroll_buffer, _enroll_end_ts
    _enroll_buffer.clear()
    _enroll_end_ts = time.monotonic() + _ENROLL_SEC
    _enroll_active = True
    print(f"[ENROLL] 開始錄製說話人聲紋，請說話 {_ENROLL_SEC:.0f} 秒…", flush=True)
    return {
        "status":  "recording",
        "seconds": _ENROLL_SEC,
        "message": f"請對著麥克風說話 {_ENROLL_SEC:.0f} 秒，系統正在錄製您的聲紋",
    }

@app.get("/api/enroll_status")
async def enroll_status():
    """查詢聲紋錄製與驗證狀態"""
    global _enroll_active, _enroll_end_ts
    remaining = max(0.0, _enroll_end_ts - time.monotonic()) if _enroll_active else 0.0
    try:
        from speaker_verifier import speaker_verifier
        sv_status = speaker_verifier.status_dict()
    except Exception as ex:
        sv_status = {"error": str(ex)}
    return {
        "enrolling":            _enroll_active,
        "remaining_sec":        round(remaining, 1),
        "speaker_verifier":     sv_status,
    }

@app.post("/api/verify_continuous")
async def verify_continuous(enabled: bool):
    """開啟 / 關閉說話人聲紋持續監測模式（每 2 秒印一次相似度到伺服器終端機）"""
    global _verify_continuous, _verify_continuous_buf
    _verify_continuous = enabled
    _verify_continuous_buf.clear()
    status = "開啟" if enabled else "關閉"
    print(f"[VERIFY] 持續監測模式已{status}", flush=True)
    return {"continuous": enabled, "message": f"持續監測已{status}，請看伺服器終端機輸出"}

@app.post("/api/set_param")
async def api_set_param(name: str, value: float):
    """動態調整 ASR / 聲紋相關參數（不重啟生效）
    可調參數：threshold / standby_rms / pcm_gain / silence_sec / silence_rms
    """
    try:
        import asr_core as _asr
        import speaker_verifier as _sv

        if name == "threshold":
            _sv.set_threshold(value)
            msg = f"聲紋相似度門檻設為 {_sv.THRESHOLD:.2f}"
        elif name == "standby_rms":
            _asr.set_standby_rms_thresh(value)
            msg = f"待機靜音 RMS 門檻設為 {_asr.STANDBY_RMS_THRESH:.0f}"
        elif name == "pcm_gain":
            _asr.set_pcm_gain(value)
            msg = f"麥克風增益設為 {_asr.PCM_GAIN:.1f}x"
        elif name == "silence_sec":
            _asr.set_silence_sec(value)
            msg = f"主動錄音靜音判斷秒數設為 {value:.1f}s"
        elif name == "silence_rms":
            _asr.set_silence_rms_thresh(value)
            msg = f"主動模式靜音 RMS 門檻設為 {value:.0f}"
        elif name == "idle_filter_min_chars":
            global _idle_filter_min_chars
            _idle_filter_min_chars = max(0, int(value))
            msg = f"短句過濾門檻設為 {_idle_filter_min_chars} 字（0 = 不過濾）"
        else:
            return {"status": "error", "detail": f"未知參數：{name}"}

        print(f"[SET_PARAM] {msg}", flush=True)
        return {"status": "ok", "name": name, "value": value, "message": msg}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.post("/api/bypass_wake")
async def bypass_wake(enabled: bool):
    """開啟 / 關閉旁路模式：跳過喚醒詞「哈囉曼波」，所有 STT 結果直接送給 AI 處理。
    開啟後終端機會顯示每次 STT 辨識結果（[ASR-旁路] STT → '...'）。"""
    import asr_core
    asr_core.set_bypass_wake(enabled)
    status = "開啟" if enabled else "關閉"
    return {"bypass_wake": enabled, "message": f"旁路模式已{status}，所有語音將直接送 AI 處理（不需喚醒詞）"}

@app.post("/api/test_speaker_verify")
async def test_speaker_verify():
    """
    開始 3 秒測試錄音，完成後回報聲紋比對結果。
    使用方式：對著 ESP32 麥克風說話，等 /api/verify_result 查詢結果。
    """
    global _verify_test_active, _verify_test_buffer, _verify_test_end_ts
    _verify_test_buffer.clear()
    _verify_test_end_ts = time.monotonic() + _VERIFY_TEST_SEC
    _verify_test_active = True
    return {
        "status":  "recording",
        "seconds": _VERIFY_TEST_SEC,
        "message": f"請對著麥克風說話 {_VERIFY_TEST_SEC:.0f} 秒，系統正在驗證聲紋",
    }

@app.get("/api/verify_result")
async def verify_result():
    """查詢聲紋測試驗證結果（test_speaker_verify 完成後呼叫）"""
    global _verify_test_active
    if _verify_test_active:
        remaining = max(0.0, _verify_test_end_ts - time.monotonic())
        return {"status": "recording", "remaining_sec": round(remaining, 1)}
    if len(_verify_test_buffer) == 0:
        return {"status": "no_data", "message": "尚未進行測試，請先呼叫 /api/test_speaker_verify"}
    try:
        from speaker_verifier import speaker_verifier, THRESHOLD
        pcm = bytes(_verify_test_buffer)
        passed, similarity = speaker_verifier.verify_with_score(pcm)
        return {
            "status":     "done",
            "passed":     passed,
            "similarity": round(similarity, 4) if similarity is not None else None,
            "threshold":  THRESHOLD,
            "message":    "✅ 驗證通過" if passed else "❌ 驗證失敗（相似度不足）",
        }
    except Exception as ex:
        return {"status": "error", "detail": str(ex)}

@app.post("/api/delete_speaker")
async def delete_speaker():
    """刪除已儲存的說話人聲紋（停用說話人驗證）"""
    try:
        from speaker_verifier import speaker_verifier
        ok = speaker_verifier.delete_enrollment()
        return {"status": "deleted" if ok else "not_found"}
    except Exception as ex:
        return {"status": "error", "detail": str(ex)}

@app.post("/api/speaker_verify_toggle")
async def speaker_verify_toggle(enabled: bool):
    """手動開啟 / 關閉說話人驗證（不刪除聲紋）"""
    try:
        from speaker_verifier import speaker_verifier
        if enabled:
            speaker_verifier.enable()
        else:
            speaker_verifier.disable()
        return {"enabled": enabled}
    except Exception as ex:
        return {"status": "error", "detail": str(ex)}

async def _speaker_event_push(data: dict):
    """推送 Speaker 事件到所有已連線的 SSE 客戶端"""
    dead = []
    for q in _speaker_sse_queues:
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        try:
            _speaker_sse_queues.remove(q)
        except ValueError:
            pass

@app.get("/api/speaker_events")
async def speaker_events(request: Request):
    """說話人聲紋事件 SSE 端點（即時推送驗證結果、音量、錄製完成通知）"""
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _speaker_sse_queues.append(q)

    async def stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(q.get(), timeout=5.0)
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"  # 保持連線
        finally:
            try:
                _speaker_sse_queues.remove(q)
            except ValueError:
                pass

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# ── Debug 錄音 API ────────────────────────────────────────────────────────────

@app.post("/api/debug_record/start")
async def debug_record_start():
    """開始 Debug 錄音（收音進 _debug_rec_buffer，直到呼叫 stop）"""
    global _debug_rec_active, _debug_rec_buffer
    _debug_rec_buffer = bytearray()
    _debug_rec_active = True
    print("[DEBUG_REC] 開始錄音", flush=True)
    return {"status": "recording"}

@app.post("/api/debug_record/stop")
async def debug_record_stop():
    """停止 Debug 錄音並儲存為 WAV 檔案"""
    global _debug_rec_active, _debug_rec_buffer
    _debug_rec_active = False

    if not _debug_rec_buffer:
        return {"status": "error", "msg": "無收音資料"}

    import wave
    import os
    from datetime import datetime

    os.makedirs(_DEBUG_REC_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(_DEBUG_REC_DIR, f"debug_{ts}.wav")

    pcm_data = bytes(_debug_rec_buffer)
    _debug_rec_buffer = bytearray()

    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(1)        # 單聲道
        wf.setsampwidth(2)        # 16-bit PCM
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_data)

    duration = len(pcm_data) / (SAMPLE_RATE * 2)
    print(f"[DEBUG_REC] 已儲存 {filepath}（{duration:.1f} 秒）", flush=True)
    return {"status": "saved", "file": filepath, "duration_sec": round(duration, 1)}

# ── Debug 狀態面板 API ──────────────────────────────────────────────────────
@app.get("/api/debug_status")
def api_debug_status():
    """回傳伺服器全域狀態，供管理介面 Debug 面板輪詢使用"""
    # 安全讀取 WebSocket 連線狀態（避免競態條件）
    _cam = esp32_camera_ws
    _aud = esp32_audio_ws
    try:
        cam_ok = _cam is not None and _cam.client_state == WebSocketState.CONNECTED
    except Exception:
        cam_ok = False
    try:
        aud_ok = _aud is not None and _aud.client_state == WebSocketState.CONNECTED
    except Exception:
        aud_ok = False

    # 計算運行時間
    uptime_sec = int(time.time() - _server_start_time)
    h, rem = divmod(uptime_sec, 3600)
    m, s = divmod(rem, 60)

    return {
        # ── 連線狀態 ──
        "esp32_camera_connected": cam_ok,
        "esp32_audio_connected":  aud_ok,
        "ui_client_count":        len(ui_clients),
        "camera_viewer_count":    len(camera_viewers),
        "imu_ws_client_count":    len(imu_ws_clients),
        # ── 導航狀態 ──
        "orchestrator_state":     orchestrator.get_state() if orchestrator else "未初始化",
        "navigation_active":      navigation_active,
        "cross_street_active":    cross_street_active,
        # ── 模型狀態 ──
        "yolo_seg_loaded":          yolo_seg_model is not None,
        "obstacle_detector_loaded": obstacle_detector is not None,
        "gpu_available":            torch.cuda.is_available(),
        "gpu_name":                 torch.cuda.get_device_name(0) if torch.cuda.is_available() else "N/A",
        # ── ASR 狀態 ──
        "current_partial_len":  len(current_partial),
        "recent_finals_count":  len(recent_finals),
        "last_final":           recent_finals[-1][:60] if recent_finals else "",
        # ── 音訊狀態 ──
        "debug_rec_active":     _debug_rec_active,
        "debug_rec_bytes":      len(_debug_rec_buffer),
        "enroll_active":        _enroll_active,
        "verify_continuous":    _verify_continuous,
        "sample_rate":          SAMPLE_RATE,
        # ── 系統資訊 ──
        "uptime":               f"{h:02d}:{m:02d}:{s:02d}",
        "server_port":          SERVER_PORT,
        "device_id":            os.environ.get("DEVICE_ID", "glasses_01"),
    }

# 注册 /stream.wav
register_stream_route(app)

# ---------- WebSocket：WebUI 文本（ASR/AI 状态推送） ----------
@app.websocket("/ws_ui")
async def ws_ui(ws: WebSocket):
    await ws.accept()
    ui_clients[id(ws)] = ws
    try:
        init = {"partial": current_partial, "finals": recent_finals[-10:]}
        await ws.send_text("INIT:" + json.dumps(init, ensure_ascii=False))
        while True:
            await asyncio.sleep(30)
            try:
                await ws.send_text("PING")
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        ui_clients.pop(id(ws), None)

# ---------- WebSocket：ESP32 音频入口（ASR 上行） ----------
# APP 連線時會送 START:BYPASS，此旗標用於跳過硬體專用的歡迎音效
_audio_bypass_mode = False

@app.websocket("/ws_audio")
async def ws_audio(ws: WebSocket):
    global esp32_audio_ws, _audio_bypass_mode
    if esp32_audio_ws is not None:
        await ws.close(code=1013)
        return
    esp32_audio_ws = ws
    await ws.accept()
    print("\n[AUDIO] client connected")
    recognition = None
    streaming = False
    last_ts = time.monotonic()

    # 若 3 秒內沒收到 START，主動送 RESTART 讓 ESP32 補發
    async def _auto_restart_if_no_start():
        await asyncio.sleep(3.0)
        if not streaming:
            print("[AUDIO] 未收到 START，送 RESTART 給 ESP32", flush=True)
            try:
                await ws.send_text("RESTART")
            except Exception:
                pass
    asyncio.create_task(_auto_restart_if_no_start())

    async def stop_rec(send_notice: Optional[str] = None):
        nonlocal recognition, streaming
        if recognition:
            try: recognition.stop()
            except Exception: pass
            recognition = None
        await set_current_recognition(None)
        streaming = False
        if send_notice:
            try: await ws.send_text(send_notice)
            except Exception: pass

    async def on_sdk_error(_msg: str):
        await stop_rec(send_notice="RESTART")

    try:
        while True:
            if WebSocketState and ws.client_state != WebSocketState.CONNECTED:
                break
            try:
                msg = await ws.receive()
            except WebSocketDisconnect:
                break
            except RuntimeError as e:
                if "Cannot call \"receive\"" in str(e):
                    break
                raise

            if "text" in msg and msg["text"] is not None:
                raw = (msg["text"] or "").strip()
                cmd = raw.upper()

                if cmd == "START" or cmd == "START:BYPASS":
                    bypass = cmd == "START:BYPASS"
                    _audio_bypass_mode = bypass
                    mode_label = "BYPASS（APP 模式，跳過喚醒詞）" if bypass else "正常"
                    print(f"[AUDIO] {cmd} received — 模式: {mode_label}")
                    await stop_rec()
                    loop = asyncio.get_running_loop()
                    def post(coro):
                        asyncio.run_coroutine_threadsafe(coro, loop)

                    # 組裝 ASR 回調（注入所有依賴）
                    cb = ASRCallback(
                        on_sdk_error=lambda s: post(on_sdk_error(s)),
                        post=post,
                        ui_broadcast_partial=ui_broadcast_partial,
                        ui_broadcast_final=ui_broadcast_final,
                        is_playing_now_fn=is_playing_now,
                        start_ai_with_text_fn=start_ai_with_text_custom,
                        full_system_reset_fn=full_system_reset,
                        interrupt_lock=interrupt_lock,
                        # 喚醒詞「哈囉」→ 播放開始對話音效
                        on_wake_fn=lambda: play_audio_threadsafe("開始對話"),
                        # 結束詞「謝謝 曼波」→ 播放結束對話音效
                        on_end_fn=lambda: play_audio_threadsafe("結束對話"),
                        # 主動錄音自然結束 → 不播放結束音效
                        on_recording_end_fn=lambda: play_audio_threadsafe("結束收音"),
                    )

                    # 使用 Google Speech-to-Text 串流 ASR（Groq 已保留備用）
                    recognition = GoogleASR(
                        credentials_path=GOOGLE_CREDENTIALS_PATH,
                        sample_rate=SAMPLE_RATE,
                        callback=cb,
                        bypass_wake=bypass,
                    )
                    recognition.start()
                    await set_current_recognition(recognition)
                    streaming = True
                    last_ts = time.monotonic()
                    await ui_broadcast_partial("（已開始接收音訊…）")
                    await ws.send_text("OK:STARTED")

                elif cmd == "STOP":
                    await stop_rec(send_notice="OK:STOPPED")

                elif raw.startswith("PROMPT:"):
                    # 设备端主动发起一轮：同样使用"先硬重置后播放"的强语义
                    text = raw[len("PROMPT:"):].strip()
                    if text:
                        async with interrupt_lock:
                            await start_ai_with_text_custom(text) # 使用自定义的启动函数
                        await ws.send_text("OK:PROMPT_ACCEPTED")
                    else:
                        await ws.send_text("ERR:EMPTY_PROMPT")

            elif "bytes" in msg and msg["bytes"] is not None:
                raw_bytes = msg["bytes"]

                # ── Debug 錄音：同時捕捉音訊（不阻礙 ASR）──────────────────
                global _debug_rec_active, _debug_rec_buffer
                if _debug_rec_active:
                    _debug_rec_buffer.extend(raw_bytes)

                # ── 說話人聲紋錄製（同時收音，不阻礙 ASR）──────────────────
                global _enroll_active, _enroll_buffer, _enroll_end_ts
                global _verify_test_active, _verify_test_buffer, _verify_test_end_ts
                global _verify_continuous, _verify_continuous_buf
                global _last_rms_push_ts

                # 全時 RMS 推送：不論任何模式，只要有 SSE 客戶端就推送音量
                if _speaker_sse_queues and len(raw_bytes) >= 2:
                    _now_mono = time.monotonic()
                    if _now_mono - _last_rms_push_ts >= 0.15:
                        _last_rms_push_ts = _now_mono
                        _chunk_rms = audioop.rms(raw_bytes, 2)
                        asyncio.create_task(_speaker_event_push({
                            "type": "rms", "rms": _chunk_rms, "ts": time.time(),
                        }))

                # 持續監測：每累積 _VERIFY_CONTINUOUS_SEC 秒音訊就驗證一次
                if _verify_continuous:
                    _verify_continuous_buf.extend(raw_bytes)
                    needed = int(SAMPLE_RATE * 2 * _VERIFY_CONTINUOUS_SEC)
                    if len(_verify_continuous_buf) >= needed:
                        pcm_snap = bytes(_verify_continuous_buf[:needed])
                        del _verify_continuous_buf[:needed]
                        try:
                            # RMS 音量門檻：靜音時不做聲紋比對，避免偽陽性
                            import struct
                            import math
                            shorts = struct.unpack(f"<{len(pcm_snap)//2}h", pcm_snap)
                            rms = math.sqrt(sum(s*s for s in shorts) / len(shorts)) if shorts else 0
                            # 推送 RMS 數值到 SSE 客戶端（音量儀表用）
                            asyncio.create_task(_speaker_event_push({
                                "type": "rms", "rms": round(rms), "ts": time.time(),
                            }))
                            if rms < STANDBY_RMS_THRESH:
                                print(f"[VERIFY] 靜音（RMS={rms:.0f} < {STANDBY_RMS_THRESH}），跳過", flush=True)
                                asyncio.create_task(_speaker_event_push({
                                    "type": "silence",
                                    "rms": round(rms),
                                    "threshold": STANDBY_RMS_THRESH,
                                    "ts": time.time(),
                                }))
                            else:
                                from speaker_verifier import speaker_verifier, THRESHOLD
                                passed, sim = speaker_verifier.verify_with_score(pcm_snap)
                                if sim is None:
                                    print("[VERIFY] 無法計算相似度（驗證未啟用或尚無聲紋）", flush=True)
                                    asyncio.create_task(_speaker_event_push({
                                        "type": "verify_skip",
                                        "reason": "no_enrollment",
                                        "ts": time.time(),
                                    }))
                                else:
                                    bar = int(sim * 30)
                                    bar_str = "█" * bar + "░" * (30 - bar)
                                    status = "✅ 通過" if passed else "❌ 拒絕"
                                    print(
                                        f"[VERIFY] {status}  相似度={sim:.4f}  門檻={THRESHOLD}"
                                        f"\n         [{bar_str}]",
                                        flush=True,
                                    )
                                    asyncio.create_task(_speaker_event_push({
                                        "type": "verify",
                                        "passed": passed,
                                        "similarity": round(sim, 4),
                                        "threshold": THRESHOLD,
                                        "rms": round(rms),
                                        "ts": time.time(),
                                    }))
                        except Exception as ex:
                            print(f"[VERIFY] 錯誤: {ex}", flush=True)

                # 單次測試驗證收音
                if _verify_test_active:
                    now_mono = time.monotonic()
                    if now_mono < _verify_test_end_ts:
                        _verify_test_buffer.extend(raw_bytes)
                    else:
                        _verify_test_active = False
                        print("[VERIFY_TEST] 收音完畢，等待查詢 /api/verify_result", flush=True)

                if _enroll_active:
                    now_mono = time.monotonic()
                    if now_mono < _enroll_end_ts:
                        _enroll_buffer.extend(raw_bytes)
                    else:
                        # 錄製時間到，建立聲紋
                        _enroll_active = False
                        pcm_snap = bytes(_enroll_buffer)
                        _enroll_buffer.clear()
                        _enroll_ok = False
                        try:
                            from speaker_verifier import speaker_verifier
                            _enroll_ok = speaker_verifier.enroll(pcm_snap, SAMPLE_RATE)
                            msg_txt = "聲紋錄製完成！說話人驗證已啟用。" if _enroll_ok else "聲紋錄製失敗，請重試。"
                        except Exception as ex:
                            msg_txt = f"聲紋錄製錯誤: {ex}"
                        print(f"[ENROLL] {msg_txt}", flush=True)
                        await ui_broadcast_partial(f"[系統] {msg_txt}")
                        asyncio.create_task(_speaker_event_push({
                            "type": "enroll_done",
                            "ok": _enroll_ok,
                            "message": msg_txt,
                            "ts": time.time(),
                        }))

                if not streaming:
                    pass  # 尚未收到 START，正常等待中，不印 log
                elif not recognition:
                    pass  # ASR 尚未初始化，丟棄
                else:
                    try:
                        recognition.send_audio_frame(raw_bytes)
                        last_ts = time.monotonic()
                    except Exception:
                        await on_sdk_error("send_audio_frame failed")
                # 臨時 debug：確認音訊有到伺服器（每 100 幀印一次）
                if not hasattr(ws, '_audio_dbg_cnt'):
                    ws._audio_dbg_cnt = 0
                ws._audio_dbg_cnt += 1
                if ws._audio_dbg_cnt % 100 == 1:
                    print(f"[AUDIO-DBG] 已收 {ws._audio_dbg_cnt} 幀，streaming={streaming}", flush=True)

    except Exception as e:
        print(f"\n[WS ERROR] {e}")
    finally:
        await stop_rec()
        try:
            if WebSocketState is None or ws.client_state == WebSocketState.CONNECTED:
                await ws.close(code=1000)
        except Exception:
            pass
        if esp32_audio_ws is ws:
            esp32_audio_ws = None
        print("[WS] connection closed")

# ---------- WebSocket：ESP32 相机入口（JPEG 二进制） ----------
@app.websocket("/ws/camera")
async def ws_camera_esp(ws: WebSocket):
    global esp32_camera_ws, blind_path_navigator, cross_street_navigator, cross_street_active, navigation_active, orchestrator
    if esp32_camera_ws is not None:
        await ws.close(code=1013)
        return
    esp32_camera_ws = ws
    await ws.accept()
    print("[CAMERA] ESP32 connected")

    # 連線後送畫質/幀率指令，降低 2.4GHz 頻寬壓力
    await asyncio.sleep(0.5)
    try:
        await ws.send_text("SET:QUALITY=15")  # 畫質 15：縮小傳輸量，YOLO imgsz=320 精度已足夠
        await ws.send_text("SET:FPS=20")      # 20fps：幀間隔 50ms，降低等幀延遲
        print("[CAMERA] 已送出畫質/幀率限制指令（quality=15, fps=20）", flush=True)
    except Exception:
        pass

    # 硬體連線成功後播放歡迎音效（APP 模式跳過，歡迎語音僅供 ESP32 眼鏡使用）
    def _play_welcome():
        import time as _time
        _time.sleep(6.0)  # 等待 ESP32 音訊串流穩定就緒
        if _audio_bypass_mode:
            print("[WELCOME] APP 模式，跳過歡迎音效", flush=True)
            return
        from audio_player import play_audio_threadsafe
        play_audio_threadsafe("歡迎使用AI智慧眼鏡")
    threading.Thread(target=_play_welcome, daemon=True).start()
    
    # 【新增】初始化盲道导航器
    if blind_path_navigator is None and yolo_seg_model is not None:
        blind_path_navigator = BlindPathNavigator(yolo_seg_model, obstacle_detector)
        print("[NAVIGATION] 盲道导航器已初始化")
    else:
        if blind_path_navigator is not None:
            print("[NAVIGATION] 导航器已存在，无需重新初始化")
        elif yolo_seg_model is None:
            print("[NAVIGATION] 警告：YOLO模型未加载，无法初始化导航器")
    
    # 【新增】初始化过马路导航器
    if cross_street_navigator is None:
        if yolo_seg_model:
            cross_street_navigator = CrossStreetNavigator(
                seg_model=yolo_seg_model,
                coco_model=None,  # 不使用交通灯检测
                obs_model=None    # 暂时也不用障碍物检测，让它更快
            )
            print("[CROSS_STREET] 过马路导航器已初始化（简化版 - 仅斑马线检测）")
        else:
            print("[CROSS_STREET] 错误：缺少分割模型，无法初始化过马路导航器")
            
            if not yolo_seg_model:
                print("[CROSS_STREET] - 缺少分割模型 (yolo_seg_model)")
            if not obstacle_detector:
                print("[CROSS_STREET] - 缺少障碍物检测器 (obstacle_detector)")
    
    if orchestrator is None and blind_path_navigator is not None and cross_street_navigator is not None:
        orchestrator = NavigationMaster(blind_path_navigator, cross_street_navigator)
        print("[NAV MASTER] 统领状态机已初始化（托管模式）")
    frame_counter = 0  # 添加帧计数器
    
    try:
        while True:
            msg = await ws.receive()
            if "bytes" in msg and msg["bytes"] is not None:
                data = msg["bytes"]
                frame_counter += 1
                
                # 【新增】录制原始帧
                try:
                    sync_recorder.record_frame(data)
                except Exception as e:
                    if frame_counter % 100 == 0:  # 避免日志刷屏
                        print(f"[RECORDER] 录制帧失败: {e}")
                
                try:
                    last_frames.append((time.time(), data))
                except Exception:
                    pass
                
                # 推送到bridge_io（供yolomedia使用）
                bridge_io.push_raw_jpeg(data)

                # 【速度優化】清空積壓幀：上一輪 YOLO 推理期間 WebSocket 積壓的舊幀
                # 全部推給 bridge_io / recorder，但導航推理只用最新一幀
                while True:
                    try:
                        _fm = await asyncio.wait_for(ws.receive(), timeout=0.001)
                        _t  = _fm.get('type', '')
                        if _t in ('websocket.disconnect', 'websocket.close'):
                            raise WebSocketDisconnect()
                        _fd = _fm.get('bytes')
                        if _fd:
                            frame_counter += 1
                            try: sync_recorder.record_frame(_fd)
                            except Exception: pass
                            try: last_frames.append((time.time(), _fd))
                            except Exception: pass
                            bridge_io.push_raw_jpeg(_fd)
                            data = _fd  # 丟棄舊幀，保留最新
                    except asyncio.TimeoutError:
                        break
                    except WebSocketDisconnect:
                        raise
                    except Exception:
                        break

                # 【调试】检查导航条件
                if frame_counter % 30 == 0:  # 每30帧输出一次
                    state_dbg = orchestrator.get_state() if orchestrator else "N/A"
                    print(f"[NAVIGATION DEBUG] 帧:{frame_counter}, state={state_dbg}, yolomedia_running={yolomedia_running}")
                
                # 统一解码（添加更严格的异常处理）
                try:
                    arr = np.frombuffer(data, dtype=np.uint8)
                    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    # 验证解码结果
                    if bgr is None or bgr.size == 0:
                        if frame_counter % 30 == 0:
                            print(f"[JPEG] 解码失败：数据长度={len(data)}")
                        bgr = None
                except Exception as e:
                    if frame_counter % 30 == 0:
                        print(f"[JPEG] 解码异常: {e}")
                    bgr = None

                # 【托管】优先交给统领状态机（寻物未占用画面时）
                # 【修改】找物品模式时不执行导航处理，让yolomedia接管画面
                if orchestrator and not yolomedia_running and bgr is not None:
                    current_state = orchestrator.get_state()
                    
                    # 【新增】找物品模式：不处理画面，等待yolomedia发送处理后的帧
                    if current_state == "ITEM_SEARCH":
                        # 找物品模式下，如果yolomedia还没开始发送帧，先显示原始画面
                        if not yolomedia_sending_frames and camera_viewers:
                            ok, enc = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                            if ok:
                                jpeg_data = enc.tobytes()
                                dead = []
                                for viewer_ws in list(camera_viewers):
                                    try:
                                        await viewer_ws.send_bytes(jpeg_data)
                                    except Exception:
                                        dead.append(viewer_ws)
                                for d in dead:
                                    camera_viewers.discard(d)
                        continue  # 跳过后续的导航处理
                    
                    out_img = bgr
                    try:
                        # YOLO 推理丟進執行緒池，避免阻塞 asyncio 事件迴圈
                        _loop = asyncio.get_event_loop()

                        if current_state == "TRAFFIC_LIGHT_DETECTION":
                            import trafficlight_detection
                            result = await _loop.run_in_executor(
                                None,
                                lambda: trafficlight_detection.process_single_frame(
                                    bgr, ui_broadcast_callback=ui_broadcast_final
                                )
                            )
                            out_img = result['vis_image'] if result['vis_image'] is not None else bgr

                        else:
                            # 其他模式：正常的導航處理（在執行緒池執行，不阻塞收幀）
                            res = await _loop.run_in_executor(
                                None, orchestrator.process_frame, bgr
                            )

                            if res.guidance_text:
                                try:
                                    play_voice_text(res.guidance_text)
                                    await ui_broadcast_final(f"[导航] {res.guidance_text}")
                                except Exception:
                                    pass

                            out_img = res.annotated_image if res.annotated_image is not None else bgr
                    except Exception as e:
                        if frame_counter % 100 == 0:
                            print(f"[NAV MASTER] 处理帧时出错: {e}")

                    # 廣播圖像（並行送給所有 viewer，不逐一等待）
                    if camera_viewers and out_img is not None:
                        ok, enc = cv2.imencode(".jpg", out_img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                        if ok:
                            jpeg_data = enc.tobytes()
                            dead = []
                            send_tasks = []
                            viewer_list = list(camera_viewers)
                            for viewer_ws in viewer_list:
                                send_tasks.append(viewer_ws.send_bytes(jpeg_data))
                            results = await asyncio.gather(*send_tasks, return_exceptions=True)
                            for viewer_ws, r in zip(viewer_list, results):
                                if isinstance(r, Exception):
                                    dead.append(viewer_ws)
                            for d in dead:
                                camera_viewers.discard(d)
                    # 已托管，進入下一幀
                    continue

                # 【回退】寻物占用或者未解码成功，按原始画面回传
                if not yolomedia_sending_frames and camera_viewers:
                    try:
                        if bgr is None:
                            arr = np.frombuffer(data, dtype=np.uint8)
                            bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                        if bgr is not None:
                            ok, enc = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                            if ok:
                                jpeg_data = enc.tobytes()
                                dead = []
                                for viewer_ws in list(camera_viewers):
                                    try:
                                        await viewer_ws.send_bytes(jpeg_data)
                                    except Exception:
                                        dead.append(viewer_ws)
                                for ws in dead:
                                    camera_viewers.discard(ws)
                    except Exception as e:
                        print(f"[CAMERA] Broadcast error: {e}")

            elif "type" in msg and msg["type"] in ("websocket.close", "websocket.disconnect"):
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[CAMERA ERROR] {e}")
    finally:
        try:
            if WebSocketState is None or ws.client_state == WebSocketState.CONNECTED:
                await ws.close(code=1000)
        except Exception:
            pass
        esp32_camera_ws = None
        print("[CAMERA] ESP32 disconnected")
        
        # 【新增】清理导航状态
        if blind_path_navigator:
            blind_path_navigator.reset()
        if cross_street_navigator:
            cross_street_navigator.reset()
        if orchestrator:
            orchestrator.reset()
            print("[NAV MASTER] 统领器已重置")

# ---------- WebSocket：浏览器订阅相机帧 ----------
@app.websocket("/ws/viewer")
async def ws_viewer(ws: WebSocket):
    await ws.accept()
    camera_viewers.add(ws)
    print(f"[VIEWER] Browser connected. Total viewers: {len(camera_viewers)}", flush=True)
    try:
        while True:
            # 保持连接活跃，每 30 秒送一次 PING 防止 Cloudflare idle timeout（100s）
            await asyncio.sleep(30)
            try:
                await ws.send_text("PING")
            except Exception:
                break
    except WebSocketDisconnect:
        print("[VIEWER] Browser disconnected", flush=True)
    finally:
        try:
            camera_viewers.remove(ws)
        except Exception:
            pass
        print(f"[VIEWER] Removed. Total viewers: {len(camera_viewers)}", flush=True)

# ---------- WebSocket：浏览器订阅 IMU ----------
@app.websocket("/ws")
async def ws_imu(ws: WebSocket):
    await ws.accept()
    imu_ws_clients.add(ws)
    try:
        while True:
            await asyncio.sleep(30)
            try:
                await ws.send_text("PING")
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        imu_ws_clients.discard(ws)

async def imu_broadcast(msg: str):
    if not imu_ws_clients: return
    dead = []
    for ws in list(imu_ws_clients):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        imu_ws_clients.discard(ws)

# ---------- 服务端 IMU 估计（原样保留） ----------
from math import atan2, hypot, pi
GRAV_BETA   = 0.98
STILL_W     = 0.4
YAW_DB      = 0.08
YAW_LEAK    = 0.2
ANG_EMA     = 0.15
AUTO_REZERO = True
USE_PROJ    = True
FREEZE_STILL= True
G     = 9.807
A_TOL = 0.08 * G
gLP = {"x":0.0, "y":0.0, "z":0.0}
gOff= {"x":0.0, "y":0.0, "z":0.0}
BIAS_ALPHA = 0.002
yaw  = 0.0
Rf = Pf = Yf = 0.0
ref = {"roll":0.0, "pitch":0.0, "yaw":0.0}
holdStart = 0.0
isStill   = False
last_ts_imu = 0.0
last_wall = 0.0
imu_store: List[Dict[str, Any]] = []

def _wrap180(a: float) -> float:
    a = a % 360.0
    if a >= 180.0: a -= 360.0
    if a < -180.0: a += 360.0
    return a

def process_imu_and_maybe_store(d: Dict[str, Any]):
    global gLP, gOff, yaw, Rf, Pf, Yf, ref, holdStart, isStill, last_ts_imu, last_wall

    t_ms = float(d.get("ts", 0.0))
    now_wall = time.monotonic()
    if t_ms <= 0.0:
        t_ms = (now_wall * 1000.0)
    if last_ts_imu <= 0.0 or t_ms <= last_ts_imu or (t_ms - last_ts_imu) > 3000.0:
        dt = 0.02
    else:
        dt = (t_ms - last_ts_imu) / 1000.0
    last_ts_imu = t_ms

    ax = float(((d.get("accel") or {}).get("x", 0.0)))
    ay = float(((d.get("accel") or {}).get("y", 0.0)))
    az = float(((d.get("accel") or {}).get("z", 0.0)))
    wx = float(((d.get("gyro")  or {}).get("x", 0.0)))
    wy = float(((d.get("gyro")  or {}).get("y", 0.0)))
    wz = float(((d.get("gyro")  or {}).get("z", 0.0)))

    gLP["x"] = GRAV_BETA * gLP["x"] + (1.0 - GRAV_BETA) * ax
    gLP["y"] = GRAV_BETA * gLP["y"] + (1.0 - GRAV_BETA) * ay
    gLP["z"] = GRAV_BETA * gLP["z"] + (1.0 - GRAV_BETA) * az
    gmag = hypot(gLP["x"], gLP["y"], gLP["z"]) or 1.0
    gHat = {"x": gLP["x"]/gmag, "y": gLP["y"]/gmag, "z": gLP["z"]/gmag}

    roll  = (atan2(az, ay)   * 180.0 / pi)
    pitch = (atan2(-ax, ay)  * 180.0 / pi)

    aNorm = hypot(ax, ay, az); wNorm = hypot(wx, wy, wz)
    nearFlat = (abs(roll) < 2.0 and abs(pitch) < 2.0)
    stillCond = (abs(aNorm - G) < A_TOL) and (wNorm < STILL_W)

    if stillCond:
        if holdStart <= 0.0: holdStart = t_ms
        if not isStill and (t_ms - holdStart) > 350.0: isStill = True
        gOff["x"] = (1.0 - BIAS_ALPHA)*gOff["x"] + BIAS_ALPHA*wx
        gOff["y"] = (1.0 - BIAS_ALPHA)*gOff["y"] + BIAS_ALPHA*wy
        gOff["z"] = (1.0 - BIAS_ALPHA)*gOff["z"] + BIAS_ALPHA*wz
    else:
        holdStart = 0.0; isStill = False

    if USE_PROJ:
        yawdot = ((wx - gOff["x"])*gHat["x"] + (wy - gOff["y"])*gHat["y"] + (wz - gOff["z"])*gHat["z"])
    else:
        yawdot = (wy - gOff["y"])

    if abs(yawdot) < YAW_DB: yawdot = 0.0
    if FREEZE_STILL and stillCond: yawdot = 0.0

    yaw = _wrap180(yaw + yawdot * dt)

    if (YAW_LEAK > 0.0) and nearFlat and stillCond and abs(yaw) > 0.0:
        step = YAW_LEAK * dt * (-1.0 if yaw > 0 else (1.0 if yaw < 0 else 0.0))
        if abs(yaw) <= abs(step): yaw = 0.0
        else: yaw += step

    global Rf, Pf, Yf, ref, last_wall
    Rf = ANG_EMA * roll  + (1.0 - ANG_EMA) * Rf
    Pf = ANG_EMA * pitch + (1.0 - ANG_EMA) * Pf
    Yf = ANG_EMA * yaw   + (1.0 - ANG_EMA) * Yf

    if AUTO_REZERO and nearFlat and (wNorm < STILL_W):
        if holdStart <= 0.0: holdStart = t_ms
        if not isStill and (t_ms - holdStart) > 350.0:
            ref.update({"roll": Rf, "pitch": Pf, "yaw": Yf})
            isStill = True

    R = _wrap180(Rf - ref["roll"])
    P = _wrap180(Pf - ref["pitch"])
    Y = _wrap180(Yf - ref["yaw"])

    now_wall = time.monotonic()
    if last_wall <= 0.0 or (now_wall - last_wall) >= 0.100:
        last_wall = now_wall
        item = {
            "ts": t_ms/1000.0,
            "angles": {"roll": R, "pitch": P, "yaw": Y},
            "accel":  {"x": ax, "y": ay, "z": az},
            "gyro":   {"x": wx, "y": wy, "z": wz},
        }
        imu_store.append(item)

# ---------- UDP 接收 IMU 并转发 ----------
class UDPProto(asyncio.DatagramProtocol):
    def connection_made(self, transport):
        print(f"[UDP] listening on {UDP_IP}:{UDP_PORT}")
    def datagram_received(self, data, addr):
        try:
            s = data.decode('utf-8', errors='ignore').strip()
            d = json.loads(s)
            if 'ts' not in d and 'timestamp_ms' in d:
                d['ts'] = d.pop('timestamp_ms')
            process_imu_and_maybe_store(d)
            asyncio.create_task(imu_broadcast(json.dumps(d)))
        except Exception:
            pass



# === UDP 廣播：讓 App 自動發現伺服器 IP ===
@app.on_event("startup")
async def on_startup_udp_broadcast():
    """每 2 秒廣播伺服器資訊到區網，App 監聽 port 47777 後自動連線"""
    import socket as _socket

    def _broadcast():
        sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_BROADCAST, 1)
        sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        msg = json.dumps({
            "service": "ai_glasses",
            "port":    SERVER_PORT,
        }).encode()
        print("[DISCOVERY] UDP 廣播已啟動（port 47777，每 2 秒）", flush=True)
        while True:
            try:
                sock.sendto(msg, ('<broadcast>', 47777))
            except Exception:
                pass
            time.sleep(2)

    threading.Thread(target=_broadcast, daemon=True).start()


# === 新增：注册给 bridge_io 的发送回调（把 JPEG 广播给 /ws/viewer） ===
@app.on_event("startup")
async def on_startup_register_bridge_sender():
    # 保存主线程的事件循环
    main_loop = asyncio.get_event_loop()
    
    def _sender(jpeg_bytes: bytes):
        # 注意：这个函数可能在非协程线程里被调用，需要切回主事件循环
        try:
            # 检查事件循环状态，避免在关闭时发送
            if main_loop.is_closed():
                return
            
            # 标记YOLO已经开始发送处理后的帧
            global yolomedia_sending_frames
            if not yolomedia_sending_frames:
                yolomedia_sending_frames = True
                print("[YOLOMEDIA] 开始发送处理后的帧，切换到YOLO画面", flush=True)
            
            async def _broadcast():
                if not camera_viewers:
                    return
                dead = []
                for ws in list(camera_viewers):
                    try:
                        await ws.send_bytes(jpeg_bytes)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    try:
                        camera_viewers.remove(ws)
                    except Exception:
                        pass
            
            # 使用保存的主线程事件循环
            future = asyncio.run_coroutine_threadsafe(_broadcast(), main_loop)
            # 不等待结果，避免阻塞生产线程
        except Exception as e:
            # 只在非预期错误时打印日志
            if "Event loop is closed" not in str(e):
                print(f"[DEBUG] _sender error: {e}", flush=True)

    bridge_io.set_sender(_sender)

@app.on_event("startup")
async def on_startup_init_audio():
    """启动时初始化音频系统 + 預載 Google SpeechClient"""
    # 在后台线程中初始化，避免阻塞启动
    def _init():
        try:
            initialize_audio_system()
        except Exception as e:
            print(f"[AUDIO] 初始化失败: {e}")

    threading.Thread(target=_init, daemon=True).start()

    # 背景預載 Google SpeechClient（gRPC 連線較慢，提前建立可縮短首次語音辨識等待時間）
    preload_speech_client(GOOGLE_CREDENTIALS_PATH)

@app.on_event("startup")
async def on_startup():
    loop = asyncio.get_running_loop()
    try:
        await loop.create_datagram_endpoint(lambda: UDPProto(), local_addr=(UDP_IP, UDP_PORT))
    except OSError as e:
        print(f"[UDP] port {UDP_PORT} 無法綁定（{e}），IMU 資料將不可用，但服務繼續啟動", flush=True)

    # 注入語音推播 callback：每次命中預錄 WAV，同步推 SPEAK: 到 /ws_ui
    # APP 收到後用本地 WAV 播放，不依賴 /stream.wav
    # 注意：play_voice_text 可能從非同步 thread 呼叫，必須用 run_coroutine_threadsafe
    _main_loop = asyncio.get_running_loop()

    def _speak_push(text: str, duration_ms: int) -> None:
        msg = json.dumps({"type": "speak", "text": text, "duration_ms": duration_ms}, ensure_ascii=False)
        asyncio.run_coroutine_threadsafe(ui_broadcast_raw(f"SPEAK:{msg}"), _main_loop)

    register_speak_push(_speak_push)

_disc_stop = threading.Event()

@app.on_event("startup")
async def on_startup_discovery():
    """UDP 探索回應器：收到 ESP32 廣播後，回傳本機 IP，讓 ESP32 自動找到伺服器。"""
    import socket as _socket

    def _get_local_ip_for(peer: str) -> str:
        peer_prefix = '.'.join(peer.split('.')[:3])  # 例如 "10.207.23"
        # 優先找與 ESP32 同 /24 子網的本機 IP
        try:
            hostname = _socket.gethostname()
            for info in _socket.getaddrinfo(hostname, None, _socket.AF_INET):
                ip = info[4][0]
                if ip.startswith(peer_prefix + '.'):
                    return ip
        except Exception:
            pass
        # 備用：讓 OS 路由表決定
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        try:
            s.connect((peer, 80))
            return s.getsockname()[0]
        finally:
            s.close()

    def _run():
        sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        sock.bind(('', 12346))
        sock.settimeout(1.0)
        print("[DISC] UDP 探索回應器已啟動（port 12346）", flush=True)
        while not _disc_stop.is_set():
            try:
                data, addr = sock.recvfrom(64)
                if data == b'AIGLASS_DISCOVER':
                    my_ip = _get_local_ip_for(addr[0])
                    reply = f'AIGLASS_HOST:{my_ip}'.encode()
                    # 使用獨立 socket 送回應，同時嘗試 unicast 與子網廣播
                    # 廣播可穿透 WiFi client isolation，確保 ESP32 收到
                    subnet_bcast = my_ip.rsplit('.', 1)[0] + '.255'
                    for dest in [addr, (subnet_bcast, addr[1])]:
                        try:
                            reply_sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
                            reply_sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_BROADCAST, 1)
                            reply_sock.bind((my_ip, 0))
                            reply_sock.sendto(reply, dest)
                            reply_sock.close()
                        except Exception:
                            pass
                    print(f"[DISC] {addr[0]} 詢問 -> 回應 {my_ip}（unicast + bcast {subnet_bcast}）", flush=True)
            except _socket.timeout:
                continue
            except Exception as e:
                print(f"[DISC] 錯誤: {e}", flush=True)
        sock.close()

    asyncio.get_running_loop().run_in_executor(None, _run)

@app.on_event("shutdown")
async def on_shutdown_discovery():
    _disc_stop.set()

@app.on_event("shutdown")
async def on_shutdown():
    """应用关闭时的清理工作"""
    print("[SHUTDOWN] 开始清理资源...")
    
    # 停止YOLO媒体处理
    stop_yolomedia()
    
    # 停止音频和AI任务
    await hard_reset_audio("shutdown")
    
    print("[SHUTDOWN] 资源清理完成")

# ── 本機裝置模式（LOCAL_MODE=true）──────────────────────────────────────────

def _init_navigators():
    """初始化導航器（本機模式與 ESP32 模式共用）。"""
    global blind_path_navigator, cross_street_navigator, orchestrator
    if blind_path_navigator is None and yolo_seg_model is not None:
        blind_path_navigator = BlindPathNavigator(yolo_seg_model, obstacle_detector)
        print("[NAVIGATION] 盲道導航器已初始化", flush=True)
    if cross_street_navigator is None and yolo_seg_model is not None:
        cross_street_navigator = CrossStreetNavigator(
            seg_model=yolo_seg_model,
            coco_model=None,
            obs_model=None,
        )
        print("[CROSS_STREET] 過馬路導航器已初始化", flush=True)
    if orchestrator is None and blind_path_navigator is not None and cross_street_navigator is not None:
        orchestrator = NavigationMaster(blind_path_navigator, cross_street_navigator)
        print("[NAV MASTER] 狀態機已初始化", flush=True)


@app.on_event("startup")
async def on_startup_init():
    """伺服器啟動時：初始化導航器（不需等待攝影機連線），LOCAL_MODE 時另啟本機裝置。"""
    # 無論哪種模式，都在背景等待模型載入後初始化 orchestrator
    asyncio.create_task(_startup_init_navigators())

    import local_device
    if local_device.LOCAL_MODE:
        asyncio.create_task(_local_mode_init())


async def _startup_init_navigators():
    """啟動時初始化導航器（背景執行，等待 YOLO 模型載入，最多 120 秒）。

    不需要等待攝影機 WebSocket 連線，讓導航 API 在手機剛連上時就能使用。
    """
    for _ in range(240):          # 最多等 120 秒（每 0.5 秒檢查一次）
        if yolo_seg_model is not None:
            break
        await asyncio.sleep(0.5)

    _init_navigators()
    if orchestrator:
        print("[NAV MASTER] 啟動時初始化完成，狀態機就緒", flush=True)
    else:
        print("[NAV MASTER] 啟動初始化失敗：模型未載入或路徑錯誤", flush=True)


async def _local_mode_init():
    """本機模式初始化（背景執行，不阻塞 uvicorn 啟動）。"""
    import local_device
    try:
        print("[LOCAL] 本機裝置模式已啟用，跳過 ESP32 等待", flush=True)

        # 等待 YOLO 模型載入完畢（最多 60 秒）
        for _ in range(120):
            if yolo_seg_model is not None:
                break
            await asyncio.sleep(0.5)

        # 初始化導航器
        _init_navigators()

        # 啟動攝影機 / 麥克風 / 喇叭執行緒
        local_device.start()

        # 等麥克風執行緒穩定
        await asyncio.sleep(1.0)

        # 建立 ASR（與 ws_audio 相同的 callback 結構）
        loop = asyncio.get_running_loop()
        def post(coro):
            asyncio.run_coroutine_threadsafe(coro, loop)

        cb = ASRCallback(
            on_sdk_error=lambda s: print(f"[LOCAL-ASR] SDK 錯誤: {s}", flush=True),
            post=post,
            ui_broadcast_partial=ui_broadcast_partial,
            ui_broadcast_final=ui_broadcast_final,
            is_playing_now_fn=is_playing_now,
            start_ai_with_text_fn=start_ai_with_text_custom,
            full_system_reset_fn=full_system_reset,
            interrupt_lock=interrupt_lock,
            on_wake_fn=lambda: play_audio_threadsafe("開始對話"),
            on_end_fn=lambda: play_audio_threadsafe("結束對話"),
            on_recording_end_fn=lambda: play_audio_threadsafe("結束收音"),
        )

        recognition = GoogleASR(
            credentials_path=GOOGLE_CREDENTIALS_PATH,
            sample_rate=SAMPLE_RATE,
            callback=cb,
        )
        recognition.start()
        await set_current_recognition(recognition)

        # 把 ASR 接收端掛到麥克風執行緒
        local_device.set_local_recognition(recognition)

        # 播放歡迎音效
        def _welcome():
            import time as _t
            _t.sleep(3.0)
            play_audio_threadsafe("歡迎使用AI智慧眼鏡")
        threading.Thread(target=_welcome, daemon=True).start()

        print("[LOCAL] 本機模式初始化完成，可直接對電腦麥克風說話", flush=True)

    except Exception as e:
        import traceback
        print(f"[LOCAL] 本機模式初始化失敗：{e}", flush=True)
        traceback.print_exc()


@app.on_event("shutdown")
async def on_shutdown_local_mode():
    import local_device
    if local_device.LOCAL_MODE:
        local_device.stop()


# --- 导出接口（可选） ---
def get_last_frames():
    return last_frames

def get_camera_ws():
    return esp32_camera_ws


# ── 文件閱讀端點 ──────────────────────────────────────────────────────────────

class ReadDocumentRequest(BaseModel):
    image_b64: str   # base64 JPEG / PNG，由 APP 手機鏡頭拍攝


class ExplainDocumentRequest(BaseModel):
    text:     str    # 先前 OCR 取得的文件全文
    question: str    # 使用者問題（首次說明 / 追問）


def _compress_image_b64(image_b64: str, max_width: int = 1280, quality: int = 80) -> str:
    """壓縮 base64 圖片：縮小到 max_width 並以 JPEG 重新編碼，大幅減少 API 傳輸量。"""
    import base64
    try:
        raw = base64.b64decode(image_b64)
        img_array = np.frombuffer(raw, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img is None:
            return image_b64  # 解碼失敗，回傳原圖

        h, w = img.shape[:2]
        if w > max_width:
            scale = max_width / w
            img = cv2.resize(img, (max_width, int(h * scale)), interpolation=cv2.INTER_AREA)

        _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, quality])
        compressed = base64.b64encode(buf.tobytes()).decode()
        original_kb = len(image_b64) * 3 / 4 / 1024
        new_kb = len(compressed) * 3 / 4 / 1024
        print(f"[DOC-READ] 圖片壓縮: {original_kb:.0f}KB → {new_kb:.0f}KB ({w}x{h} → {img.shape[1]}x{img.shape[0]})", flush=True)
        return compressed
    except Exception as e:
        print(f"[DOC-READ] 圖片壓縮失敗: {e}，使用原圖", flush=True)
        return image_b64


@app.post("/api/read_document")
async def api_read_document(req: ReadDocumentRequest):
    """
    使用 Gemini Vision 完整擷取圖片中的所有文字。
    回傳 { text, char_count }
    """
    # 壓縮圖片以加速 API 傳輸（OCR 不需要超高解析度）
    compressed_b64 = _compress_image_b64(req.image_b64, max_width=1280, quality=80)

    system = (
        "你是一位專業的文件辨識助理，協助視障者閱讀紙本文件。"
        "請完整、逐字擷取圖片中的所有文字，保留段落與換行結構，"
        "不要省略、不要摘要、不要加入你自己的評論。"
        "若圖片中沒有可讀的文字，僅回覆：【圖片中未發現文字】。"
    )
    content_list = [
        {"type": "image_url",
         "image_url": {"url": f"data:image/jpeg;base64,{compressed_b64}"}},
        {"type": "text",
         "text": "請完整擷取此圖片中的所有文字，保留原有排版與段落。"},
    ]
    text = await generate_text_async(content_list, system_prompt=system, max_tokens=8192)
    return {"text": text, "char_count": len(text)}


@app.post("/api/explain_document")
async def api_explain_document(req: ExplainDocumentRequest):
    """
    根據 OCR 文件全文回答使用者問題（說明重點 / 追問）。
    回傳 { answer }
    """
    system = (
        "你是一位貼心的文件說明助理，協助視障者理解文件內容。"
        "根據使用者提供的文件原文，用清晰、口語化的繁體中文回答問題。"
        "若回答較長，請用條列或分段，讓視障者聆聽時容易理解。"
    )
    content_list = [
        {"type": "text",
         "text": f"以下是文件全文：\n\n{req.text}\n\n使用者問題：{req.question}"},
    ]
    answer = await generate_text_async(content_list, system_prompt=system, max_tokens=2048)
    return {"answer": answer}


# ── 導航控制端點（operator 以上可使用）───────────────────────────────────────

class ItemSearchRequest(BaseModel):
    item_name: str = ""
    position_mode: str = "clock"   # "clock"（時鐘）或 "cardinal"（前後左右）


@app.post("/api/nav/blindpath")
async def api_nav_blindpath():
    """啟動盲道導航（不需登入）"""
    await start_ai_with_text_custom("開始導航")
    return {"ok": True, "state": orchestrator.get_state() if orchestrator else "unavailable"}


@app.post("/api/nav/crossing")
async def api_nav_crossing():
    """啟動過馬路模式（不需登入）"""
    await start_ai_with_text_custom("開始過馬路")
    return {"ok": True, "state": orchestrator.get_state() if orchestrator else "unavailable"}


@app.post("/api/nav/traffic_light")
async def api_nav_traffic_light():
    """啟動紅綠燈偵測（不需登入）"""
    await start_ai_with_text_custom("檢測紅綠燈")
    return {"ok": True, "state": orchestrator.get_state() if orchestrator else "unavailable"}


@app.post("/api/nav/item_search")
async def api_nav_item_search(req: ItemSearchRequest):
    """啟動物品尋找（不需登入）"""
    global _position_mode
    # 儲存使用者本次選擇的方位模式
    if req.position_mode in ("clock", "cardinal"):
        _position_mode = req.position_mode
    text = f"幫我找{req.item_name}" if req.item_name else "幫我找東西"
    await start_ai_with_text_custom(text)
    return {"ok": True, "state": orchestrator.get_state() if orchestrator else "unavailable"}


class PositionModeRequest(BaseModel):
    mode: str  # "clock" 或 "cardinal"


@app.post("/api/settings/position_mode")
async def api_set_position_mode(req: PositionModeRequest):
    """設定方位播報模式（不需登入，即時生效）"""
    global _position_mode
    if req.mode not in ("clock", "cardinal"):
        return {"ok": False, "error": "mode 必須是 clock 或 cardinal"}
    _position_mode = req.mode
    return {"ok": True, "mode": _position_mode}


@app.get("/api/settings/position_mode")
async def api_get_position_mode():
    """取得目前方位播報模式"""
    return {"mode": _position_mode}


@app.post("/api/nav/stop")
async def api_nav_stop():
    """停止目前導航（不需登入）"""
    await start_ai_with_text_custom("停止導航")
    return {"ok": True, "state": orchestrator.get_state() if orchestrator else "unavailable"}


@app.get("/api/nav/state")
def api_nav_state():
    """查詢目前導航狀態（不需登入）"""
    # orchestrator 未初始化時回傳 IDLE（而非 unavailable）
    # 避免 APP 端把 "unavailable" 誤判為導航中而無法停止
    state = orchestrator.get_state() if orchestrator else "IDLE"
    return {"state": state}

if __name__ == "__main__":
    uvicorn.run(
        app, host=SERVER_HOST, port=SERVER_PORT,
        log_level="warning", access_log=False,
        loop="asyncio", workers=1, reload=False
    )
