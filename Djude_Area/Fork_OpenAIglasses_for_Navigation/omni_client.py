# omni_client.py
# -*- coding: utf-8 -*-
"""
Gemini 2.5 Flash + Gemini TTS 替代 Qwen-Omni-Turbo。

流程：
  1. Gemini 2.5 Flash（圖片 + 文字 → 文字回應）
  2. 依句子切分，逐句呼叫 Gemini TTS（文字 → PCM16 24kHz）
  3. 逐句 yield OmniStreamPiece，第一句音訊盡快送出

介面與原 omni_client.py 完全相容，app_main.py 無需修改使用邏輯。
"""

import json, base64, re, asyncio, threading, urllib.request, urllib.error
from typing import AsyncGenerator, List, Dict, Any, Optional

from config import (
    GEMINI_API_KEY, GEMINI_API_KEY_2, GEMINI_API_KEY_3, GEMINI_API_KEY_4,
    GEMINI_API_KEY_5, GEMINI_API_KEY_6, GEMINI_API_KEY_7,
    GEMINI_API_KEY_8, GEMINI_API_KEY_9, GEMINI_API_KEY_10,
)

# ── API Key 輪換池（自動過濾空值）────────────────────────────────────────────
_GEMINI_KEYS = [k for k in [
    GEMINI_API_KEY, GEMINI_API_KEY_2, GEMINI_API_KEY_3, GEMINI_API_KEY_4,
    GEMINI_API_KEY_5, GEMINI_API_KEY_6, GEMINI_API_KEY_7,
    GEMINI_API_KEY_8, GEMINI_API_KEY_9, GEMINI_API_KEY_10,
] if k]
if not _GEMINI_KEYS:
    raise RuntimeError("未設定任何 GEMINI_API_KEY，請在 .env 中至少設定一組金鑰")

_key_index = 0
_key_lock = threading.Lock()

def _current_key() -> str:
    return _GEMINI_KEYS[_key_index]

def _rotate_key() -> None:
    global _key_index
    with _key_lock:
        _key_index = (_key_index + 1) % len(_GEMINI_KEYS)
    print(f"[Gemini] API Key 已切換至第 {_key_index + 1} 組（共 {len(_GEMINI_KEYS)} 組）", flush=True)

# ── 模型設定 ──────────────────────────────────────────────────────────────────
_FLASH_MODEL = "gemini-2.5-flash"
_TTS_MODEL   = "gemini-2.5-flash-preview-tts"
_BASE        = "https://generativelanguage.googleapis.com/v1beta/models"

# Qwen voice → Gemini voice 對照（保持 app_main.py 不用改）
_VOICE_MAP = {
    "Cherry": "Aoede",   # 女聲
    "Ethan":  "Puck",    # 男聲
}
_DEFAULT_VOICE = "Aoede"

# 句子切分正則（中英文句末標點）
_SENTENCE_END = re.compile(r'[。！？!?]+')

# ── 資料類別 ──────────────────────────────────────────────────────────────────

class OmniStreamPiece:
    """對外統一增量資料：text_delta / audio_b64 擇一或同時。"""
    def __init__(self, text_delta: Optional[str] = None,
                 audio_b64: Optional[str] = None):
        self.text_delta = text_delta
        self.audio_b64  = audio_b64

# ── 工具函式 ──────────────────────────────────────────────────────────────────

def _map_voice(voice: str) -> str:
    return _VOICE_MAP.get(voice, voice if voice else _DEFAULT_VOICE)

def _convert_parts(content_list: List[Dict[str, Any]]) -> List[Dict]:
    """將 OpenAI 格式 content_list 轉換為 Gemini parts 格式。"""
    parts = []
    for item in content_list:
        t = item.get("type", "")
        if t == "text":
            parts.append({"text": item["text"]})
        elif t == "image_url":
            url = item["image_url"]["url"]
            if url.startswith("data:"):
                # data:image/jpeg;base64,{b64}
                header, data = url.split(",", 1)
                mime_type = header.split(":")[1].split(";")[0]
                parts.append({"inline_data": {"mime_type": mime_type, "data": data}})
    return parts

def _split_sentences(text: str) -> List[str]:
    """將文字切分為句子列表（以句末標點為界）。"""
    segs = _SENTENCE_END.split(text)
    puncs = _SENTENCE_END.findall(text)
    sentences = []
    for i, seg in enumerate(segs):
        seg = seg.strip()
        if not seg:
            continue
        punc = puncs[i] if i < len(puncs) else ""
        sentences.append(seg + punc)
    return sentences

