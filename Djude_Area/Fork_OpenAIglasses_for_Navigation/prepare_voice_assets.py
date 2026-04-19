# prepare_voice_assets.py
# 將 voice/ 目錄的預錄 WAV 複製到 Android/assets/audio/
# 使用 SHA256 前 16 碼作為檔名，避免中文路徑問題
# 並生成 Android/assets/voice_map.json（text → hash_filename）
#
# 執行：uv run python prepare_voice_assets.py

import os
import json
import shutil
import hashlib

VOICE_DIR    = os.path.join(os.path.dirname(__file__), "voice")
MAP_FILE     = os.path.join(VOICE_DIR, "map.zh-CN.json")
ASSETS_DIR   = os.path.join(os.path.dirname(__file__), "Android", "assets", "audio")
OUT_MAP_FILE = os.path.join(os.path.dirname(__file__), "Android", "assets", "voice_map.json")

def text_to_hash(text: str) -> str:
    """文字 → SHA256 前 16 碼（足夠唯一，不會碰撞）"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

def main():
    os.makedirs(ASSETS_DIR, exist_ok=True)

    with open(MAP_FILE, "r", encoding="utf-8") as f:
        voice_map = json.load(f)

    out_map = {}   # text → {hash_file, duration_ms}
    copied = 0
    skipped = 0
    missing = 0

    for text, info in voice_map.items():
        files = (info or {}).get("files") or []
        if not files:
            continue

        src_fname = files[0]
        # 支援 ../music/XXX.WAV 相對路徑
        if src_fname.startswith("../"):
            src_path = os.path.join(VOICE_DIR, "..", src_fname[3:])
        else:
            src_path = os.path.join(VOICE_DIR, src_fname)

        src_path = os.path.normpath(src_path)
        if not os.path.exists(src_path):
            print(f"  [缺失] {text} → {src_path}")
            missing += 1
            continue

        h = text_to_hash(text)
        dst_fname = f"{h}.wav"
        dst_path  = os.path.join(ASSETS_DIR, dst_fname)

        if not os.path.exists(dst_path):
            shutil.copy2(src_path, dst_path)
            copied += 1
        else:
            skipped += 1

        out_map[text] = {
            "file":        dst_fname,
            "duration_ms": (info or {}).get("duration_ms", 2000),
        }

    with open(OUT_MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(out_map, f, ensure_ascii=False, indent=2)

    print(f"\n完成：複製 {copied}，已存在 {skipped}，缺失 {missing}")
    print(f"輸出 map：{OUT_MAP_FILE}（共 {len(out_map)} 筆）")
    print(f"資產目錄：{ASSETS_DIR}")

if __name__ == "__main__":
    main()
