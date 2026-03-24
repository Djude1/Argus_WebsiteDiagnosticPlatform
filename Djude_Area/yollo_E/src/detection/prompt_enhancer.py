# ============================================
# YOLOE 文字提示增強器
# ============================================
"""
利用 YOLOE 的 CLIP 開放詞彙特性，將簡短類別名稱
轉換為更精確的描述性提示，大幅提升日常物品辨識率。

原理：
  YOLOE 使用 CLIP 將文字提示轉為嵌入向量，再與影像特徵比對。
  更具體的描述可幫助 CLIP 區分外觀相似的物品，降低誤判。

範例：
  "mouse"        → "computer mouse device"     （避免與動物老鼠混淆）
  "remote"       → "TV remote control"         （更具體的遙控器描述）
  "bottle"       → "plastic drink bottle"      （更精確的瓶子描述）
"""

from typing import Dict, List, Optional, Tuple
from loguru import logger


# ============================================
# 增強提示對照表
# ============================================
# 格式：原始類別名 → 增強後的描述性提示
# 原則：
#   1. 增加材質、用途、外觀等具體描述
#   2. 消除歧義（如 mouse: 電腦滑鼠 vs 老鼠）
#   3. 加入常見場景關鍵字（日常、超市、便利商店）
#   4. 保持簡潔（CLIP 對 3-6 個詞效果最佳）

