# ============================================
# 類別名稱對應表
# ============================================
"""
COCO 類別名稱中英文對應
支援日常物品辨識
"""

from typing import Dict, Optional, List, Any


# ============================================
# COCO 80 類別中英文對照表
# ============================================

COCO_LABELS_CN: Dict[int, str] = {
    0: "人",
    1: "自行車",
    2: "汽車",
    3: "機車",
    4: "飛機",
    5: "公車",
    6: "火車",
    7: "卡車",
    8: "船",
    9: "紅綠燈",
    10: "消防栓",
    11: "停止標誌",
    12: "停車計時器",
    13: "長椅",
    14: "鳥",
    15: "貓",
    16: "狗",
    17: "馬",
    18: "羊",
    19: "牛",
    20: "大象",
    21: "熊",
    22: "斑馬",
    23: "長頸鹿",
    24: "背包",
    25: "雨傘",
    26: "手提包",  # 可用於錢包
    27: "領帶",
    28: "行李箱",
    29: "飛盤",
    30: "滑雪板",
    31: "滑雪板",
    32: "運動球",
    33: "風箏",
    34: "棒球棒",
    35: "棒球手套",
    36: "滑板",
    37: "衝浪板",
    38: "網球拍",
    39: "瓶子",  # 可用於水瓶、可樂
    40: "紅酒杯",
    41: "杯子",  # 可用於可樂罐
    42: "叉子",
    43: "刀子",
    44: "湯匙",
    45: "碗",
    46: "香蕉",
    47: "蘋果",
    48: "三明治",
    49: "柳橙",
    50: "花椰菜",
    51: "胡蘿蔔",
    52: "熱狗",
    53: "披薩",
    54: "甜甜圈",
    55: "蛋糕",
    56: "椅子",
    57: "沙發",
    58: "盆栽",
    59: "床",
    60: "餐桌",
    61: "廁所",
    62: "電視",
    63: "筆記型電腦",
    64: "滑鼠",
    65: "遙控器",
    66: "鍵盤",
    67: "手機",  # ✅ 手機
    68: "微波爐",
    69: "烤箱",
    70: "烤麵包機",
    71: "洗手台",
    72: "冰箱",
    73: "書",
    74: "時鐘",
    75: "花瓶",
    76: "剪刀",
    77: "泰迪熊",
    78: "吹風機",
    79: "牙刷",
}

# ============================================
# 日常物品類別映射 (COCO 類別對應)
# ============================================

DAILY_ITEMS_MAPPING: Dict[str, List[str]] = {
    # 目標物品 -> COCO 類別名稱列表
    "手機": ["cell phone"],
    "水瓶": ["bottle"],
    "可樂": ["bottle", "cup"],
    "錢包": ["handbag", "backpack", "suitcase"],
    "背包": ["backpack"],
    "鑰匙": [],  # COCO 沒有，需自定義訓練
    "台灣紙鈔": [],  # 需自定義訓練
    "書": ["book"],
    "剪刀": ["scissors"],
    "時鐘": ["clock"],
    "杯子": ["cup", "bottle"],
    "碗": ["bowl"],
    "叉子": ["fork"],
    "湯匙": ["spoon"],
    "遙控器": ["remote"],
    "鍵盤": ["keyboard"],
    "滑鼠": ["mouse"],
    "筆電": ["laptop"],
    "電視": ["tv"],
}

# ============================================
# 英文名稱到中文名稱映射 (用於 YOLOE 開放詞彙)
# ============================================

