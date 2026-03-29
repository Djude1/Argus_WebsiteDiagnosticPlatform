# asr_core.py
# -*- coding: utf-8 -*-
import asyncio
import json
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

ASR_DEBUG_RAW = os.getenv("ASR_DEBUG_RAW", "0") == "1"


def _shorten(s: str, limit: int = 200) -> str:
    if not s:
        return ""
    return s if len(s) <= limit else (s[:limit] + "...")


def _safe_to_dict(x: Any) -> Dict[str, Any]:
    if isinstance(x, dict):
        return x
    for attr in ("to_dict", "model_dump", "__dict__"):
        try:
            v = getattr(x, attr, None)
        except Exception:
            v = None
        if callable(v):
            try:
                d = v()
                if isinstance(d, dict):
                    return d
            except Exception:
                pass
        elif isinstance(v, dict):
            return v
    try:
        s = str(x)
        if s and s.lstrip().startswith("{") and s.rstrip().endswith("}"):
            return json.loads(s)
    except Exception:
        pass
    return {"_raw": str(x)}


def _extract_sentence(event_obj: Any) -> Tuple[Optional[str], Optional[bool]]:
    d = _safe_to_dict(event_obj)
    cands: List[Dict[str, Any]] = [d]
    for k in ("output", "data", "result"):
        v = d.get(k)
        if isinstance(v, dict):
            cands.append(v)
    for obj in cands:
        sent = obj.get("sentence")
        if isinstance(sent, dict):
            text = sent.get("text")
            is_end = sent.get("sentence_end")
            if is_end is not None:
                is_end = bool(is_end)
            return text, is_end
    for obj in cands:
        if "text" in obj and isinstance(obj.get("text"), str):
            return obj.get("text"), None
    return None, None


def _normalize(s: str) -> str:
    return (s or "").strip().lower()