ENHANCED_PROMPTS: Dict[str, str] = {
    # ===== 個人隨身物品 =====
    "cell phone": "smartphone mobile phone device",
    "wallet": "leather wallet billfold",
    "keys": "metal keys keychain",
    "glasses": "eyeglasses spectacles",
    "watch": "wristwatch on wrist",
    "earphone": "wireless earbuds earphone",
    "headphone": "over-ear headphone headset",
    "pen": "writing pen ballpoint",
    "pencil": "wooden pencil for writing",
    "notebook": "paper notebook journal",
    "umbrella": "folding umbrella",
    "mask": "face mask surgical mask",
    "handbag": "woman handbag purse",
    "backpack": "school backpack bag",

    # ===== 電子產品 =====
    "laptop": "laptop computer notebook PC",
    "mouse": "computer mouse device",
    "keyboard": "computer keyboard typing",
    "remote": "TV remote control device",
    "charger": "phone charger cable adapter",
    "power bank": "portable power bank battery charger",
    "battery": "AA battery cell",

    # ===== 飲料容器 =====
    "bottle": "plastic drink bottle",
    "water bottle": "plastic water bottle",
    "cup": "drinking cup mug",
    "coffee cup": "paper coffee cup with lid",
    "can": "aluminum drink can",
    "soda can": "soda pop aluminum can",
    "beer can": "beer aluminum can",
    "juice box": "juice box carton with straw",
    "milk carton": "milk carton box",
    "tea bottle": "bottled tea drink",
    "wine glass": "wine glass stemware",
    "beer bottle": "glass beer bottle",
    "wine bottle": "glass wine bottle",
    "boba tea": "bubble tea boba drink cup",

    # ===== 零食 / 包裝食品 =====
    "snack bag": "sealed snack chip bag package",
    "chip bag": "potato chip bag package",
    "candy": "wrapped candy sweet",
    "chocolate bar": "chocolate candy bar wrapped",
    "chocolate": "chocolate bar candy",
    "gum": "chewing gum pack",
    "cookie": "baked cookie biscuit",
    "cracker": "soda cracker biscuit",
    "instant noodles": "instant noodle ramen package",
    "instant noodle cup": "cup noodle instant ramen",
    "cereal box": "cereal breakfast box",
    "popcorn": "popcorn bag bucket",
    "nuts": "mixed nuts snack bag",
    "dried fruit": "dried fruit snack bag",
    "jerky": "beef jerky dried meat snack",
    "bread": "sliced bread loaf",
    "bagel": "round bagel bread",
    "croissant": "flaky croissant pastry",
    "bun": "steamed bun baozi",

    # ===== 生鮮蔬果 =====
    "banana": "yellow banana fruit",
    "apple": "red apple fruit",
    "orange": "orange citrus fruit",
    "tomato": "red tomato vegetable",
    "potato": "brown potato vegetable",
    "onion": "round onion vegetable",
    "garlic": "garlic bulb clove",
    "pepper": "red green pepper chili",
    "cucumber": "green cucumber vegetable",
    "lettuce": "green lettuce salad leaf",
    "cabbage": "green cabbage head",
    "corn": "yellow corn cob",
    "mushroom": "mushroom fungus",
    "lemon": "yellow lemon citrus",
    "grape": "purple green grape bunch",
    "watermelon": "large green watermelon",
    "pineapple": "pineapple tropical fruit",
    "mango": "yellow mango fruit",
    "strawberry": "red strawberry fruit",
    "pear": "green pear fruit",
    "peach": "peach stone fruit",
    "egg": "chicken egg",
    "egg carton": "egg carton box container",

    # ===== 熟食 / 即食 =====
    "rice ball": "rice ball onigiri wrapped",
    "bento box": "bento box meal container",
    "sushi": "sushi roll Japanese food",
    "sandwich": "bread sandwich with filling",
    "pizza": "pizza pie slice",
    "donut": "glazed donut doughnut",
    "cake": "frosted cake dessert",
    "salad": "fresh green salad bowl",
    "ice cream": "ice cream cone scoop",
    "yogurt": "yogurt cup container",
    "cheese": "cheese block slice",

    # ===== 日用品 / 清潔用品 =====
    "tissue box": "tissue box paper dispenser",
    "tissue paper": "tissue paper napkin",
    "toilet paper": "toilet paper roll",
    "toothbrush": "toothbrush oral care",
    "toothpaste": "toothpaste tube",
    "soap": "bar soap hand soap",
    "shampoo": "shampoo bottle hair wash",
    "sunscreen": "sunscreen lotion bottle",
    "lotion": "lotion cream bottle",
    "detergent": "laundry detergent bottle",
    "dish soap": "dish soap liquid bottle",
    "medicine": "medicine pill bottle box",
    "bandage": "adhesive bandage band-aid",
    "hand sanitizer": "hand sanitizer gel bottle",

    # ===== 容器 / 包裝 =====
    "plastic bag": "plastic shopping bag",
    "paper bag": "brown paper bag",
    "shopping bag": "retail shopping bag",
    "bag": "carrying bag tote",
    "box": "cardboard box package",
    "cardboard box": "brown cardboard shipping box",
    "jar": "glass jar container",
    "container": "plastic food container",
    "tray": "food serving tray",
    "plate": "round dinner plate dish",
    "bowl": "round bowl dish",
    "basket": "woven basket container",

    # ===== 餐具 =====
    "fork": "metal eating fork utensil",
    "knife": "eating knife utensil",
    "spoon": "metal eating spoon utensil",
    "scissors": "cutting scissors tool",

    # ===== 家具 / 大型物品 =====
    "chair": "sitting chair seat",
    "couch": "sofa couch furniture",
    "dining table": "dining table desk surface",
    "tv": "television TV screen monitor",
    "refrigerator": "refrigerator fridge appliance",
    "microwave": "microwave oven appliance",
    "clock": "wall clock time display",
    "vase": "decorative flower vase",
    "potted plant": "potted plant houseplant",
    "book": "paper book textbook",

    # ===== 人物 / 動物 =====
    "person": "person human standing",

    # ===== 台灣在地物品 =====
    "coin": "metal coin currency",
    "banknote": "paper banknote money bill",
    "receipt": "printed receipt paper slip",
    "credit card": "plastic credit card",
    "id card": "identification ID card",
    "easy card": "EasyCard transit card",
    "health insurance card": "health insurance IC card",

    # ===== 便利商店 / 超市擴充 =====
    # 飲料類
    "sports drink": "sports drink bottle Pocari Sweat",
    "coffee bottle": "bottled coffee drink",
    "tea can": "canned tea drink",
    "soda bottle": "plastic soda bottle Coca Cola",
    "mineral water": "mineral water bottle clear",
    "flavored milk": "flavored milk drink bottle",
    "energy drink can": "energy drink can Red Bull",
    "yogurt drink": "yogurt drink bottle",
    "fruit juice": "fruit juice bottle drink",
    "soy milk": "soy milk drink carton bottle",
    "coconut water": "coconut water drink bottle",

    # 冰品 / 冷凍
    "ice cream bar": "ice cream bar popsicle stick",
    "ice cream cup": "ice cream cup container",
    "frozen dumplings": "frozen dumpling bag package",
    "frozen vegetables": "frozen vegetable bag",
    "frozen meat": "frozen meat package",

    # 調理包 / 即食
    "microwave meal": "microwave ready meal box",
    "curry rice": "curry rice meal package",
    "pasta sauce": "pasta sauce jar bottle",
    "canned food": "canned food tin can",
    "instant soup": "instant soup packet",

    # 零食 / 餅乾擴充
    "potato chips": "potato chips bag Lay's",
    "tortilla chips": "tortilla chips bag nachos",
    "pretzels": "pretzel snack bag",
    "rice cracker": "rice cracker snack bag senbei",
    "dried seaweed": "dried seaweed snack nori",
    "beef jerky": "beef jerky dried meat snack",
    "pork jerky": "pork jerky dried meat",
    "fish snack": "dried fish snack package",
    "cake slice": "cake slice pastry dessert",
    "pastry": "pastry baked good",
    "muffin": "muffin baked cake",
    "brownie": "brownie chocolate cake",
    "wafer": "wafer cookie snack",
    "biscuit": "biscuit cookie snack",
    "energy bar": "energy protein bar",

    # 調味料 / 醬料
    "soy sauce": "soy sauce bottle",
    "ketchup": "ketchup tomato sauce bottle",
    "mayonnaise": "mayonnaise sauce bottle jar",
    "mustard": "mustard sauce bottle",
    "hot sauce": "hot sauce chili bottle",
    "salad dressing": "salad dressing bottle",
    "cooking oil": "cooking oil bottle",
    "vinegar": "vinegar bottle condiment",
    "salt shaker": "salt shaker container",
    "pepper shaker": "pepper shaker container",
    "sugar packet": "sugar packet sweetener",

    # 沖泡飲品
    "instant coffee": "instant coffee packet jar",
    "tea bag": "tea bag packet",
    "hot chocolate": "hot chocolate powder packet",
    "oatmeal": "oatmeal cereal packet",

    # 生鮮擴充
    "pork": "pork meat package tray",
    "beef": "beef meat package tray",
    "seafood": "seafood fish shrimp package",
    "tofu package": "tofu package container",
    "tempeh": "tempeh fermented soybean",
    "green onion": "green onion scallion vegetable",
    "ginger": "ginger root vegetable",
    "cilantro": "cilantro herb vegetable",

    # 水果擴充
    "papaya": "papaya tropical fruit",
    "guava": "guava tropical fruit",
    "dragon fruit": "dragon fruit pitaya",
    "kiwi": "kiwi fruit fuzzy",
    "cherry": "cherry red fruit small",
    "blueberry": "blueberry small fruit",
    "avocado": "avocado green fruit",
    "coconut": "coconut brown fruit",

    # 乳製品
    "milk bottle": "milk bottle dairy",
    "cheese slice": "cheese slice dairy",
    "butter package": "butter package dairy",
    "cream cheese": "cream cheese package",

    # 個人護理
    "facial cleanser": "facial cleanser bottle tube",
    "moisturizer": "moisturizer cream lotion bottle",
    "lip balm": "lip balm tube chapstick",
    "contact lens": "contact lens case solution",
    "tissue pack": "tissue pack pocket size",
    "wet wipes": "wet wipes package",
    "cotton pad": "cotton pad package cosmetic",
    "q tip": "cotton swab q tip package",
    "feminine hygiene": "feminine hygiene pad product",
    "razor": "razor shaving blade",
    "shaving cream": "shaving cream can tube",

    # 文具 / 雜貨
    "stapler": "stapler office tool",
    "paper clip": "paper clip metal fastener",
    "highlighter": "highlighter marker pen",
    "marker": "marker pen drawing",
    "tape dispenser": "tape dispenser holder",
    "post it": "post it sticky note",
    "calculator": "calculator electronic device",
    "scotch tape": "scotch tape roll adhesive",
    "glue stick": "glue stick adhesive",
    "correction tape": "correction tape white out",

    # 家居用品
    "light bulb": "light bulb lamp",
    "battery pack": "battery pack AA AAA",
    "extension cord": "extension cord power strip",
    "trash bag roll": "trash bag roll plastic",
    "sponge pack": "sponge pack cleaning",
    "dish cloth": "dish cloth towel kitchen",
    "air freshener": "air freshener spray",
    "insect repellent": "insect repellent spray",

    # 寵物用品
    "pet food": "pet food bag cat dog",
    "cat litter": "cat litter bag box",
    "pet treat": "pet treat snack bag",
    "dog toy": "dog toy chew ball",

    # 嬰兒用品
    "diaper": "diaper nappy package",
    "baby wipes": "baby wipes package",
    "baby bottle": "baby bottle milk",
    "baby food": "baby food jar pouch",
    "formula": "baby formula milk powder",

    # 購物 / 結帳
    "shopping basket": "shopping basket plastic",
    "shopping cart": "shopping cart metal",
    "price tag": "price tag label sticker",
    "barcode": "barcode label sticker",
    "cash register": "cash register machine POS",
    "card reader": "card reader payment terminal",
}


