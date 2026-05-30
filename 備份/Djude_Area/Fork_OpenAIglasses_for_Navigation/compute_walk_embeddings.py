"""
A1: 預計算 yoloe-26n-seg 場景 Embedding
輸出：embeddings/outdoor.npy + indoor.npy（手機端不需要跑 Text Encoder）
"""
import os
import json
import torch
import numpy as np
from ultralytics import YOLOE

MODEL_PATH = "model/yoloe-26n-seg.pt"
OUT_DIR    = "embeddings"

SCENES = {
    "outdoor": [
        'person', 'bicycle', 'car', 'motorcycle', 'bus', 'truck',
        'animal', 'scooter', 'stroller', 'dog',
        'pole', 'post', 'bollard', 'utility pole', 'light pole', 'signpost',
        'bench', 'chair', 'potted plant', 'hydrant', 'cone', 'stone', 'box',
        'trash can', 'barrel', 'cart', 'fence', 'barrier', 'wall', 'gate', 'door',
        'rock', 'tree', 'branch', 'curb', 'stairs', 'step', 'ramp', 'hole',
        'bag', 'suitcase', 'backpack', 'table', 'ladder', 'object', 'obstacle',
    ],
    "indoor": [
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

def main():
    assert os.path.exists(MODEL_PATH), f"找不到模型：{MODEL_PATH}"
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"載入模型：{MODEL_PATH}")
    model = YOLOE(MODEL_PATH)

    for scene_name, labels in SCENES.items():
        print(f"\n計算 {scene_name}（{len(labels)} 個標籤）...")
        with torch.inference_mode():
            embeddings = model.get_text_pe(labels)

        npy_path   = os.path.join(OUT_DIR, f"{scene_name}.npy")
        json_path  = os.path.join(OUT_DIR, f"{scene_name}_labels.json")

        np.save(npy_path, embeddings.cpu().numpy())
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(labels, f, ensure_ascii=False, indent=2)

        print(f"  shape={embeddings.shape}  → {npy_path}")
        print(f"  標籤  → {json_path}")

    print("\n全部完成！")
    print(f"  {OUT_DIR}/outdoor.npy")
    print(f"  {OUT_DIR}/indoor.npy")

if __name__ == "__main__":
    main()
