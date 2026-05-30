#!/usr/bin/env python3
"""Visualization 效能測試腳本"""

import sys
import time
from pathlib import Path

# 添加 src 到路徑
_src_path = Path(__file__).resolve().parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

import numpy as np
import cv2
from dataclasses import dataclass, field
from typing import List

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont
import os
import platform


@dataclass
class BoundingBox:
    x1: float
    y1: float
    x2: float
    y2: float
    def to_tuple(self):
        return (int(self.x1), int(self.y1), int(self.x2), int(self.y2))


@dataclass
class DetectionResult:
    bbox: BoundingBox
    confidence: float
    class_id: int
    class_name: str
    class_name_cn: str = ""


@dataclass
class FrameDetectionResult:
    detections: List[DetectionResult] = field(default_factory=list)
    inference_time_ms: float = 0.0
    fps: float = 0.0
    frame_shape: tuple = (0, 0, 0)
    
    @property
    def count(self):
        return len(self.detections)


ITEMS = [
    ("cell phone", "手機"),
    ("bottle", "水瓶"),
    ("cup", "杯子"),
    ("backpack", "背包"),
    ("handbag", "手提包"),
    ("remote", "遙控器"),
    ("keyboard", "鍵盤"),
    ("mouse", "滑鼠"),
]


def create_mock(num_dets=5):
    detections = []
    for i in range(num_dets):
        item = ITEMS[i % len(ITEMS)]
        box_w = np.random.randint(50, 150)
        box_h = np.random.randint(50, 150)
        x1 = np.random.randint(0, 640 - box_w)
        y1 = np.random.randint(50, 480 - box_h)
        bbox = BoundingBox(x1=x1, y1=y1, x2=x1+box_w, y2=y1+box_h)
        conf = np.random.uniform(0.5, 0.99)
        det = DetectionResult(bbox=bbox, confidence=conf, class_id=i,
                              class_name=item[0], class_name_cn=item[1])
        detections.append(det)
    return FrameDetectionResult(detections=detections)


def get_font():
    if platform.system() == "Windows":
        for p in ["C:/Windows/Fonts/msjh.ttc", "C:/Windows/Fonts/msyh.ttc"]:
            if os.path.exists(p):
                return p
    return None


def draw_unopt(img, result):
    """未優化：每個文字單獨轉換"""
    out = img.copy()
    font_path = get_font()
    for det in result.detections:
        x1, y1, x2, y2 = det.bbox.to_tuple()
        np.random.seed(det.class_id * 123)
        color = tuple(map(int, np.random.randint(0, 255, 3)))
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        label = f"{det.class_name_cn} {det.confidence:.2f}"
        if font_path:
            font = ImageFont.truetype(font_path, 20)
            dummy = PILImage.new("RGB", (1, 1))
            d = ImageDraw.Draw(dummy)
            bb = d.textbbox((0, 0), label, font=font)
            tw, th = int(bb[2] - bb[0]), int(bb[3] - bb[1])
            cv2.rectangle(out, (x1, y1 - th - 10), (x1 + tw + 5, y1), color, -1)
            rgb = cv2.cvtColor(out, cv2.COLOR_BGR2RGB)
            pil = PILImage.fromarray(rgb)
            draw = ImageDraw.Draw(pil)
            draw.text((x1 + 2, y1 - th - 7), label, font=font, fill=(255, 255, 255))
            out = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    return out


# 優化版本
from utils.visualization import draw_detections as draw_opt


def bench(iters=100, num_dets=5):
    print(f"測試: {iters} 次, {num_dets} 偵測物件")
    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    result = create_mock(num_dets)
    
    t0 = time.perf_counter()
    for _ in range(iters):
        draw_unopt(frame, result)
    unopt = (time.perf_counter() - t0) / iters * 1000
    
    t0 = time.perf_counter()
    for _ in range(iters):
        draw_opt(frame, result, show_label_cn=True)
    opt = (time.perf_counter() - t0) / iters * 1000
    
    speedup = unopt / opt
    print(f"未優化: {unopt:.2f} ms")
    print(f"優化:   {opt:.2f} ms")
    print(f"加速:   {speedup:.2f}x")
    return unopt, opt, speedup


def main():
    print("="*50)
    print("Visualization 效能優化驗證")
    print("="*50)
    print("\n優化: 字體快取 + 批次繪製中文")
    print("-"*50)
    
    print("\n[主要測試] 5 偵測物件")
    _, _, sp = bench(100, 5)
    
    print("\n[不同偵測數量]")
    for n in [1, 3, 5, 10]:
        _, _, sp = bench(50, n)
    
    # 儲存圖片
    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    result = create_mock(5)
    output = draw_opt(frame, result, show_label_cn=True)
    out_dir = Path(__file__).parent.parent / "data" / "benchmark"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "viz_benchmark.jpg"
    cv2.imwrite(str(out_path), output)
    print(f"\n測試圖片: {out_path}")
    
    if sp > 1.1:
        print(f"\n✅ 優化有效! 加速 {sp:.2f}x")
    else:
        print(f"\n結果: 加速 {sp:.2f}x")


if __name__ == "__main__":
    main()
