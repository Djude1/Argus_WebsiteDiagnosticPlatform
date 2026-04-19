# YOLO 障礙物偵測模型訓練紀錄 v1

> 訓練日期：2026-04-10
> 模型：YOLO11s-seg（Small Segment）
> 產出：`model/obstacle-v1-seg.pt`（58.3 MB）

---

## 一、目的

替換現有的 YOLOE 開放詞彙模型（`model/yoloe-11l-seg.pt`），改用在專案標註資料上訓練的封閉詞彙分割模型，提升準確性、穩定性和速度。

## 二、訓練資料來源

**所有資料都來自你提供的 `YOLO訓練場/` 資料夾中的 zip 檔案，沒有額外新增任何資料。**

| 檔案 | 圖片數 | 類別數 | 使用狀態 |
|------|--------|--------|----------|
| `all.v1i.yolo26.zip` | 1,352 | 22 | ✓ 使用（主資料集，含 train/valid/test） |
| `11246034.v2i.yolo26.zip` | 338 | 20 | ✓ 使用（與主資料集不重複） |
| `11246041.v5i.yolo26 (1).zip` | 209 | 19 | ✗ 跳過（內容與主資料集 100% 重複） |

### 資料處理流程

1. 解壓兩個 zip 到暫存目錄
2. 類別精簡：22 類 → 14 類（排除店鋪、不相關號誌等）
3. 類別 ID 重新映射（兩個 zip 的 ID 順序不同）
4. 過濾掉 bbox 格式標註（僅保留 polygon 格式，分割訓練必需）
5. 以圖片為單位做分層抽樣，重新分割 train/val/test

### 合併後統計

| 分割 | 圖片數 |
|------|--------|
| train | 1,348 |
| val | 168 |
| test | 168 |
| **合計** | **1,684** |

### 類別分布

| ID | 類別名稱 | 標註數 | 說明 |
|----|----------|--------|------|
| 0 | person | 8,079 | 行人 |
| 1 | bicycle | 872 | 自行車 |
| 2 | car | 4,242 | 汽車 |
| 3 | motorcycle | 4,366 | 機車 |
| 4 | bus | 160 | 公車 |
| 5 | obstacle | 4,200 | 通用障礙物 |
| 6 | curb | 1,783 | 路緣（高低差） |
| 7 | stairs | 151 | 樓梯 |
| 8 | guide_bricks | 411 | 導盲磚 |
| 9 | crossing_crosswalk | 1,006 | 斑馬線 |
| 10 | crossing_green_light | 46 | 綠燈（polygon 標註極少） |
| 11 | crossing_red_light | 59 | 紅燈（polygon 標註極少） |
| 12 | green_sidewalk | 214 | 綠色人行道 |
| 13 | sidewalk | 81 | 人行道 |
| | **合計** | **25,670** | |

### 排除的類別

| 原類別 | 原因 |
|--------|------|
| 7-11, Metro, familymart | 店鋪識別，與避障無關 |
| irrelevant_crosswalk | 不相關斑馬線 |
| irrelevant_green/red/yellow_light | 不相關號誌 |
| crossing_yellow_light | 僅 1 筆標註，合併至 crossing_red_light |

## 三、測試資料說明

**測試集也是從你提供的照片中分割出來的。**

具體流程：

1. 將 `all.v1i.yolo26.zip`（已有 train/valid/test 分割）和 `11246034.v2i.yolo26.zip`（僅 train）合併
2. 合併後打散重新分割：80% train / 10% val / 10% test
3. 測試集的 168 張圖片來自你的 zip 中的原始照片

→ 也就是說，模型訓練從頭到尾只用了你放在 `YOLO訓練場/` 的照片，沒有從外部取得或生成任何額外資料。

## 四、模型配置

