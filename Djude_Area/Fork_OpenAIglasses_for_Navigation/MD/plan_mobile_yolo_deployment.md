# 手機端 YOLO 視障導航系統部署計畫

> 狀態：規劃中（2026-04-21）
> 目標：將 YOLO 推論全部移至手機端，零伺服器依賴，提升 FPS 與隱私性
> **現階段範圍：路上避障（outdoor）+ 室內避障（indoor）兩個場景**

---

## ⚠️ 核心原則（不可違反）

1. **ALL.pt 完全不動**：現有避障邏輯維持原樣，yoloe-26n-seg 走獨立測試路徑
2. **先測試，再整合**：yoloe-26n-seg 效果通過人工驗收後，才進行正式替換
3. **程式碼測試責任**：伺服器端 Python 測試由 Claude 負責；Flutter APP UI 由開發者驗收
4. **平行運行**：測試期間 yoloe-26n-seg 和 ALL.pt 同時存在，不互相影響

---

## 架構總覽

```
手機端
├── 感知層   Camera + GPS + IMU
├── 推論層   3 個 ONNX 模型
├── 融合層   兩層場景切換決策引擎（GPS 精度 + 物件觸發）
└── 輸出層   TTS 語音 + 震動
```

---

## 模型選型決策

| 功能 | 模型 | 理由 |
|------|------|------|
| 開放詞彙避障 | `yoloe-26n-seg`（11.2MB） | YOLOE nano 唯一存在的版本，yoloe-11n-seg 不存在 |
| 紅綠燈偵測 | `yolo26n-seg` 微調（~5MB） | NMS-Free、邊緣優化、比 YOLOv8n 快 43% |
| 導航核心（curb/盲道）| `ALL.pt` → ONNX（~25MB） | 專門訓練的固定類別，YOLOE 開放詞彙無法取代 |

### 為什麼不全用 ALL.pt

ALL.pt 是固定 14 類，YOLOE-26n-seg 是開放詞彙（可帶入任意文字標籤）。
兩者互補：ALL.pt 負責導航核心（精準），YOLOE 負責通用避障（彈性）。

---

## Phase 1：PC 端準備

### 1.1 模型匯出

```python
from ultralytics import YOLO, YOLOE

# ALL.pt → ONNX（fp16）
YOLO('model/ALL.pt').export(format='onnx', half=True, simplify=True)

# yoloe-26n-seg → ONNX（Vision Encoder only，Text Encoder 不需上手機）
YOLOE('model/yoloe-26n-seg.pt').export(format='onnx', half=True, simplify=True)

# 紅綠燈微調後 → ONNX
YOLO('runs/traffic/v1/weights/best.pt').export(format='onnx', half=True, simplify=True)
```

### 1.2 預計算 Embedding（兩組場景：路上 + 室內）

在 PC 上用 yoloe-26n-seg 的 Text Encoder 計算向量，存 `.npy`，手機只載向量不跑 Text Encoder。

```python
# compute_walk_embeddings.py
import torch, numpy as np, json, os
from ultralytics import YOLOE

model = YOLOE('model/yoloe-26n-seg.pt')
os.makedirs('embeddings', exist_ok=True)

SCENES = {
    "outdoor": [
        # 路上行走避障——原始 yoloe-11l-seg 時代沿用標籤
        'person', 'bicycle', 'car', 'motorcycle', 'bus', 'truck',
        'animal', 'scooter', 'stroller', 'dog',
        'pole', 'post', 'bollard', 'utility pole', 'light pole', 'signpost',
        'bench', 'chair', 'potted plant', 'hydrant', 'cone', 'stone', 'box',
        'trash can', 'barrel', 'cart', 'fence', 'barrier', 'wall', 'gate', 'door',
        'rock', 'tree', 'branch', 'curb', 'stairs', 'step', 'ramp', 'hole',
        'bag', 'suitcase', 'backpack', 'table', 'ladder', 'object', 'obstacle',
    ],
    "indoor": [
        # 室內行走避障——家具 + 障礙物 + 人
        'person', 'dog', 'animal',
        'chair', 'office chair', 'stool', 'sofa',
        'table', 'desk', 'dining table',
        'door', 'glass wall', 'glass partition', 'threshold', 'step',
        'stairs', 'ramp', 'hole',
        'trash can', 'potted plant', 'umbrella',
        'power cord', 'cable', 'backpack', 'bag', 'suitcase',
        'box', 'cart', 'ladder', 'barrier', 'cone',
        'wet floor sign', 'obstacle', 'object',
    ],
}

for scene_name, labels in SCENES.items():
    with torch.inference_mode():
        embeddings = model.get_text_pe(labels)
    np.save(f'embeddings/{scene_name}.npy', embeddings.cpu().numpy())
    with open(f'embeddings/{scene_name}_labels.json', 'w', encoding='utf-8') as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)
    print(f'{scene_name}: {len(labels)} 個標籤，shape={embeddings.shape}')

print('完成！產出：embeddings/outdoor.npy / indoor.npy')
```

