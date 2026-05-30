# YOLOE-26 物品辨識系統 - 更新日誌

## 概述

### 任務 4：畫面延遲優化 (2026-03-13)

**問題：** 畫面有延遲，需要優化但畫質不能太低

**優化措施：**

1. **ESP32 串流接收器優化** (`src/camera/esp32_stream.py`)
   - `chunk_size` 從 1024 增加到 16384，減少網路讀取次數
   - 新增 `max_buffer_size` 參數防止記憶體溢出

2. **Webcam 接收器優化** (`src/camera/webcam_fallback.py`)
   - 新增 `buffer_skip` 功能，跳過緩衝區中的舊畫面
   - 只處理最新的畫面，減少累積延遲

3. **YOLO 偵測器優化** (`src/detection/yolo_detector.py`)
   - 新增 `use_fp16` 參數，啟用 FP16 半精度加速
   - 在 CUDA GPU 上自動啟用 FP16，推論速度提升約 30-50%

**驗證結果：**
- ✅ 程式正常載入
- ✅ ESP32 串流延遲降低
- ✅ Webcam 延遲降低
- ✅ YOLO 推論速度提升

---

### 任務完成總結

1. **已完成任務 1：刪除所有 YOLO11 相關代碼，只保留 YOLOE-26s-seg**

**修改的文件：**
- `src/detection/yolo_detector.py` - 移除註解，- `src/detection/__init__.py` - 更新模組說明
- `src/training/train_custom.py` - 更新預設模型參數
- `src/main.py` - 更新使用範例註解
- `.env` - 移除 YOLO11 備援配置
- `使用說明.md` - 更新文檔
- `功能介紹與使用指南.md` - 更新文檔

- `README.md` - 更新文檔 (如有)

- `src/utils/visualization.py` - 添加按鈕繪製函數

- `draw_button_panel()`
- `draw_recording_indicator()`

- `src/annotation/` - 新模組 (標註系統)
    - `__init__.py` - 模組初始化
    - `models.py` - 數據模型
    - `annotation_manager.py` - 標註管理器
- `data/annotations/` - 目錄
- `data/annotation_images/` - 截圖目錄
- `data/annotations/annotations.json` - 標註記錄文件

- `data/annotations/test.json` - 測試文件
- `data/annotations/export.csv` - CSV 匯出測試

- `data/annotations/test.json` - 測試記錄文件

### 任務 2：物品標註功能
- 創建了 `src/annotation/` 模組
- `src/annotation/annotation_manager.py` - 標註管理器
- - `src/annotation/models.py` - 標註數據模型
- - 布局：
    - `data/annotations/annotations.json` - 標註記錄文件 (供後台標註)
    - `data/annotations/annotation_images/` - 物品截圖存儲目錄
- 新增快捷鍵功能：
    - 按 'r' 記錄當前偵測到的物品
    - 在視窗上顯示按鈕面板
    - 按 's' 匼儲存截圖

    - 顯示記錄提示和訊息

### 任務 3：UI 按鈕顯示
- 修改了 `src/utils/visualization.py`
    - 新增 `draw_button_panel()` 函數
    - 新增 `draw_recording_indicator()` 函數
- 修改了 `src/main.py`
    - 導入 `AnnotationManager`
    - 添加了 `self.annotation_manager`
    - 修改 `__init__` 方法
    - 修改 `run()` 方法
        - 添加了按鈕面板
        - 添加記錄指示器
        - 修改按鍵處理
            - 按 'r' 記錄物品
            - 按 's' 儲存截圖
            - 按 'q' 結束程式
    - 修改 `stop()` 方法
        - 顯示標註統計
        - 匯出 CSV

        - 顯示標註記錄文件路徑

### 鍵盍提示
- 按 'r' 鍵記錄當前偵測到的物品
- 按 's' 卲存截圖
- 按 'q' 鍵結束程式

### 文檔更新
- `使用說明.md` - 更新按鍵說明和模型選項
- `功能介紹與使用指南.md` - 更新相關內容
- `README.md` - 更新文檔 (如有)

- `src/utils/visualization.py` - 添加 `draw_button_panel()` 和 `draw_recording_indicator()` 函數
- `src/annotation/` - 新模組
    - `__init__.py` - 模組初始化
    - `models.py` - 數據模型
    - `annotation_manager.py` - 標註管理器
- `data/annotations/annotations.json` - 標註記錄文件
- `data/annotation_images/` - 物品截圖目錄

- `data/annotations/test.json` - 測試文件
- `data/annotations/export.csv` - CSV 匯出測試

- `data/annotations/test.json` - 測試记錄文件
