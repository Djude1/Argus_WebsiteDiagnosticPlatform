#!/usr/bin/env python3
# ============================================
# 驗證腳本 - 驗證文件結構
# ============================================
"""
驗證 annotations.json 的文件結構是否正確
"""

import json
import io
import sys

# 設置 stdout 編碼為 UTF-8 (解決 Windows 編碼問題)
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 讀取並驗證
annotations_file = "data/annotations/annotations.json"

# 載出檔案
with open(annotations_file, "r", encoding="utf-8") as f:
    data = json.load(f)

    # 從 data 中取得 records 列表
    records = data.get("records", [])

    print("[OK] 檔案結構正確!")
    print(f"版本: {data.get('version', '1.0')}")
    print(f"最後更新: {data.get('last_updated')}")
    print(f"記錄總數: {data.get('total_records', 0)}")
    print(f"記錄列表: {len(records)}")

    # 打印每個記錄的詳細資訊
    for record in records:
        print(f"\n記錄 ID: {record['id']}")
        print(f"  類別: {record['class_name']}")
        print(f"  中文名: {record['class_name_cn']}")
        print(f"  信心度: {record['confidence']:.2f}")
        print(f"  時間戳: {record['timestamp']}")
        print(f"  會話 ID: {record.get('session_id')}")
        print(f"  圖片路徑: {record.get('image_path')}")
        print(f"  狀態: {record['status']}")
        print(f"  擁有者: {record.get('owner', '(空)')}")
        print(f"  描述: {record.get('description', '(空)')}")
        print(f"  自定義標籤: {record.get('custom_label', '(空)')}")
        print(f"  備註: {record.get('notes', '(空)')}")
        print(f"  額外資料: {record.get('extra_data', {})}")
        print("-" * 50)
