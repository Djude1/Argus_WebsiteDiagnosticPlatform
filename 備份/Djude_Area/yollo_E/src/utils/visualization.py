# ============================================
# 視覺化工具
# ============================================
"""
繪製偵測結果和視覺化
"""

import cv2
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import os
import platform

# PIL 用於繪製中文文字
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

# 支援直接執行和套件匯入兩種模式
try:
    from ..detection.yolo_detector import DetectionResult, FrameDetectionResult
except ImportError:
    from detection.yolo_detector import DetectionResult, FrameDetectionResult


# ============================================
# 中文字體設定（效能優化版）
# ============================================

# 全域字體快取 - 避免每次繪製都重新載入字體
_FONT_CACHE: Dict[int, ImageFont.FreeTypeFont] = {}


def _get_chinese_font_path() -> Optional[str]:
    """取得系統中可用的中文字體路徑"""
    system = platform.system()

    if system == "Windows":
        # Windows 常見中文字體
        font_paths = [
            "C:/Windows/Fonts/msjh.ttc",  # 微軟正黑體
            "C:/Windows/Fonts/msyh.ttc",  # 微軟雅黑
            "C:/Windows/Fonts/simhei.ttf",  # 黑體
            "C:/Windows/Fonts/simsun.ttc",  # 宋體
        ]
    elif system == "Darwin":  # macOS
        font_paths = [
            "/System/Library/Fonts/PingFang.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ]
    else:  # Linux
        font_paths = [
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        ]

    for path in font_paths:
        if os.path.exists(path):
            return path

    return None


# 預設中文字體路徑
_DEFAULT_CHINESE_FONT_PATH = _get_chinese_font_path()


def _get_cached_font(font_size: int, font_path: Optional[str] = None) -> ImageFont.FreeTypeFont:
    """
    取得快取的字體物件（避免重複載入）

    參數:
        font_size: 字體大小
        font_path: 字體路徑（可選）

    回傳:
        字體物件
    """
    # 使用路徑和大小作為快取鍵
    cache_key = hash((font_path, font_size))

    if cache_key not in _FONT_CACHE:
        if font_path and os.path.exists(font_path):
            try:
                _FONT_CACHE[cache_key] = ImageFont.truetype(font_path, font_size)
            except Exception:
                _FONT_CACHE[cache_key] = ImageFont.load_default()
        else:
            _FONT_CACHE[cache_key] = ImageFont.load_default()

    return _FONT_CACHE[cache_key]


def _contains_chinese(text: str) -> bool:
    """檢查字串是否包含中文字符"""
    for char in text:
        if "\u4e00" <= char <= "\u9fff":
            return True
    return False


def _draw_text_with_pil(
    image: np.ndarray,
    text: str,
    position: Tuple[int, int],
    font_size: int = 20,
    color: Tuple[int, int, int] = (255, 255, 255),
    font_path: Optional[str] = None,
) -> np.ndarray:
    """
    使用 PIL 繪製文字（支援中文）

    參數:
        image: OpenCV 影像 (BGR)
        text: 要繪製的文字
        position: 文字左上角位置 (x, y)
        font_size: 字體大小
        color: 文字顏色 (B, G, R)
        font_path: 字體檔案路徑，若為 None 則使用預設字體

    回傳:
        繪製後的影像 (BGR)
    """
    # BGR 轉 RGB
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    pil_image = PILImage.fromarray(image_rgb)

    draw = ImageDraw.Draw(pil_image)

    # 使用快取的字體（避免重複載入）
    font = _get_cached_font(font_size, font_path)

    # PIL 使用 RGB，所以需要反轉 BGR 到 RGB
    rgb_color = (color[2], color[1], color[0])

    # 繪製文字
    draw.text(position, text, font=font, fill=rgb_color)

    # RGB 轉回 BGR
    result = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

    return result


def _get_text_size_with_pil(
    text: str,
    font_size: int = 20,
    font_path: Optional[str] = None,
) -> Tuple[int, int]:
    """
    使用 PIL 計算文字大小

    參數:
        text: 文字內容
        font_size: 字體大小
        font_path: 字體檔案路徑

    回傳:
        (寬度, 高度)
    """
    # 使用快取的字體（避免重複載入）
    font = _get_cached_font(font_size, font_path)

    # 創建臨時影像來計算文字大小
    dummy_image = PILImage.new("RGB", (1, 1))
    draw = ImageDraw.Draw(dummy_image)
    bbox = draw.textbbox((0, 0), text, font=font)
    width = int(bbox[2] - bbox[0])
    height = int(bbox[3] - bbox[1])

    return width, height


# ============================================
# 批次中文文字繪製（效能優化）
# ============================================


def _draw_chinese_texts_batch(
    image: np.ndarray,
    texts: List[Tuple[str, Tuple[int, int], Tuple[int, int, int]]],
    font_size: int = 20,
    font_path: Optional[str] = None,
) -> np.ndarray:
    """
    批次繪製中文文字（只做一次 BGR↔RGB 轉換）

    參數:
        image: OpenCV 影像 (BGR)
        texts: 文字列表 [(文字, 位置, 顏色), ...]
        font_size: 字體大小
        font_path: 字體檔案路徑

    回傳:
        繪製後的影像 (BGR)
    """
    if not texts:
        return image

    # 只做一次 BGR→RGB 轉換
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    pil_image = PILImage.fromarray(image_rgb)
    draw = ImageDraw.Draw(pil_image)

    # 使用快取的字體
    font = _get_cached_font(font_size, font_path)

    # 批次繪製所有文字
    for text, position, color in texts:
        # BGR → RGB
        rgb_color = (color[2], color[1], color[0])
        draw.text(position, text, font=font, fill=rgb_color)

    # 只做一次 RGB→BGR 轉換
    result = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

    return result


# 顏色定義
COLORS = {
    "green": (0, 255, 0),
    "red": (0, 0, 255),
    "blue": (255, 0, 0),
    "yellow": (0, 255, 255),
    "cyan": (255, 255, 0),
    "magenta": (255, 0, 255),
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "orange": (0, 165, 255),
}


def get_color_for_class(class_id: int) -> Tuple[int, int, int]:
    """根據類別 ID 生成固定顏色"""
    np.random.seed(class_id * 123)
    return tuple(map(int, np.random.randint(0, 255, 3)))


def draw_detections(
    image: np.ndarray,
    result: FrameDetectionResult,
    show_confidence: bool = True,
    show_label_cn: bool = True,
    box_thickness: int = 2,
    font_scale: float = 0.6,
    font_thickness: int = 1,
    custom_labels: Optional[Dict[str, str]] = None,
    chinese_font_size: int = 20,
) -> np.ndarray:
    """
    在影像上繪製偵測結果（效能優化版：批次繪製中文）

    參數:
        image: 輸入影像
        result: 偵測結果
        show_confidence: 是否顯示信心度
        show_label_cn: 是否顯示中文標籤
        box_thickness: 邊框粗細
        font_scale: 字體大小（用於英文）
        font_thickness: 字體粗細
        custom_labels: 自定義標籤對應表 {class_name: custom_label}
        chinese_font_size: 中文字體大小

    回傳:
        繪製後的影像
    """
    output = image.copy()

    # 收集需要用 PIL 繪製的中文文字（批次處理）
    chinese_texts: List[Tuple[str, Tuple[int, int], Tuple[int, int, int]]] = []

    # 第一階段：用 OpenCV 繪製所有邊界框、標籤背景和英文文字
    for detection in result.detections:
        # 取得邊界框座標
        x1, y1, x2, y2 = detection.bbox.to_tuple()

        # 根據類別選擇顏色
        color = get_color_for_class(detection.class_id)

        # 繪製邊界框
        cv2.rectangle(output, (x1, y1), (x2, y2), color, box_thickness)

        # 準備標籤文字 - 優先使用自定義標籤
        if custom_labels and detection.class_name in custom_labels:
            label = custom_labels[detection.class_name]
        elif show_label_cn and detection.class_name_cn:
            label = detection.class_name_cn
        else:
            label = detection.class_name

        if show_confidence:
            label += f" {detection.confidence:.2f}"

        # 檢查是否包含中文
        has_chinese = _contains_chinese(label)

        if has_chinese and _DEFAULT_CHINESE_FONT_PATH:
            # 使用 PIL 繪製中文文字 - 先計算大小並繪製背景
            text_width, text_height = _get_text_size_with_pil(
                label, chinese_font_size, _DEFAULT_CHINESE_FONT_PATH
            )

            # 繪製標籤背景
            cv2.rectangle(output, (x1, y1 - text_height - 10), (x1 + text_width + 5, y1), color, -1)

            # 收集中文文字，稍後批次繪製
            chinese_texts.append((label, (x1 + 2, y1 - text_height - 7), COLORS["white"]))
        else:
            # 使用 OpenCV 繪製英文文字
            (text_width, text_height), baseline = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness
            )

            # 繪製標籤背景
            cv2.rectangle(output, (x1, y1 - text_height - 10), (x1 + text_width, y1), color, -1)

            # 繪製標籤文字
            cv2.putText(
                output,
                label,
                (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                COLORS["white"],
                font_thickness,
            )

    # 第二階段：批次繪製所有中文文字（只做一次 BGR↔RGB 轉換）
    if chinese_texts:
        output = _draw_chinese_texts_batch(
            output,
            chinese_texts,
            font_size=chinese_font_size,
            font_path=_DEFAULT_CHINESE_FONT_PATH,
        )

    return output


def draw_fps(
    image: np.ndarray,
    fps: float,
    position: Tuple[int, int] = (10, 30),
    font_scale: float = 0.8,
    color: Tuple[int, int, int] = COLORS["green"],
    thickness: int = 2,
) -> np.ndarray:
    """
    在影像上繪製 FPS

    參數:
        image: 輸入影像
        fps: FPS 值
        position: 文字位置
        font_scale: 字體大小
        color: 文字顏色
        thickness: 文字粗細

    回傳:
        繪製後的影像
    """
    output = image.copy()

    text = f"FPS: {fps:.1f}"
    cv2.putText(output, text, position, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness)

    return output


def draw_info_panel(
    image: np.ndarray,
    info: dict,
    position: Tuple[int, int] = (10, 30),
    font_scale: float = 0.6,
    color: Tuple[int, int, int] = COLORS["green"],
    thickness: int = 2,
    line_spacing: int = 25,
) -> np.ndarray:
    """
    繪製資訊面板

    參數:
        image: 輸入影像
        info: 資訊字典
        position: 起始位置
        font_scale: 字體大小
        color: 文字顏色
        thickness: 文字粗細
        line_spacing: 行距

    回傳:
        繪製後的影像
    """
    output = image.copy()

    y = position[1]
    for key, value in info.items():
        text = f"{key}: {value}"
        cv2.putText(
            output, text, (position[0], y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness
        )
        y += line_spacing

    return output


def save_detection_image(
    image: np.ndarray, output_dir: str, prefix: str = "detection", suffix: str = ""
) -> str:
    """
    儲存偵測圖片

    參數:
        image: 輸入影像
        output_dir: 輸出目錄
        prefix: 檔名前綴
        suffix: 檔名後綴

    回傳:
        儲存的檔案路徑
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{prefix}_{timestamp}{suffix}.jpg"
    filepath = output_path / filename

    cv2.imwrite(str(filepath), image)

    return str(filepath)


def create_detection_grid(
    images: List[np.ndarray],
    grid_size: Tuple[int, int] = None,
    cell_size: Tuple[int, int] = (300, 300),
) -> np.ndarray:
    """
    建立偵測結果網格圖

    參數:
        images: 影像列表
        grid_size: 網格大小 (cols, rows)，若為 None 則自動計算
        cell_size: 每個格子的大小 (width, height)

    回傳:
        網格影像
    """
    if not images:
        return np.zeros((cell_size[1], cell_size[0], 3), dtype=np.uint8)

    # 計算網格大小
    n = len(images)
    if grid_size is None:
        cols = int(np.ceil(np.sqrt(n)))
        rows = int(np.ceil(n / cols))
    else:
        cols, rows = grid_size

    # 調整每張圖片大小
    resized_images = []
    for img in images:
        resized = cv2.resize(img, cell_size)
        resized_images.append(resized)

    # 填充空白圖片
    while len(resized_images) < cols * rows:
        blank = np.zeros((cell_size[1], cell_size[0], 3), dtype=np.uint8)
        resized_images.append(blank)

    # 建立網格
    rows_images = []
    for i in range(rows):
        row_images = resized_images[i * cols : (i + 1) * cols]
        row = np.hstack(row_images)
        rows_images.append(row)

    grid = np.vstack(rows_images)

    return grid


# ============================================
# 按鈕繪製
# ============================================


def draw_button(
    image: np.ndarray,
    text: str,
    position: Tuple[int, int] = (10, 60),
    size: Tuple[int, int] = (150, 40),
    bg_color: Tuple[int, int, int] = (70, 130, 180),
    text_color: Tuple[int, int, int] = (255, 255, 255),
    font_scale: float = 0.6,
    thickness: int = 2,
    is_active: bool = False,
) -> np.ndarray:
    """
    在影像上繪製按鈕

    參數:
        image: 輸入影像
        text: 按鈕文字
        position: 按鈕左上角位置 (x, y)
        size: 按鈕大小 (width, height)
        bg_color: 背景顏色 (B, G, R)
        text_color: 文字顏色 (B, G, R)
        font_scale: 字體大小
        thickness: 文字粗細
        is_active: 是否為啟用狀態（高亮）

    回傳:
        繪製後的影像
    """
    output = image.copy()
    x, y = position
    w, h = size

    # 啟用狀態時使用更亮的顏色
    if is_active:
        bg_color = (
            min(bg_color[0] + 50, 255),
            min(bg_color[1] + 50, 255),
            min(bg_color[2] + 50, 255),
        )

    # 繪製按鈕背景（圓角矩形效果）
    cv2.rectangle(output, (x, y), (x + w, y + h), bg_color, -1, cv2.LINE_AA)

    # 繪製邊框
    cv2.rectangle(output, (x, y), (x + w, y + h), (255, 255, 255), 2, cv2.LINE_AA)

    # 計算文字位置（置中）
    (text_width, text_height), baseline = cv2.getTextSize(
        text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
    )
    text_x = x + (w - text_width) // 2
    text_y = y + (h + text_height) // 2

    # 繪製按鈕文字
    cv2.putText(
        output,
        text,
        (text_x, text_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        text_color,
        thickness,
        cv2.LINE_AA,
    )

    return output


def draw_help_panel(
    image: np.ndarray,
    commands: List[Tuple[str, str]] = None,
    position: Tuple[int, int] = (10, 110),
    bg_color: Tuple[int, int, int] = (0, 0, 0),
    alpha: float = 0.6,
) -> np.ndarray:
    """
    繪製幫助面板（顯示快捷鍵說明）

    參數:
        image: 輸入影像
        commands: 指令列表 [(按鍵, 說明), ...]
        position: 面板左上角位置 (x, y)
        bg_color: 背景顏色 (B, G, R)
        alpha: 透明度 (0.0 - 1.0)

    回傳:
        繪製後的影像
    """
    if commands is None:
        commands = [
            ("Q", "Quit"),
            ("S", "Screenshot"),
            ("R", "Record"),
        ]

    output = image.copy()
    x, y = position

    # 計算面板大小
    max_key_width = 0
    max_desc_width = 0
    for key, desc in commands:
        key_size = cv2.getTextSize(key, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
        desc_size = cv2.getTextSize(desc, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
        max_key_width = max(max_key_width, key_size[0])
        max_desc_width = max(max_desc_width, desc_size[0])

    panel_width = max_key_width + max_desc_width + 40
    line_height = 25
    panel_height = len(commands) * line_height + 20

    # 建立半透明覆蓋層
    overlay = output.copy()
    cv2.rectangle(overlay, (x, y), (x + panel_width, y + panel_height), bg_color, -1)

    # 混合覆蓋層
    cv2.addWeighted(overlay, alpha, output, 1 - alpha, 0, output)

    # 繪製邊框
    cv2.rectangle(output, (x, y), (x + panel_width, y + panel_height), (255, 255, 255), 1)

    # 繪製文字
    current_y = y + 20
    for key, desc in commands:
        # 按鍵（黃色）
        cv2.putText(
            output,
            f"[{key}]",
            (x + 10, current_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            COLORS["yellow"],
            1,
            cv2.LINE_AA,
        )
        # 說明（白色）
        cv2.putText(
            output,
            desc,
            (x + 10 + max_key_width + 10, current_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            COLORS["white"],
            1,
            cv2.LINE_AA,
        )
        current_y += line_height

    return output


def draw_recording_indicator(
    image: np.ndarray,
    is_recording: bool = True,
    position: Tuple[int, int] = (10, 10),
) -> np.ndarray:
    """
    繪製記錄指示器

    參數:
        image: 輸入影像
        is_recording: 是否正在記錄
        position: 指示器位置 (x, y)

    回傳:
        繪製後的影像
    """
    output = image.copy()
    x, y = position

    if is_recording:
        # 繪製紅色圓點
        cv2.circle(output, (x + 10, y + 15), 8, (0, 0, 255), -1)
        # 繪製文字
        cv2.putText(
            output,
            "Recording",
            (x + 25, y + 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 255),
            1,
            cv2.LINE_AA,
        )

    return output
