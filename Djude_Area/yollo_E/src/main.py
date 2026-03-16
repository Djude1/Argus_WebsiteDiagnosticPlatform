#!/usr/bin/env python3
# ============================================
# YOLO 日常物品辨識系統 - 主程式
# ============================================
"""
主程式入口
整合 ESP32 串流、YOLO 辨識、資料庫記錄、物品標註功能
"""

import argparse
import signal
import sys
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List

import cv2
import numpy as np
from loguru import logger
import tkinter as tk
from tkinter import ttk, messagebox

# 設定 loguru
logger.remove()
logger.add(
    sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>"
)

# 支援直接執行和套件匯入兩種模式
if __name__ == "__main__" and __package__ is None:
    # 直接執行時，添加 src 目錄到路徑
    _src_path = Path(__file__).resolve().parent
    if str(_src_path) not in sys.path:
        sys.path.insert(0, str(_src_path))
    from config import get_config, get_esp32_stream_url, get_model_path, get_db_path
    from camera.esp32_stream import ESP32StreamReceiver
    from camera.webcam_fallback import WebcamReceiver
    from detection.yolo_detector import YOLODetector, FrameDetectionResult
    from detection.label_mapper import LabelMapper
    from database.db_manager import DatabaseManager
    from database.item_logger import ItemLogger, LoggerConfig
    from utils.visualization import (
        draw_detections,
        draw_fps,
        draw_info_panel,
        draw_button,
        draw_help_panel,
        draw_recording_indicator,
        save_detection_image,
    )
    from annotation.annotation_manager import AnnotationManager, AnnotationConfig
    from annotation.models import AnnotationRecord, AnnotationStatus
else:
    # 套件匯入模式
    from .config import get_config, get_esp32_stream_url, get_model_path, get_db_path
    from .camera.esp32_stream import ESP32StreamReceiver
    from .camera.webcam_fallback import WebcamReceiver
    from .detection.yolo_detector import YOLODetector, FrameDetectionResult
    from .detection.label_mapper import LabelMapper
    from .database.db_manager import DatabaseManager
    from .database.item_logger import ItemLogger, LoggerConfig
    from .utils.visualization import (
        draw_detections,
        draw_fps,
        draw_info_panel,
        draw_button,
        draw_help_panel,
        draw_recording_indicator,
        save_detection_image,
    )
    from .annotation.annotation_manager import AnnotationManager, AnnotationConfig
    from .annotation.models import AnnotationRecord, AnnotationStatus