### 1.3 紅綠燈模型微調

```python
# finetune_traffic.py
from ultralytics import YOLO

model = YOLO('yolo26n-seg.pt')
model.train(
    data='datasets/taiwan_traffic/data.yaml',
    epochs=100,
    imgsz=640,
    batch=16,
    project='runs/traffic',   # 純 ASCII！Windows 中文路徑地雷
    name='v1',
    patience=20,
    freeze=10,
)
```

**資料集 yaml：**
```yaml
path: datasets/taiwan_traffic
train: images/train
val: images/val
nc: 8
names:
  0: 行人紅燈
  1: 行人綠燈
  2: 行人黃燈
  3: 遠端紅燈
  4: 遠端綠燈
  5: 遠端黃燈
  6: 斑馬線
  7: 遠端斑馬線
```

**資料集來源建議：**
| 來源 | 用途 |
|------|------|
| S2TLD（中國） | 基礎大量資料 |
| 自拍台灣路口影片 | 最關鍵，50-100 張就有效 |
| Roboflow 公開集 | 補充多樣性 |

---

## Phase 2：兩層場景切換融合引擎

```
優先級：Layer 2（物件觸發）> Layer 1（GPS 精度）
```

### Layer 1：GPS 精度（判斷室內 / 室外）

**不需要 AI 模型**，直接用 GPS 定位精度值判斷：

```dart
class GpsSceneDetector {
  // GPS 精度（accuracy，單位：公尺）
  // 室外：衛星訊號強，精度 < 10m
  // 室內：衛星訊號弱，精度 > 25m（牆壁遮蔽）
  static const double OUTDOOR_THRESHOLD = 10.0;   // m，< 此值 = 確定室外
  static const double INDOOR_THRESHOLD  = 25.0;   // m，> 此值 = 確定室內

  Scene detect(double accuracyMeters) {
    if (accuracyMeters < OUTDOOR_THRESHOLD) return Scene.outdoor;
    if (accuracyMeters > INDOOR_THRESHOLD)  return Scene.indoor;
    return Scene.unknown;  // 介於中間，維持上一個場景
  }
}
```

| GPS 精度 | 判斷 | 原因 |
|---------|------|------|
| < 10m | 室外 | 衛星直視，訊號強 |
| 10~25m | 不確定（維持現狀）| 可能在騎樓、地下室出入口 |
| > 25m | 室內 | 建築物遮蔽衛星訊號 |

- 每 5 秒更新一次 GPS 精度
- 切換需連續 3 次同結果才生效（防抖）

### Layer 2：模型偵測觸發（最高優先，即時）

YOLOE 偵測到場景特有物品 → 立即切換 Embedding 集：

```dart
const TRIGGER_INDOOR = {
  'wet floor sign',   // 室內地板警示牌
  'office chair',     // 辦公椅
  'stool',            // 圓椅
  'glass wall',       // 玻璃牆（室內常見）
  'glass partition',  // 玻璃隔板
};

const TRIGGER_OUTDOOR = {
  'car', 'bus', 'truck', 'motorcycle',  // 馬路上的車
  'traffic cone',                        // 交通錐
  'utility pole',                        // 電線桿
};

void checkTriggers(List<Detection> detections, Scene currentScene) {
  for (var det in detections) {
    if (det.confidence < 0.6) continue;
    final label = det.className.toLowerCase();
    if (TRIGGER_INDOOR.contains(label) && currentScene != Scene.indoor) {
      _switchScene(Scene.indoor, reason: 'object_trigger:$label');
      return;
    }
    if (TRIGGER_OUTDOOR.contains(label) && currentScene != Scene.outdoor) {
      _switchScene(Scene.outdoor, reason: 'object_trigger:$label');
      return;
    }
  }
}
```