def _compact_text(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").strip())


def _is_related_text(a: str, b: str) -> bool:
    aa = _compact_text(a)
    bb = _compact_text(b)
    if not aa or not bb:
        return False
    return aa in bb or bb in aa


def _normalize_submit_text(s: str) -> str:
    t = (s or "").strip()
    if re.search(r"[\u4e00-\u9fff]", t):
        t = re.sub(r"\s+", "", t)
    else:
        t = re.sub(r"\s+", " ", t)
    return t.strip()


INTERRUPT_KEYWORDS = [
    x.strip() for x in os.getenv("INTERRUPT_KEYWORDS", "停下,别说了,停止").split(",") if x.strip()
]
# 放宽提交阈值，缩短延迟，提高口令命中率
ASR_MIN_FINAL_CHARS = int(os.getenv("ASR_MIN_FINAL_CHARS", "3"))
ASR_DROP_FILLER_FINALS = os.getenv("ASR_DROP_FILLER_FINALS", "0") == "1"
ASR_FINAL_COMMIT_DELAY_MS = int(os.getenv("ASR_FINAL_COMMIT_DELAY_MS", "600"))
ASR_FINAL_MAX_WAIT_MS = int(os.getenv("ASR_FINAL_MAX_WAIT_MS", "1500"))
ASR_FINAL_DEDUP_WINDOW_MS = int(os.getenv("ASR_FINAL_DEDUP_WINDOW_MS", "1200"))
ASR_FILLER_PHRASES = [
    x.strip()
    for x in os.getenv(
        "ASR_FILLER_PHRASES",
        "请问,在吗,有接吗,什么意思,现在是,什么也,那个,嗯,呃,你们但接",
    ).split(",")
    if x.strip()
]


_current_recognition: Optional[object] = None
_rec_lock = asyncio.Lock()


async def set_current_recognition(r):
    global _current_recognition
    async with _rec_lock:
        _current_recognition = r


async def stop_current_recognition():
    global _current_recognition
    async with _rec_lock:
        r = _current_recognition
        _current_recognition = None
    if r:
        try:
            r.stop()
        except Exception:
            pass


class ASRCallback:
    def __init__(
        self,
        on_sdk_error: Callable[[str], None],
        post: Callable[[asyncio.Future], None],
        ui_broadcast_partial,
        ui_broadcast_final,
        is_playing_now_fn: Callable[[], bool],
        start_ai_with_text_fn,
        full_system_reset_fn,
        interrupt_lock: asyncio.Lock,
    ):
        self._on_sdk_error = on_sdk_error
        self._post = post
        self._ui_partial = ui_broadcast_partial
        self._ui_final = ui_broadcast_final
        self._is_playing = is_playing_now_fn
        self._start_ai = start_ai_with_text_fn
        self._full_reset = full_system_reset_fn
        self._interrupt_lock = interrupt_lock
        self._hot_interrupted = False

        self._latest_partial_text: str = ""
        self._pending_final_text: str = ""
        self._pending_last_update_ts: float = 0.0
        self._pending_start_ts: float = 0.0
        self._pending_seq: int = 0

        self._last_committed_text: str = ""
        self._last_committed_ts: float = 0.0

    def on_open(self):
        pass

    def on_close(self):
        pass

    def on_complete(self):
        pass

    def on_error(self, err):
        try:
            self._post(self._ui_partial(""))
            self._on_sdk_error(str(err))
        except Exception:
            pass

    def on_result(self, result):
        self._handle(result)

    def on_event(self, event):
        self._handle(event)

    def _has_hotword(self, text: str) -> bool:
        t = _normalize(text)
        if not t:
            return False
        for w in INTERRUPT_KEYWORDS:
            ww = _normalize(w)
            if ww and ww in t:
                return True
        return False

    def _pick_commit_text(self, final_text: str) -> str:
        p = (self._latest_partial_text or "").strip()
        f = (final_text or "").strip()
        if not p:
            return f
        if _is_related_text(p, f):
            return p if len(_compact_text(p)) >= len(_compact_text(f)) else f
        return f

    async def _commit_when_stable(self, seq: int):
        delay_s = max(0.0, ASR_FINAL_COMMIT_DELAY_MS / 1000.0)
        max_wait_s = max(delay_s, ASR_FINAL_MAX_WAIT_MS / 1000.0)

        while True:
            if seq != self._pending_seq:
                return
            now = time.monotonic()
            if (now - self._pending_last_update_ts) >= delay_s:
                break
            if (now - self._pending_start_ts) >= max_wait_s:
                break
            await asyncio.sleep(0.05)

        if seq != self._pending_seq:
            return

        final_text = (self._pending_final_text or "").strip()
        if not final_text:
            return

        if self._is_playing():
            print(f"[ASR DROP] commit during playback: '{_shorten(final_text)}'", flush=True)
            return

        commit_text = _normalize_submit_text(self._pick_commit_text(final_text))
        compact = _compact_text(commit_text)
        if len(compact) < ASR_MIN_FINAL_CHARS:
            print(f"[ASR SHORT DROP] len={len(compact)} text='{_shorten(commit_text)}'", flush=True)
            return

        if ASR_DROP_FILLER_FINALS:
            norm = _normalize(compact)
            if any(_normalize(_compact_text(p)) == norm for p in ASR_FILLER_PHRASES):
                print(f"[ASR FILLER DROP] '{_shorten(commit_text)}'", flush=True)
                return

        dedup_window_s = max(0.0, ASR_FINAL_DEDUP_WINDOW_MS / 1000.0)
        if (
            _compact_text(self._last_committed_text) == compact
            and (time.monotonic() - self._last_committed_ts) <= dedup_window_s
        ):
            print(f"[ASR DEDUP DROP] '{_shorten(commit_text)}'", flush=True)
            return

        try:
            print(f"[ASR FINAL]  len={len(commit_text)} text='{commit_text}'", flush=True)
            await self._ui_final(commit_text)
        except Exception:
            pass

        async with self._interrupt_lock:
            print(f"[LLM INPUT TEXT] {commit_text}", flush=True)
            await self._start_ai(commit_text)

        self._last_committed_text = commit_text
        self._last_committed_ts = time.monotonic()

    def _handle(self, event: Any):
        if ASR_DEBUG_RAW:
            try:
                rawd = _safe_to_dict(event)
                print("[ASR EVENT RAW]", json.dumps(rawd, ensure_ascii=False), flush=True)
            except Exception:
                pass

        text, is_end = _extract_sentence(event)
        if text is None:
            return
        text = text.strip()
        if not text:
            return

        if not self._hot_interrupted and self._has_hotword(text):
            self._hot_interrupted = True

            async def _hot_reset():
                async with self._interrupt_lock:
                    print(f"[ASR HOTWORD] '{_shorten(text)}' -> FULL RESET", flush=True)
                    await self._full_reset("Hotword interrupt")

            try:
                self._post(_hot_reset())
            except Exception:
                pass
            return

        self._latest_partial_text = text
        now = time.monotonic()

        if self._pending_final_text and _is_related_text(self._pending_final_text, text):
            if len(_compact_text(text)) >= len(_compact_text(self._pending_final_text)):
                self._pending_final_text = text
                self._pending_last_update_ts = now

        try:
            print(f"[ASR PARTIAL] len={len(text)} text='{_shorten(text)}'", flush=True)
            self._post(self._ui_partial(text))
        except Exception:
            pass

        if is_end is not True:
            return

        if self._is_playing():
            print(f"[ASR DROP] during playback: '{_shorten(text)}'", flush=True)
            self._hot_interrupted = False
            return

        self._pending_final_text = text
        self._pending_last_update_ts = now
        self._pending_start_ts = now
        self._pending_seq += 1
        seq = self._pending_seq

        try:
            self._post(self._commit_when_stable(seq))
        except Exception:
            pass

        self._hot_interrupted = False