class YOLODetectionSystem:
    """YOLO 辨識系統主類別"""

    def __init__(
        self,
        source: str = "esp32",
        model_path: str = None,
        use_custom_model: bool = False,
        confidence: float = 0.5,
        save_to_db: bool = True,
        save_images: bool = False,
        display: bool = True,
    ):
        """
        初始化辨識系統

        參數:
            source: 影像來源 ("esp32" 或 "webcam")
            model_path: 模型路徑
            use_custom_model: 是否使用自定義模型
            confidence: 信心度門檻
            save_to_db: 是否儲存到資料庫
            save_images: 是否儲存辨識圖片
            display: 是否顯示影像
        """
        self.source = source
        self.confidence = confidence
        self.save_to_db = save_to_db
        self.save_images = save_images
        self.display = display

        # 載入配置
        self.config = get_config()

        # 設定模型路徑
        if model_path:
            self.model_path = model_path
        else:
            self.model_path = get_model_path(use_custom=use_custom_model)

        # 初始化元件
        self.camera = None
        self.detector = None
        self.label_mapper = LabelMapper()
        self.db_manager = None
        self.item_logger = None
        self.annotation_manager = None

        # 狀態
        self.running = False
        self.frame_count = 0
        self.start_time = None

        # 記錄狀態
        self.is_recording = False
        self.last_record_time = 0
        self.record_message = ""
        self.record_message_time = 0

        logger.info("YOLO 辨識系統初始化中...")

    def initialize(self) -> bool:
        """初始化所有元件"""
        try:
            # 確保目錄存在
            data_dir = Path(__file__).parent.parent / "data"
            annotations_dir = data_dir / "annotations"
            annotation_images_dir = data_dir / "annotation_images"

            annotations_dir.mkdir(parents=True, exist_ok=True)
            annotation_images_dir.mkdir(parents=True, exist_ok=True)

            # 初始化標註管理器
            annotation_config = AnnotationConfig(
                annotation_file=str(annotations_dir / "annotations.json"),
                image_dir=str(annotation_images_dir),
                auto_save=True,
            )
            self.annotation_manager = AnnotationManager(annotation_config)
            logger.info("標註管理器已初始化")

            # 初始化資料庫
            if self.save_to_db:
                self.db_manager = DatabaseManager(str(get_db_path()))
                logger_config = LoggerConfig(
                    save_images=self.save_images, min_confidence=self.confidence, dedup_interval=5.0
                )
                self.item_logger = ItemLogger(self.db_manager, logger_config)
                logger.info("資料庫已初始化")

            # 解析開放詞彙偵測類別 (YOLOE 模型專用)
            prompt_classes = None
            if self.config.model.detection_classes:
                prompt_classes = [
                    c.strip() for c in self.config.model.detection_classes.split(",") if c.strip()
                ]
                logger.info(f"開放詞彙偵測類別: {prompt_classes}")

            # 初始化 YOLO 偵測器
            self.detector = YOLODetector(
                model_path=self.model_path,
                confidence_threshold=self.confidence,
                device="auto",
                prompt_classes=prompt_classes,  # 傳遞開放詞彙類別
            )
            logger.info(f"YOLO 模型已載入: {self.model_path}")

            # 初始化攝影機
            if self.source == "esp32":
                self.camera = ESP32StreamReceiver(
                    esp32_ip=self.config.esp32.ip,
                    port=self.config.esp32.port,
                    stream_path=self.config.esp32.stream_path,
                )
                logger.info(f"ESP32 串流接收器已初始化: {self.config.esp32.stream_url}")
            else:
                self.camera = WebcamReceiver(
                    camera_index=0,
                    width=self.config.camera.frame_width,
                    height=self.config.camera.frame_height,
                )
                logger.info("Webcam 接收器已初始化")

            return True

        except Exception as e:
            logger.error(f"初始化失敗: {e}")
            import traceback

            traceback.print_exc()
            return False

    def run(self):
        """執行辨識系統"""
        if not self.initialize():
            logger.error("系統初始化失敗，無法啟動")
            return

        logger.info("=" * 50)
        logger.info("YOLO 日常物品辨識系統啟動")
        logger.info("=" * 50)
        logger.info(f"影像來源: {self.source}")
        logger.info(f"模型: {self.model_path}")
        logger.info(f"信心度門檻: {self.confidence}")
        logger.info("按 'q' 鍵結束程式")
        logger.info("按 'r' 鍵記錄當前偵測到的物品")
        logger.info("按 's' 鍵儲存當前畫面")
        logger.info("=" * 50)

        # 開始辨識會話
        session_id = None
        if self.item_logger:
            session_id = self.item_logger.start_session(
                source=self.source,
                source_ip=self.config.esp32.ip if self.source == "esp32" else None,
            )

        self.running = True
        self.start_time = time.time()
        self.frame_count = 0

        try:
            # 連接攝影機
            if not self.camera.connect():
                logger.error("無法連接到影像來源")
                return

            # 主迴圈
            while self.running:
                # 讀取畫面
                ret, frame = self.camera.read_frame()
                if not ret or frame is None:
                    logger.warning("無法讀取畫面")
                    continue

                self.frame_count += 1

                current_time = time.time()

                # 執行 YOLO 辨識
                result = self.detector.detect(frame)

                # 為每個 detection 設置中文標籤（從 LabelMapper 取得）
                for detection in result.detections:
                    if not detection.class_name_cn:
                        # 使用 LabelMapper 取得中文名稱
                        detection.class_name_cn = self.label_mapper.get_chinese_name_from_en(
                            detection.class_name
                        )

                # 記錄到資料庫
                if self.item_logger:
                    self.item_logger.log_frame(result, frame)

                # 顯示結果
                if self.display:
                    # 繪製偵測結果（使用 YOLO 原始標籤）
                    output = draw_detections(
                        frame,
                        result,
                        show_label_cn=True,  # 使用 class_name_cn
                    )

                    # 顯示資訊面板
                    info = {
                        "FPS": f"{result.fps:.1f}",
                        "Objects": result.count,
                        "Source": self.source,
                    }
                    output = draw_info_panel(output, info, position=(10, 30))

                    # 繪製按鍵面板（使用英文）
                    button_y = output.shape[0] - 100
                    output = draw_help_panel(output, position=(10, button_y))

                    # 繪製記錄指示器
                    if self.is_recording:
                        output = draw_recording_indicator(
                            output, True, position=(output.shape[1] - 150, 10)
                        )

                    # 顯示記錄訊息
                    if self.record_message and (current_time - self.record_message_time) < 3.0:
                        cv2.putText(
                            output,
                            self.record_message,
                            (10, output.shape[0] - 120),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (0, 255, 0),
                            2,
                            cv2.LINE_AA,
                        )

                    cv2.imshow("YOLO Detection", output)

                    # 按鍵處理
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        logger.info("使用者按下 'q' 鍵，結束程式")
                        break
                    elif key == ord("r"):
                        # 記錄當前偵測結果到標註檔案
                        self._record_detections(result, frame, session_id)
                    elif key == ord("s"):
                        # 儲存當前畫面
                        filepath = save_detection_image(output, "screenshots")
                        logger.info(f"已儲存畫面: {filepath}")
                        self.record_message = f"Saved: {Path(filepath).name}"
                        self.record_message_time = time.time()

        except KeyboardInterrupt:
            logger.info("收到中斷訊號")
        except Exception as e:
            logger.error(f"執行錯誤: {e}")
            import traceback

            traceback.print_exc()
        finally:
            self.stop()

    def _record_detections(
        self, result: FrameDetectionResult, frame: np.ndarray, session_id: Optional[int]
    ):
        """
        記錄偵測結果到標註檔案

        參數:
            result: 畫面偵測結果
            frame: 原始影像
            session_id: 會話 ID
        """
        # 立即複製當前畫面，確保即使物品移開也能保存截圖
        captured_frame = frame.copy()

        if not result.detections:
            self.record_message = "沒有偵測到任何物品"
            self.record_message_time = time.time()
            logger.info("沒有偵測到任何物品")
            return

        # 取得歷史標籤（用於下拉式選單）
        label_history = self.annotation_manager.get_label_history()

        # 在新線程中顯示對話框，避免阻塞主迴圈
        def show_dialog():
            try:
                # 先記錄偵測結果（使用捕獲的畫面）
                records = self.annotation_manager.add_detections(
                    result.detections, frame=captured_frame, session_id=session_id
                )

                if not records:
                    logger.info("沒有記錄任何物品")
                    return

                # 創建對話框
                root = tk.Tk()
                root.title("記錄物品資訊")
                root.geometry("550x450")
                root.resizable(False, False)

                # 設定視窗置頂
                root.attributes("-topmost", True)

                # 主框架
                main_frame = ttk.Frame(root, padding="10")
                main_frame.pack(fill=tk.BOTH, expand=True)

                # 標題
                title_label = ttk.Label(
                    main_frame,
                    text=f"已偵測到 {len(records)} 個物品，請填寫標籤",
                    font=("Arial", 12, "bold"),
                )
                title_label.pack(pady=(0, 10))

                # 提示說明
                hint_label = ttk.Label(
                    main_frame,
                    text="中文欄位：選擇或輸入物品中文名稱（系統會自動轉英文）\n英文欄位：自動填入對應英文，可自行修改",
                    font=("Arial", 9),
                    foreground="gray",
                )
                hint_label.pack(pady=(0, 5))

                # 創建滾動框架
                canvas = tk.Canvas(main_frame, height=280)
                scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
                scrollable_frame = ttk.Frame(canvas)

                scrollable_frame.bind(
                    "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
                )

                canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
                canvas.configure(yscrollcommand=scrollbar.set)

                canvas.pack(side="left", fill="both", expand=True)
                scrollbar.pack(side="right", fill="y")

                # 存儲輸入框的字典
                entries = {}

                # 為每個物品創建輸入欄位
                for i, record in enumerate(records):
                    item_frame = ttk.LabelFrame(
                        scrollable_frame,
                        text=f"物品 {i + 1}: {record.class_name_cn or record.class_name}",
                        padding="5",
                    )
                    item_frame.pack(fill=tk.X, padx=5, pady=5)

                    # 中文物品名稱（下拉式選單 + 可輸入）
                    ttk.Label(item_frame, text="中文名稱:").grid(
                        row=0, column=0, sticky=tk.W, padx=5, pady=2
                    )

                    # 建立下拉式選單的變數和值列表
                    cn_var = tk.StringVar()
                    cn_values = [""] + [item["cn"] for item in label_history]
                    cn_combo = ttk.Combobox(
                        item_frame, textvariable=cn_var, values=cn_values, width=27
                    )
                    cn_combo.grid(row=0, column=1, padx=5, pady=2)

                    # 英文標籤（自動填入 + 可編輯）
                    ttk.Label(item_frame, text="英文標籤:").grid(
                        row=1, column=0, sticky=tk.W, padx=5, pady=2
                    )
                    en_var = tk.StringVar()
                    en_entry = ttk.Entry(item_frame, textvariable=en_var, width=30)
                    en_entry.grid(row=1, column=1, padx=5, pady=2)

                    # 當選擇歷史標籤時，自動填入對應的英文
                    def on_cn_select(event, cn_var=cn_var, en_var=en_var, combo=cn_combo):
                        selected_cn = cn_var.get()
                        if selected_cn:
                            # 從歷史標籤中找對應的英文
                            for item in label_history:
                                if item["cn"] == selected_cn:
                                    en_var.set(item["en"])
                                    break
                            else:
                                # 如果沒有歷史記錄，嘗試從對應表轉換
                                en_label = self.label_mapper.get_english_name_from_cn(selected_cn)
                                if en_label != selected_cn:  # 有找到對應
                                    en_var.set(en_label)

                    # 當輸入中文時，自動嘗試轉換為英文
                    def on_cn_change(event, cn_var=cn_var, en_var=en_var):
                        # 如果英文欄位為空，才自動填入
                        if not en_var.get():
                            cn_text = cn_var.get()
                            en_label = self.label_mapper.get_english_name_from_cn(cn_text)
                            if en_label != cn_text:  # 有找到對應
                                en_var.set(en_label)

                    cn_combo.bind("<<ComboboxSelected>>", on_cn_select)
                    cn_combo.bind("<FocusOut>", on_cn_change)

                    entries[record.id] = {
                        "cn_var": cn_var,
                        "en_var": en_var,
                        "cn_combo": cn_combo,
                        "en_entry": en_entry,
                    }

                # 按鈕框架
                button_frame = ttk.Frame(root, padding="10")
                button_frame.pack(fill=tk.X)

                def save_and_close():
                    """保存並關閉"""
                    try:
                        saved_count = 0
                        for record_id, entry_dict in entries.items():
                            cn_label = entry_dict["cn_var"].get().strip()
                            en_label = entry_dict["en_var"].get().strip()

                            # 更新標註（description 用中文，custom_label 用英文）
                            if cn_label or en_label:
                                self.annotation_manager.update_annotation(
                                    record_id=record_id,
                                    description=cn_label,
                                    custom_label=en_label,
                                )
                                self.annotation_manager.mark_annotated(
                                    record_id=record_id,
                                    owner="",
                                    description=cn_label,
                                    custom_label=en_label,
                                    notes="",
                                )
                                saved_count += 1

                        logger.info(f"已保存 {saved_count} 個物品的標籤")
                        self.record_message = f"已保存 {saved_count} 個物品的標籤"
                        self.record_message_time = time.time()
                        root.destroy()
                    except Exception as e:
                        logger.error(f"保存失敗: {e}")
                        messagebox.showerror("錯誤", f"保存失敗: {str(e)}")

                def skip_and_close():
                    """跳過並關閉"""
                    logger.info("已跳過標註")
                    self.record_message = f"已記錄 {len(records)} 個物品（未標註）"
                    self.record_message_time = time.time()
                    root.destroy()

                # 保存按鈕
                save_btn = ttk.Button(
                    button_frame, text="💾 保存", command=save_and_close, width=15
                )
                save_btn.pack(side=tk.LEFT, padx=10)

                # 跳過按鈕
                skip_btn = ttk.Button(button_frame, text="⏭ 跳過", command=skip_and_close, width=15)
                skip_btn.pack(side=tk.LEFT, padx=10)

                # 取消按鈕
                cancel_btn = ttk.Button(
                    button_frame, text="❌ 取消", command=root.destroy, width=15
                )
                cancel_btn.pack(side=tk.RIGHT, padx=10)

                # 顯示記錄的物品資訊
                logger.info(f"已記錄 {len(records)} 個物品到標註檔案")
                for record in records:
                    logger.info(
                        f"  - {record.class_name_cn or record.class_name} (信心度: {record.confidence:.2f})"
                    )

                # 設定記錄訊息
                self.record_message = f"已記錄 {len(records)} 個物品，請填寫標籤"
                self.record_message_time = time.time()

                root.mainloop()

            except Exception as e:
                logger.error(f"記錄失敗: {e}")
                import traceback

                traceback.print_exc()
                self.record_message = f"記錄失敗: {str(e)}"
                self.record_message_time = time.time()

        # 在新線程中運行對話框
        dialog_thread = threading.Thread(target=show_dialog, daemon=True)
        dialog_thread.start()

    def stop(self):
        """停止系統"""
        self.running = False

        # 計算統計
        if self.start_time and self.frame_count > 0:
            elapsed = time.time() - self.start_time
            avg_fps = self.frame_count / elapsed
        else:
            elapsed = 0
            avg_fps = 0

        # 結束會話
        session_id = (
            getattr(self.item_logger, "current_session", None) if self.item_logger else None
        )
        if session_id and self.item_logger:
            self.item_logger.end_session(total_frames=self.frame_count, avg_fps=avg_fps)

        # 顯示標註統計
        if self.annotation_manager:
            stats = self.annotation_manager.get_statistics()
            logger.info("=" * 50)
            logger.info("標註統計:")
            logger.info(f"  總記錄數: {stats['total']}")
            logger.info(f"  待標註: {stats['pending']}")
            logger.info(f"  已標註: {stats['annotated']}")
            logger.info(f"  標註檔案: data/annotations/annotations.json")

        # 清理資源
        if self.camera:
            self.camera.disconnect()

        cv2.destroyAllWindows()

        logger.info("=" * 50)
        logger.info("系統已停止")
        logger.info(f"總幀數: {self.frame_count}")
        logger.info(f"執行時間: {elapsed:.1f} 秒")
        logger.info(f"平均 FPS: {avg_fps:.1f}")
        logger.info("=" * 50)

    def get_annotation_stats(self) -> Dict[str, Any]:
        """取得標註統計資訊"""
        if self.annotation_manager:
            return self.annotation_manager.get_statistics()
        return {}

    def export_annotations_csv(self, output_path: str = "data/annotations/export.csv") -> bool:
        """匯出標註記錄為 CSV 格式"""
        if self.annotation_manager:
            return self.annotation_manager.export_to_csv(output_path)
        return False