### 融合決策完整流程

```
每 5 秒執行（GPS 更新時）：
┌─ Layer 2 偵測到觸發物件（conf > 0.6）？
│  └─ YES → 立即切換，冷卻 15 秒
│
└─ NO → Layer 1 GPS 精度判斷結果？
   ├─ 確定室外（< 10m）→ 切換為 outdoor embedding
   ├─ 確定室內（> 25m）→ 切換為 indoor embedding
   └─ 不確定（10~25m）→ 維持現有 embedding，不切換
```

---

## Phase 3：Flutter 推論架構

### 3.1 套件

```yaml
dependencies:
  onnxruntime: ^1.x
  camera: ^0.10.x
  geolocator: ^10.x
  device_info_plus: ^9.x    # 讀取 CPU / RAM / 溫度
```

### 3.2 兩 Isolate 並行管線

```dart
class InferencePipeline {
  late SendPort _obstaclePort;   // Isolate A：避障（每幀，yoloe-26n-seg）
  late SendPort _trafficPort;    // Isolate B：紅綠燈（過馬路模式才啟動）

  Future<void> init() async {
    _obstaclePort = await _spawnIsolate('obstacle', 'assets/models/yoloe_26n_seg.onnx');
    // 紅綠燈 Isolate 延遲啟動，省記憶體
  }

  void switchEmbedding(Scene scene) {
    // 不中斷推論，下一幀生效
    _obstaclePort.send({
      'action': 'switch_embedding',
      'path': 'assets/embeddings/${scene.name}.npy',
    });
  }
}
```

### 3.3 記憶體預算（中階 Android 3GB RAM）

| 模型 | 記憶體 |
|------|--------|
| yoloe-26n-seg ONNX | ~80MB |
| ALL.pt ONNX（導航核心）| ~120MB |
| 紅綠燈（按需載入）| ~20MB |
| 2 組 Embedding（outdoor + indoor）| ~3MB |
| **合計** | **~223MB** |

> 紅綠燈模型只在「過馬路模式」啟動時載入，結束後立即釋放。

---

## Phase 4：執行順序

```
Week 1：PC 端準備
  [ ] 執行 compute_walk_embeddings.py，產出 outdoor.npy / indoor.npy
  [ ] 匯出 ALL.pt → ONNX，確認精度無損
  [ ] 紅綠燈資料集整理（台灣路口拍攝 100 張）
  [ ] 1-epoch 測試存檔（確認中文路徑地雷沒踩）

Week 2：紅綠燈微調
  [ ] yolo26n-seg 微調訓練
  [ ] 匯出 ONNX，驗證 8 類別正確
  [ ] 測試場 Gradio 介面驗收

Week 3：Flutter 整合
  [ ] ONNX Runtime 套件整合，跑通 ALL.pt 推論
  [ ] yoloe-26n-seg + embedding.npy 推論測試
  [ ] FPS 基準測試（目標：中階手機 10+ FPS）

Week 4：場景切換
  [ ] GPS 精度場景切換實作
  [ ] 物件觸發切換實作
  [ ] 兩層融合邏輯整合測試
  [ ] 端對端實地測試（室外街道 + 室內建築）

Week 5：調整優化
  [ ] Embedding 切換延遲測試
  [ ] 低端手機（2GB RAM）壓力測試
  [ ] TTS 語音播報整合驗收
```

---

## 技術風險

| 風險 | 可能性 | 應對 |
|------|--------|------|
| ONNX Runtime 不支援 yoloe-26n-seg 某層 | 中 | 先用 Python onnxruntime 驗證再轉 Flutter |
| 中階手機 FPS 不達標（< 5 FPS）| 中 | 降輸入解析度至 320×320，或每 2 幀推一次 |
| Embedding 切換時閃爍誤報 | 低 | 切換期間暫停語音播報 0.5 秒 |
| GPS 室內精度值不穩定 | 中 | 加連續 3 次確認防抖；物件觸發可補償 |
| GPS 在騎樓/地下室出入口誤判 | 中 | 10~25m 區間維持現有場景不切換 |

---

## 相關檔案