EN_TO_CN_MAPPING: Dict[str, str] = {
    # COCO 80 類別
    "person": "人",
    "bicycle": "自行車",
    "car": "汽車",
    "motorcycle": "機車",
    "airplane": "飛機",
    "bus": "公車",
    "train": "火車",
    "truck": "卡車",
    "boat": "船",
    "traffic light": "紅綠燈",
    "fire hydrant": "消防栓",
    "stop sign": "停止標誌",
    "parking meter": "停車計時器",
    "bench": "長椅",
    "bird": "鳥",
    "cat": "貓",
    "dog": "狗",
    "horse": "馬",
    "sheep": "羊",
    "cow": "牛",
    "elephant": "大象",
    "bear": "熊",
    "zebra": "斑馬",
    "giraffe": "長頸鹿",
    "backpack": "背包",
    "umbrella": "雨傘",
    "handbag": "手提包",
    "tie": "領帶",
    "suitcase": "行李箱",
    "frisbee": "飛盤",
    "skis": "滑雪板",
    "snowboard": "滑雪板",
    "sports ball": "運動球",
    "kite": "風箏",
    "baseball bat": "棒球棒",
    "baseball glove": "棒球手套",
    "skateboard": "滑板",
    "surfboard": "衝浪板",
    "tennis racket": "網球拍",
    "bottle": "瓶子",
    "wine glass": "紅酒杯",
    "cup": "杯子",
    "fork": "叉子",
    "knife": "刀子",
    "spoon": "湯匙",
    "bowl": "碗",
    "banana": "香蕉",
    "apple": "蘋果",
    "sandwich": "三明治",
    "orange": "柳橙",
    "broccoli": "花椰菜",
    "carrot": "胡蘿蔔",
    "hot dog": "熱狗",
    "pizza": "披薩",
    "donut": "甜甜圈",
    "cake": "蛋糕",
    "chair": "椅子",
    "couch": "沙發",
    "potted plant": "盆栽",
    "bed": "床",
    "dining table": "餐桌",
    "toilet": "廁所",
    "tv": "電視",
    "laptop": "筆記型電腦",
    "mouse": "滑鼠",
    "remote": "遙控器",
    "keyboard": "鍵盤",
    "cell phone": "手機",
    "microwave": "微波爐",
    "oven": "烤箱",
    "toaster": "烤麵包機",
    "sink": "洗手台",
    "refrigerator": "冰箱",
    "book": "書",
    "clock": "時鐘",
    "vase": "花瓶",
    "scissors": "剪刀",
    "teddy bear": "泰迪熊",
    "hair drier": "吹風機",
    "toothbrush": "牙刷",
    # 常見變體
    "wallet": "錢包",
    "keys": "鑰匙",
}

# ============================================
# 中文名稱到英文名稱映射 (用於用戶輸入轉換)
# ============================================

