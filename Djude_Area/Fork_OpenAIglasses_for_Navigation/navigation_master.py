# navigation_master.py
# -*- coding: utf-8 -*-
import time
import math
import cv2
import numpy as np
from dataclasses import dataclass
from typing import Optional, Dict, Any, Deque, List, Tuple
from collections import deque

# 工作流导入（与现有文件解耦）
from workflow_blindpath import BlindPathNavigator, ProcessingResult as BlindResult
from workflow_crossstreet import CrossStreetNavigator, CrossStreetResult as CrossResult

# ========== 状态常量 ==========
IDLE = "IDLE"                          # 空闲/未启用
CHAT = "CHAT"                          # 对话模式（不进行导航，只返回原始画面）
BLINDPATH_NAV = "BLINDPATH_NAV"        # 正在走盲道（复用 BlindPathNavigator）
SEEKING_CROSSWALK = "SEEKING_CROSSWALK"# 盲道阶段发现斑马线，正对准/靠近
WAIT_TRAFFIC_LIGHT = "WAIT_TRAFFIC_LIGHT" # 到达斑马线后等待交通灯（可选/占位）
CROSSING = "CROSSING"                  # 正在过马路（复用 CrossStreetNavigator）
SEEKING_NEXT_BLINDPATH = "SEEKING_NEXT_BLINDPATH" # 过完马路后寻找下一段盲道入口（上盲道）
RECOVERY = "RECOVERY"                  # 兜底/恢复（感知暂时丢失时）
TRAFFIC_LIGHT_DETECTION = "TRAFFIC_LIGHT_DETECTION"  # 红绿灯检测模式
ITEM_SEARCH = "ITEM_SEARCH"            # 找物品模式（暂停导航，由yolomedia处理画面）

# ========== 返回结构 ==========
@dataclass
class OrchestratorResult:
    annotated_image: Optional[np.ndarray]
    guidance_text: str
    state: str
    extras: Dict[str, Any]

# ========== 实用：信号平滑/多数表决 ==========
class MajorityFilter:
    def __init__(self, size: int = 8):
        self.buf: Deque[str] = deque(maxlen=size)

    def push(self, v: str):
        self.buf.append(v)

    def majority(self) -> str:
        if not self.buf:
            return "unknown"
        cnt = {}
        for v in self.buf:
            cnt[v] = cnt.get(v, 0) + 1
        # 稳健排序：unknown 权重最低
        items = sorted(cnt.items(), key=lambda x: (0 if x[0]=="unknown" else 1, x[1]), reverse=True)
        return items[0][0]

    def history(self) -> List[str]:
        return list(self.buf)

    def clear(self):
        self.buf.clear()

