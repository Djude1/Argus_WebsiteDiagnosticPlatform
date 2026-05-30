# audio_compressor.py
# -*- coding: utf-8 -*-
"""
音频压缩工具 - 用于减少网络带宽占用
支持将16kHz 16bit PCM压缩为更小的格式
"""
import os
import wave
import struct
import numpy as np
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class AudioCompressor:
    """音频压缩器 - 支持多种压缩算法"""
    
    @staticmethod
    def pcm16_to_ulaw(pcm_data: bytes) -> bytes:
        """
        将16位PCM转换为8位μ-law
        压缩率：50%（16bit -> 8bit）
        """
        # 解析16位PCM
        samples = np.frombuffer(pcm_data, dtype=np.int16)
        
        # μ-law压缩
        ulaw_data = bytearray()
        for sample in samples:
            ulaw_byte = AudioCompressor._linear_to_ulaw(sample)
            ulaw_data.append(ulaw_byte)
        
        return bytes(ulaw_data)
    
    @staticmethod
    def ulaw_to_pcm16(ulaw_data: bytes) -> bytes:
        """
        将8位μ-law转换回16位PCM
        """
        pcm_samples = []
        for ulaw_byte in ulaw_data:
            pcm_sample = AudioCompressor._ulaw_to_linear(ulaw_byte)
            pcm_samples.append(pcm_sample)
        
        return np.array(pcm_samples, dtype=np.int16).tobytes()
    
    @staticmethod
    def _linear_to_ulaw(sample: int) -> int:
        """
        16位线性PCM转μ-law
        """
        # μ-law编码表
        ULAW_MAX = 0x1FFF
        ULAW_BIAS = 0x84
        
        # 限制范围
        sample = max(-32768, min(32767, sample))
        
        # 获取符号位
        sign = 0
        if sample < 0:
            sign = 0x80
            sample = -sample
        
        # 添加偏置
        sample = sample + ULAW_BIAS
        
        # 限制最大值
        if sample > ULAW_MAX:
            sample = ULAW_MAX
        
        # 查找指数和尾数
        exponent = 7
        for exp in range(7, -1, -1):
            if sample & (0x4000 >> exp):
                exponent = exp
                break
        
        mantissa = (sample >> (exponent + 3)) & 0x0F
        ulawbyte = ~(sign | (exponent << 4) | mantissa) & 0xFF
        
        return ulawbyte
    
    @staticmethod
    def _ulaw_to_linear(ulawbyte: int) -> int:
        """
        μ-law转16位线性PCM
        """
        ULAW_BIAS = 0x84
        
        ulawbyte = ~ulawbyte & 0xFF
        sign = ulawbyte & 0x80
        exponent = (ulawbyte >> 4) & 0x07
        mantissa = ulawbyte & 0x0F
        
        sample = ((mantissa << 3) + ULAW_BIAS) << exponent
        
        if sign:
            sample = -sample
            
        return sample
    
    @staticmethod
    def pcm16_to_adpcm(pcm_data: bytes) -> bytes:
        """
        将16位PCM转换为4位ADPCM
        压缩率：75%（16bit -> 4bit）
        保持较好的语音质量
        """
        samples = np.frombuffer(pcm_data, dtype=np.int16)
        
        # IMA ADPCM 步长表
        step_table = [
            7, 8, 9, 10, 11, 12, 13, 14, 16, 17,
            19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
            50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
            130, 143, 157, 173, 190, 209, 230, 253, 279, 307,
            337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
            876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
            2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358,
            5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
            15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767
        ]
        
        # 索引调整表
        index_table = [-1, -1, -1, -1, 2, 4, 6, 8]
        
        # 初始化
        adpcm_data = bytearray()
        predicted = 0
        step_index = 0
        
        # 每两个样本打包成一个字节
        for i in range(0, len(samples), 2):
            byte = 0
            
            for j in range(2):
                if i + j < len(samples):
                    sample = samples[i + j]
                    
                    # 计算差值
                    diff = sample - predicted
                    
                    # 量化
                    step = step_table[step_index]
                    adpcm_sample = 0
                    
                    if diff < 0:
                        adpcm_sample = 8
                        diff = -diff
                    
                    if diff >= step:
                        adpcm_sample |= 4
                        diff -= step
                        
                    step >>= 1
                    if diff >= step:
                        adpcm_sample |= 2
                        diff -= step
                        
                    step >>= 1
                    if diff >= step:
                        adpcm_sample |= 1
                    
                    # 更新预测值
                    step = step_table[step_index]
                    diff = 0
                    if adpcm_sample & 4:
                        diff += step
                    step >>= 1
                    if adpcm_sample & 2:
                        diff += step
                    step >>= 1
                    if adpcm_sample & 1:
                        diff += step
                    step >>= 1
                    diff += step
                    
                    if adpcm_sample & 8:
                        predicted -= diff
                    else:
                        predicted += diff
                    
                    # 限制预测值范围
                    if predicted > 32767:
                        predicted = 32767
                    elif predicted < -32768:
                        predicted = -32768
                    
                    # 更新步长索引
                    step_index += index_table[adpcm_sample & 7]
                    if step_index < 0:
                        step_index = 0
                    elif step_index > 88:
                        step_index = 88
                    
                    # 打包到字节中
                    if j == 0:
                        byte = adpcm_sample
                    else:
                        byte |= (adpcm_sample << 4)
            
            adpcm_data.append(byte)
        
        # 添加头部信息：初始预测值和步长索引
        header = struct.pack('<hB', predicted, step_index)
        return header + bytes(adpcm_data)
    
    @staticmethod
    def adpcm_to_pcm16(adpcm_data: bytes) -> bytes:
        """
        将4位ADPCM转换回16位PCM
        """
        if len(adpcm_data) < 3:
            return b''
        
        # 读取头部
        predicted, step_index = struct.unpack('<hB', adpcm_data[:3])
        adpcm_bytes = adpcm_data[3:]
        
        # IMA ADPCM 步长表
        step_table = [
            7, 8, 9, 10, 11, 12, 13, 14, 16, 17,
            19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
            50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
            130, 143, 157, 173, 190, 209, 230, 253, 279, 307,
            337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
            876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
            2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358,
            5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
            15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767
        ]
        
        # 索引调整表
        index_table = [-1, -1, -1, -1, 2, 4, 6, 8]
        
        pcm_samples = []
        
        for byte in adpcm_bytes:
            # 解码两个4位样本
            for shift in [0, 4]:
                adpcm_sample = (byte >> shift) & 0x0F
                
                # 计算差值
                step = step_table[step_index]
                diff = 0
                
                if adpcm_sample & 4:
                    diff += step
                step >>= 1
                if adpcm_sample & 2:
                    diff += step
                step >>= 1
                if adpcm_sample & 1:
                    diff += step
                step >>= 1
                diff += step
                
                if adpcm_sample & 8:
                    predicted -= diff
                else:
                    predicted += diff
                
                # 限制范围
                if predicted > 32767:
                    predicted = 32767
                elif predicted < -32768:
                    predicted = -32768
                
                pcm_samples.append(predicted)
                
                # 更新步长索引
                step_index += index_table[adpcm_sample & 7]
                if step_index < 0:
                    step_index = 0
                elif step_index > 88:
                    step_index = 88
        
        return np.array(pcm_samples, dtype=np.int16).tobytes()
    
    @staticmethod
    def downsample_pcm16(pcm_data: bytes, from_rate: int = 16000, to_rate: int = 8000) -> bytes:
        """
        降采样（可选）
        16kHz -> 8kHz 可以再减少50%数据量
        """
        if from_rate == to_rate:
            return pcm_data
            
        # 解析PCM数据
        samples = np.frombuffer(pcm_data, dtype=np.int16)
        
        # 简单的降采样（每隔一个样本取一个）
        if from_rate == 16000 and to_rate == 8000:
            downsampled = samples[::2]
        else:
            # 更复杂的重采样需要scipy
            ratio = to_rate / from_rate
            new_length = int(len(samples) * ratio)
            downsampled = np.interp(
                np.linspace(0, len(samples) - 1, new_length),
                np.arange(len(samples)),
                samples
            ).astype(np.int16)
        
        return downsampled.tobytes()


