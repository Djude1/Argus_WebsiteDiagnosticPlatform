# ============================================
# 偵測結果 JSON 記錄器
# ============================================
"""
將每次偵測結果以 JSONL 格式儲存，方便後續分析與回顧。
每日產生一個檔案，檔名格式：detections_YYYYMMDD.jsonl
"""

import json
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger


class DetectionLogger:
    """偵測結果記錄器 - 將偵測結果存入 JSON 檔"""

    def __init__(
        self,
        log_dir: Optional[str] = None,
        buffer_size: int = 10,
        flush_interval: float = 5.0,
    ):
        """
        初始化記錄器

        參數:
            log_dir: 記錄檔存放目錄（預設為 data/detection_logs/）
            buffer_size: 緩衝區大小，累積多少筆後寫入磁碟
            flush_interval: 自動寫入間隔（秒）
        """
        if log_dir is None:
            self._log_dir = Path(__file__).parent.parent.parent / "data" / "detection_logs"
        else:
            self._log_dir = Path(log_dir)

        self._log_dir.mkdir(parents=True, exist_ok=True)

        self._buffer: List[Dict[str, Any]] = []
        self._buffer_size = buffer_size
        self._flush_interval = flush_interval
        self._lock = threading.Lock()
        self._current_date: Optional[str] = None
        self._current_file: Optional[Path] = None
        self._total_logged = 0

        # 啟動定時寫入執行緒
        self._flush_timer: Optional[threading.Timer] = None
        self._start_flush_timer()

        logger.info(f"偵測記錄器已初始化，存放目錄: {self._log_dir}")

    def _get_log_file(self) -> Path:
        """取得當天的記錄檔路徑"""
        today = datetime.now().strftime("%Y%m%d")
        if today != self._current_date:
            self._current_date = today
            self._current_file = self._log_dir / f"detections_{today}.jsonl"
        return self._current_file

    def log(self, detections: List[Dict[str, Any]], fps: float = 0.0, frame_count: int = 0):
        """
        記錄一次偵測結果

        參數:
            detections: 偵測結果列表，每項包含 class_name, class_name_cn, confidence, bbox
            fps: 當前 FPS
            frame_count: 當前幀數
        """
        if not detections:
            return

        record = {
            "timestamp": datetime.now().isoformat(),
            "epoch": time.time(),
            "frame_count": frame_count,
            "fps": round(fps, 1),
            "count": len(detections),
            "detections": [
                {
                    "class_name": d.get("class_name", ""),
                    "class_name_cn": d.get("class_name_cn", ""),
                    "confidence": round(d.get("confidence", 0), 3),
                    "bbox": d.get("bbox"),
                }
                for d in detections
            ],
        }

        with self._lock:
            self._buffer.append(record)
            if len(self._buffer) >= self._buffer_size:
                self._flush_buffer()

    def _flush_buffer(self):
        """將緩衝區內容寫入磁碟（須持有 _lock）"""
        if not self._buffer:
            return

        log_file = self._get_log_file()
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                for record in self._buffer:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

            self._total_logged += len(self._buffer)
            count = len(self._buffer)
            self._buffer.clear()
            logger.debug(f"已寫入 {count} 筆偵測記錄至 {log_file.name}")
        except Exception as e:
            logger.error(f"寫入偵測記錄失敗: {e}")

    def flush(self):
        """手動強制寫入"""
        with self._lock:
            self._flush_buffer()

    def _start_flush_timer(self):
        """啟動定時寫入"""
        def _timer_flush():
            with self._lock:
                self._flush_buffer()
            self._start_flush_timer()

        self._flush_timer = threading.Timer(self._flush_interval, _timer_flush)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    def get_today_stats(self) -> Dict[str, Any]:
        """取得今日偵測統計"""
        log_file = self._get_log_file()
        stats = {
            "date": self._current_date,
            "file": str(log_file),
            "total_logged": self._total_logged,
            "buffer_pending": len(self._buffer),
        }

        # 讀取今日檔案統計
        if log_file.exists():
            try:
                class_counts: Dict[str, int] = {}
                total_records = 0
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                            total_records += 1
                            for det in record.get("detections", []):
                                name = det.get("class_name_cn") or det.get("class_name", "未知")
                                class_counts[name] = class_counts.get(name, 0) + 1
                        except json.JSONDecodeError:
                            continue

                stats["total_records"] = total_records
                stats["class_counts"] = class_counts
            except Exception as e:
                stats["error"] = str(e)

        return stats

    def get_history_files(self) -> List[Dict[str, Any]]:
        """列出所有歷史記錄檔"""
        files = []
        for f in sorted(self._log_dir.glob("detections_*.jsonl"), reverse=True):
            files.append({
                "filename": f.name,
                "date": f.stem.replace("detections_", ""),
                "size_kb": round(f.stat().st_size / 1024, 1),
            })
        return files

    def close(self):
        """關閉記錄器，寫入剩餘資料"""
        if self._flush_timer:
            self._flush_timer.cancel()
        self.flush()
        logger.info(f"偵測記錄器已關閉，共記錄 {self._total_logged} 筆")