| 檔案 | 說明 |
|------|------|
| `model/yoloe-26n-seg.pt` | 已下載，待匯出 ONNX |
| `model/ALL.pt` | 待匯出 ONNX |
| `YOLO測試場/taiwan_trafficlight-v1.pt` | 紅綠燈微調參考基準 |
| `yolo_標籤.txt` | 教室/賣場/室內標籤參考（未來場景擴充備用）|
| `obstacle_detector_client.py` | 伺服器端避障邏輯（手機化後可廢棄）|

---

## Phase A：APP 管理員介面 — yoloe-26n-seg AR 測試頁

> 這是第一個實作目標。ALL.pt 完全不動，獨立新增測試入口。

### A.1 入口位置

在 Flutter APP 管理員設定頁新增一個按鈕：

```
設定頁
└── [開發者工具]（需登入 admin 才顯示）
    └── [yoloe-26n-seg AR 測試]  ← 新增這個
```

### A.2 AR 測試頁功能設計

> **強制要求**：
> - AR 畫面**全螢幕**，相機佔滿整個螢幕（含瀏海/打孔區），無邊框
> - 偵測框標籤**一律顯示繁體中文**，不顯示英文類別名稱

```
┌─────────────────────────────────┐  ← 全螢幕（無邊框、無導航列）
│  📷 相機即時畫面（滿版）          │
│                                 │
│  ┌──────────┐                  │
│  │ 人  92%  │  ← 繁體中文標籤  │  ← AR 偵測框疊加層
│  └──────────┘                  │
│       ┌───────────┐            │
│       │ 椅子  76%  │            │
│       └───────────┘            │
│                                 │
│  ┄┄┄┄┄┄ 半透明控制列 ┄┄┄┄┄┄┄  │  ← 底部半透明，不擋畫面
│  [路上] [室內]   FPS:12  偵測:3 │
│  conf [──●──] 0.25             │
│  [截圖]              [✕ 返回]  │
└─────────────────────────────────┘
```

### A.3 Flutter 頁面結構

```dart
// lib/screens/yoloe_ar_test_screen.dart

class YoloeArTestScreen extends StatefulWidget { ... }

class _YoloeArTestScreenState extends State<YoloeArTestScreen> {
  late CameraController _camera;
  late OnnxModel _yoloeModel;
  Scene _currentScene = Scene.outdoor;
  double _confThreshold = 0.25;
  List<Detection> _detections = [];
  int _fps = 0;

  Future<void> _initModel() async {
    _yoloeModel = await OnnxModel.load('assets/models/yoloe_26n_seg.onnx');
    await _switchScene(Scene.outdoor);
  }

  Future<void> _switchScene(Scene scene) async {
    final emb = await EmbeddingLoader.load(scene);
    _yoloeModel.setEmbedding(emb);
    setState(() => _currentScene = scene);
  }

  void _onCameraFrame(CameraImage image) async {
    final result = await _yoloeModel.infer(image, conf: _confThreshold);
    setState(() => _detections = result.detections);
  }

  @override
  void dispose() {
    _yoloeModel.release();  // 離開頁面立即釋放，不影響主系統
    super.dispose();
  }
}
```

### A.4 標籤中英對照表（完整）

```dart
// lib/constants/yoloe_label_zh.dart
const Map<String, String> YOLOE_LABEL_ZH = {
  // 人與動物
  'person': '人', 'dog': '狗', 'animal': '動物',
  'stroller': '嬰兒車', 'scooter': '滑板車',
  // 車輛
  'bicycle': '腳踏車', 'motorcycle': '機車', 'car': '轎車',
  'bus': '公車', 'truck': '卡車',
  // 柱狀障礙
  'pole': '電線桿', 'post': '柱子', 'bollard': '護柱',
  'utility pole': '電線桿', 'light pole': '路燈桿', 'signpost': '路牌',
  // 路邊設施
  'bench': '長椅', 'trash can': '垃圾桶', 'hydrant': '消防栓',
  'cone': '三角錐', 'barrel': '桶子', 'cart': '推車', 'box': '箱子',
  'stone': '石頭',
  // 阻隔物
  'fence': '圍欄', 'barrier': '護欄', 'wall': '牆壁',
  'gate': '大門', 'door': '門',
  // 地面障礙
  'curb': '路緣石', 'stairs': '階梯', 'step': '台階',
  'ramp': '坡道', 'hole': '坑洞', 'rock': '岩石', 'branch': '樹枝',
  // 植物
  'tree': '樹木', 'potted plant': '盆栽',
  // 行李
  'bag': '包包', 'suitcase': '行李箱', 'backpack': '背包',
  // 家具
  'chair': '椅子', 'table': '桌子', 'office chair': '辦公椅',
  'sofa': '沙發', 'desk': '書桌', 'stool': '圓椅',
  'dining table': '餐桌',
  // 室內障礙
  'glass wall': '玻璃牆', 'glass partition': '玻璃隔板',
  'threshold': '門檻', 'power cord': '電源線', 'cable': '電線',
  'wet floor sign': '小心地滑', 'umbrella': '雨傘',
  // 通用
  'obstacle': '障礙物', 'object': '物體',
  'ladder': '梯子', 'traffic cone': '交通錐',
};

String labelZh(String en) => YOLOE_LABEL_ZH[en.toLowerCase()] ?? en;
```