class CompressedAudioCache:
    """压缩音频缓存"""
    
    def __init__(self, compression_type: str = "adpcm", use_downsample: bool = False):
        """
        compression_type: "none", "ulaw", "adpcm"
        """
        self.compression_type = compression_type
        self.use_downsample = use_downsample
        self._cache = {}  # {filepath: compressed_data}
        self._original_sizes = {}  # {filepath: original_size}
        
    def load_and_compress(self, filepath: str) -> Optional[bytes]:
        """加载并压缩音频文件（统一转换为8kHz）"""
        if filepath in self._cache:
            return self._cache[filepath]
        
        try:
            with wave.open(filepath, 'rb') as wav:
                # 检查格式
                channels = wav.getnchannels()
                sampwidth = wav.getsampwidth()
                framerate = wav.getframerate()
                
                if channels != 1:
                    logger.warning(f"{filepath} 不是单声道")
                if sampwidth != 2:
                    logger.warning(f"{filepath} 不是16位音频")
                
                # 读取所有数据
                frames = wav.readframes(wav.getnframes())
                
                # 如果是立体声，转换为单声道
                if channels == 2:
                    import audioop
                    frames = audioop.tomono(frames, sampwidth, 1, 0)
                
                # 【修改】始终转换为8kHz（使用ratecv保证音调和速度不变）
                if framerate != 8000:
                    import audioop
                    frames, _ = audioop.ratecv(frames, sampwidth, 1, framerate, 8000, None)
                    framerate = 8000
                
                # 记录原始大小（转换后的大小）
                self._original_sizes[filepath] = len(frames)
                
                # 压缩
                if self.compression_type == "ulaw":
                    compressed = AudioCompressor.pcm16_to_ulaw(frames)
                    # 添加简单的头部信息（1字节标识 + 4字节原始长度）
                    header = struct.pack('!BI', 0x01, len(frames))  # 0x01表示μ-law
                    compressed = header + compressed
                elif self.compression_type == "adpcm":
                    compressed = AudioCompressor.pcm16_to_adpcm(frames)
                    # 添加简单的头部信息（1字节标识 + 4字节原始长度）
                    header = struct.pack('!BI', 0x02, len(frames))  # 0x02表示ADPCM
                    compressed = header + compressed
                else:
                    compressed = frames
                
                self._cache[filepath] = compressed
                
                # 打印压缩率
                compression_ratio = len(compressed) / self._original_sizes[filepath]
                logger.info(f"[压缩] {os.path.basename(filepath)}: "
                          f"{self._original_sizes[filepath]} -> {len(compressed)} bytes "
                          f"({compression_ratio:.1%})")
                
                return compressed
                
        except Exception as e:
            logger.error(f"压缩音频失败 {filepath}: {e}")
            return None
    
    def decompress(self, compressed_data: bytes) -> Optional[bytes]:
        """解压音频数据"""
        if not compressed_data or len(compressed_data) < 5:
            return compressed_data
        
        try:
            # 检查头部
            compression_type = compressed_data[0]
            if compression_type == 0x01:  # μ-law标识
                header_size = 5
                original_length = struct.unpack('!I', compressed_data[1:5])[0]
                ulaw_data = compressed_data[header_size:]
                
                # μ-law解压
                pcm_data = AudioCompressor.ulaw_to_pcm16(ulaw_data)
                
                return pcm_data
            elif compression_type == 0x02:  # ADPCM标识
                header_size = 5
                original_length = struct.unpack('!I', compressed_data[1:5])[0]
                adpcm_data = compressed_data[header_size:]
                
                # ADPCM解压
                pcm_data = AudioCompressor.adpcm_to_pcm16(adpcm_data)
                
                return pcm_data
            else:
                # 未压缩的数据
                return compressed_data
                
        except Exception as e:
            logger.error(f"解压音频失败: {e}")
            return compressed_data
    
    def get_compression_stats(self) -> dict:
        """获取压缩统计信息"""
        total_original = sum(self._original_sizes.values())
        total_compressed = sum(len(data) for data in self._cache.values())
        
        return {
            "files_cached": len(self._cache),
            "total_original_size": total_original,
            "total_compressed_size": total_compressed,
            "compression_ratio": total_compressed / total_original if total_original > 0 else 0,
            "bytes_saved": total_original - total_compressed
        }


# 全局压缩音频缓存实例
# 默认使用ADPCM压缩，音质更好，压缩率也不错（75%）
# 可通过环境变量 AIGLASS_COMPRESS_TYPE 设置: none, ulaw, adpcm
import os
compression_type = os.getenv("AIGLASS_COMPRESS_TYPE", "adpcm").lower()
if compression_type not in ["none", "ulaw", "adpcm"]:
    compression_type = "adpcm"
compressed_audio_cache = CompressedAudioCache(compression_type=compression_type, use_downsample=False) 