def _gemini_request(endpoint: str, payload: bytes, timeout: int) -> dict:
    """送出 Gemini API 請求，遇 429（配額耗盡）自動輪換 Key 後重試。"""
    for attempt in range(len(_GEMINI_KEYS)):
        key = _current_key()
        url = f"{_BASE}/{endpoint}?key={key}"
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "gemini-omni/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"[Gemini] Key {attempt + 1} 配額已用盡，切換下一組...", flush=True)
                _rotate_key()
                continue
            # 印出詳細錯誤內容，方便除錯
            try:
                err_body = e.read().decode(errors="replace")
                print(f"[Gemini] HTTP {e.code} 錯誤內容: {err_body[:500]}", flush=True)
            except Exception:
                pass
            raise
    raise RuntimeError(f"所有 {len(_GEMINI_KEYS)} 組 Gemini API Key 配額均已用盡")


def _call_flash(parts: List[Dict], system_prompt: str) -> str:
    """呼叫 Gemini 2.5 Flash，回傳文字回應（阻塞式）。"""
    payload = json.dumps({
        "contents": [{"parts": parts}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {"maxOutputTokens": 300},
    }).encode()
    result = _gemini_request(f"{_FLASH_MODEL}:generateContent", payload, timeout=20)
    return result["candidates"][0]["content"]["parts"][0].get("text", "").strip()

def _call_tts(text: str, voice: str) -> Optional[bytes]:
    """呼叫 Gemini TTS，回傳 PCM16 24kHz bytes（阻塞式）。"""
    # TTS 模型對無標點的短句會返回 finishReason=OTHER，補句號確保正常生成
    if text and text[-1] not in "。！？!?.，,":
        text = text + "。"
    payload = json.dumps({
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}
            },
        },
    }).encode()
    try:
        result = _gemini_request(f"{_TTS_MODEL}:generateContent", payload, timeout=15)
        cand = result.get("candidates", [{}])[0]
        if "content" not in cand:
            print(f"[GeminiTTS] 無音訊內容（finishReason={cand.get('finishReason', '?')}）", flush=True)
            return None
        data = cand["content"]["parts"][0].get("inlineData", {}).get("data", "")
        return base64.b64decode(data) if data else None
    except Exception as e:
        print(f"[GeminiTTS] 錯誤: {e}", flush=True)
        return None

# ── 主要介面 ──────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "你是智慧導盲眼鏡的AI助手。"
    "請用繁體中文簡短回答，不超過兩句話，語氣自然清晰。"
)

async def stream_chat(
    content_list: List[Dict[str, Any]],
    voice: str = "Cherry",
    audio_format: str = "wav",
) -> AsyncGenerator[OmniStreamPiece, None]:
    """
    Gemini 2.5 Flash + TTS 串流對話（介面與原 Qwen-Omni 相容）。

    流程：
      1. 呼叫 Gemini Flash 取得文字回應
      2. yield text_delta（供 UI 顯示）
      3. 逐句呼叫 TTS，yield audio_b64（PCM16 24kHz，與原降頻邏輯相容）
    """
    gemini_voice = _map_voice(voice)
    parts = _convert_parts(content_list)
    if not parts:
        return

    loop = asyncio.get_running_loop()

    # ① 取得文字回應
    try:
        full_text = await loop.run_in_executor(None, _call_flash, parts, _SYSTEM_PROMPT)
    except Exception as e:
        print(f"[GeminiFlash] 錯誤: {e}", flush=True)
        return

    if not full_text:
        return

    print(f"[GeminiFlash] 回應: {full_text}", flush=True)

    # ② 先 yield 文字（UI 顯示用）
    yield OmniStreamPiece(text_delta=full_text)

    # ③ 逐句合成語音並 yield
    sentences = _split_sentences(full_text)
    if not sentences:
        sentences = [full_text]

    # 將連續短句（<5字）合併到下一句，避免 TTS finishReason=OTHER
    merged: List[str] = []
    buf = ""
    for s in sentences:
        buf = (buf + s) if buf else s
        if len(buf.replace(" ", "")) >= 5:
            merged.append(buf)
            buf = ""
    if buf:
        if merged:
            merged[-1] += buf  # 殘餘短句合入最後一句
        else:
            merged.append(buf)
    sentences = merged if merged else [full_text]

    for sentence in sentences:
        if not sentence.strip():
            continue
        try:
            pcm_bytes = await loop.run_in_executor(None, _call_tts, sentence, gemini_voice)
            if pcm_bytes:
                yield OmniStreamPiece(audio_b64=base64.b64encode(pcm_bytes).decode())
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[GeminiTTS] 句子合成失敗: {e}", flush=True)
