"""
yoloe-11l-seg vs yoloe-26l-seg 效能比較測試腳本
比較模型大小、推理速度與信心分數
"""

import os
import sys
import time
import numpy as np
import cv2
from pathlib import Path

# 測試用文字提示（開放詞彙）
TEST_PROMPTS = ["person", "car", "dog", "bottle", "chair", "backpack"]

# 測試影像：優先使用現有圖片，否則建立合成影像
def get_test_image():
    # 嘗試尋找現有測試影像
    for pattern in ["*.jpg", "*.png"]:
        imgs = list(Path(".").rglob(pattern))
        # 過濾掉不必要的路徑
        imgs = [p for p in imgs if ".venv" not in str(p) and "node_modules" not in str(p)]
        if imgs:
            img = cv2.imread(str(imgs[0]))
            if img is not None:
                print(f"  使用測試影像：{imgs[0]}")
                return cv2.resize(img, (640, 480))

    # 建立合成測試影像（模擬真實場景）
    print("  建立合成測試影像（640x480）")
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    # 背景
    img[:] = (180, 200, 180)
    # 模擬道路
    cv2.rectangle(img, (200, 0), (440, 480), (100, 100, 100), -1)
    # 模擬盲道
    for i in range(0, 480, 40):
        cv2.rectangle(img, (220, i), (260, i + 30), (255, 220, 0), -1)
        cv2.rectangle(img, (380, i), (420, i + 30), (255, 220, 0), -1)
    # 模擬行人
    cv2.ellipse(img, (320, 150), (30, 40), 0, 0, 360, (200, 150, 100), -1)
    cv2.rectangle(img, (300, 190), (340, 300), (50, 100, 200), -1)
    # 模擬車輛
    cv2.rectangle(img, (80, 200), (160, 280), (0, 0, 200), -1)
    cv2.rectangle(img, (480, 250), (580, 340), (0, 200, 0), -1)
    return img


def test_model(model_path: str, model_name: str, test_img: np.ndarray, warmup_runs: int = 3, bench_runs: int = 10):
    """測試單一模型的效能"""
    from ultralytics import YOLO

    print(f"\n{'='*50}")
    print(f"測試模型：{model_name}")
    print(f"路徑：{model_path}")

    # 模型大小
    size_mb = os.path.getsize(model_path) / (1024 * 1024)
    print(f"模型大小：{size_mb:.1f} MB")

    # 載入模型
    t_load = time.time()
    model = YOLO(model_path)
    load_time = (time.time() - t_load) * 1000
    print(f"載入時間：{load_time:.0f} ms")

    # 設定開放詞彙類別
    try:
        model.set_classes(TEST_PROMPTS)
        print(f"開放詞彙設定：{TEST_PROMPTS} ✅")
        use_open_vocab = True
    except Exception as e:
        print(f"開放詞彙不支援，使用預設 COCO 類別：{e}")
        use_open_vocab = False

    # 暖機
    print(f"暖機 {warmup_runs} 次...")
    for _ in range(warmup_runs):
        _ = model(test_img, verbose=False)

    # 效能基準測試
    print(f"基準測試 {bench_runs} 次...")
    times = []
    all_results = []
    for _ in range(bench_runs):
        t0 = time.perf_counter()
        results = model(test_img, verbose=False)
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000)
        all_results.append(results)

    avg_ms = np.mean(times)
    std_ms = np.std(times)
    min_ms = np.min(times)
    max_ms = np.max(times)

    print(f"\n推理速度（ms/frame）：")
    print(f"  平均：{avg_ms:.1f} ± {std_ms:.1f}")
    print(f"  最快：{min_ms:.1f}  最慢：{max_ms:.1f}")

    # 分析最後一次結果的偵測
    last_results = all_results[-1][0]
    detections = []

    if last_results.boxes is not None and len(last_results.boxes) > 0:
        boxes = last_results.boxes
        for i in range(len(boxes)):
            conf = float(boxes.conf[i])
            cls_id = int(boxes.cls[i])
            # 取得類別名稱
            if use_open_vocab and cls_id < len(TEST_PROMPTS):
                cls_name = TEST_PROMPTS[cls_id]
            elif hasattr(model, 'names') and cls_id in model.names:
                cls_name = model.names[cls_id]
            else:
                cls_name = f"cls_{cls_id}"
            detections.append((cls_name, conf))

        detections.sort(key=lambda x: x[1], reverse=True)
        avg_conf = np.mean([d[1] for d in detections]) if detections else 0

        print(f"\n偵測結果（共 {len(detections)} 個）：")
        for cls_name, conf in detections[:5]:  # 顯示前 5 個
            print(f"  {cls_name}: {conf:.3f}")
        print(f"平均信心分數：{avg_conf:.3f}")
    else:
        print("\n偵測結果：無偵測到物件")
        avg_conf = 0.0
        detections = []

    # 分割遮罩
    if last_results.masks is not None:
        n_masks = len(last_results.masks)
        print(f"分割遮罩數量：{n_masks}")
    else:
        print("分割遮罩：無")

    return {
        "name": model_name,
        "path": model_path,
        "size_mb": size_mb,
        "load_ms": load_time,
        "avg_ms": avg_ms,
        "std_ms": std_ms,
        "min_ms": min_ms,
        "max_ms": max_ms,
        "n_detections": len(detections),
        "avg_conf": avg_conf,
        "detections": detections[:5],
        "use_open_vocab": use_open_vocab,
    }