# ========== 红绿灯识别 ==========
class TrafficLightDetector:
    """
    红绿灯识别器：
    1) 优先尝试 yoloe_backend 风格的检测（如可用）；
    2) 回退：无模型时，使用 HSV 颜色启发式在上半屏寻找亮红/黄/绿的“灯团”。
    输出：('red'|'green'|'yellow'|'unknown', meta)
    """
    def __init__(self):
        self.has_backend = False
        self.backend = None
        try:
            # 尝试动态导入（根据你本地 yoloe_backend 的接口调整）
            import yoloe_backend as _yeb  # noqa
            self.backend = _yeb
            self.has_backend = True
        except Exception:
            self.has_backend = False
            self.backend = None

    def _try_backend(self, bgr: np.ndarray) -> Tuple[str, Dict[str, Any]]:
        """
        尝试调用 yoloe_backend 风格的接口。由于各项目实现不同，这里做“宽容地调用”：
        - 优先尝试 backend.detect(image, target_classes=['traffic light'])
        - 次选 backend.infer_image(image) 后在结果中过滤 'traffic light'
        - 以上都失败则返回 unknown
        预期结果条目应含 bbox 或 mask，可自行扩展“颜色判定”逻辑（ROI 取样 HSV）
        """
        if not self.has_backend or self.backend is None:
            return "unknown", {"reason": "backend_not_available"}

        res = None
        try:
            if hasattr(self.backend, "detect"):
                # 假定 detect 返回 [{'name': 'traffic light', 'box':[x1,y1,x2,y2], ...}, ...]
                res = self.backend.detect(bgr, target_classes=["traffic light"])
            elif hasattr(self.backend, "infer_image"):
                # 假定 infer_image 返回 [{'label': 'traffic light', 'bbox': [x1,y1,x2,y2], ...}, ...]
                res = self.backend.infer_image(bgr)
            else:
                return "unknown", {"reason": "backend_no_suitable_api"}
        except Exception as e:
            return "unknown", {"reason": f"backend_failed:{e}"}

        if not res or len(res) == 0:
            return "unknown", {"reason": "no_detection"}

        # 拿到最大框作为主灯，做 HSV 颜色判断
        H, W = bgr.shape[:2]
        best = None
        best_area = 0
        boxes = []
        for item in res:
            # 统一盒字段
            if "box" in item and isinstance(item["box"], (list, tuple)) and len(item["box"]) == 4:
                x1, y1, x2, y2 = item["box"]
            elif "bbox" in item and isinstance(item["bbox"], (list, tuple)) and len(item["bbox"]) == 4:
                x1, y1, x2, y2 = item["bbox"]
            else:
                continue
            x1 = int(max(0, min(W-1, x1))); x2 = int(max(0, min(W-1, x2)))
            y1 = int(max(0, min(H-1, y1))); y2 = int(max(0, min(H-1, y2)))
            if x2 <= x1 or y2 <= y1:
                continue
            area = (x2 - x1) * (y2 - y1)
            boxes.append((x1, y1, x2, y2, area))
            if area > best_area:
                best_area = area
                best = (x1, y1, x2, y2)

        if best is None:
            return "unknown", {"reason": "no_valid_bbox", "raw": len(res)}

        x1, y1, x2, y2 = best
        roi = bgr[y1:y2, x1:x2]
        color = self._classify_color_hsv(roi)
        return color, {"bbox": best, "count": len(res), "boxes": boxes}

    def _classify_color_hsv(self, roi_bgr: np.ndarray) -> str:
        """对 ROI 做 HSV 基于阈值的红/黄/绿简单判定；取面积最大的主色。"""
        if roi_bgr is None or roi_bgr.size == 0:
            return "unknown"
        hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)

        # 红色范围（两段）
        lower_red1 = np.array([0, 80, 120]); upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([160, 80, 120]); upper_red2 = np.array([180, 255, 255])
        mask_r1 = cv2.inRange(hsv, lower_red1, upper_red1)
        mask_r2 = cv2.inRange(hsv, lower_red2, upper_red2)
        mask_red = cv2.bitwise_or(mask_r1, mask_r2)

        # 绿色
        lower_green = np.array([40, 60, 120]); upper_green = np.array([90, 255, 255])
        mask_green = cv2.inRange(hsv, lower_green, upper_green)

        # 黄色
        lower_yellow = np.array([18, 80, 150]); upper_yellow = np.array([35, 255, 255])
        mask_yellow = cv2.inRange(hsv, lower_yellow, upper_yellow)

        # 面积阈值（相对 ROI）
        total = roi_bgr.shape[0] * roi_bgr.shape[1] + 1e-6
        r_ratio = float(np.count_nonzero(mask_red)) / total
        g_ratio = float(np.count_nonzero(mask_green)) / total
        y_ratio = float(np.count_nonzero(mask_yellow)) / total

        # 简单抑制“脏背景导致的弱响应”
        thr = 0.03
        candidates = []
        if r_ratio > thr: candidates.append(("red", r_ratio))
        if g_ratio > thr: candidates.append(("green", g_ratio))
        if y_ratio > thr: candidates.append(("yellow", y_ratio))
        if not candidates:
            return "unknown"
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    def detect(self, bgr: np.ndarray) -> Tuple[str, Dict[str, Any]]:
        """
        总入口：先尝试后端；失败则在上半屏自行找“亮色灯团”（无需框）。
        """
        # 1) 尝试后端
        if self.has_backend:
            color, meta = self._try_backend(bgr)
            if color != "unknown":
                return color, {"method": "backend", **meta}

        # 2) 回退：上半屏 HSV 聚类 + 连通域，选最大“灯团”判色
        H, W = bgr.shape[:2]
        roi = bgr[:int(H * 0.5), :]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # 高亮阈值（抑制暗部/车灯）
        v = hsv[:, :, 2]
        bright = (v > 140).astype(np.uint8) * 255

        # 粗分颜色
        col = self._classify_color_hsv(roi)
        return col, {"method": "fallback", "note": "no_backend", "bright_ratio": float(np.mean(bright > 0))}

