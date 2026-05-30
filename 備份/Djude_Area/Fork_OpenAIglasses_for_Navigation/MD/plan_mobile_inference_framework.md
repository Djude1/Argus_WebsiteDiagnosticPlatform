# 手機端推論框架選型分析（ONNX vs TFLite）

## 現況問題

`onnxruntime` Flutter 套件沒有零拷貝 API。output0 (1,82,8400) + output1 (1,32,160,160)，
主 isolate 透過 `dynamic List<num>` 逐項複製約 **200ms**，這不是 YOLOE 模型慢，是資料搬運慢。

## 三選項比較

| 面向 | ONNX Runtime（現狀）| TFLite | ONNX + XNNPACK |
|------|:---:|:---:|:---:|
| 資料提取 | `dynamic List<num>` 逐項複製 | 零拷貝 Float32List | 同 ONNX |
| 硬體加速（NNAPI/GPU）| 設定複雜，效果不穩 | 一個 flag 搞定 | 僅 CPU 加速 |
| YOLOE-seg 轉換風險 | 無（原生 ONNX）| 中高（需驗證 op 相容性）| 無 |
| 預估端到端速度 | ~300ms | **~80–150ms** | ~220ms |
| 工作量 | 0 | 中（轉換 + API 改寫）| **低（改 2 行）** |

## 建議路線：兩步走

### Step 1：ONNX + XNNPACK（今天）

在 `yoloe_inference.dart` init() 改：

```dart
final opts = OrtSessionOptions()
  ..setIntraOpNumThreads(4)
  ..appendXnnpack(numThreads: 4);
```

預期節省 20–30% 推論時間，不解決資料複製問題但成本最低。

### Step 2：評估 TFLite 轉換

```bash
uv run python -c "
from ultralytics import YOLO
m = YOLO('model/onnx/yoloe_26n_seg_outdoor.onnx')
m.export(format='tflite', imgsz=640)
"
```

- **轉換成功** → 換 `tflite_flutter`，用零拷貝 Float32List，加 NNAPI delegate，預期 300ms → 80ms
- **轉換失敗**（常見：`aten::slice`、自定義 op 不支援）→ 留 ONNX + XNNPACK，等 Ultralytics 修 TFLite export

TFLite 換完後 API 形式：

```dart
final interpreter = await Interpreter.fromAsset('yoloe_26n_seg.tflite',
    options: InterpreterOptions()..addDelegate(NnApiDelegate()));
// output0 / output1 直接是 Float32List，無任何複製
```

## 不建議的選項

- **MNN / PyTorch Mobile**：Flutter binding 不成熟，維護成本高
- **ExecuTorch**：Flutter 支援尚未穩定

## 決策紀錄

- 2026-04-22：保留 ONNX，待 YOLOE-seg 本地推論效果確認後再評估 TFLite 路線