def download_model_if_needed(model_name: str, save_path: str) -> bool:
    """若模型不存在則透過 ultralytics 下載"""
    if os.path.exists(save_path):
        print(f"  模型已存在：{save_path}")
        return True

    print(f"  下載 {model_name} 中...")
    try:
        from ultralytics import YOLO
        # ultralytics 會自動下載並快取模型
        model = YOLO(model_name)
        # 確認下載後快取位置
        import ultralytics
        cache_dir = Path(ultralytics.__file__).parent.parent / "weights"
        # 尋找快取
        candidates = [
            Path.home() / ".config" / "Ultralytics" / model_name,
            Path(model_name),
        ]
        for c in candidates:
            if c.exists():
                import shutil
                shutil.copy(c, save_path)
                print(f"  已複製到 {save_path}")
                return True
        print(f"  模型已載入（快取位置未知），將直接使用 '{model_name}' 名稱")
        return True  # 可以直接用名稱載入
    except Exception as e:
        print(f"  下載失敗：{e}")
        return False


def print_comparison_table(results: list):
    """輸出比較表格"""
    print("\n" + "="*70)
    print("模型效能比較報告")
    print("="*70)

    headers = ["指標", "yoloe-11l-seg", "yoloe-26l-seg"]
    rows = []

    def get_val(r, key, fmt="{:.1f}"):
        return fmt.format(r[key]) if r else "N/A"

    r11 = next((r for r in results if "11l" in r["name"]), None)
    r26l = next((r for r in results if "26l" in r["name"]), None)
    r26s = next((r for r in results if "26s" in r["name"]), None)

    # 若有 26s，也加入比較
    if r26s:
        headers.append("yoloe-26s-seg")

    def row(label, key, fmt="{:.1f}", suffix=""):
        vals = [label, get_val(r11, key, fmt) + suffix, get_val(r26l, key, fmt) + suffix]
        if r26s:
            vals.append(get_val(r26s, key, fmt) + suffix)
        return vals

    rows = [
        row("大小 (MB)", "size_mb", "{:.1f}", " MB"),
        row("載入時間 (ms)", "load_ms", "{:.0f}", " ms"),
        row("平均推理速度", "avg_ms", "{:.1f}", " ms"),
        row("最快推理速度", "min_ms", "{:.1f}", " ms"),
        row("推理速度標準差", "std_ms", "{:.1f}", " ms"),
        row("偵測物件數", "n_detections", "{:.0f}", " 個"),
        row("平均信心分數", "avg_conf", "{:.3f}", ""),
    ]

    # 計算欄寬
    col_widths = [max(len(str(r[i])) for r in [headers] + rows) + 2 for i in range(len(headers))]

    # 列印表格
    sep = "+" + "+".join("-" * w for w in col_widths) + "+"
    print(sep)
    print("|" + "|".join(str(h).center(col_widths[i]) for i, h in enumerate(headers)) + "|")
    print(sep.replace("-", "="))
    for row_data in rows:
        print("|" + "|".join(str(v).center(col_widths[i]) for i, v in enumerate(row_data)) + "|")
        print(sep)

    # 建議
    print("\n建議：")
    if r26l:
        speedup = r11["avg_ms"] / r26l["avg_ms"] if r26l["avg_ms"] > 0 else 1
        size_ratio = r26l["size_mb"] / r11["size_mb"] if r11 else 1
        if speedup > 1.2:
            print(f"  yoloe-26l 比 yoloe-11l 快 {speedup:.1f}x，且大小比率 {size_ratio:.1f}x")
        elif speedup < 0.8:
            print(f"  yoloe-26l 比 yoloe-11l 慢 {1/speedup:.1f}x，但可能精度更高")
        else:
            print(f"  兩模型推理速度相近（差異 < 20%）")

        # 針對眼鏡應用的建議
        print(f"\n  >> 針對 AI 智慧眼鏡即時應用（目標 < 100ms/frame）：")
        if r11 and r11["avg_ms"] < 100:
            print(f"    yoloe-11l 推理 {r11['avg_ms']:.0f}ms - [OK] 適合即時應用")
        if r26l and r26l["avg_ms"] < 100:
            print(f"    yoloe-26l 推理 {r26l['avg_ms']:.0f}ms - [OK] 適合即時應用")
        elif r26l:
            print(f"    yoloe-26l 推理 {r26l['avg_ms']:.0f}ms - [警告] 可能過慢，需考量")


