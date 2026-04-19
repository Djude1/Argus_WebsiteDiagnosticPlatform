# model_client.py
# -*- coding: utf-8 -*-
"""
連接到 model_server.py 的客戶端。
提供與 ultralytics YOLO / ObstacleDetectorClient 相同的介面，
實際推論由 model_server 代勞，不佔本 process 的 GPU VRAM。

當 app_main.py 偵測到 MODEL_SERVER_PORT 環境變數時自動使用此模組。
"""

import os
import pickle
import socket
import struct
import threading
import logging
import numpy as np
import torch

logger = logging.getLogger("ModelClient")

_SERVER_HOST = os.getenv("MODEL_SERVER_HOST", "127.0.0.1")
_SERVER_PORT = int(os.getenv("MODEL_SERVER_PORT", "9099"))

# ──────────────────────────────────────────────────────────────────────────────
# 執行緒本地 TCP 連線（每個執行緒維持一條持久連線）
# ──────────────────────────────────────────────────────────────────────────────

_local = threading.local()


def _get_conn() -> socket.socket:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = socket.create_connection((_SERVER_HOST, _SERVER_PORT), timeout=15)
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        _local.conn = conn
    return conn


def _recv_exact(conn: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ConnectionResetError("model_server 連線中斷")
        buf.extend(chunk)
    return bytes(buf)


def _call(req: dict) -> list:
    """送出推論請求，回傳 FakeResult 列表；自動重連一次"""
    data   = pickle.dumps(req, protocol=pickle.HIGHEST_PROTOCOL)
    header = struct.pack(">I", len(data))
    for attempt in range(2):
        try:
            conn = _get_conn()
            conn.sendall(header + data)
            hdr    = _recv_exact(conn, 4)
            length = struct.unpack(">I", hdr)[0]
            resp   = _recv_exact(conn, length)
            items  = pickle.loads(resp)
            return [FakeResult(item) for item in items]
        except (OSError, ConnectionResetError) as e:
            logger.warning(f"model_server 連線失敗（嘗試 {attempt+1}/2）: {e}")
            _local.conn = None   # 下次重建連線
    logger.error("model_server 推論失敗，回傳空結果")
    return []


# ──────────────────────────────────────────────────────────────────────────────
# 模擬 ultralytics Results 物件
# ──────────────────────────────────────────────────────────────────────────────

class FakeBoxes:
    def __init__(self, cls, conf, xyxy=None):
        self.cls  = torch.from_numpy(cls)  if cls  is not None else torch.empty(0)
        self.conf = torch.from_numpy(conf) if conf is not None else torch.empty(0)
        self.xyxy = torch.from_numpy(xyxy) if xyxy is not None else torch.empty(0)


class FakeMasks:
    def __init__(self, data: np.ndarray):
        self.data = torch.from_numpy(data)


class FakeResult:
    def __init__(self, item: dict):
        self.orig_shape = item.get("orig_shape")
        self.names      = item.get("names", {})
        md = item.get("masks_data")
        self.masks = FakeMasks(md) if md is not None else None
        self.boxes = FakeBoxes(
            item.get("boxes_cls"),
            item.get("boxes_conf"),
            item.get("boxes_xyxy"),
        ) if item.get("has_boxes") else None


# ──────────────────────────────────────────────────────────────────────────────
# RemoteYOLO：替換 workflow_blindpath.py 使用的 YOLO 物件
# ──────────────────────────────────────────────────────────────────────────────

class RemoteYOLO:
    """介面與 ultralytics.YOLO 相同，實際推論委託給 model_server"""

    def __init__(self, model_name: str):
        self.model_name = model_name

    def predict(self, image, **kwargs):
        return _call({
            "model":  self.model_name,
            "img":    np.ascontiguousarray(image),
            "kwargs": kwargs,
        })

    # 以下為 YOLO / YOLOE 可能被呼叫的空操作方法
    def to(self, device):              return self
    def fuse(self):                    return self
    def set_classes(self, *a, **kw):   pass
    def get_text_pe(self, *a, **kw):   return None

    @property
    def device(self):
        return "remote"


# ──────────────────────────────────────────────────────────────────────────────
# RemoteObstacleDetector：替換 ObstacleDetectorClient
# ──────────────────────────────────────────────────────────────────────────────

class RemoteObstacleDetector:
    """
    介面與 ObstacleDetectorClient 相同（只需 .detect()）。
    model_server 端已預計算白名單特徵，此類不需要再設定。
    """

    def detect(self, image: np.ndarray, path_mask: np.ndarray = None) -> list:
        import cv2
        H, W = image.shape[:2]
        conf_thr = float(os.getenv("AIGLASS_OBS_CONF", "0.25"))

        results = _call({
            "model":  "yolo-obs",
            "img":    np.ascontiguousarray(image),
            "kwargs": {"verbose": False, "conf": conf_thr},
        })
        if not results or results[0].masks is None:
            return []

        r = results[0]
        num_boxes = len(r.boxes.cls) if (r.boxes is not None and r.boxes.cls is not None) else 0
        obstacles = []

        # 障礙物白名單（與 ObstacleDetectorClient 保持一致）
        _whitelist_lower = {
            'person', 'bicycle', 'car', 'motorcycle', 'bus', 'truck',
            'animal', 'scooter', 'stroller', 'dog',
            'pole', 'post', 'bollard', 'utility pole', 'light pole', 'signpost',
            'bench', 'chair', 'potted plant', 'hydrant', 'cone', 'stone', 'box',
            'trash can', 'barrel', 'cart',
            'fence', 'barrier', 'wall', 'gate', 'door',
            'rock', 'tree', 'branch', 'curb',
            'stairs', 'step', 'ramp', 'hole',
            'bag', 'suitcase', 'backpack',
            'table', 'ladder',
            'object', 'obstacle',
        }

        for i, mask_tensor in enumerate(r.masks.data):
            if i >= num_boxes:
                continue

            mask = mask_tensor.float().numpy()
            if mask.max() <= 1.0:
                mask = (mask > 0.5).astype(np.uint8) * 255
            else:
                mask = mask.astype(np.uint8)

            mask = cv2.resize(mask, (W, H), interpolation=cv2.INTER_NEAREST)
            area = int(np.sum(mask > 0))
            if area / (H * W) > 0.7:
                continue

            if path_mask is not None:
                if int(np.sum(cv2.bitwise_and(mask, path_mask) > 0)) < 30:
                    continue

            cls_id = int(r.boxes.cls[i])
            names  = r.names
            if isinstance(names, dict):
                class_name = names.get(cls_id, "Unknown")
            elif isinstance(names, (list, tuple)) and 0 <= cls_id < len(names):
                class_name = names[cls_id]
            else:
                class_name = "Unknown"

            # 白名單過濾：非障礙物類別（如 guide_bricks、sidewalk）略過
            if class_name.lower() not in _whitelist_lower:
                continue

            y_coords, x_coords = np.where(mask > 0)
            if len(y_coords) == 0:
                continue

            conf_val = float(r.boxes.conf[i]) if r.boxes.conf is not None else 0.5
            obstacles.append({
                "name":           class_name.strip(),
                "confidence":     conf_val,
                "mask":           mask,
                "area":           area,
                "area_ratio":     area / (H * W),
                "center_x":       float(np.mean(x_coords)),
                "center_y":       float(np.mean(y_coords)),
                "bottom_y_ratio": float(np.max(y_coords) / H),
            })

        return obstacles
