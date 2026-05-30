# `model/onnx/` — 手機端 YOLOE 推論模型倉庫

本資料夾存放「手機端（Flutter APP）ONNX Runtime 推論」用的 `yoloe-26n-seg` 系列模型匯出檔，以及對應的類別標籤清單。

## 檔案清單

| 檔案 | 大小 | 用途 | 是否部署於 APK |
|------|------|------|----------------|
| `yoloe_26n_seg_outdoor.onnx` | ~10.7 MB | 戶外場景（45 類：person / bicycle / car / bus / truck / pole / tree / curb / stairs ...） | ✅ 目前部署 |
| `outdoor_labels.json` | 592 B | 對應 outdoor 模型的類別名稱（索引順序與 ONNX 輸出一致） | ✅ 目前部署 |
| `yoloe_26n_seg_indoor.onnx` | ~10.6 MB | 室內場景（34 類：person / chair / sofa / table / door / stairs / potted plant ...） | ⛔ 暫停使用（見下方） |
| `indoor_labels.json` | 474 B | 對應 indoor 模型的類別名稱 | ⛔ 暫停使用 |

> 部署於 APK 的副本實際放置於 `Android/assets/models/`（由 `pubspec.yaml` 的 `assets: - assets/models/` 自動打包）。
> 本資料夾是**主備份**與**未打包副本**的集中存放點。

## 為何 indoor 模型暫停使用？

當前 APP 的 `yoloE26N-seg AR` 測試頁（`Android/lib/screens/yoloe_ar_test_screen.dart`）已改為「**純避障模式**」，行為對齊伺服器端 `workflow_blindpath.py::_add_obstacle_visualization`：

- 近距離障礙（`bottom_y_ratio > 0.7` 或 `area_ratio > 0.1`）→ 紅色輪廓、線寬 3
- 遠距離障礙 → 黃色輪廓、線寬 2（alpha ~0.8）
- `curb`（路緣）→ 粉色輪廓、線寬 2（保留色號供未來「盲道導航」等其他用途）
- 過大遮罩（`area_ratio > 0.7`）→ 視為誤判直接過濾
- 只描邊、不填色（填色是盲道專屬語意）

因此目前：

- 移除了 `Scene` enum 與室內／室外切換按鈕（先前的 `_switchScene()`、`_sceneBtn()` 已刪除）
- `YoloeInference.init()` 不再接受 `Scene` 參數，固定載入 `yoloe_26n_seg_outdoor.onnx` + `outdoor_labels.json`
- 管理員介面的「YOLOe26N-seg」按鈕仍可正常開啟測試頁（保留入口）
- APK 不再打包 indoor 模型，節省 ~10.6 MB + ~0.5 KB 安裝大小

## 開發進度（對應 `MD/plan_mobile_yolo_deployment.md` Phase A）

- [x] **A.1 — Ultralytics ONNX 匯出**：`yoloe-26n-seg` 權重 → ONNX（含 proto、mask coeff 輸出），`opset=12`、`imgsz=640`、`dynamic=False`
- [x] **A.2 — 雙場景類別匯出**：依 `indoor_labels.json` / `outdoor_labels.json` 分別 export 出 `yoloe_26n_seg_indoor.onnx` / `yoloe_26n_seg_outdoor.onnx`
- [x] **A.3 — Flutter ONNX Runtime 整合**：`Android/lib/services/yoloe_inference.dart` 完成
  - `onnxruntime: ^1.4.1` 套件接入
  - `CameraImage` YUV420 → RGB → letterbox 640 → CHW Float32 前處理
  - 後處理：sigmoid(proto × mask coeff) > 0.5 → Moore neighbor 8-connectivity 輪廓追蹤
  - 直式座標旋轉：`(srcH - 1 - sy, sx)` 對應 90° CW 旋轉
  - 新增 `areaRatio`、`bottomYRatio` 計算（取代早期單純 bbox 面積）
  - `maskFgCount` 以遮罩像素實際面積（而非 bbox）計算 `area_ratio`，更貼近伺服器端邏輯
- [x] **A.4 — AR 測試頁（避障模式）**：`Android/lib/screens/yoloe_ar_test_screen.dart` 完成
  - `_DetectionPainter` 依 `isNear` / `label=='curb'` 套用近紅 / 遠黃 / curb 粉色
  - 近距離標籤加上「(近)」後綴
  - 右上角紅色「避障模式」徽章取代先前的室內/室外切換列
  - `flutter analyze` 通過（0 issues）
- [ ] **A.5 — 實機驗證**：需在 Android 實機上確認推論延遲、遮罩形狀精準度、近/遠判定是否直觀（尚未執行）
- [ ] **A.6 — 室內場景恢復（暫緩）**：若將來要重啟室內模型，需：
  1. 把 `yoloe_26n_seg_indoor.onnx` + `indoor_labels.json` 複製回 `Android/assets/models/`
  2. 在 `yoloe_inference.dart` / `yoloe_ar_test_screen.dart` 重新加回 `Scene` 切換邏輯
  3. 評估同時載入兩個 ONNX 的記憶體成本，或採「按需載入、釋放舊 session」策略

## 不打包進 APK 的細節

`pubspec.yaml` 的資產宣告是**目錄層級**：

```yaml
flutter:
  assets:
    - assets/models/
```

這意味著 `Android/assets/models/` 內的所有檔案都會被 Flutter build 打進 APK。因此要排除 indoor 模型，只能把檔案實體移出該目錄（不存在 ignore 語法）。本資料夾即為移出後的存放位置。

## 相關程式碼位置

- 推論服務：`Android/lib/services/yoloe_inference.dart`
- AR 測試頁：`Android/lib/screens/yoloe_ar_test_screen.dart`
- 中文標籤對照：`Android/lib/core/yoloe_label_zh.dart`
- 伺服器避障規則（對齊對象）：`workflow_blindpath.py::_add_obstacle_visualization`（line 2353–2435）
- 伺服器障礙過濾：`obstacle_detector_client.py`（area > 0.7 過濾）

## 檔案完整性

| 檔案 | SHA256 |
|------|--------|
| `yoloe_26n_seg_indoor.onnx` | `cd42ab213a5340132de08a6e76f8ba230c7580cd9bd34e4cae6676deadc1e9bc` |
| `indoor_labels.json` | `d7f67c88534171baf7d0aa48ea1f7e2c4f096a93d074b97eb6cb2e5845f24799` |

（驗證於 2026-04-21。若未來要恢復部署，請先比對 hash 確認檔案未損毀。）
