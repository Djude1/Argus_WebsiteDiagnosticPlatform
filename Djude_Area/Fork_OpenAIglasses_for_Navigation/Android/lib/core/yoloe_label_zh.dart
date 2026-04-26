// lib/core/yoloe_label_zh.dart
// yoloe-26n-seg 開放詞彙標籤中英對照表
// 對應計畫：MD/plan_mobile_yolo_deployment.md Phase A.4
// AR 偵測框一律顯示繁體中文，不顯示英文類別名稱

const Map<String, String> kYoloeLabelZh = {
  // 人與動物
  'person': '人',
  'dog': '狗',
  'animal': '動物',
  'stroller': '嬰兒車',
  'scooter': '滑板車',

  // 車輛
  'bicycle': '腳踏車',
  'motorcycle': '機車',
  'car': '轎車',
  'bus': '公車',
  'truck': '卡車',

  // 柱狀障礙
  'pole': '電線桿',
  'post': '柱子',
  'bollard': '護柱',
  'utility pole': '電線桿',
  'light pole': '路燈桿',
  'signpost': '路牌',

  // 路邊設施
  'bench': '長椅',
  'trash can': '垃圾桶',
  'hydrant': '消防栓',
  'cone': '三角錐',
  'traffic cone': '交通錐',
  'barrel': '桶子',
  'cart': '推車',
  'box': '箱子',
  'stone': '石頭',

  // 阻隔物
  'fence': '圍欄',
  'barrier': '護欄',
  'wall': '牆壁',
  'gate': '大門',
  'door': '門',

  // 地面障礙
  'curb': '路緣石',
  'stairs': '階梯',
  'step': '台階',
  'ramp': '坡道',
  'hole': '坑洞',
  'rock': '岩石',
  'branch': '樹枝',

  // 植物
  'tree': '樹木',
  'potted plant': '盆栽',

  // 行李
  'bag': '包包',
  'suitcase': '行李箱',
  'backpack': '背包',

  // 家具
  'chair': '椅子',
  'table': '桌子',
  'office chair': '辦公椅',
  'sofa': '沙發',
  'desk': '書桌',
  'stool': '圓椅',
  'dining table': '餐桌',

  // 室內障礙
  'glass wall': '玻璃牆',
  'glass partition': '玻璃隔板',
  'threshold': '門檻',
  'power cord': '電源線',
  'cable': '電線',
  'wet floor sign': '小心地滑',
  'umbrella': '雨傘',

  // 通用
  'obstacle': '障礙物',
  'object': '物體',
  'ladder': '梯子',
};

/// 取得繁體中文標籤；找不到對照時回傳原英文。
String labelZh(String en) =>
    kYoloeLabelZh[en.toLowerCase()] ?? en;
