# 模型本地化計畫（On-Device Inference）

> 狀態：構想中，尚未動工  
> 記錄日期：2026-04-12

---

## 背景

目前架構：

```
手機相機 → WiFi → 伺服器（YOLO + TTS）→ WiFi → APP（播放音訊）
```

每一幀畫面跨網路走兩次，導致：
- 依賴穩定 WiFi
- 增加感知延遲（網路 RTT + 排隊）
- 伺服器故障時視障者完全無法使用

---

## 評估結論

### 語音（TTS / 預錄 WAV）
- **可行，低風險**，已完成（見語音本地化實作）
- 預錄 WAV 打包進 APK，`flutter_tts` 補 fallback

### YOLO 模型
- **可行，中等風險**，取決於目標手機型號

| 項目 | 現況（伺服器 GPU） | 手機 NPU 目標 |
|------|-------------------|--------------|
| 模型 | ALL.pt（YOLO11s-seg，14類）| TFLite INT8 量化 |
| 推論速度 | ~15ms/幀 | ~30–80ms/幀（中高階手機）|
| 精度損失 | - | 量化後 1–3% mAP 下降 |
| 模型大小 | ~30MB（fp32） | ~8–12MB（INT8） |
| 功耗 | 伺服器電費 | 手機電池，連續使用發熱 |

---

## 轉換步驟（供未來參考）

```bash
# 1. 匯出 ONNX
uv run python -c "from ultralytics import YOLO; YOLO('YOLO測試場/ALL.pt').export(format='onnx', imgsz=640, simplify=True)"

# 2. ONNX → TFLite（需 ai-edge-torch 或 onnx2tf）
pip install onnx2tf
onnx2tf -i ALL.onnx -o tflite_output

# 3. INT8 量化（需代表性資料集）
# 參考 TFLite 量化文件

# 4. Flutter 整合
# flutter pub add tflite_flutter
# 放入 Android/assets/model/all.tflite
```

---

## 目標手機規格門檻

| 規格 | 最低需求 |
|------|---------|
| SoC | Snapdragon 778G / Dimensity 1200 以上 |
| RAM | 6GB 以上 |
| 推論目標 | 15fps（66ms/幀）以內 |

建議先用 **Pixel 8 / Samsung S24** 驗證，再擴大支援。

---

## 架構變化

**現況**
```
ESP32 → WiFi → Python Server（YOLO + TTS）→ WiFi → APP
```

**本地化後**
```
手機相機 → 手機 NPU（YOLO）→ 手機喇叭（本地 WAV）
                    ↕（非即時，選填）
              雲端 Gemini（場景描述 / 語音對話）
```

ESP32 在此架構下**不再需要**，眼鏡硬體設計需對應調整。

---

## 待決定

- [ ] 確認目標手機型號
- [ ] 驗證 ALL.pt → TFLite 轉換後 mask 輸出是否正確
- [ ] 評估分割模型在手機上的電池消耗（連續10分鐘導航）
- [ ] 決定是否保留 ESP32 作為攝影機輸入，僅 YOLO 本地化