class PromptEnhancer:
    """YOLOE 文字提示增強器"""

    def __init__(self, custom_prompts: Optional[Dict[str, str]] = None):
        """
        初始化增強器

        參數:
            custom_prompts: 額外的自訂增強提示（會覆蓋預設值）
        """
        self._prompts = ENHANCED_PROMPTS.copy()
        if custom_prompts:
            self._prompts.update(custom_prompts)

        # 使用者定義的變體描述（類別名 → 變體列表）
        self._variants: Dict[str, List[str]] = {}

        # 建立反向映射：增強提示 → 原始類別名
        self._reverse_map: Dict[str, str] = {}
        for original, enhanced in self._prompts.items():
            self._reverse_map[enhanced.lower()] = original

        logger.info(f"提示增強器已初始化，共 {len(self._prompts)} 個增強提示")

    def add_variants(self, class_name: str, variants: List[str]):
        """
        為類別新增使用者定義的變體描述，擴展 CLIP 提示覆蓋範圍

        參數:
            class_name: 類別名稱（如 "mouse"）
            variants: 變體描述列表（如 ["gaming mouse", "wireless mouse"]）
        """
        key = class_name.lower().strip()
        if key not in self._variants:
            self._variants[key] = []
        for v in variants:
            v_clean = v.strip()
            if v_clean and v_clean not in self._variants[key]:
                self._variants[key].append(v_clean)

    def set_variants(self, class_name: str, variants: List[str]):
        """設定類別的變體列表（覆蓋現有）"""
        key = class_name.lower().strip()
        self._variants[key] = [v.strip() for v in variants if v.strip()]

    def get_variants(self, class_name: str) -> List[str]:
        """取得類別的變體列表"""
        return self._variants.get(class_name.lower().strip(), [])

    def load_all_variants(self, variants_data: Dict[str, List[str]]):
        """批次載入所有變體資料"""
        for class_name, variants in variants_data.items():
            self._variants[class_name.lower().strip()] = [v.strip() for v in variants if v.strip()]

    def enhance(self, class_name: str) -> str:
        """
        將類別名轉為增強提示（含使用者變體）

        參數:
            class_name: 原始類別名（如 "mouse"）

        回傳:
            增強後的提示（如 "computer mouse device"），
            若有使用者變體則附加（如 "computer mouse device, gaming mouse, wireless mouse"）
        """
        key = class_name.lower().strip()
        base = self._prompts.get(key, class_name)
        variants = self._variants.get(key, [])

        if not variants:
            return base

        # 將變體附加到基礎提示（用逗號分隔，CLIP 可處理）
        return f"{base}, {', '.join(variants)}"

    def enhance_list(self, class_names: List[str]) -> Tuple[List[str], Dict[str, str]]:
        """
        批次增強類別列表

        參數:
            class_names: 原始類別名列表

        回傳:
            (enhanced_list, mapping)
            - enhanced_list: 增強後的提示列表
            - mapping: 增強提示 → 原始類別名 的映射
        """
        enhanced = []
        mapping = {}

        for name in class_names:
            name_clean = name.strip()
            prompt = self.enhance(name_clean)
            enhanced.append(prompt)
            mapping[prompt] = name_clean

        return enhanced, mapping

    def resolve(self, enhanced_name: str) -> str:
        """
        將增強提示反向解析為原始類別名

        參數:
            enhanced_name: 增強後的提示（如 "computer mouse device"）

        回傳:
            原始類別名（如 "mouse"），若無對應則返回原始值
        """
        return self._reverse_map.get(enhanced_name.lower().strip(), enhanced_name)

    def add_prompt(self, class_name: str, enhanced_prompt: str):
        """動態新增增強提示"""
        self._prompts[class_name.lower().strip()] = enhanced_prompt
        self._reverse_map[enhanced_prompt.lower()] = class_name.lower().strip()

    def get_all_prompts(self) -> Dict[str, str]:
        """取得所有增強提示對照"""
        return self._prompts.copy()

    def get_stats(self) -> Dict[str, int]:
        """取得統計"""
        return {
            "total_prompts": len(self._prompts),
            "categories": {
                "personal": len([k for k in self._prompts if k in [
                    "cell phone", "wallet", "keys", "glasses", "watch",
                    "earphone", "headphone", "pen", "pencil", "notebook",
                    "umbrella", "mask", "handbag", "backpack",
                ]]),
                "electronics": len([k for k in self._prompts if k in [
                    "laptop", "mouse", "keyboard", "remote", "charger",
                    "power bank", "battery", "tv",
                ]]),
                "food_drink": len([k for k in self._prompts if k in [
                    "bottle", "cup", "can", "bread", "banana", "apple",
                    "sandwich", "rice ball", "bento box",
                ]]),
            },
        }