CN_TO_EN_MAPPING: Dict[str, str] = {
    # 基礎類別
    "人": "person",
    "自行車": "bicycle",
    "汽車": "car",
    "機車": "motorcycle",
    "飛機": "airplane",
    "公車": "bus",
    "火車": "train",
    "卡車": "truck",
    "船": "boat",
    "紅綠燈": "traffic light",
    "消防栓": "fire hydrant",
    "停止標誌": "stop sign",
    "停車計時器": "parking meter",
    "長椅": "bench",
    "鳥": "bird",
    "貓": "cat",
    "狗": "dog",
    "馬": "horse",
    "羊": "sheep",
    "牛": "cow",
    "大象": "elephant",
    "熊": "bear",
    "斑馬": "zebra",
    "長頸鹿": "giraffe",
    "背包": "backpack",
    "雨傘": "umbrella",
    "手提包": "handbag",
    "領帶": "tie",
    "行李箱": "suitcase",
    "飛盤": "frisbee",
    "滑雪板": "snowboard",
    "運動球": "sports ball",
    "風箏": "kite",
    "棒球棒": "baseball bat",
    "棒球手套": "baseball glove",
    "滑板": "skateboard",
    "衝浪板": "surfboard",
    "網球拍": "tennis racket",
    "瓶子": "bottle",
    "紅酒杯": "wine glass",
    "杯子": "cup",
    "叉子": "fork",
    "刀子": "knife",
    "湯匙": "spoon",
    "碗": "bowl",
    "香蕉": "banana",
    "蘋果": "apple",
    "三明治": "sandwich",
    "柳橙": "orange",
    "花椰菜": "broccoli",
    "胡蘿蔔": "carrot",
    "熱狗": "hot dog",
    "披薩": "pizza",
    "甜甜圈": "donut",
    "蛋糕": "cake",
    "椅子": "chair",
    "沙發": "couch",
    "盆栽": "potted plant",
    "床": "bed",
    "餐桌": "dining table",
    "廁所": "toilet",
    "電視": "tv",
    "筆記型電腦": "laptop",
    "滑鼠": "mouse",
    "遙控器": "remote",
    "鍵盤": "keyboard",
    "手機": "phone",
    "微波爐": "microwave",
    "烤箱": "oven",
    "烤麵包機": "toaster",
    "洗手台": "sink",
    "冰箱": "refrigerator",
    "書": "book",
    "時鐘": "clock",
    "花瓶": "vase",
    "剪刀": "scissors",
    "泰迪熊": "teddy bear",
    "吹風機": "hair drier",
    "牙刷": "toothbrush",
    "錢包": "wallet",
    "鑰匙": "keys",
    # 自定義物品（台灣常用）
    "悠遊卡": "easy card",
    "健保卡": "health insurance card",
    "身分證": "id card",
    "信用卡": "credit card",
    "皮夾": "wallet",
    "零錢包": "coin purse",
    "眼鏡": "glasses",
    "手錶": "watch",
    "鑰匙圈": "keychain",
    "水瓶": "water bottle",
    "瓶裝水": "bottled water",
    "筆電": "laptop",
}

# ============================================
# 自定義類別 (需訓練)
# ============================================

CUSTOM_CLASSES: Dict[int, str] = {
    # 預留給自定義類別 (從 80 開始)
    80: "鑰匙",
    81: "100元紙鈔",
    82: "200元紙鈔",
    83: "500元紙鈔",
    84: "1000元紙鈔",
    85: "2000元紙鈔",
    86: "錢包",
    87: "鑰匙圈",
    88: "悠遊卡",
    89: "健保卡",
    90: "身分證",
    91: "信用卡",
    92: "皮夾",
    93: "零錢包",
    94: "眼鏡",
    95: "手錶",
}

# ============================================
# 類別分組
# ============================================

CATEGORY_GROUPS: Dict[str, List[int]] = {
    "貴重物品": [67, 26, 24, 28, 80, 86, 87, 88, 89, 90, 91, 92, 93],  # 手機、包包、鑰匙、證件
    "飲料容器": [39, 40, 41, 45],  # 瓶子、杯子、碗
    "電子產品": [62, 63, 64, 65, 66, 67],  # 電視、筆電、滑鼠、遙控器、鍵盤、手機
    "紙鈔": [81, 82, 83, 84, 85],  # 台灣紙鈔
    "餐具": [42, 43, 44, 45],  # 叉子、刀子、湯匙、碗
    "食物": [46, 47, 48, 49, 50, 51, 52, 53, 54, 55],  # 各種食物
}