| 項目 | 設定 |
|------|------|
| 架構 | YOLO11s-seg（Small） |
| 預訓練權重 | `yolo11s-seg.pt`（COCO 預訓練） |
| 參數量 | 10,072,234 |
| GFLOPs | 32.8 |
| 輸入尺寸 | 640×640 |
| 訓練 epoch | 112（timeout 中斷，最佳 epoch = 102） |
| Batch size | 16 |
| Optimizer | AdamW（lr=0.001, weight_decay=0.0005） |
| 學習率排程 | 餘弦退火（lrf=0.01） |
| 混合精度 | FP16（AMP） |
| GPU | NVIDIA RTX 3060 Laptop（6GB VRAM） |

### 資料增強

| 增強 | 數值 | 說明 |
|------|------|------|
| hsv_h / hsv_s / hsv_v | 0.015 / 0.7 / 0.4 | 色彩抖動 |
| degrees | 5.0 | 小幅旋轉（眼鏡視角穩定） |
| translate | 0.1 | 平移 |
| scale | 0.5 | 縮放 |
| fliplr | 0.5 | 左右翻轉 |
| flipud | 0.0 | 不做上下翻轉（不符合實際場景） |
| mosaic | 1.0 | Mosaic 拼接 |
| mixup | 0.1 | 圖片混合 |
| copy_paste | 0.1 | 分割物件複製貼上 |

## 五、測試集評估結果

### 整體指標

| 指標 | 結果 | 驗收門檻 | 狀態 |
|------|------|----------|------|
| Box mAP50 | **0.661** | ≥ 0.60 | ✓ 通過 |
| Mask mAP50 | **0.637** | ≥ 0.50 | ✓ 通過 |
| Box mAP50-95 | **0.497** | — | 參考 |
| Mask mAP50-95 | **0.421** | — | 參考 |
| Box Precision | **0.744** | — | 參考 |
| Box Recall | **0.518** | ≥ 0.55 | ≈ 邊緣 |
| 推論速度（中位數） | **16.0 ms** | < 40 ms | ✓ 通過 |
| 推論速度（P95） | **26.5 ms** | — | 參考 |
| 模型大小 | **58.3 MB** | < 50 MB | ✗ 略超 |

### 每類別 AP50（測試集）

| ID | 類別 | Box AP50 | Mask AP50 | 判定 |
|----|------|----------|-----------|------|
| 0 | person | 0.744 | 0.708 | 優 |
| 1 | bicycle | 0.593 | 0.530 | 可 |
| 2 | car | 0.729 | 0.677 | 優 |
| 3 | motorcycle | 0.680 | 0.629 | 良 |
| 4 | bus | 0.600 | 0.600 | 可（樣本僅 10） |
| 5 | obstacle | 0.621 | 0.573 | 良 |
| 6 | curb | 0.743 | 0.712 | 優 |
| 7 | stairs | 0.833 | 0.699 | 優（樣本僅 14） |
| 8 | guide_bricks | 0.650 | 0.705 | 良 |
| 9 | crossing_crosswalk | **0.911** | **0.905** | 極優 |
| 10 | crossing_green_light | 0.320 | 0.320 | 差（polygon 標註僅 11） |
| 11 | crossing_red_light | 0.275 | 0.275 | 差（polygon 標註僅 10） |
| 12 | green_sidewalk | **0.884** | **0.922** | 極優 |
| 13 | sidewalk | 0.667 | 0.667 | 可（樣本僅 9） |

### 弱項分析

- **crossing_green/red_light**：原始標註大多是 bbox 格式，polygon 標註僅剩 46/59 筆，資料量嚴重不足。但這兩類由專用的紅綠燈模型 `trafficlight.pt` 負責偵測，對整體系統影響不大。
- **bus / stairs / sidewalk**：測試集樣本太少（10/14/9），AP 數值僅供參考。
- **Recall 0.518**：略低於 0.55 門檻。可透過降低推論時的 conf threshold（如 0.20 → 0.15）來提升 recall。

## 六、檔案結構

訓練相關的所有檔案都保留在 `YOLO訓練場/` 中：

