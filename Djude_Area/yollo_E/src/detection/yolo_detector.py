# ============================================
# YOLO 物件偵測器
# ============================================
"""
使用 Ultralytics YOLO 進行物件偵測
支援 YOLOE-26 開放詞彙實例分割模型

YOLOE-26 特性：
- 開放詞彙偵測：可偵測任何物品，不限於預訓練類別
- 文字提示功能：使用 set_classes() 指定要偵測的物品
- 實例分割：同時輸出邊界框和分割遮罩
"""

import time
import numpy as np
import cv2
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from pathlib import Path
from loguru import logger
import sys
from PIL import Image, ImageDraw, ImageFont

from detection.prompt_enhancer import PromptEnhancer

# 設定 loguru
logger.remove()
logger.add(
    sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>"
)


@dataclass
class BoundingBox:
    """邊界框"""

    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def center(self) -> tuple:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    def to_tuple(self) -> tuple:
        return (int(self.x1), int(self.y1), int(self.x2), int(self.y2))


@dataclass
class DetectionResult:
    """單一偵測結果"""

    bbox: BoundingBox
    confidence: float
    class_id: int
    class_name: str
    class_name_cn: str = ""  # 中文名稱

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bbox": self.bbox.to_tuple(),
            "confidence": self.confidence,
            "class_id": self.class_id,
            "class_name": self.class_name,
            "class_name_cn": self.class_name_cn,
        }


@dataclass
class FrameDetectionResult:
    """單一畫面的偵測結果"""

    detections: List[DetectionResult] = field(default_factory=list)
    inference_time_ms: float = 0.0
    fps: float = 0.0
    frame_shape: tuple = (0, 0, 0)

    @property
    def count(self) -> int:
        return len(self.detections)

    def get_by_class(self, class_name: str) -> List[DetectionResult]:
        """依類別名稱篩選結果"""
        return [d for d in self.detections if d.class_name == class_name]

    def get_high_confidence(self, threshold: float = 0.7) -> List[DetectionResult]:
        """取得高信心度結果"""
        return [d for d in self.detections if d.confidence >= threshold]