def main():
    print("yoloe 模型效能比較測試")
    print(f"測試提示詞：{TEST_PROMPTS}")

    # 取得測試影像
    print("\n準備測試影像...")
    test_img = get_test_image()
    print(f"  影像尺寸：{test_img.shape}")

    # 定義待測模型
    models_to_test = [
        {
            "path": "model/yoloe-11l-seg.pt",
            "name": "yoloe-11l-seg",
            "download_name": None,  # 已存在
        },
        {
            "path": "model/yoloe-26l-seg.pt",
            "name": "yoloe-26l-seg",
            "download_name": "yoloe-26l-seg.pt",  # 需要下載
        },
    ]

    # 若 yoloe-26s-seg.pt 存在，也加入比較
    if os.path.exists("yollo_E/yoloe-26s-seg.pt"):
        models_to_test.append({
            "path": "yollo_E/yoloe-26s-seg.pt",
            "name": "yoloe-26s-seg",
            "download_name": None,
        })

    # 下載缺少的模型
    print("\n檢查模型...")
    for m in models_to_test:
        if not os.path.exists(m["path"]) and m["download_name"]:
            print(f"\n需要下載 {m['name']}...")
            success = download_model_if_needed(m["download_name"], m["path"])
            if not success:
                # 嘗試直接用名稱
                m["path"] = m["download_name"]

    # 執行測試
    results = []
    for m in models_to_test:
        path = m["path"]
        if not os.path.exists(path) and path == m.get("download_name"):
            # 讓 ultralytics 自動下載
            pass
        elif not os.path.exists(path):
            print(f"\n⚠️  跳過 {m['name']}：路徑不存在 ({path})")
            continue

        try:
            result = test_model(path, m["name"], test_img)
            results.append(result)
        except Exception as e:
            print(f"\n❌ 測試 {m['name']} 失敗：{e}")
            import traceback
            traceback.print_exc()

    # 輸出比較表格
    if len(results) >= 2:
        print_comparison_table(results)
    elif len(results) == 1:
        print(f"\n只有一個模型測試成功，無法比較")
    else:
        print("\n❌ 沒有模型測試成功")

    return results


if __name__ == "__main__":
    results = main()