### A.5 AR 疊加層（CustomPainter）

```dart
class DetectionPainter extends CustomPainter {
  final List<Detection> detections;
  final Size imageSize;

  @override
  void paint(Canvas canvas, Size size) {
    for (var det in detections) {
      final rect = _scaleBox(det.box, imageSize, size);

      // 偵測框
      canvas.drawRect(rect, Paint()
        ..color = Colors.greenAccent
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.5);

      // mask 半透明疊加
      if (det.mask != null) {
        _drawMask(canvas, det.mask!, size, Colors.greenAccent.withOpacity(0.25));
      }

      // 標籤（繁體中文 + 信心值）
      final zhLabel = '${labelZh(det.label)}  ${(det.conf * 100).toInt()}%';
      _drawLabel(canvas, zhLabel, rect.topLeft);
    }
  }

  void _drawLabel(Canvas canvas, String text, Offset pos) {
    final tp = TextPainter(
      text: TextSpan(
        text: text,
        style: const TextStyle(
          color: Colors.white,
          fontSize: 13,
          fontWeight: FontWeight.bold,
          shadows: [Shadow(color: Colors.black, blurRadius: 4)],
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();

    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(pos.dx, pos.dy - 20, tp.width + 8, 22),
        const Radius.circular(4),
      ),
      Paint()..color = Colors.black54,
    );
    tp.paint(canvas, Offset(pos.dx + 4, pos.dy - 18));
  }
}
```

### A.6 全螢幕相機實作

```dart
@override
Widget build(BuildContext context) {
  return Scaffold(
    backgroundColor: Colors.black,
    extendBodyBehindAppBar: true,  // 延伸到系統列後方
    body: Stack(
      fit: StackFit.expand,  // 強制填滿整個螢幕
      children: [
        // 1. 相機預覽（全螢幕）
        CameraPreview(_camera),

        // 2. AR 偵測框疊加
        CustomPaint(
          painter: DetectionPainter(
            detections: _detections,
            imageSize: Size(
              _camera.value.previewSize!.height,
              _camera.value.previewSize!.width,
            ),
          ),
        ),

        // 3. 底部半透明控制列
        Positioned(
          bottom: 0, left: 0, right: 0,
          child: Container(
            color: Colors.black.withOpacity(0.5),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Column(children: [
              Row(children: [
                _sceneBtn('路上', Scene.outdoor),
                _sceneBtn('室內', Scene.indoor),
                const Spacer(),
                // FPS + 效能監控（右上角旁邊，僅 AR 測試頁 + debug 畫面顯示）
                Text(
                  'FPS:$_fps  CPU:$_cpuPercent%  RAM:${_ramFreeMB}MB  $_tempC°C',
                  style: const TextStyle(color: Colors.greenAccent, fontSize: 11),
                ),
                const SizedBox(width: 8),
                Text('偵測:${_detections.length}', style: const TextStyle(color: Colors.white)),
              ]),
              Row(children: [
                const Text('門檻', style: TextStyle(color: Colors.white70, fontSize: 12)),
                Expanded(child: Slider(
                  value: _confThreshold, min: 0.1, max: 0.9, divisions: 16,
                  onChanged: (v) => setState(() => _confThreshold = v),
                )),
                Text(_confThreshold.toStringAsFixed(2),
                    style: const TextStyle(color: Colors.white, fontSize: 12)),
              ]),
            ]),
          ),
        ),

        // 4. 返回按鈕（右上角）
        Positioned(
          top: MediaQuery.of(context).padding.top + 8,
          right: 12,
          child: IconButton(
            icon: const Icon(Icons.close, color: Colors.white, size: 28),
            onPressed: () => Navigator.pop(context),
          ),
        ),
      ],
    ),
  );
}

// 效能監控（每秒讀取一次，讀系統檔不做運算）
Timer? _perfTimer;
int _cpuPercent = 0;
int _ramFreeMB = 0;
int _tempC = 0;

void _startPerfMonitor() {
  _perfTimer = Timer.periodic(const Duration(seconds: 1), (_) async {
    final cpu  = await _readCpuUsage();
    final ram  = await _readRamFreeMB();
    final temp = await _readTempC();
    if (mounted) setState(() { _cpuPercent = cpu; _ramFreeMB = ram; _tempC = temp; });
  });
}

// 讀 /proc/stat 計算 CPU 使用率
Future<int> _readCpuUsage() async { ... }
// 讀 /proc/meminfo 取得可用 RAM
Future<int> _readRamFreeMB() async { ... }
// 讀 /sys/class/thermal/thermal_zone0/temp 取得溫度
Future<int> _readTempC() async { ... }
```