# ========== 视觉辅助工具 ==========
def _color_bgr(name: str) -> Tuple[int, int, int]:
    if name == "red": return (0, 0, 255)
    if name == "green": return (0, 255, 0)
    if name == "yellow": return (0, 255, 255)
    if name == "blue": return (255, 0, 0)
    if name == "orange": return (0, 165, 255)
    if name == "cyan": return (255, 255, 0)
    if name == "magenta": return (255, 0, 255)
    if name == "gray": return (128, 128, 128)
    if name == "white": return (255, 255, 255)
    return (200, 200, 200)

def _put_text(img, text, org, color=(255,255,255), scale=0.7, thick=2, outline=True):
    if outline:
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                if dx==0 and dy==0: continue
                cv2.putText(img, text, (org[0]+dx, org[1]+dy), cv2.FONT_HERSHEY_SIMPLEX, scale, (0,0,0), thick+1)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick)

def _draw_badge(img, text, pos=(10, 28), fg="white", bg="blue"):
    color_fg = _color_bgr(fg); color_bg = _color_bgr(bg)
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    x, y = pos
    pad = 6
    cv2.rectangle(img, (x-4, y-th-pad), (x+tw+8, y+pad//2), color_bg, -1)
    _put_text(img, text, (x, y), color=color_fg, scale=0.6, thick=2, outline=False)

def _draw_state_panel(img, kv: Dict[str, Any], pos=(10, 60)):
    x, y = pos
    line_h = 22
    for i, (k, v) in enumerate(kv.items()):
        _put_text(img, f"{k}: {v}", (x, y + i*line_h), color=(255,255,255), scale=0.6, thick=2)

def _draw_frame_border(img, color=(0,255,0), thickness=3):
    h, w = img.shape[:2]
    cv2.rectangle(img, (0,0), (w-1, h-1), color, thickness)

def _draw_progress_bar(img, ratio: float, pos=(10, 90), size=(180, 10), color="cyan"):
    ratio = max(0.0, min(1.0, float(ratio)))
    x, y = pos
    w, h = size
    cv2.rectangle(img, (x, y), (x+w, y+h), (80,80,80), 1)
    cv2.rectangle(img, (x+1, y+1), (x+1+int((w-2)*ratio), y+h-1), _color_bgr(color), -1)

# ========== 统领器 ==========
class NavigationMaster:
    def __init__(self,
                 blind_nav: BlindPathNavigator,
                 cross_nav: CrossStreetNavigator,
                 *,
                 min_tts_interval: float = 1.2):
        self.blind = blind_nav
        self.cross = cross_nav
        self.state = IDLE
        self.last_guidance_ts = 0.0
        self.min_tts_interval = min_tts_interval

        # 防抖/稳定计数
        self.cnt_crosswalk_seen = 0         # 盲道侧看见斑马线（approaching/ready）
        self.cnt_align_ready = 0            # 斑马线 ready + 对准达标
        self.cnt_cross_end = 0              # 过马路结束条件累计
        self.cnt_lost = 0                   # 感知丢失累计（进入 RECOVERY）

        # 冷却期避免状态抖动
        self.cooldown_until = 0.0

        # 紧急恢复目标
        self.prev_target_state = BLINDPATH_NAV

        # 交通灯
        self.tld = TrafficLightDetector()
        self.tl_major = MajorityFilter(size=8)
        self.tl_last_color = "unknown"

        # 参数（可按现场再调）
        self.FRAMES_CROSS_SEEN = 8
        self.FRAMES_ALIGN_READY = 12
        self.FRAMES_CROSS_END = 12
        self.FRAMES_NEXT_BLIND_OK = 8
        self.FRAMES_LOST_MAX = 45

        self.ANGLE_ALIGN_THR_DEG = 12.0
        self.OFFSET_ALIGN_THR = 0.15

        self.COOLDOWN_SEC = 0.6
        
        # 找物品状态管理
        self.prev_nav_state_before_search = None  # 找物品前的导航状态，用于恢复

    # ----- 外部交互 -----
    def get_state(self) -> str:
        return self.state
    
    def start_blind_path_navigation(self):
        """启动盲道导航模式"""
        self.state = BLINDPATH_NAV
        self.cooldown_until = time.time() + self.COOLDOWN_SEC
        if self.blind:
            self.blind.reset()
    
    def stop_navigation(self):
        """停止导航，回到对话模式"""
        self.state = CHAT
        self.cooldown_until = time.time() + self.COOLDOWN_SEC
        if self.blind:
            self.blind.reset()
    
    def start_crossing(self):
        """启动过马路模式"""
        self.state = CROSSING
        self.cooldown_until = time.time() + self.COOLDOWN_SEC
        if self.cross:
            self.cross.reset()
    
    def start_traffic_light_detection(self):
        """启动红绿灯检测模式"""
        self.state = TRAFFIC_LIGHT_DETECTION
        self.cooldown_until = time.time() + self.COOLDOWN_SEC
    
    def is_in_navigation_mode(self):
        """检查是否在导航模式（非对话模式）"""
        return self.state not in ["CHAT", "IDLE", "TRAFFIC_LIGHT_DETECTION", "ITEM_SEARCH"]
    
    def start_item_search(self):
        """启动找物品模式，暂停当前导航"""
        # 保存当前导航状态（如果在导航中）
        if self.state in [BLINDPATH_NAV, SEEKING_CROSSWALK, WAIT_TRAFFIC_LIGHT, CROSSING, SEEKING_NEXT_BLINDPATH]:
            self.prev_nav_state_before_search = self.state
            print(f"[NAV MASTER] 暂停导航状态 {self.state}，切换到找物品模式")
        else:
            self.prev_nav_state_before_search = None
        
        self.state = ITEM_SEARCH
        self.cooldown_until = time.time() + self.COOLDOWN_SEC
    
    def stop_item_search(self, restore_nav: bool = True):
        """停止找物品模式"""
        # 如果需要恢复之前的导航状态
        if restore_nav and self.prev_nav_state_before_search:
            self.state = self.prev_nav_state_before_search
            print(f"[NAV MASTER] 找物品结束，恢复到导航状态 {self.state}")
            self.prev_nav_state_before_search = None
        else:
            # 否则回到对话模式
            self.state = CHAT
            print(f"[NAV MASTER] 找物品结束，回到对话模式")
        
        self.cooldown_until = time.time() + self.COOLDOWN_SEC

    def force_state(self, s: str):
        self.state = s
        self.cooldown_until = time.time() + self.COOLDOWN_SEC

    def on_voice_command(self, text: str):
        t = (text or "").strip()
        if "开始过马路" in t:
            # 直接进入等待/或立即过马路（低速环境可直过）
            if self.state in (BLINDPATH_NAV, SEEKING_CROSSWALK, WAIT_TRAFFIC_LIGHT, IDLE, RECOVERY, SEEKING_NEXT_BLINDPATH):
                self.state = WAIT_TRAFFIC_LIGHT
                self.cooldown_until = time.time() + self.COOLDOWN_SEC
        elif "立即通过" in t or "现在通过" in t:
            self.state = CROSSING
            self.cooldown_until = time.time() + self.COOLDOWN_SEC
        elif "停止" in t or "结束" in t:
            self.state = IDLE
        elif "继续" in t:
            if self.state == IDLE:
                self.state = BLINDPATH_NAV

    def reset(self):
        self.state = IDLE
        self.cnt_crosswalk_seen = 0
        self.cnt_align_ready = 0
        self.cnt_cross_end = 0
        self.cnt_lost = 0
        self.tl_major.clear()
        self.tl_last_color = "unknown"
        self.prev_target_state = BLINDPATH_NAV
        self._last_wait_light_announce = 0  # 重置等待绿灯播报时间
        try:
            self.blind.reset()
        except Exception:
            pass
        try:
            self.cross.reset()
        except Exception:
            pass

    # ----- 内部工具 -----
    def _say(self, now: float, text: str) -> str:
        if not text:
            return ""
        if now - self.last_guidance_ts >= self.min_tts_interval:
            self.last_guidance_ts = now
            return text
        return ""

    def _draw_tl_status(self, img: np.ndarray, color: str, meta: Dict[str, Any]):
        if img is None:
            return
        color_bgr = _color_bgr(color)
        # 角标与文本
        cv2.circle(img, (24, 24), 10, color_bgr, -1)
        _put_text(img, f"信号灯: {color}", (40, 30), color=color_bgr, scale=0.6, thick=2, outline=False)
        # 画 bbox（若有）
        if meta and "bbox" in meta:
            x1, y1, x2, y2 = meta["bbox"]
            cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), color_bgr, 2)

        # 多数表决历史（最近8帧）
        hist = self.tl_major.history()
        if hist:
            x0, y0 = 10, 50
            r = 6
            gap = 16
            for i, hcol in enumerate(hist[-12:]):
                cv2.circle(img, (x0 + i*gap, y0), r, _color_bgr(hcol), -1)
            _put_text(img, "信号历史", (x0, y0+20), color=(255,255,255), scale=0.5, thick=1)

    # ----- 主循环 -----
    def process_frame(self, bgr: np.ndarray) -> OrchestratorResult:
        now = time.time()
        
        # 【修改】IDLE状态默认进入CHAT模式，而不是自动开始导航
        if self.state == IDLE:
            self.state = CHAT
            self.cooldown_until = now + self.COOLDOWN_SEC
        
        # 【新增】CHAT模式：只返回原始画面，不进行导航
        if self.state == CHAT:
            return OrchestratorResult(
                annotated_image=bgr,
                guidance_text="",
                state="CHAT",
                extras={"mode": "对话模式"}
            )
        
        # 【新增】红绿灯检测模式：只返回原始画面，由红绿灯模块处理
        if self.state == TRAFFIC_LIGHT_DETECTION:
            return OrchestratorResult(
                annotated_image=bgr,
                guidance_text="",
                state="TRAFFIC_LIGHT_DETECTION",
                extras={"mode": "红绿灯检测模式"}
            )
        
        # 【新增】找物品模式：只返回原始画面，由yolomedia处理
        if self.state == ITEM_SEARCH:
            return OrchestratorResult(
                annotated_image=bgr,
                guidance_text="",
                state="ITEM_SEARCH",
                extras={"mode": "找物品模式", "prev_nav_state": self.prev_nav_state_before_search}
            )

        # 冷却期内允许继续输出画面，但避免"瞬时切换"
        in_cooldown = now < self.cooldown_until

        # 各状态处理
        if self.state in (BLINDPATH_NAV, SEEKING_CROSSWALK, SEEKING_NEXT_BLINDPATH, RECOVERY):
            # —— 盲道侧 —— 统一调用盲道导航器
            try:
                bres: BlindResult = self.blind.process_frame(bgr)
            except Exception as e:
                # 异常 → 进入恢复态
                self.state = RECOVERY
                self.cnt_lost += 5
                ann_err = bgr.copy()
                # 【移除】所有可视化干扰
                # _draw_badge(ann_err, "NAV ERROR", (10, 28), fg="white", bg="red")
                # _put_text(ann_err, str(e), (10, 56), color=(255,255,255), scale=0.55)
                return OrchestratorResult(ann_err, self._say(now, ""), self.state, {"error": str(e)})

            ann = bres.annotated_image if bres.annotated_image is not None else bgr.copy()
            say = bres.guidance_text or ""

            state_info = bres.state_info or {}
            cross_stage = state_info.get("crosswalk_stage", "not_detected")
            blind_state = state_info.get("state", "UNKNOWN")
            # 可选字段（若工作流未来补充）
            angle = float(state_info.get("last_angle", 0.0))
            center_x_ratio = float(state_info.get("last_center_x_ratio", 0.5))

            # —— 盲道 → 发现斑马线（approaching/ready）
            if self.state == BLINDPATH_NAV:
                if cross_stage in ("approaching", "ready"):
                    self.cnt_crosswalk_seen += 1
                else:
                    self.cnt_crosswalk_seen = max(0, self.cnt_crosswalk_seen - 1)

                if self.cnt_crosswalk_seen >= self.FRAMES_CROSS_SEEN and not in_cooldown:
                    self.state = SEEKING_CROSSWALK
                    self.cooldown_until = now + self.COOLDOWN_SEC
                    say = "正在接近斑马线，为您对准方向。"

                # 【移除】所有可视化干扰
                # _draw_badge(ann, f"STATE: {self.state}", (10, 28), fg="white", bg="blue")
                # _draw_state_panel(ann, {
                #     "盲道状态": blind_state,
                #     "斑马线阶段": cross_stage,
                #     "靠近计数": self.cnt_crosswalk_seen,
                # }, pos=(10, 60))
                # _draw_progress_bar(ann, max(0.0, min(1.0, self.cnt_crosswalk_seen / max(1, self.FRAMES_CROSS_SEEN))), pos=(10, 120), size=(180, 10), color="cyan")
                # _draw_frame_border(ann, color=_color_bgr("blue"), thickness=3)

            # —— 对准阶段：同时利用 blind 内部 crosswalk_tracker 的角度与偏移（若提供）
            elif self.state == SEEKING_CROSSWALK:
                aligned = (abs(angle) <= self.ANGLE_ALIGN_THR_DEG and abs(center_x_ratio - 0.5) <= self.OFFSET_ALIGN_THR)
                if cross_stage == "ready" and aligned:
                    self.cnt_align_ready += 1
                else:
                    self.cnt_align_ready = max(0, self.cnt_align_ready - 1)

                if self.cnt_align_ready >= self.FRAMES_ALIGN_READY and not in_cooldown:
                    self.state = WAIT_TRAFFIC_LIGHT
                    self.cooldown_until = now + self.COOLDOWN_SEC
                    say = "已到达斑马线，请等待红绿灯。"

                # 【移除】所有可视化干扰
                # _draw_badge(ann, f"STATE: {self.state}", (10, 28), fg="white", bg="orange")
                # panel = {
                #     "阶段": cross_stage,
                #     "对准计数": self.cnt_align_ready,
                # }
                # if "last_angle" in state_info:
                #     panel["角度(°)"] = f"{angle:.1f}"
                # if "last_center_x_ratio" in state_info:
                #     panel["偏移"] = f"{(center_x_ratio-0.5):+.2f}"
                # _draw_state_panel(ann, panel, pos=(10, 60))
                # _draw_progress_bar(ann, max(0.0, min(1.0, self.cnt_align_ready / max(1, self.FRAMES_ALIGN_READY))), pos=(10, 120), size=(220, 10), color="yellow")
                # _draw_frame_border(ann, color=_color_bgr("orange"), thickness=3)

            # —— 过马路后寻找下一段盲道（上盲道流程）
            elif self.state == SEEKING_NEXT_BLINDPATH:
                if blind_state == "NAVIGATING":
                    self.cnt_cross_end += 1
                else:
                    self.cnt_cross_end = max(0, self.cnt_cross_end - 1)
                if self.cnt_cross_end >= self.FRAMES_NEXT_BLIND_OK and not in_cooldown:
                    self.state = BLINDPATH_NAV
                    self.cooldown_until = now + self.COOLDOWN_SEC
                    say = "方向正确，请继续前进。"

                # 【移除】所有可视化干扰
                # _draw_badge(ann, f"STATE: {self.state}", (10, 28), fg="white", bg="green")
                # _draw_state_panel(ann, {
                #     "盲道状态": blind_state,
                #     "回归计数": self.cnt_cross_end
                # }, pos=(10, 60))
                # _draw_progress_bar(ann, max(0.0, min(1.0, self.cnt_cross_end / max(1, self.FRAMES_NEXT_BLIND_OK))), pos=(10, 120), size=(200, 10), color="green")
                # _draw_frame_border(ann, color=_color_bgr("green"), thickness=3)

            # —— 恢复态：一旦盲道恢复可用则回盲道
            elif self.state == RECOVERY:
                if blind_state in ("ONBOARDING", "NAVIGATING"):
                    self.state = BLINDPATH_NAV
                    self.cooldown_until = now + self.COOLDOWN_SEC
                    say = ""
                else:
                    say = ""
                # 【移除】所有可视化干扰
                # _draw_badge(ann, f"STATE: {self.state}", (10, 28), fg="white", bg="red")
                # _draw_state_panel(ann, {
                #     "提示": "请缓慢环顾/抬头/降低手机角度",
                #     "丢失计数": self.cnt_lost
                # }, pos=(10, 60))
                # _draw_frame_border(ann, color=_color_bgr("red"), thickness=3)

            # 丢失计数（兜底）
            if blind_state == "UNKNOWN" and cross_stage == "not_detected":
                self.cnt_lost += 1
            else:
                self.cnt_lost = max(0, self.cnt_lost - 2)
            if self.cnt_lost >= self.FRAMES_LOST_MAX and self.state != RECOVERY:
                self.prev_target_state = self.state
                self.state = RECOVERY
                self.cooldown_until = now + self.COOLDOWN_SEC
                say = "环境复杂，进入恢复模式。"

            # 【移除】冷却进度条
            # if in_cooldown:
            #     remain = max(0.0, self.cooldown_until - now)
            #     ratio = 1.0 - min(1.0, remain / self.COOLDOWN_SEC)
            #     _draw_progress_bar(ann, ratio, pos=(10, 140), size=(160, 8), color="gray")

            return OrchestratorResult(ann, self._say(now, say), self.state, {"source": "blind", "cross_stage": cross_stage, "blind_state": blind_state})

        if self.state == WAIT_TRAFFIC_LIGHT:
            ann = bgr.copy()
            # 红绿灯识别（多数表决+冷却）
            color, meta = self.tld.detect(bgr)
            self.tl_major.push(color)
            major = self.tl_major.majority()
            self.tl_last_color = major

            # 【移除】所有可视化干扰
            # _draw_badge(ann, f"STATE: {self.state}", (10, 28), fg="white", bg="magenta")
            # self._draw_tl_status(ann, major, meta)
            # _draw_state_panel(ann, {
            #     "提示": "请等待绿灯或语音确认"立即通过"",
            #     "冷却": f"{max(0.0, self.cooldown_until - now):.1f}s"
            # }, pos=(10, 80))
            # _draw_frame_border(ann, color=_color_bgr("magenta"), thickness=3)

            say = ""
            if major == "green" and not in_cooldown:
                self.state = CROSSING
                self.cooldown_until = now + self.COOLDOWN_SEC
                say = "绿灯稳定，开始通行。"
            else:
                # 只在刚进入状态或每隔一段时间才播报
                if not hasattr(self, '_last_wait_light_announce'):
                    self._last_wait_light_announce = 0
                if now - self._last_wait_light_announce > 5.0:  # 5秒播报一次
                    say = "正在等待绿灯…"
                    self._last_wait_light_announce = now



            # 【移除】冷却进度
            # if in_cooldown:
            #     remain = max(0.0, self.cooldown_until - now)
            #     ratio = 1.0 - min(1.0, remain / self.COOLDOWN_SEC)
            #     _draw_progress_bar(ann, ratio, pos=(10, 140), size=(160, 8), color="gray")

            return OrchestratorResult(ann, self._say(now, say), self.state, {"traffic_light": major})

        if self.state == CROSSING:
            try:
                cres: CrossResult = self.cross.process_frame(bgr)
            except Exception as e:
                # 异常 → 恢复
                self.state = RECOVERY
                ann_err = bgr.copy()
                # 【移除】所有可视化干扰
                # _draw_badge(ann_err, "CROSS ERROR", (10, 28), fg="white", bg="red")
                # _put_text(ann_err, str(e), (10, 56), color=(255,255,255), scale=0.55)
                return OrchestratorResult(ann_err, self._say(now, ""), self.state, {"error": str(e)})

            ann = cres.annotated_image if cres.annotated_image is not None else bgr.copy()
            say = cres.guidance_text or ""

            # 新增：检查是否检测到盲道
            blind_path_detected = getattr(cres, 'blind_path_detected', False)
            blind_path_guidance = getattr(cres, 'blind_path_guidance', "")
            
            # 如果检测到盲道且需要引导，优先处理盲道引导
            if blind_path_detected and blind_path_guidance:
                # 如果应该切换到盲道导航（盲道很近），直接切换状态
                if hasattr(cres, "should_switch_to_blindpath") and cres.should_switch_to_blindpath:
                    if not in_cooldown:
                        self.state = BLINDPATH_NAV
                        self.cooldown_until = now + self.COOLDOWN_SEC
                        say = "已到盲道跟前，切换到盲道导航。"  # 使用现有语音文件
                        self.cnt_cross_end = 0  # 重置计数器
                        # 重置盲道导航器状态
                        if hasattr(self.blind, 'reset'):
                            self.blind.reset()
                else:
                    # 盲道较远，继续过马路但给出盲道引导
                    # say 已经在 cres.guidance_text 中包含了盲道引导信息
                    pass

            # 原有的结束条件：连续多帧"寻找斑马线"
            end_hint = False
            if "寻找斑马线" in (say or ""):
                end_hint = True
            # 注意：不再单纯因为 should_switch_to_blindpath 就结束过马路
            # if hasattr(cres, "should_switch_to_blindpath") and cres.should_switch_to_blindpath:
            #     end_hint = True

            self.cnt_cross_end = self.cnt_cross_end + 1 if end_hint else max(0, self.cnt_cross_end - 1)

            if self.cnt_cross_end >= self.FRAMES_CROSS_END and not in_cooldown:
                self.state = SEEKING_NEXT_BLINDPATH
                self.cooldown_until = now + self.COOLDOWN_SEC
                say = "过马路结束，准备上人行道。"

            # 【移除】所有可视化干扰
            # _draw_badge(ann, f"STATE: {self.state}", (10, 28), fg="white", bg="cyan")
            # _draw_state_panel(ann, {
            #     "结束计数": self.cnt_cross_end,
            #     "冷却": f"{max(0.0, self.cooldown_until - now):.1f}s"
            # }, pos=(10, 60))
            # _draw_progress_bar(ann, max(0.0, min(1.0, self.cnt_cross_end / max(1, self.FRAMES_CROSS_END))), pos=(10, 120), size=(220, 10), color="cyan")
            # _draw_frame_border(ann, color=_color_bgr("cyan"), thickness=3)
            # if in_cooldown:
            #     remain = max(0.0, self.cooldown_until - now)
            #     ratio = 1.0 - min(1.0, remain / self.COOLDOWN_SEC)
            #     _draw_progress_bar(ann, ratio, pos=(10, 140), size=(160, 8), color="gray")

            return OrchestratorResult(ann, self._say(now, say), self.state, {"source": "cross", "end_cnt": self.cnt_cross_end})

        # 兜底
        ann = bgr.copy()
        # 【移除】所有可视化干扰
        # _draw_badge(ann, f"STATE: {self.state}", (10, 28), fg="white", bg="gray")
        # _draw_frame_border(ann, color=_color_bgr("gray"), thickness=2)
        return OrchestratorResult(ann, "", self.state, {})


