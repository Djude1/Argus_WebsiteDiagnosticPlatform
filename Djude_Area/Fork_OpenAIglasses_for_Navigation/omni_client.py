# omni_client.py
# -*- coding: utf-8 -*-
"""
Gemini 2.5 Flash 串流 + Gemini TTS 並行合成。

流程：
  1. streamGenerateContent（SSE 串流）逐塊取得文字
  2. 偵測句子邊界，立即啟動 TTS Future（與後續 Flash 生成並行）
  3. Flash 完成後 yield 全文（UI 顯示用）
  4. 按句序 await TTS Future，逐句 yield audio_b64
     （大部分 TTS 在 Flash 串流期間已並行執行完畢）

備援機制：串流失敗時自動切換為阻塞式 generateContent + 原始逐句 TTS。
介面與原 omni_client.py 完全相容，app_main.py 無需修改使用邏輯。
"""

import json, base64, re, asyncio, threading, urllib.request, urllib.error
from typing import AsyncGenerator, List, Dict, Any, Optional

from config import (
    GEMINI_API_KEY, GEMINI_API_KEY_2, GEMINI_API_KEY_3, GEMINI_API_KEY_4,
    GEMINI_API_KEY_5, GEMINI_API_KEY_6, GEMINI_API_KEY_7,
    GEMINI_API_KEY_8, GEMINI_API_KEY_9, GEMINI_API_KEY_10,
    GEMINI_API_KEY_11, GEMINI_API_KEY_12, GEMINI_API_KEY_13,
    GEMINI_API_KEY_14, GEMINI_API_KEY_15, GEMINI_API_KEY_16,
)

