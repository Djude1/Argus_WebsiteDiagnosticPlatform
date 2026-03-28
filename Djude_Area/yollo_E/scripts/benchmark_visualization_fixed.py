#!/usr/bin/env python3
# ============================================
# Visualization 效能測試腳本
# ============================================
"""
測試 visualization.py 的效能優化效果：
1. 字體快取
2. 批次繪製中文
"""

import sys
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np
import cv2

# 添加 src 到路徑
_src_path = Path(__file__).resolve().parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

# 測試資料結構
@dataclass
class BoundingBox:
    x1: float
    y1: float
    x2: float
    y2: float
    def to_tuple(self) -> tuple:
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
    def count(self) -> int:
        return len(self.detections)


# 測試用物品列表
ITEMS = [
    ("cell phone", "手機"),
    ("bottle", "水瓶"),
    ("cup", "杯子"),
    ("backpack", "背包"),
    ("handbag", "手提包"),
    ("remote", "遙控器"),
    ("keyboard", "鍵盤"),
    ("mouse", "滑鼠"),
    ("laptop", "筆電"),
    ("wallet", "錢包"),
]


def create_mock_detections(num_detections=5, frame_width=640, frame_height=480):
    """建立模擬偵測結果"""
    detections = []
    
    for i in range(num_detections):
        item_idx = i % len(ITEMS)
        class_name, class_name_cn = ITEMS[item_idx]
        
        box_width = np.random.randint(50, 150)
        box_height = np.random.randint(50, 150)
        x1 = np.random.randint(0, frame_width - box_width)
        y1 = np.random.randint(50, frame_height - box_height)
        x2 = x1 + box_width
        y2 = y1 + box_height
        
        bbox = BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2)
        confidence = np.random.uniform(0.5, 0.99)
        detection = DetectionResult(
            bbox=bbox, confidence=confidence, class_id=i,
            class_name=class_name, class_name_cn=class_name_cn
        )
        detections.append(detection)
    
    return FrameDetectionResult(
        detections=detections,
        inference_time_ms=30.0,
        fps=30.0,
        frame_shape=(frame_height, frame_width, 3)
    )


# 未優化版本
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont
import os
import platform


def get_font_path():
    """取得中文字體路徑"""
    if platform.system() == "Windows":
        for p in ["C:/Windows/Fonts/msjh.ttc", "C:/Windows/Fonts/msyh.ttc"]:
            if os.path.exists(p):
                return p
    return None


def draw_unoptimized(image, result, font_size=20):
    """未優化版本：每個文字都單獨做 BGR<->RGB 轉換"""
    output = image.copy()
    font_path = get_font_path()
    
    for det in result.detections:
        x1, y1, x2, y2 = det.bbox.to_tuple()
        np.random.seed(det.class_id * 123)
        color = tuple(map(int, np.random.randint(0, 255, 3)))
        cv2.rectangle(output, (x1, y1), (x2, y2), color, 2)
        
        label = f"{det.class_name_cn} {det.confidence:.2f}" if det.class_name_cn else f"{det.class_name} {det.confidence:.2f}"
        
        if font_path:
            # 每次都重新載入字體
            font = ImageFont.truetype(font_path, font_size)
            
            # 計算文字大小
            dummy = PILImage.new("RGB", (1, 1))
            d = ImageDraw.Draw(dummy)
            bbox = d.textbbox((0, 0), label, font=font)
            tw, th = int(bbox[2] - bbox[0]), int(bbox[3] - bbox[1])
            
            # 繪製標籤背景
            cv2.rectangle(output, (x1, y1 - th - 10), (x1 + tw + 5, y1), color, -1)
            
            # 每個文字都單獨做 BGR<->RGB 轉換（未優化）
            rgb = cv2.cvtColor(output, cv2.COLOR_BGR2RGB)
            pil = PILImage.fromarray(rgb)
            draw = ImageDraw.Draw(pil)
            draw.text((x1 + 2, y1 - th - 7), label, font=font, fill=(255, 255, 255))
            output = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    
    return output


# 優化版本 - 直接使用 visualization.py 的函數
from utils.visualization import draw_detections as draw_optimized


def benchmark(iterations=100, num_dets=5):
    """效能測試"""
    print(f"測試: {iterations} 次迭代, {num_dets} 個偵測物件")
    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    result = create_mock_detections(num_dets)
    
    # 未優化版本
    t0 = time.perf_counter()
    for _ in range(iterations):
        _ = draw_unoptimized(frame, result)
    t1 = time.perf_counter()
    unopt_time = (t1 - t0) / iterations * 1000
    
    # 優化版本
    t0 = time.perf_counter()
    for _ in range(iterations):
        _ = draw_optimized(frame, result, show_label_cn=True)
    t1 = time.perf_counter()
    opt_time = (t1 - t0) / iterations * 1000
    
    speedup = unopt_time / opt_time
    fps_unopt = 1000 / unopt_time
    fps_opt = 1000 / opt_time
    
    improvement = fps_opt - fps_unopt
    
    
    print(f"未優化: {unopt_time:.3f} ms ({fps_unopt:.1f} FPS)")
    print(f"優化:   {opt_time:.3f} ms ({fps_opt:.1f} FPS)")
    print(f"加速:   {speedup:.2f}x")
    print(f"FPS 提升: +{improvement:.1f}")
    
    return {
        "unopt_time": unopt_time,
        "opt_time": opt_time,
        "speedup": speedup,
        "improvement": improvement,
    }


def main():
    print("="*60)
    print("Visualization 效能優化驗證測試")
    print("="*60)
    print("
優化項目:")
    print("  1. 字體快取 - 避免每次繪製都重新載入字體")
    print("  2. 批次繪製中文 - 只做一次 BGR<->RGB 轉換")
    print("="*60)
    
    # 主要測試
    print("
[主要測試] 5 個偵測物件")
    result = benchmark(100, 5)
    
    # 不同數量測試
    print("
[不同偵測數量測試]")
    for n in [1, 3, 5, 10, 15]:
        result = benchmark(50, n)
        print(f"  {n} 個: {result["unopt_time"]:.2f}ms -> {result["opt_time"]:.2f}ms ({result["speedup"]:.2f}x)")
    
    # 儲存測試圖片
    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    result = create_mock_detections(5)
    output = draw_optimized(frame, result, show_label_cn=True)
    
    out_dir = Path(__file__).parent.parent / "data" / "benchmark"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "viz_benchmark.jpg"
    cv2.imwrite(str(out_path), output)
    print(f"
測試圖片: {out_path}")
    
    if result["speedup"] > 1.1:
        print(f"
✅ 優化有效！加速 {result["speedup"]:.2f}x")
    else:
        print(f"
⚠️ 加速 {result["speedup"]:.2f}x")
    
    print("
"*60)
    print("測試完成！ 請執行: python scripts/benchmark_visualization.py")
    print("="*60)


if __name__ == "__main__":
    main()

