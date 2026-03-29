# yoloe_backend.py
# -*- coding: utf-8 -*-
from typing import List, Dict, Any, Optional, Tuple, Union
import os
import cv2
import numpy as np

# 兼容 YOLOE / YOLO
try:
    from ultralytics import YOLOE as _MODEL
except Exception:
    from ultralytics import YOLO as _MODEL

DEFAULT_MODEL_PATH = os.getenv("YOLOE_MODEL_PATH", r"C:\Users\Administrator\Desktop\rebuild1002\model\yoloe-11l-seg.pt")
TRACKER_CFG        = os.getenv("YOLO_TRACKER_YAML", "bytetrack.yaml")

class YoloEBackend:
    def __init__(self, model_path: Optional[str] = None, device: Optional[Union[str, int]] = None):
        self.model = _MODEL(model_path or DEFAULT_MODEL_PATH)
        self.model.to("cuda")
        self.device = device

    def set_text_classes(self, names: List[str]):
        # YOLOE 文本提示：与你模板一致
        self.model.set_classes(names, self.model.get_text_pe(names))

    def segment(self,
                frame_bgr: np.ndarray,
                conf: float = 0.20,
                iou: float = 0.45,
                imgsz: int = 640,
                persist: bool = True
                ) -> Dict[str, Any]:
        """
        返回:
          dict{
            'masks': List[np.uint8(H,W)],      # 0/1 mask
            'boxes': List[Tuple[x1,y1,x2,y2]],
            'cls_ids': List[int],
            'names': List[str],
            'ids': List[Optional[int]]
          }
        """
        r = self.model.track(
            frame_bgr,
            conf=conf, iou=iou, imgsz=imgsz,
            persist=persist, tracker=TRACKER_CFG, verbose=False
        )[0]

        out = {"masks": [], "boxes": [], "cls_ids": [], "names": [], "ids": []}
        masks_obj = getattr(r, "masks", None)
        boxes_obj = getattr(r, "boxes", None)

        if masks_obj is None or getattr(masks_obj, "data", None) is None:
            return out

        mask_arr = masks_obj.data.cpu().numpy()  # [N, h, w], float(0..1)
        H, W = frame_bgr.shape[:2]
        id2name = r.names if hasattr(r, "names") else {}
        N = mask_arr.shape[0]

        if boxes_obj is not None:
            xyxy = boxes_obj.xyxy.cpu().numpy()
            cls  = boxes_obj.cls.cpu().tolist()
            tids = boxes_obj.id.int().cpu().tolist() if boxes_obj.id is not None else [None]*N
        else:
            xyxy = [None]*N
            cls  = [0]*N
            tids = [None]*N

        for i in range(N):
            bin_mask = (mask_arr[i] > 0.5).astype(np.uint8)
            if bin_mask.shape[:2] != (H, W):
                bin_mask = cv2.resize(bin_mask, (W, H), interpolation=cv2.INTER_NEAREST)
            out["masks"].append(bin_mask)
            out["boxes"].append(tuple(xyxy[i]) if xyxy[i] is not None else None)
            cid = int(cls[i]) if cls is not None else 0
            out["cls_ids"].append(cid)
            out["names"].append(id2name.get(cid, str(cid)))
            out["ids"].append(int(tids[i]) if tids[i] is not None else None)
        return out