# ── API Key 輪換池（自動過濾空值）────────────────────────────────────────────
_GEMINI_KEYS = [k for k in [
    GEMINI_API_KEY, GEMINI_API_KEY_2, GEMINI_API_KEY_3, GEMINI_API_KEY_4,
    GEMINI_API_KEY_5, GEMINI_API_KEY_6, GEMINI_API_KEY_7,
    GEMINI_API_KEY_8, GEMINI_API_KEY_9, GEMINI_API_KEY_10,
    GEMINI_API_KEY_11, GEMINI_API_KEY_12, GEMINI_API_KEY_13,
    GEMINI_API_KEY_14, GEMINI_API_KEY_15, GEMINI_API_KEY_16,
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

def _merge_short_sentences(sentences: List[str]) -> List[str]:
    """將連續短句（<5字）合併到下一句，避免 TTS finishReason=OTHER。"""
    merged: List[str] = []
    buf = ""
    for s in sentences:
        buf = (buf + s) if buf else s
        if len(buf.replace(" ", "")) >= 5:
            merged.append(buf)
            buf = ""
    if buf:
        if merged:
            merged[-1] += buf
        else:
            merged.append(buf)
    return merged if merged else sentences

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
    """呼叫 Gemini 2.5 Flash，回傳文字回應（阻塞式，作為串流失敗時的備援）。"""
    payload = json.dumps({
        "contents": [{"parts": parts}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {"maxOutputTokens": 300},
    }).encode()
    result = _gemini_request(f"{_FLASH_MODEL}:generateContent", payload, timeout=20)
    return result["candidates"][0]["content"]["parts"][0].get("text", "").strip()


def _call_flash_long(parts: List[Dict], system_prompt: str, max_tokens: int) -> str:
    """長文字版 Gemini 呼叫（OCR / 文件問答），支援更大 token 上限。"""
    payload_obj: Dict[str, Any] = {
        "contents": [{"parts": parts}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.1},
    }
    if system_prompt:
        payload_obj["systemInstruction"] = {"parts": [{"text": system_prompt}]}
    payload = json.dumps(payload_obj).encode()
    result = _gemini_request(f"{_FLASH_MODEL}:generateContent", payload, timeout=90)
    try:
        return result["candidates"][0]["content"]["parts"][0].get("text", "").strip()
    except (KeyError, IndexError):
        return ""


async def generate_text_async(content_list: List[Dict[str, Any]],
                              system_prompt: str = "",
                              max_tokens: int = 8192) -> str:
    """
    公開非串流介面：傳入 content_list（可含圖片 + 文字），
    回傳 Gemini 純文字回應。適合 OCR、文件問答等不需要音訊的場合。
    在 asyncio 執行緒池中執行，不阻塞事件迴圈。
    """
    parts = _convert_parts(content_list)
    loop  = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _call_flash_long, parts, system_prompt, max_tokens
    )

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

# ── Flash SSE 串流實作 ─────────────────────────────────────────────────────────

def _stream_flash_sync(parts: List[Dict], system_prompt: str):
    """
    同步生成器：透過 streamGenerateContent SSE 逐塊 yield 文字片段。
    遇 429 自動輪換 Key 後重試；其他錯誤直接 raise。
    """
    payload = json.dumps({
        "contents": [{"parts": parts}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {"maxOutputTokens": 300},
    }).encode()

    for attempt in range(len(_GEMINI_KEYS)):
        key = _current_key()
        url = f"{_BASE}/{_FLASH_MODEL}:streamGenerateContent?alt=sse&key={key}"
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "gemini-omni/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                for raw_line in r:
                    line = raw_line.decode("utf-8").rstrip("\r\n")
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(data_str)
                        cands = chunk.get("candidates", [])
                        if not cands:
                            continue
                        c_parts = cands[0].get("content", {}).get("parts", [])
                        if not c_parts:
                            continue
                        text = c_parts[0].get("text", "")
                        if text:
                            yield text
                    except (KeyError, IndexError, json.JSONDecodeError):
                        continue
            return  # 成功完成，結束重試迴圈
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"[GeminiFlash-Stream] Key {attempt + 1} 配額已用盡（429），切換...", flush=True)
                _rotate_key()
                continue
            try:
                err_body = e.read().decode(errors="replace")
                print(f"[GeminiFlash-Stream] HTTP {e.code}: {err_body[:500]}", flush=True)
            except Exception:
                pass
            raise
        except Exception as e:
            print(f"[GeminiFlash-Stream] 連線例外: {e}", flush=True)
            raise

    raise RuntimeError(f"所有 {len(_GEMINI_KEYS)} 組 Gemini API Key 配額均已用盡")


async def _async_stream_flash(parts: List[Dict], system_prompt: str) -> AsyncGenerator[str, None]:
    """
    將 _stream_flash_sync 同步生成器包裝為非同步生成器。
    透過 Queue + Thread 轉接，不阻塞 asyncio event loop。
    """
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    _DONE = object()  # 哨兵物件，代表生成結束

    def _producer():
        try:
            for chunk in _stream_flash_sync(parts, system_prompt):
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)

    t = threading.Thread(target=_producer, daemon=True)
    t.start()

    while True:
        item = await queue.get()
        if item is _DONE:
            break
        if isinstance(item, Exception):
            raise item
        yield item

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
    Gemini 2.5 Flash 串流 + TTS 並行合成（介面與原 Qwen-Omni 相容）。

    流程：
      1. streamGenerateContent SSE 串流取得文字
      2. 偵測句子邊界 → 立即啟動 TTS Future（與 Flash 生成並行）
      3. Flash 完成後 yield 全文（UI 顯示）
      4. 按句序 await TTS Future → yield audio_b64
         （大部分 TTS 在 Flash 串流期間已並行執行完畢）
      5. 串流失敗時自動備援至阻塞式 generateContent + 原始逐句 TTS
    """
    gemini_voice = _map_voice(voice)
    parts = _convert_parts(content_list)
    if not parts:
        return

    loop = asyncio.get_running_loop()

    full_text_parts: List[str] = []   # 完整文字片段累積
    tts_futures: List[Any] = []       # TTS Future 清單（按句序）
    text_accumulator = ""             # 尚未切句的文字緩衝
    pending_buf = ""                  # 待合併的短句緩衝

    # ① 串流取得 Flash 文字，邊取邊啟動 TTS
    stream_failed = False
    try:
        async for chunk in _async_stream_flash(parts, _SYSTEM_PROMPT):
            full_text_parts.append(chunk)
            text_accumulator += chunk

            # 嘗試切出完整句子並立即啟動 TTS
            while True:
                match = _SENTENCE_END.search(text_accumulator)
                if not match:
                    break
                end_pos = match.end()
                sentence = text_accumulator[:end_pos].strip()
                text_accumulator = text_accumulator[end_pos:]

                if not sentence:
                    continue

                # 短句合併緩衝（避免 TTS finishReason=OTHER）
                pending_buf += sentence
                if len(pending_buf.replace(" ", "")) >= 5:
                    s_to_tts = pending_buf
                    pending_buf = ""
                    # 立即啟動 TTS，不等待（與後續 Flash 生成並行）
                    future = loop.run_in_executor(None, _call_tts, s_to_tts, gemini_voice)
                    tts_futures.append(future)

    except Exception as e:
        print(f"[GeminiFlash-Stream] 串流失敗: {e}", flush=True)
        stream_failed = True

    # 串流完全失敗（無任何內容）→ 備援至阻塞式 generateContent
    if not full_text_parts:
        if not stream_failed:
            # 串流成功但 Flash 無回應
            return
        print("[GeminiFlash-Stream] 無任何串流內容，啟動阻塞式備援...", flush=True)
        try:
            fallback_text = await loop.run_in_executor(None, _call_flash, parts, _SYSTEM_PROMPT)
        except Exception as e2:
            print(f"[GeminiFlash] 備援也失敗: {e2}", flush=True)
            return
        if not fallback_text:
            return
        print(f"[GeminiFlash] 備援回應: {fallback_text}", flush=True)
        # 備援：yield 全文 + 逐句序列 TTS（原始流程）
        yield OmniStreamPiece(text_delta=fallback_text)
        fb_sentences = _merge_short_sentences(
            _split_sentences(fallback_text) or [fallback_text]
        )
        for sentence in fb_sentences:
            if not sentence.strip():
                continue
            try:
                pcm = await loop.run_in_executor(None, _call_tts, sentence, gemini_voice)
                if pcm:
                    yield OmniStreamPiece(audio_b64=base64.b64encode(pcm).decode())
            except asyncio.CancelledError:
                raise
            except Exception as e3:
                print(f"[GeminiTTS] 備援合成失敗: {e3}", flush=True)
        return

    # ② 處理 Flash 串流結束後剩餘的未分句文字（無句末標點的片段）
    remaining = (text_accumulator + pending_buf).strip()
    if remaining:
        future = loop.run_in_executor(None, _call_tts, remaining, gemini_voice)
        tts_futures.append(future)

    full_text = "".join(full_text_parts).strip()
    if not full_text:
        return

    print(f"[GeminiFlash] 串流完成，全文: {full_text}", flush=True)

    # ③ yield 完整文字（UI 顯示用）
    yield OmniStreamPiece(text_delta=full_text)

    # ④ 按句序 await TTS Future，yield 音訊
    #    此時大部分 TTS 已在 Flash 串流期間並行完成，await 幾乎無額外等待
    for future in tts_futures:
        try:
            pcm_bytes = await future
            if pcm_bytes:
                yield OmniStreamPiece(audio_b64=base64.b64encode(pcm_bytes).decode())
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[GeminiTTS] 合成失敗: {e}", flush=True)
