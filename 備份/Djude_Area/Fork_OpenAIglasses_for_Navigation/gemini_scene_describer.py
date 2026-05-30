# gemini_scene_describer.py
# 每 10 秒在背景非同步送縮圖給 Gemini Flash，補充 YOLO 可能漏掉的危險描述。
# 完全不阻塞主導航迴圈，優先級最低，僅在 YOLO 無明顯事件時播報。

import threading
import time
import base64
import logging

import cv2

logger = logging.getLogger(__name__)

# ── 可由外部覆寫 ─────────────────────────────────────────────────────────────
INTERVAL: float = 10.0          # 觸發間隔（秒）
JPEG_QUALITY: int = 60          # 縮圖品質（越低越省 token）
THUMB_W: int = 320              # 縮圖寬度
THUMB_H: int = 240              # 縮圖高度
TTS_VOICE: str = "Leda"         # Gemini TTS 聲音（Leda 為中文女聲）

# 這些關鍵字出現時，代表環境安全，不播報
_SAFE_KEYWORDS = ("環境安全", "环境安全", "安全", "無危險", "无危险")


class GeminiSceneDescriber:
    """
    背景非同步 Gemini Flash 場景補充描述器。

    使用方式（在主導航迴圈中）：
        describer = GeminiSceneDescriber()

        # 每幀呼叫 tick，傳入最新畫面與導航狀態
        describer.tick(frame, navigation_active=True)

        # 在 YOLO 無明顯事件時取得待播報文字
        extra = describer.get_pending()
        if extra:
            play_voice_text(extra)
            await ui_broadcast_final(f"[导航] {extra}")
    """

    def __init__(self):
        self._last_trigger: float = 0.0   # 上次觸發時間
        self._running: bool = False        # 是否有請求正在進行
        self._pending: str | None = None   # 待播報文字
        self._lock = threading.Lock()

    # ── 每幀呼叫（主迴圈）─────────────────────────────────────────────────────
    def tick(self, frame, navigation_active: bool = True) -> None:
        """
        每幀呼叫一次。
        - navigation_active=False 時不分析（節省 API quota）
        - 每隔 INTERVAL 秒自動在背景觸發一次 Gemini 分析
        """
        if not navigation_active:
            return
        now = time.time()
        if (now - self._last_trigger) >= INTERVAL and not self._running:
            self._last_trigger = now
            self._running = True
            threading.Thread(
                target=self._worker,
                args=(frame.copy(),),
                daemon=True,
                name="GeminiSceneDescriber",
            ).start()

    def get_pending(self) -> str | None:
        """
        取得並清除待播報描述。
        主迴圈應在 YOLO 無明顯事件（guidance_text 為空）時呼叫。
        """
        with self._lock:
            text = self._pending
            self._pending = None
        return text

    def clear(self) -> None:
        """清除待播報（例如導航停止時呼叫）。"""
        with self._lock:
            self._pending = None

    # ── 背景執行緒 ───────────────────────────────────────────────────────────
    def _worker(self, frame) -> None:
        try:
            # ① 取得目前 position_mode（時鐘 / 前後左右）
            try:
                from app_main import _position_mode
            except Exception:
                _position_mode = "cardinal"

            position_hint = (
                "請用「X點鐘方向」描述物件位置（例：3點鐘方向有台階）"
                if _position_mode == "clock"
                else "請用「前方/左側/右側/左前方/右前方」描述位置"
            )

            # ② 縮圖（320×240，減少 token 用量）
            small = cv2.resize(frame, (THUMB_W, THUMB_H))
            _, buf = cv2.imencode(
                ".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
            )
            b64 = base64.b64encode(buf.tobytes()).decode()

            # ③ 呼叫 Gemini Flash（純文字回傳，不需 TTS）
            from omni_client import _call_flash

            parts = [
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": b64,
                    }
                },
                {
                    "text": (
                        "你是視障輔助AI助理。"
                        "請用繁體中文、一句話（15字以內），告知視障者此畫面中，"
                        "一般物件偵測（YOLO）可能漏掉的潛在危險或重要提示，"
                        "例如：台階邊緣、坡道、玻璃門/牆、窄通道、積水、"
                        "施工圍欄、突出物等。台灣道路較複雜，請格外注意。"
                        f"{position_hint}。"
                        "若無明顯危險，只回覆「環境安全」，不要加任何其他字。"
                        "只輸出描述本身，不要任何前綴、解釋或標點之外的文字。"
                    )
                },
            ]

            result = _call_flash(parts, system_prompt="").strip()
            logger.info(f"[GeminiScene] 分析結果: {result}")

            # ④ 「環境安全」不播報，其他設為待播
            if result and not any(kw in result for kw in _SAFE_KEYWORDS):
                with self._lock:
                    self._pending = result

        except Exception as e:
            logger.warning(f"[GeminiScene] 分析失敗: {e}", exc_info=False)
        finally:
            self._running = False