### A.7 程式碼測試責任（Claude 負責）

```python
# test_yoloe26n_server.py（PC 端驗證，確保模型行為正確再送 Flutter）

import numpy as np, json, torch
from ultralytics import YOLOE

def test_embedding_load():
    model = YOLOE('model/yoloe-26n-seg.pt')
    for scene in ['outdoor', 'indoor']:
        emb = torch.from_numpy(np.load(f'embeddings/{scene}.npy'))
        labels = json.load(open(f'embeddings/{scene}_labels.json', encoding='utf-8'))
        model.set_classes(labels, emb)
        assert len(model.names) == len(labels), f'{scene} 標籤數不符'
    print('embedding 載入測試 ✓')

def test_inference_shape(img_path: str):
    import cv2
    model = YOLOE('model/yoloe-26n-seg.pt')
    emb = torch.from_numpy(np.load('embeddings/outdoor.npy'))
    labels = json.load(open('embeddings/outdoor_labels.json', encoding='utf-8'))
    model.set_classes(labels, emb)
    img = cv2.imread(img_path)
    r = model.predict(img, conf=0.25, verbose=False)[0]
    assert r.boxes is not None, '無 boxes 輸出'
    assert r.masks is not None, '無 masks 輸出（應為 seg 模型）'
    print(f'推論測試 ✓  偵測 {len(r.boxes)} 個物件')

def test_scene_switch_latency():
    import time
    model = YOLOE('model/yoloe-26n-seg.pt')
    for scene in ['outdoor', 'indoor']:
        emb = torch.from_numpy(np.load(f'embeddings/{scene}.npy'))
        labels = json.load(open(f'embeddings/{scene}_labels.json', encoding='utf-8'))
        t0 = time.perf_counter()
        model.set_classes(labels, emb)
        ms = (time.perf_counter() - t0) * 1000
        print(f'{scene} 切換延遲：{ms:.1f}ms')

if __name__ == '__main__':
    test_embedding_load()
    test_inference_shape('YOLO測試場/test_image.jpg')
    test_scene_switch_latency()
```

**驗收標準（全部通過才送 Flutter）：**

| 測試項目 | 通過條件 |
|---------|---------|
| embedding 載入正確 | 標籤數完全一致 |
| 推論有 masks 輸出 | 非 None |
| 戶外偵測到人 | conf > 0.35 |
| 室內偵測到椅子/桌子 | conf > 0.30 |
| embedding 切換延遲 | < 50ms |
| ALL.pt 行為未受影響 | 獨立測試確認 |

---

## Phase B：伺服器演進計畫

> 手機端有 YOLO 之後，伺服器的角色和架構需要對應調整。

### B.1 現在的架構（伺服器負擔重）

