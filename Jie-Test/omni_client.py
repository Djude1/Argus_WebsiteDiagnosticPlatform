# omni_client.py
# -*- coding: utf-8 -*-

import os
import base64
import asyncio
from typing import AsyncGenerator, Dict, Any, List, Optional

from openai import AsyncOpenAI

# ===== 从环境变量读取 OpenAI 配置 =====
API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("未设置 OPENAI_API_KEY")

BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
CHAT_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")  # 用于对话的模型
TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "tts-1")           # 语音合成模型
TTS_VOICE = os.getenv("OPENAI_TTS_VOICE", "alloy")           # 默认音色

# 初始化异步 OpenAI 客户端
client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)


class OmniStreamPiece:
    """对外的统一增量数据：text/audio 二选一或同时。"""
    def __init__(self, text_delta: Optional[str] = None, audio_b64: Optional[str] = None):
        self.text_delta = text_delta
        self.audio_b64 = audio_b64


async def stream_chat(
    content_list: List[Dict[str, Any]],
    voice: str = TTS_VOICE,
    audio_format: str = "wav",
) -> AsyncGenerator[OmniStreamPiece, None]:
    """
    使用 OpenAI 实现多模态对话流式输出：
    1. 通过 GPT-4o-mini 等模型流式生成文本回复。
    2. 将完整回复通过 TTS 转换为音频，分块返回（Base64 编码）。
    3. 保持与原 OmniStreamPiece 接口兼容。
    """
    # 构造消息（支持图片 + 文本）
    messages = [{"role": "user", "content": content_list}]

    text_buffer: List[str] = []          # 累积文本增量
    full_text: Optional[str] = None      # 最终完整文本

    try:
        # === 第一步：流式获取文本回复 ===
        stream = await client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            stream=True,
            max_tokens=500,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                text_buffer.append(delta.content)
                # 实时返回文本增量
                yield OmniStreamPiece(text_delta=delta.content)

        # 拼接完整文本
        full_text = "".join(text_buffer).strip()
        if not full_text:
            full_text = "（空响应）"

        # === 第二步：将完整文本转换为音频 ===
        # 调用 OpenAI TTS 生成音频（返回完整音频字节）
        response = await client.audio.speech.create(
            model=TTS_MODEL,
            voice=voice,
            input=full_text,
            response_format=audio_format,  # 支持 "wav", "mp3", "opus", "aac", "flac"
        )

        # 获取音频字节数据
        audio_bytes = response.content

        # 将音频分块（每块约 1KB）并 Base64 编码后返回
        chunk_size = 1024
        for i in range(0, len(audio_bytes), chunk_size):
            chunk = audio_bytes[i:i + chunk_size]
            b64_chunk = base64.b64encode(chunk).decode("ascii")
            yield OmniStreamPiece(audio_b64=b64_chunk)

    except Exception as e:
        print(f"[OmniClient] 错误: {e}", flush=True)
        # 返回错误信息作为文本增量，便于前端/日志查看
        yield OmniStreamPiece(text_delta=f"[AI 错误] {e}")