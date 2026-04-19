# model_server.py
# -*- coding: utf-8 -*-
"""
共用模型推論伺服器：載入所有 YOLO 模型一次，供多個 app_main.py instance 共用。
避免每個 instance 各自佔用 GPU VRAM。

啟動方式（由 start_multi_device.py 自動呼叫，或手動）：
    uv run python model_server.py

環境變數：
    MODEL_SERVER_HOST  伺服器綁定位址（預設 127.0.0.1）
    MODEL_SERVER_PORT  監聽 port（預設 9099）
"""

import asyncio
import os
import pickle
import struct
import logging
import torch

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ModelServer")

HOST = os.getenv("MODEL_SERVER_HOST", "127.0.0.1")
PORT = int(os.getenv("MODEL_SERVER_PORT", "9099"))

_models: dict = {}
_inference_locks: dict = {}  # 每個模型各自一把鎖，不同模型可並行推論

OBSTACLE_WHITELIST = [
    'person', 'bicycle', 'car', 'motorcycle', 'bus', 'truck',
    'animal', 'scooter', 'stroller', 'dog',
    'pole', 'post', 'bollard', 'utility pole', 'light pole', 'signpost',
    'bench', 'chair', 'potted plant', 'hydrant', 'cone', 'stone', 'box',
    'trash can', 'barrel', 'cart',
    'fence', 'barrier', 'wall', 'gate', 'door',
    'rock', 'tree', 'branch', 'curb',
    'stairs', 'step', 'ramp', 'hole',
    'bag', 'suitcase', 'backpack',
    'table', 'ladder', 'object', 'obstacle',
]


def _load_models() -> bool:
    """同步載入所有模型（在 executor 中執行）。
    相同路徑的 .pt 檔只載入一次，多個 key 共用同一個模型實例以節省 VRAM。"""
    from ultralytics import YOLO, YOLOE
    from config import BLIND_PATH_MODEL, OBSTACLE_MODEL, TRAFFICLIGHT_MODEL

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"使用設備: {device}")

    # 已載入路徑快取：path → model instance（避免同一 .pt 重複佔用 VRAM）
    _loaded: dict = {}

    def _load_standard_yolo(path: str, key: str) -> bool:
        """載入標準 YOLO；若路徑已載入則直接共用"""
        if not os.path.exists(path):
            logger.warning(f"找不到模型檔: {path}（{key}）")
            return False
        if path in _loaded:
            _models[key] = _loaded[path]
            logger.info(f"{key} 共用已載入模型: {path}")
            return True
        m = YOLO(path)
        m.to(device)
        _models[key] = m
        _loaded[path] = m
        logger.info(f"{key} 就緒（{path}）")
        return True

    # ── 盲道分割模型 ───────────────────────────────────────────────────────────
    _load_standard_yolo(BLIND_PATH_MODEL, "yolo-seg")

    # ── 障礙物偵測模型（嘗試 YOLOE；若路徑已載入或非 YOLOE 則用標準 YOLO）────
    if not os.path.exists(OBSTACLE_MODEL):
        logger.warning(f"找不到障礙物模型: {OBSTACLE_MODEL}")
    elif OBSTACLE_MODEL in _loaded:
        # 與盲道模型同一個檔案，直接共用
        _models["yolo-obs"] = _loaded[OBSTACLE_MODEL]
        _models["yolo-obs-is-yoloe"] = False
        logger.info(f"yolo-obs 共用已載入模型: {OBSTACLE_MODEL}")
    else:
        logger.info(f"載入障礙物模型: {OBSTACLE_MODEL}")
        try:
            obs = YOLOE(OBSTACLE_MODEL)
            obs.to(device)
            obs.fuse()
            with torch.inference_mode():
                embeddings = obs.get_text_pe(OBSTACLE_WHITELIST)
            obs.set_classes(OBSTACLE_WHITELIST, embeddings)
            _models["yolo-obs"] = obs
            _models["yolo-obs-is-yoloe"] = True
            _loaded[OBSTACLE_MODEL] = obs
            logger.info("yolo-obs 就緒（YOLOE 白名單特徵已預計算）")
        except Exception as yoloe_err:
            logger.info(f"非 YOLOE 模型（{yoloe_err}），改用標準 YOLO...")
            obs = YOLO(OBSTACLE_MODEL)
            obs.to(device)
            _models["yolo-obs"] = obs
            _models["yolo-obs-is-yoloe"] = False
            _loaded[OBSTACLE_MODEL] = obs
            logger.info(f"yolo-obs 就緒（標準 YOLO，類別: {list(obs.names.values())}）")

    # ── 紅綠燈模型 ─────────────────────────────────────────────────────────────
    _load_standard_yolo(TRAFFICLIGHT_MODEL, "trafficlight")

    logger.info(f"模型載入完成，共 {len(_models)} 個：{list(_models.keys())}")
    return len(_models) > 0