class LabelMapper:
    """類別名稱對應器"""

    def __init__(self, include_custom: bool = True):
        """
        初始化對應器

        參數:
            include_custom: 是否包含自定義類別
        """
        self.labels_cn = COCO_LABELS_CN.copy()

        if include_custom:
            self.labels_cn.update(CUSTOM_CLASSES)

    def get_chinese_name(self, class_id: int, default: str = "") -> str:
        """取得類別中文名稱"""
        return self.labels_cn.get(class_id, default)

    def get_chinese_name_from_en(self, class_name_en: str) -> str:
        """從英文名稱取得中文名稱"""
        # 直接查找英文到中文映射表
        class_name_lower = class_name_en.lower().strip()
        if class_name_lower in EN_TO_CN_MAPPING:
            return EN_TO_CN_MAPPING[class_name_lower]

        # 嘗試部分匹配（處理 "cell phone" vs "cellphone" 等變體）
        for en_name, cn_name in EN_TO_CN_MAPPING.items():
            if class_name_lower in en_name or en_name in class_name_lower:
                return cn_name

        # 檢查自定義類別
        for cid, cname in CUSTOM_CLASSES.items():
            if class_name_en.lower() in cname.lower():
                return cname

        return class_name_en

    def get_english_name_from_cn(self, class_name_cn: str) -> str:
        """
        從中文名稱取得英文名稱

        參數:
            class_name_cn: 中文類別名稱（如 "手機", "瓶子"）

        回傳:
            英文名稱，如果找不到則返回原中文名稱
        """
        # 直接查找中文到英文映射表
        if class_name_cn in CN_TO_EN_MAPPING:
            return CN_TO_EN_MAPPING[class_name_cn]

        # 嘗試部分匹配
        for cn_name, en_name in CN_TO_EN_MAPPING.items():
            if class_name_cn in cn_name or cn_name in class_name_cn:
                return en_name

        # 嘗試從英文到中文映射表反向查找
        for en_name, cn_name in EN_TO_CN_MAPPING.items():
            if class_name_cn == cn_name or class_name_cn in cn_name:
                return en_name

        return class_name_cn

    def get_category(self, class_id: int) -> Optional[str]:
        """取得類別所屬分類"""
        for category, class_ids in CATEGORY_GROUPS.items():
            if class_id in class_ids:
                return category
        return None

    def is_valuable(self, class_id: int) -> bool:
        """判斷是否為貴重物品"""
        return class_id in CATEGORY_GROUPS.get("貴重物品", [])

    def is_currency(self, class_id: int) -> bool:
        """判斷是否為紙鈔"""
        return class_id in CATEGORY_GROUPS.get("紙鈔", [])

    def get_all_labels(self) -> Dict[int, str]:
        """取得所有標籤"""
        return self.labels_cn.copy()

    def search(self, keyword: str) -> List[Dict[str, Any]]:
        """搜尋類別"""
        results = []
        keyword_lower = keyword.lower()

        for class_id, name_cn in self.labels_cn.items():
            if keyword_lower in name_cn.lower():
                results.append(
                    {
                        "class_id": class_id,
                        "name_cn": name_cn,
                        "category": self.get_category(class_id),
                        "is_valuable": self.is_valuable(class_id),
                    }
                )

        return results


# ============================================
# 便捷函式
# ============================================


def get_chinese_label(class_id: int) -> str:
    """取得類別中文名稱 (便捷函式)"""
    return COCO_LABELS_CN.get(class_id, f"class_{class_id}")


def get_label_mapper() -> LabelMapper:
    """取得標籤對應器實例"""
    return LabelMapper()


# ============================================
# 測試程式
# ============================================

if __name__ == "__main__":
    print("=" * 50)
    print("類別名稱對應測試")
    print("=" * 50)

    mapper = LabelMapper()

    # 測試常用類別
    test_ids = [67, 39, 26, 0]  # 手機、瓶子、手提包、人

    print("\n常用類別測試:")
    for class_id in test_ids:
        name_cn = mapper.get_chinese_name(class_id)
        category = mapper.get_category(class_id)
        is_valuable = mapper.is_valuable(class_id)
        print(f"  ID {class_id}: {name_cn}")
        print(f"    分類: {category}")
        print(f"    貴重物品: {'是' if is_valuable else '否'}")

    # 搜尋測試
    print("\n搜尋測試 (關鍵字: '機'):")
    results = mapper.search("機")
    for r in results:
        print(f"  {r['class_id']}: {r['name_cn']}")

    print("\n自定義類別 (需訓練):")
    for class_id, name in CUSTOM_CLASSES.items():
        print(f"  {class_id}: {name}")
