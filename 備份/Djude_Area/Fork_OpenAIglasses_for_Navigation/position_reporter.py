# position_reporter.py
# 方位報告模組：將畫面座標轉換為時鐘方向或前後左右
# 所有與位置播報相關的功能都在此統一管理

import math


def bbox_center_to_clock(cx: float, cy: float, frame_w: int, frame_h: int) -> str:
    """
    將物件中心像素座標轉換為時鐘方向
    cx, cy : 物件中心（像素）
    frame_w, frame_h : 畫面寬高
    回傳範例 : "3點鐘方向"、"12點鐘方向"
    """
    dx = cx - frame_w / 2   # 正 = 右
    dy = cy - frame_h / 2   # 正 = 下（螢幕座標 y 向下）

    # atan2(dx, -dy)：以正上方（12點）為 0°，順時針增加
    angle = math.degrees(math.atan2(dx, -dy)) % 360
    hour = round(angle / 30) % 12
    if hour == 0:
        hour = 12
    return f"{hour}點鐘方向"


def bbox_center_to_cardinal(cx: float, cy: float, frame_w: int, frame_h: int) -> str:
    """
    將物件中心轉換為前後左右方位描述
    適合習慣方向性語言的使用者
    """
    dx = (cx - frame_w / 2) / (frame_w / 2)   # -1=最左, +1=最右

    if dx < -0.35:
        return "左側"
    elif dx < -0.15:
        return "左前方"
    elif dx > 0.35:
        return "右側"
    elif dx > 0.15:
        return "右前方"
    else:
        return "正前方"


def get_position_label(
    cx: float,
    cy: float,
    frame_w: int,
    frame_h: int,
    mode: str = "clock",
) -> str:
    """
    統一介面：根據 mode 回傳方位描述字串
    mode : "clock"    → 時鐘方向（預設）
           "cardinal" → 前後左右
    """
    if mode == "clock":
        return bbox_center_to_clock(cx, cy, frame_w, frame_h)
    return bbox_center_to_cardinal(cx, cy, frame_w, frame_h)


def estimate_distance(bbox_area: float, frame_area: float) -> str:
    """
    根據物件佔畫面比例估算距離
    """
    if frame_area <= 0:
        return ""
    ratio = bbox_area / frame_area
    if ratio > 0.25:
        return "，非常近"
    elif ratio > 0.08:
        return "，距離適中"
    elif ratio > 0.02:
        return "，距離較遠"
    else:
        return "，距離很遠"


def format_found_message(
    item_name: str,
    cx: float,
    cy: float,
    frame_w: int,
    frame_h: int,
    bbox_area: float = 0,
    mode: str = "clock",
) -> str:
    """
    組合完整的播報語句
    範例（clock）  : "找到醬油，在你的3點鐘方向，距離較遠"
    範例（cardinal）: "找到醬油，在你的左前方，距離較遠"
    """
    position = get_position_label(cx, cy, frame_w, frame_h, mode)
    distance = estimate_distance(bbox_area, frame_w * frame_h) if bbox_area > 0 else ""
    return f"找到{item_name}，在你的{position}{distance}"