def _init_locks():
    """為每個已載入的模型建立推論鎖（必須在 event loop 內呼叫）。
    共用同一個模型實例的 key 會共用同一把鎖，避免並發推論同一模型。"""
    global _inference_locks
    id_to_lock: dict = {}
    _inference_locks = {}
    for name, obj in _models.items():
        if isinstance(obj, bool):
            # 跳過 "yolo-obs-is-yoloe" 這類 flag 值
            continue
        mid = id(obj)
        if mid not in id_to_lock:
            id_to_lock[mid] = asyncio.Lock()
        _inference_locks[name] = id_to_lock[mid]
    logger.info(f"推論鎖已建立：{list(_inference_locks.keys())}（共 {len(id_to_lock)} 把）")


def _run_inference(req: dict) -> list:
    """同步執行推論，回傳可序列化的結果（在 executor 執行緒中呼叫）"""
    model_name = req["model"]
    img = req["img"]          # numpy array (H, W, 3)
    kwargs = req.get("kwargs", {})

    model = _models.get(model_name)
    if model is None:
        return []

    # YOLOE 不支援 classes / half 參數；標準 YOLO 則保留
    if model_name == "yolo-obs":
        if _models.get("yolo-obs-is-yoloe", True):
            kwargs.pop("classes", None)
            kwargs.pop("half", None)

    try:
        with torch.inference_mode():
            results = model.predict(img, **kwargs)
        return _serialize(results)
    except Exception as e:
        logger.error(f"推論失敗 [{model_name}]: {e}")
        return []


def _serialize(results) -> list:
    """將 ultralytics Results 轉為可 pickle 的純 numpy 結構"""
    out = []
    for r in results:
        item: dict = {
            "orig_shape": r.orig_shape,
            "names":      r.names,
            "has_masks":  r.masks is not None,
            "has_boxes":  r.boxes is not None,
            "masks_data": None,
            "boxes_cls":  None,
            "boxes_conf": None,
            "boxes_xyxy": None,
        }
        if r.masks is not None and r.masks.data is not None:
            d = r.masks.data
            if d.dtype in (torch.bfloat16, torch.float16):
                d = d.float()
            item["masks_data"] = d.cpu().numpy()
        if r.boxes is not None:
            if getattr(r.boxes, "cls", None) is not None:
                item["boxes_cls"]  = r.boxes.cls.cpu().numpy()
            if getattr(r.boxes, "conf", None) is not None:
                item["boxes_conf"] = r.boxes.conf.cpu().numpy()
            if getattr(r.boxes, "xyxy", None) is not None:
                item["boxes_xyxy"] = r.boxes.xyxy.cpu().numpy()
        out.append(item)
    return out


async def _handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    addr = writer.get_extra_info("peername")
    try:
        while True:
            hdr = await reader.readexactly(4)
            length = struct.unpack(">I", hdr)[0]
            data   = await reader.readexactly(length)
            req    = pickle.loads(data)

            model_name = req.get("model", "unknown")
            lock = _inference_locks.get(model_name)
            loop = asyncio.get_event_loop()

            if lock is None:
                # 找不到對應模型，直接回傳空
                result = []
            elif lock.locked():
                # 同一模型正在被另一台裝置使用 → 跳過此幀，回傳空讓呼叫方用快取
                logger.debug(f"[{model_name}] 推論中，跳過此幀（呼叫方將使用快取結果）")
                result = []
            else:
                # 取得鎖，執行推論
                async with lock:
                    result = await loop.run_in_executor(None, _run_inference, req)

            resp = pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL)
            writer.write(struct.pack(">I", len(resp)) + resp)
            await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
        pass
    except Exception as e:
        logger.error(f"客戶端處理錯誤 {addr}: {e}")
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def _main():
    global _inference_locks

    logger.info("開始載入模型（可能需要 1-2 分鐘）...")
    loop = asyncio.get_event_loop()
    ok = await loop.run_in_executor(None, _load_models)
    if not ok:
        logger.error("沒有可用模型，退出")
        return

    _init_locks()  # 模型載入完成後，為每個模型建立各自的推論鎖

    server = await asyncio.start_server(_handle_client, HOST, PORT)
    logger.info(f"ModelServer 就緒，監聽 {HOST}:{PORT}")
    print(f"[ModelServer] READY {HOST}:{PORT}", flush=True)  # 供 start_multi_device.py 偵測
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(_main())