```
ESP32 眼鏡
    │ WebSocket（影像 + 音訊）
    ▼
FastAPI 伺服器（port 8081-8084）
    ├── YOLO 推論（ALL.pt 避障/盲道/紅綠燈）  ← CPU/GPU 大戶
    ├── ASR（Google Speech-to-Text）
    ├── LLM（場景描述、語音對話）
    ├── TTS（Gemini TTS / WaveNet）
    └── NavigationMaster 狀態機
```

### B.2 手機 YOLO 後的架構（伺服器變輕）

```
手機（Flutter APP）
    ├── yoloe-26n-seg ONNX  ← 避障推論（本地）
    ├── yolo26n-seg ONNX    ← 紅綠燈（本地）
    ├── ALL.pt ONNX         ← 盲道/curb（本地）
    └── TTS WAV 預錄音檔    ← 基本語音（本地）
         │ 只在需要時才上傳（省頻寬）
         ▼
FastAPI 伺服器（精簡版）
    ├── ASR（語音對話觸發時）
    ├── LLM（場景描述、複雜問答）   ← 保留，手機算力不夠
    ├── 高品質 TTS（WaveNet/Gemini）← 保留
    ├── NavigationMaster 狀態機     ← 保留
    └── 用戶資料/聯絡人/設定同步    ← 保留
```

### B.3 伺服器需要新增的 API

```python
# 1. 手機回報偵測結果 → 伺服器做高層決策
@app.post("/api/mobile/detections")
async def receive_mobile_detections(payload: MobileDetectionPayload):
    detections = payload.detections   # [{label, conf, position}, ...]
    scene = payload.scene             # outdoor / indoor
    if _needs_description(detections):
        asyncio.create_task(_trigger_description(detections))
    return {"action": "none"}

# 2. 手機請求場景描述
@app.post("/api/mobile/describe_scene")
async def describe_scene(image: UploadFile):
    """手機拍一張圖 → 伺服器 LLM 描述 → 回傳文字"""
    ...

# 3. Embedding 版本管理（手機定期同步）
@app.get("/api/mobile/embeddings/version")
async def get_embedding_version():
    return {"version": EMBEDDING_VERSION, "scenes": ["outdoor", "indoor"]}

@app.get("/api/mobile/embeddings/{scene}")
async def download_embedding(scene: str):
    """手機下載最新 embedding"""
    ...
```

### B.4 伺服器不再需要做的事

| 功能 | 現在 | 手機 YOLO 後 |
|------|------|-------------|
| 避障 YOLO 推論 | ✅ 伺服器 | ❌ 移至手機 |
| 盲道分割 YOLO | ✅ 伺服器 | ❌ 移至手機 |
| 紅綠燈偵測 YOLO | ✅ 伺服器 | ❌ 移至手機 |
| 基本 TTS 播報 | ✅ 伺服器 | ❌ 本地 WAV |
| ASR 語音辨識 | ✅ 伺服器 | ✅ 保留 |
| LLM 場景描述 | ✅ 伺服器 | ✅ 保留 |
| 高品質 TTS | ✅ 伺服器 | ✅ 保留 |
| NavigationMaster | ✅ 伺服器 | ✅ 保留（或部分移植）|

### B.5 過渡期策略

```
Stage 1（現在）：ALL.pt 在伺服器，yoloe-26n-seg 在 APP 測試
    ↓ yoloe-26n-seg 驗收通過
Stage 2：APP 主用 yoloe-26n-seg 避障，伺服器 ALL.pt 仍保留作備援
    ↓ 穩定運行 2 週
Stage 3：伺服器移除 YOLO 推論；APP 完全本地 YOLO
```

---

## 更新後的 Phase 執行順序

```
【立即可做】
Phase A：
  [ ] A1. 執行 compute_walk_embeddings.py → 產出 outdoor.npy / indoor.npy
  [ ] A2. 執行 test_yoloe26n_server.py → 全部測試通過
  [ ] A3. Flutter APP 新增管理員入口按鈕
  [ ] A4. 實作 YoloeArTestScreen（相機 + AR 疊加 + 場景切換）
  [ ] A5. 開發者手動驗收（路上實地 + 室內建築實地）

【A 驗收通過後】
Phase 1-4（原計畫）：
  完整手機端部署 + 場景切換引擎

【平行進行】
Phase B：
  [ ] B1. 新增 /api/mobile/detections 端點
  [ ] B2. 新增 embedding 版本管理端點
  [ ] B3. Stage 2 過渡測試（雙軌並行）
```
