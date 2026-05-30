# gemini_client.py
# -*- coding: utf-8 -*-
"""
Google Gemini 多模态对话客户端
支持密钥轮换池、视觉输入、文本转语音输出
与 omni_client.py 接口兼容
"""

import os
import base64
import asyncio
from typing import AsyncGenerator, Dict, Any, List, Optional
from dataclasses import dataclass

# 尝试导入 Gemini SDK
try:
    import google.generativeai as genai
    GEMINI_SDK_AVAILABLE = True
except ImportError:
    GEMINI_SDK_AVAILABLE = False
    print("[GeminiClient] 警告: google-generativeai 未安装，请运行: pip install google-generativeai")


# ============ 密钥池管理 ============
class GeminiKeyPool:
    """Gemini API 密钥轮换池"""
    
    def __init__(self):
        self._keys: List[str] = []
        self._current_index = 0
        self._load_keys()
    
    def _load_keys(self):
        """从环境变量加载所有密钥"""
        # 按顺序检查 GEMINI_API_KEY, GEMINI_API_KEY_2, ... GEMINI_API_KEY_10
        for i in range(1, 11):
            if i == 1:
                key = os.getenv("GEMINI_API_KEY", "")
            else:
                key = os.getenv(f"GEMINI_API_KEY_{i}", "")
            
            if key and key.strip():
                self._keys.append(key.strip())
        
        print(f"[GeminiClient] 密钥池加载了 {len(self._keys)} 个 API 密钥")
    
    def get_next_key(self) -> Optional[str]:
        """获取下一个可用的密钥"""
        if not self._keys:
            return None
        
        key = self._keys[self._current_index]
        self._current_index = (self._current_index + 1) % len(self._keys)
        return key
    
    def rotate_key(self):
        """切换到下一个密钥（当配额耗尽时调用）"""
        if len(self._keys) > 1:
            old_key = self._keys[self._current_index]
            self._current_index = (self._current_index + 1) % len(self._keys)
            new_key = self._keys[self._current_index]
            print(f"[GeminiClient] 轮换密钥: ...{old_key[-4:]} -> ...{new_key[-4:]}")
            return True
        return False
    
    @property
    def key_count(self) -> int:
        return len(self._keys)


# 全局密钥池实例
_key_pool = GeminiKeyPool()


# ============ 配置从环境变量读取 ============
# 模型配置
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")  # 默认使用 gemini-2.0-flash
GEMINI_VISION_MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-2.0-flash")
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-2.0-flash-exp")  # 支持音频生成的模型

# TTS 配置
USE_TTS = os.getenv("GEMINI_USE_TTS", "true").lower() == "true"
TTS_VOICE = os.getenv("GEMINI_TTS_VOICE", "Puck")  # Puck, Aoede, Charon, etc.
TTS_STYLE = os.getenv("GEMINI_TTS_STYLE", "excited")  # excited, sad, calm, fearful, etc.

# 视觉配置
GEMINI_VISION_ALWAYS_ON = os.getenv("GEMINI_VISION_ALWAYS_ON", "0") == "1"

# 生成参数
GEMINI_MAX_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS", "500"))
GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.7"))
GEMINI_TOP_P = float(os.getenv("GEMINI_TOP_P", "0.95"))
GEMINI_TOP_K = int(os.getenv("GEMINI_TOP_K", "40"))


@dataclass
class GeminiStreamPiece:
    """与 OmniStreamPiece 兼容的增量数据类"""
    text_delta: Optional[str] = None
    audio_b64: Optional[str] = None


def _encode_image_to_base64(image_data: bytes) -> str:
    """将图像数据编码为 base64"""
    return base64.b64encode(image_data).decode("utf-8")


def _make_content_list(content_list: List[Dict[str, Any]]) -> List[Any]:
    """
    将 omni_client 格式的内容列表转换为 Gemini 格式
    支持: 文本, 图像 (base64/URL)
    """
    if not GEMINI_SDK_AVAILABLE:
        return []
    
    from google.generativeai import content_types
    
    formatted_contents = []
    
    for item in content_list:
        if isinstance(item, str):
            # 纯文本
            formatted_contents.append(item)
        elif isinstance(item, dict):
            # 检查类型
            item_type = item.get("type", "")
            
            if item_type == "image_url":
                # 图像 URL 或 base64
                image_url = item.get("image_url", {})
                if isinstance(image_url, dict):
                    url = image_url.get("url", "")
                    if url.startswith("data:"):
                        # base64 数据
                        formatted_contents.append({
                            "mime_type": "image/jpeg",
                            "data": url.split(",", 1)[1] if "," in url else ""
                        })
                    else:
                        formatted_contents.append(url)
                else:
                    formatted_contents.append(str(image_url))
            elif item_type == "text":
                formatted_contents.append(item.get("text", ""))
    
    return formatted_contents