```
YOLO訓練場/
├── all.v1i.yolo26.zip              # 原始資料（你提供的）
├── 11246034.v2i.yolo26.zip         # 原始資料（你提供的）
├── 11246041.v5i.yolo26 (1).zip     # 原始資料（重複，未使用）
├── yolo26l-seg.pt                  # 你提供的預訓練權重（未使用）
├── prepare_dataset.py              # 資料準備腳本
├── train.py                        # 訓練腳本
├── evaluate.py                     # 評估腳本
├── merged_dataset/                 # 合併後的資料集
│   ├── data.yaml
│   ├── class_distribution.txt
│   ├── train/images/ + labels/     # 1,348 張
│   ├── val/images/ + labels/       # 168 張
│   └── test/images/ + labels/      # 168 張
└── runs/obstacle_seg/v1_small/     # 訓練結果
    ├── weights/
    │   ├── best.pt                 # 最佳模型（epoch 102）→ 已複製到 model/
    │   ├── last.pt                 # 最後 epoch
    │   └── epoch{0,25,50,75,100}.pt  # checkpoint
    ├── results.csv                 # 訓練曲線數據
    ├── args.yaml                   # 訓練參數
    └── evaluation_report.txt       # 評估報告
```

產出模型：**`model/obstacle-v1-seg.pt`**（best.pt 的複本）

## 七、部署整合說明

目前模型已訓練完成並放在 `model/obstacle-v1-seg.pt`，但尚未整合進系統。要讓系統使用新模型，需要修改以下 4 個檔案：

### 1. `config.py`（1 行）

將 `OBSTACLE_MODEL` 的預設路徑從 `model/yoloe-11l-seg.pt` 改為 `model/obstacle-v1-seg.pt`。

### 2. `obstacle_detector_client.py`（核心改動）

現在這個檔案使用 `YOLOE`（開放詞彙模型），需改為標準 `YOLO`：

- **移除的東西**：
  - `from ultralytics import YOLOE` → 改為 `from ultralytics import YOLO`
  - `WHITELIST_CLASSES` 列表（46 個文字提示詞）— 封閉詞彙模型不需要
  - `whitelist_embeddings`、`get_text_pe()`、`set_classes()` — YOLOE 專用的文字特徵計算
  - `detect()` 方法中的 `self.model.set_classes(...)` 呼叫

- **保持不變的東西**：
  - GPU/AMP 配置（`DEVICE`、`AMP_POLICY`、`gpu_infer_slot()`）
  - `detect()` 中的所有後處理邏輯（mask resize、面積過濾 >70%、路徑重疊 ≥30px）
  - 回傳格式（`{name, mask, area, area_ratio, center_x, center_y, bottom_y_ratio}`）

- **原理**：YOLOE 需要先把文字提示轉成特徵向量再偵測；標準 YOLO 類別在訓練時就固定了，推論時直接輸出類別名稱，不需要文字提示。所以簡單來說就是「拿掉文字提示相關的程式碼」。

### 3. `model_server.py`（同步改動）

共用模型伺服器中，障礙物模型的載入方式也需從 `YOLOE` 改為 `YOLO`，並移除白名單特徵預計算。

### 4. `workflow_blindpath.py`（微調）

`_OBSTACLE_NAME_CN` 字典加入新類別的中文映射（例如 `curb → 路緣`、`stairs → 樓梯`），讓語音播報能正確說出中文。

### 回退機制

建議在 `.env` 中加入開關 `OBSTACLE_USE_YOLOE=true`，可隨時切回舊的 YOLOE 模型。

## 八、後續改進方向

1. **增加訓練資料**：目前僅 1,684 張，增加台灣街景資料可顯著提升效果
2. **紅綠燈模型**：現有 `trafficlight.pt` 是中國資料訓練，需研究或重新訓練台灣版
3. **升級 Medium**：若 Small 精度不夠，可嘗試 YOLO11m-seg（但要注意 6GB VRAM 限制）
4. **TensorRT 匯出**：可將推論速度再降低 30-50%
5. **降低 conf threshold**：從 0.25 降到 0.20 可提升 Recall，代價是更多誤報
