# -*- coding: utf-8 -*-
import asyncio
import os
from typing import List

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from openai_asr import OpenAIASRSession
from moonshine_asr import MoonshineASRSession
from omni_client import stream_chat
from qwen_extractor import extract_english_label


class _DummyCallback:
    def on_open(self):
        pass
    def on_close(self):
        pass
    def on_complete(self):
        pass
    def on_result(self, _result):
        pass
    def on_event(self, _event):
        pass
    def on_error(self, _err):
        pass


def verify_asr() -> None:
    provider = os.getenv("ASR_PROVIDER", "moonshine").strip().lower()
    silence_100ms = b"\x00\x00" * 1600

    if provider == "moonshine":
        sess = MoonshineASRSession(
            api_key="",
            model=os.getenv("MOONSHINE_MODEL", "base"),
            sample_rate=16000,
            callback=_DummyCallback(),
        )
        sess.start()
        for _ in range(10):
            sess.send_audio_frame(silence_100ms)
        sess.stop()
        print("[VERIFY][ASR] ok, provider=moonshine, stream_start_stop_passed")
        return

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("未设置 OPENAI_API_KEY")
    sess = OpenAIASRSession(
        api_key=api_key,
        model=os.getenv("OPENAI_ASR_MODEL", "whisper-1"),
        sample_rate=16000,
        callback=_DummyCallback(),
    )
    text = sess._transcribe_once(silence_100ms * 5)
    print(f"[VERIFY][ASR] ok, provider=openai, transcription_len={len(text)}")


async def verify_multimodal() -> None:
    content_list = [{"type": "text", "text": "请只回答‘收到’两个字。"}]
    text_parts: List[str] = []
    audio_chunks = 0

    async for piece in stream_chat(content_list, voice="alloy", audio_format="wav"):
        if piece.text_delta:
            text_parts.append(piece.text_delta)
        if piece.audio_b64:
            audio_chunks += 1

    final_text = "".join(text_parts).strip()
    if not final_text:
        raise RuntimeError("多模态对话未返回文本")
    if audio_chunks == 0:
        raise RuntimeError("多模态对话未返回音频分片")
    print(f"[VERIFY][MULTIMODAL] ok, text='{final_text[:40]}', audio_chunks={audio_chunks}")


def verify_label() -> None:
    label, src = extract_english_label("黑色记事本")
    if not label:
        raise RuntimeError("标签提取失败")
    print(f"[VERIFY][LABEL] ok, label='{label}', source='{src}'")


def main():
    verify_asr()
    asyncio.run(verify_multimodal())
    verify_label()
    print("[VERIFY] 三链路验证完成")


if __name__ == "__main__":
    main()