def main():
    """主程式入口"""
    parser = argparse.ArgumentParser(
        description="YOLO 日常物品辨識系統",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例:
  # 使用 ESP32 串流
  python main.py --source esp32
  
  # 使用本地 Webcam
  python main.py --source webcam
  
  # 使用自定義模型
  python main.py --model models/custom/yoloe_custom.pt
  
  # 不顯示視窗（背景執行）
  python main.py --no-display
        """,
    )

    parser.add_argument(
        "--source",
        type=str,
        default="webcam",
        choices=["esp32", "webcam"],
        help="影像來源 (esp32 或 webcam)",
    )

    parser.add_argument("--model", type=str, default=None, help="模型檔案路徑")

    parser.add_argument("--custom", action="store_true", help="使用自定義訓練的模型")

    parser.add_argument("--confidence", type=float, default=0.5, help="信心度門檻 (0.0 - 1.0)")

    parser.add_argument("--no-db", action="store_true", help="不儲存到資料庫")

    parser.add_argument("--save-images", action="store_true", help="儲存辨識圖片")

    parser.add_argument("--no-display", action="store_true", help="不顯示影像視窗")

    args = parser.parse_args()

    # 建立並執行系統
    system = YOLODetectionSystem(
        source=args.source,
        model_path=args.model,
        use_custom_model=args.custom,
        confidence=args.confidence,
        save_to_db=not args.no_db,
        save_images=args.save_images,
        display=not args.no_display,
    )

    # 設定訊號處理
    def signal_handler(sig, frame):
        logger.info("收到停止訊號")
        system.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 執行系統
    system.run()


if __name__ == "__main__":
    main()