class YOLODetector:
    """YOLO 物件偵測器 - 支援 YOLOE 開放詞彙模型"""

    def __init__(
        self,
        model_path: str = "yoloe-26s-seg.pt",
        confidence_threshold: float = 0.5,
        iou_threshold: float = 0.45,
        device: str = "auto",
        prompt_classes: Optional[List[str]] = None,  # YOLOE 開放詞彙：指定要偵測的類別
        use_fp16: bool = True,  # 使用 FP16 半精度加速推論
    ):
        """
        初始化 YOLO 偵測器

        參數:
            model_path: 模型檔案路徑
            confidence_threshold: 信心度門檻
            iou_threshold: IOU 門檻
            device: 運算裝置 ("auto", "cuda", "cpu", "0", "1", ...)
            prompt_classes: YOLOE 開放詞彙功能 - 指定要偵測的物品類別列表
                           例如: ["cell phone", "bottle", "cup", "keys"]
                           設為 None 則使用模型的內建類別
            use_fp16: 是否使用 FP16 半精度加速（需要 GPU 支援）
        """
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.device = device
        self.prompt_classes = prompt_classes  # 開放詞彙偵測類別
        self.use_fp16 = use_fp16

        self.model = None
        self.class_names: Dict[int, str] = {}
        self._frame_count = 0
        self._total_inference_time = 0.0
        self._is_yoloe = False  # 標記是否為 YOLOE 模型
        self._cuda_available = False

        # 提示增強器：將簡短類別名轉為更精確的 CLIP 描述
        self._prompt_enhancer = PromptEnhancer()
        # 增強提示 → 原始類別名的映射（用於將偵測結果映射回簡短名稱）
        self._enhanced_to_original: Dict[str, str] = {}

        self._load_model()

    def _load_model(self):
        """載入 YOLO 模型 - 支援 YOLOE 開放詞彙模型"""
        try:
            # 判斷是否為 YOLOE 模型
            self._is_yoloe = "yoloe" in self.model_path.lower()

            if self._is_yoloe:
                # 載入 YOLOE 開放詞彙模型
                try:
                    from ultralytics import YOLOE

                    model_class = YOLOE
                    logger.info(f"正在載入 YOLOE 開放詞彙模型: {self.model_path}")
                except ImportError:
                    logger.warning("YOLOE 尚未支援，嘗試使用 YOLO 類別載入...")
                    from ultralytics import YOLO

                    model_class = YOLO
            else:
                # 載入一般 YOLO 模型
                from ultralytics import YOLO

                model_class = YOLO
                logger.info(f"正在載入 YOLO 模型: {self.model_path}")

            # 檢查模型檔案是否存在
            if not Path(self.model_path).exists():
                logger.warning(f"模型檔案不存在: {self.model_path}")
                logger.info("將自動從網路下載...")

            # 載入模型
            self.model = model_class(self.model_path)

            # 設定裝置
            if self.device == "auto":
                # 自動選擇最佳裝置
                self._cuda_available = self._check_cuda()
                target_device = "cuda:0" if self._cuda_available else "cpu"
                self.model.to(target_device)
            else:
                self.model.to(self.device)
                self._cuda_available = "cuda" in str(self.device).lower()

            # YOLOE 開放詞彙功能：設定要偵測的類別（使用增強提示）
            # 注意：必須在啟用 FP16 之前設定，因為 CLIP 模型需要 FP32
            if self._is_yoloe and self.prompt_classes:
                try:
                    enhanced, mapping = self._prompt_enhancer.enhance_list(self.prompt_classes)
                    self._enhanced_to_original = mapping

                    # 正確方式：使用 get_text_pe() 生成文字嵌入，再設定類別
                    # 這能大幅提升開放詞彙偵測的準確率
                    text_embeddings = self.model.get_text_pe(enhanced)
                    self.model.set_classes(enhanced, text_embeddings)

                    logger.info(f"設定開放詞彙偵測類別（共 {len(enhanced)} 個，已增強提示 + 文字嵌入）")
                    for orig, enh in zip(self.prompt_classes[:5], enhanced[:5]):
                        logger.debug(f"  {orig} → {enh}")
                    if len(self.prompt_classes) > 5:
                        logger.debug(f"  ... 及其他 {len(self.prompt_classes) - 5} 個類別")
                except Exception as e:
                    logger.warning(f"設定偵測類別失敗 (使用內建類別): {e}")
                    import traceback
                    logger.debug(traceback.format_exc())

            # FP16 半精度加速（僅在 CUDA 可用時啟用，且在 set_classes 之後）
            # 注意：CLIP 模型需要 FP32，所以必須先設定類別再啟用 FP16
            if self.use_fp16 and self._cuda_available:
                try:
                    self.model.model.half()  # 轉換為 FP16
                    logger.info("已啟用 FP16 半精度加速")
                except Exception as e:
                    logger.warning(f"FP16 加速啟用失敗: {e}")

            # 取得類別名稱
            self.class_names = self.model.names

            logger.success(f"模型載入成功！")
            if self._is_yoloe:
                logger.info(f"模型類型: YOLOE 開放詞彙實例分割模型")
            logger.info(f"類別數量: {len(self.class_names)}")
            logger.info(f"運算裝置: {self.device}")
            if self.use_fp16 and self._cuda_available:
                logger.info(f"FP16 加速: 已啟用")

        except ImportError:
            logger.error("請先安裝 ultralytics: pip install ultralytics")
            raise
        except Exception as e:
            logger.error(f"模型載入失敗: {e}")
            raise

    def _check_cuda(self) -> bool:
        """檢查 CUDA 是否可用"""
        try:
            import torch

            available = torch.cuda.is_available()
            if available:
                gpu_name = torch.cuda.get_device_name(0)
                logger.info(f"偵測到 GPU: {gpu_name}")
            return available
        except:
            return False

    def detect(
        self,
        image: np.ndarray,
        conf_threshold: Optional[float] = None,
        iou_threshold: Optional[float] = None,
        classes: Optional[List[int]] = None,
    ) -> FrameDetectionResult:
        """
        執行物件偵測

        參數:
            image: 輸入影像 (BGR 格式)
            conf_threshold: 覆寫信心度門檻
            iou_threshold: 覆寫 IOU 門檻
            classes: 只偵測特定類別 (class id 列表)

        回傳:
            FrameDetectionResult: 偵測結果
        """
        if self.model is None:
            raise RuntimeError("模型尚未載入")

        start_time = time.time()

        # 使用傳入的門檻值或預設值
        conf = conf_threshold if conf_threshold is not None else self.confidence_threshold
        iou = iou_threshold if iou_threshold is not None else self.iou_threshold

        # 執行推論
        # imgsz=640 是預設值，增加可提升準確率但會降低速度
        # 對於 YOLOE 開放詞彙模型，使用較高的解析度可以提升小物件的偵測率
        results = self.model(
            image,
            conf=conf,
            iou=iou,
            classes=classes,
            imgsz=640,  # 可調整為 1280 提升準確率（會降低速度）
            augment=False,  # 設為 True 可提升準確率但會大幅降低速度
            verbose=False
        )

        inference_time = (time.time() - start_time) * 1000  # 轉換為毫秒
        self._frame_count += 1
        self._total_inference_time += inference_time

        # 解析結果
        detections = []

        if results and len(results) > 0:
            result = results[0]

            if result.boxes is not None:
                boxes = result.boxes

                for i in range(len(boxes)):
                    # 取得邊界框
                    xyxy = boxes.xyxy[i].cpu().numpy()
                    bbox = BoundingBox(
                        x1=float(xyxy[0]), y1=float(xyxy[1]), x2=float(xyxy[2]), y2=float(xyxy[3])
                    )

                    # 取得信心度和類別
                    confidence = float(boxes.conf[i].cpu().numpy())
                    class_id = int(boxes.cls[i].cpu().numpy())
                    class_name = self.class_names.get(class_id, f"class_{class_id}")

                    # 將增強提示映射回原始簡短類別名
                    if self._enhanced_to_original and class_name in self._enhanced_to_original:
                        class_name = self._enhanced_to_original[class_name]

                    detection = DetectionResult(
                        bbox=bbox, confidence=confidence, class_id=class_id, class_name=class_name
                    )

                    detections.append(detection)

        # 計算 FPS
        avg_inference_time = self._total_inference_time / self._frame_count
        fps = 1000 / avg_inference_time if avg_inference_time > 0 else 0

        return FrameDetectionResult(
            detections=detections,
            inference_time_ms=inference_time,
            fps=fps,
            frame_shape=image.shape,
        )

    def draw_detections(
        self,
        image: np.ndarray,
        result: FrameDetectionResult,
        show_confidence: bool = True,
        show_label_cn: bool = True,
        box_thickness: int = 2,
        font_scale: float = 0.6,
    ) -> np.ndarray:
        """
        在影像上繪製偵測結果（支援中文顯示）

        參數:
            image: 輸入影像
            result: 偵測結果
            show_confidence: 是否顯示信心度
            show_label_cn: 是否顯示中文標籤
            box_thickness: 邊框粗細
            font_scale: 字體大小

        回傳:
            繪製後的影像
        """
        output = image.copy()

        # 使用 PIL 繪製中文
        pil_img = Image.fromarray(cv2.cvtColor(output, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)

        # 嘗試載入中文字體
        font_size = int(font_scale * 20)
        try:
            # Windows 系統字體
            font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", font_size)
        except:
            try:
                # 備用字體
                font = ImageFont.truetype("arial.ttf", font_size)
            except:
                font = ImageFont.load_default()

        for detection in result.detections:
            # 取得邊界框座標
            x1, y1, x2, y2 = detection.bbox.to_tuple()

            # 根據類別選擇顏色 (使用雜湊生成)
            color = self._get_color_for_class(detection.class_id)

            # 繪製邊界框 (使用 cv2)
            cv2.rectangle(output, (x1, y1), (x2, y2), color, box_thickness)

            # 準備標籤文字
            if show_label_cn and detection.class_name_cn:
                label = detection.class_name_cn
            else:
                label = detection.class_name

            if show_confidence:
                label += f" {detection.confidence:.2f}"

            # 計算文字大小
            bbox = draw.textbbox((0, 0), label, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            # 繪製標籤背景
            cv2.rectangle(output, (x1, y1 - text_height - 10), (x1 + text_width + 5, y1), color, -1)

        # 轉換回 PIL 繪製文字
        pil_img = Image.fromarray(cv2.cvtColor(output, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)

        for detection in result.detections:
            x1, y1, x2, y2 = detection.bbox.to_tuple()

            if show_label_cn and detection.class_name_cn:
                label = detection.class_name_cn
            else:
                label = detection.class_name

            if show_confidence:
                label += f" {detection.confidence:.2f}"

            # 繪製文字 (白色)
            draw.text((x1 + 2, y1 - text_height - 7), label, font=font, fill=(255, 255, 255))

        # 轉回 OpenCV 格式
        output = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        # 繪製 FPS 資訊 (英文，使用 cv2 即可)
        fps_text = f"FPS: {result.fps:.1f} | Objects: {result.count}"
        cv2.putText(output, fps_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        return output

    def _get_color_for_class(self, class_id: int) -> tuple:
        """根據類別 ID 生成顏色"""
        # 使用雜湊生成固定顏色
        np.random.seed(class_id * 123)
        color = tuple(map(int, np.random.randint(0, 255, 3)))
        return color

    def update_classes(self, new_classes: List[str]) -> bool:
        """
        動態更新開放詞彙偵測類別（YOLOE 專用，自動使用增強提示）

        參數:
            new_classes: 新的偵測類別列表（英文名稱）

        回傳:
            是否更新成功
        """
        if not self._is_yoloe:
            logger.warning("非 YOLOE 模型，無法動態更新偵測類別")
            return False

        if not new_classes:
            logger.warning("偵測類別列表為空，跳過更新")
            return False

        try:
            enhanced, mapping = self._prompt_enhancer.enhance_list(new_classes)
            self._enhanced_to_original = mapping
            self.model.set_classes(enhanced)
            self.prompt_classes = new_classes
            self.class_names = self.model.names
            logger.success(f"已更新偵測類別（共 {len(new_classes)} 個，已增強提示）")
            return True
        except Exception as e:
            logger.error(f"更新偵測類別失敗: {e}")
            return False

    def get_class_names(self) -> Dict[int, str]:
        """取得所有類別名稱"""
        return self.class_names.copy()

    def get_stats(self) -> Dict[str, Any]:
        """取得統計資訊"""
        avg_time = self._total_inference_time / self._frame_count if self._frame_count > 0 else 0
        return {
            "total_frames": self._frame_count,
            "total_inference_time_ms": self._total_inference_time,
            "avg_inference_time_ms": avg_time,
            "avg_fps": 1000 / avg_time if avg_time > 0 else 0,
        }


# ============================================
# 測試程式
# ============================================

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    # 載入環境變數
    load_dotenv()

    model_path = os.getenv("MODEL_PATH", "yoloe-26s-seg.pt")
    detection_classes_str = os.getenv("DETECTION_CLASSES", "")

    # 解析偵測類別（如果有設定）
    prompt_classes = None
    if detection_classes_str:
        prompt_classes = [c.strip() for c in detection_classes_str.split(",") if c.strip()]

    print("=" * 50)
    print("YOLOE 偵測器測試")
    print("=" * 50)
    print(f"模型: {model_path}")
    if prompt_classes:
        print(f"開放詞彙類別: {prompt_classes}")
    print("=" * 50)

    # 建立偵測器
    detector = YOLODetector(model_path=model_path, prompt_classes=prompt_classes)

    # 使用 Webcam 測試
    cap = cv2.VideoCapture(0)

    print("按 'q' 鍵結束")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # 執行偵測
            result = detector.detect(frame)

            # 繪製結果
            output = detector.draw_detections(frame, result)

            # 顯示結果
            cv2.imshow("YOLOE Detection Test", output)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except Exception as e:
        print(f"錯誤: {e}")
    finally:
        cap.release()
        cv2.destroyAllWindows()

        # 顯示統計
        stats = detector.get_stats()
        print("\n統計資訊:")
        print(f"  總幀數: {stats['total_frames']}")
        print(f"  平均 FPS: {stats['avg_fps']:.1f}")