async def stream_chat(
    content_list: List[Dict[str, Any]],
    voice: str = TTS_VOICE,
    audio_format: str = "wav",
) -> AsyncGenerator[GeminiStreamPiece, None]:
    """
    使用 Gemini API 实现多模态对话流式输出
    与 omni_client.stream_chat 接口兼容
    
    Args:
        content_list: 内容列表，支持文本和图像
        voice: TTS 语音名称
        audio_format: 音频格式
    
    Yields:
        GeminiStreamPiece: 包含 text_delta 或 audio_b64
    """
    if not GEMINI_SDK_AVAILABLE:
        yield GeminiStreamPiece(text_delta="[错误] google-generativeai 未安装")
        return
    
    # 获取密钥
    api_key = _key_pool.get_next_key()
    if not api_key:
        yield GeminiStreamPiece(text_delta="[错误] 未配置 GEMINI_API_KEY")
        return
    
    # 配置 Gemini
    genai.configure(api_key=api_key)
    
    # 选择模型
    has_image = any(
        isinstance(item, dict) and item.get("type") == "image_url"
        for item in content_list
    )
    model_name = GEMINI_VISION_MODEL if has_image else GEMINI_MODEL
    
    try:
        # 创建模型
        model = genai.GenerativeModel(model_name)
        
        # 构建内容
        contents = _make_content_list(content_list)
        
        # 生成配置
        generation_config = {
            "max_output_tokens": GEMINI_MAX_TOKENS,
            "temperature": GEMINI_TEMPERATURE,
            "top_p": GEMINI_TOP_P,
            "top_k": GEMINI_TOP_K,
        }
        
        # 流式生成
        response = await model.generate_content_async(
            contents,
            generation_config=generation_config,
            stream=True,
        )
        
        text_buffer = []
        
        async for chunk in response:
            if chunk.text:
                text_buffer.append(chunk.text)
                yield GeminiStreamPiece(text_delta=chunk.text)
        
        # 生成完成后，如果启用 TTS，生成音频
        full_text = "".join(text_buffer).strip()
        if full_text and USE_TTS:
            try:
                # 使用 Gemini 的音频生成能力（如果可用）
                # 注意: gemini-2.0-flash-exp 支持音频输出
                audio_model = genai.GenerativeModel(GEMINI_TTS_MODEL)
                
                # 构建音频请求
                audio_contents = [
                    {"text": f"用中文语音朗读以下内容，只返回语音不要文本: {full_text}"}
                ]
                
                # 请求音频生成
                # 注意: 这是一个实验性功能，可能需要特定的模型
                # 如果不支持，会捕获异常并跳过
                try:
                    audio_response = await audio_model.generate_content_async(
                        audio_contents,
                        generation_config={
                            "response_modalities": ["AUDIO"],
                        },
                        stream=False
                    )
                    
                    # 如果返回了音频
                    if hasattr(audio_response, 'parts'):
                        for part in audio_response.parts:
                            if hasattr(part, 'inline_data') and part.inline_data:
                                audio_bytes = part.inline_data.data
                                # 分块返回
                                chunk_size = 1024
                                for i in range(0, len(audio_bytes), chunk_size):
                                    chunk = audio_bytes[i:i + chunk_size]
                                    b64_chunk = base64.b64encode(chunk).decode("ascii")
                                    yield GeminiStreamPiece(audio_b64=b64_chunk)
                except Exception as audio_err:
                    print(f"[GeminiClient] 音频生成跳过: {audio_err}")
                    # 静默跳过音频生成，不影响文本输出
                    
            except Exception as e:
                print(f"[GeminiClient] TTS 错误: {e}")
                # 静默失败，继续返回文本
    
    except Exception as e:
        error_msg = str(e)
        print(f"[GeminiClient] 错误: {error_msg}")
        
        # 检查是否是配额错误，尝试轮换密钥
        if "quota" in error_msg.lower() or "rate limit" in error_msg.lower():
            if _key_pool.rotate_key():
                yield GeminiStreamPiece(text_delta="[Gemini] 配额耗尽，切换密钥重试...")
            else:
                yield GeminiStreamPiece(text_delta=f"[Gemini 错误] {error_msg}")
        else:
            yield GeminiStreamPiece(text_delta=f"[Gemini 错误] {error_msg}")


def should_use_vision(user_text: str) -> bool:
    """判断是否应该使用视觉输入"""
    if GEMINI_VISION_ALWAYS_ON:
        return True
    
    vision_keywords = [
        "帮我看看", "帮我看下", "看看这", "看一下这",
        "这是什么", "图里", "图片里", "画面里", "镜头里",
        "识别一下", "识别这", "看得见", "能看到",
    ]
    return any(k in user_text for k in vision_keywords)


def get_key_pool() -> GeminiKeyPool:
    """获取密钥池实例"""
    return _key_pool


def reset_key_pool():
    """重置密钥池"""
    global _key_pool
    _key_pool = GeminiKeyPool()