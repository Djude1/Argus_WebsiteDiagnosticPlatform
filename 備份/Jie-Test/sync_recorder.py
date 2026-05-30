# sync_recorder.py
# 同步录制ESP32视频流和音频指令
# 自动确保视频和音频时间轴对齐

import os
import cv2
import wave
import numpy as np
import threading
import time
from datetime import datetime
from collections import deque
import struct

class SyncRecorder:
    """同步录制器 - 视频+音频时间对齐"""
    
    def __init__(self, output_dir="recordings", fps=15.0):
        """
        初始化录制器
        :param output_dir: 输出目录
        :param fps: 视频帧率（默认15fps）
        """
        self.output_dir = output_dir
        self.fps = fps
        self.frame_duration = 1.0 / fps  # 每帧时长（秒）
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 录制状态
        self.is_recording = False
        self.start_time = None
        
        # 视频写入器
        self.video_writer = None
        self.video_path = None
        self.last_frame = None
        self.frame_count = 0
        
        # 音频写入器
        self.audio_writer = None
        self.audio_path = None
        self.audio_buffer = bytearray()
        self.last_audio_time = 0.0
        
        # 音频参数（ESP32标准：16kHz, 16bit, Mono）
        self.sample_rate = 16000
        self.sample_width = 2  # 16bit = 2 bytes
        self.channels = 1
        
        # 线程安全
        self.lock = threading.Lock()
        
        # 性能监控
        self.frames_written = 0
        self.audio_bytes_written = 0
        self.last_log_time = time.time()
        
        print(f"[RECORDER] 录制器初始化完成 - FPS={fps}, 输出目录={output_dir}")
    
    def start_recording(self):
        """开始新的录制会话"""
        if self.is_recording:
            print("[RECORDER] 警告：已经在录制中")
            return False
        
        # 生成文件名（时间戳）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.video_path = os.path.join(self.output_dir, f"video_{timestamp}.avi")
        self.audio_path = os.path.join(self.output_dir, f"audio_{timestamp}.wav")
        
        # 重置状态
        self.start_time = time.time()
        self.last_audio_time = 0.0
        self.frame_count = 0
        self.frames_written = 0
        self.audio_bytes_written = 0
        self.audio_buffer.clear()
        self.last_frame = None
        
        # 初始化音频文件
        try:
            self.audio_writer = wave.open(self.audio_path, 'wb')
            self.audio_writer.setnchannels(self.channels)
            self.audio_writer.setsampwidth(self.sample_width)
            self.audio_writer.setframerate(self.sample_rate)
        except Exception as e:
            print(f"[RECORDER] 音频文件初始化失败: {e}")
            return False
        
        self.is_recording = True
        print(f"[RECORDER] 开始录制")
        print(f"  视频: {self.video_path}")
        print(f"  音频: {self.audio_path}")
        return True
    
    def add_frame(self, jpeg_data: bytes):
        """
        添加一帧视频（原始JPEG数据）
        :param jpeg_data: JPEG格式的图像数据
        """
        if not self.is_recording:
            return
        
        try:
            with self.lock:
                # 解码JPEG
                arr = np.frombuffer(jpeg_data, dtype=np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                
                if frame is None:
                    print(f"[RECORDER] 警告：帧解码失败")
                    return
                
                # 首帧：初始化视频写入器
                if self.video_writer is None:
                    height, width = frame.shape[:2]
                    # 使用XVID编码器（Windows兼容性好）
                    fourcc = cv2.VideoWriter_fourcc(*'XVID')
                    self.video_writer = cv2.VideoWriter(
                        self.video_path, 
                        fourcc, 
                        self.fps, 
                        (width, height)
                    )
                    
                    if not self.video_writer.isOpened():
                        print(f"[RECORDER] 错误：视频写入器初始化失败")
                        self.is_recording = False
                        return
                    
                    print(f"[RECORDER] 视频写入器初始化：{width}x{height} @ {self.fps}fps")
                
                # 写入帧
                self.video_writer.write(frame)
                self.frame_count += 1
                self.frames_written += 1
                self.last_frame = frame
                
                # 计算当前视频时长（秒）
                current_video_time = self.frame_count * self.frame_duration
                
                # 音频同步：填充静音到视频时长
                self._sync_audio_to_video(current_video_time)
                
                # 性能日志（每10秒）
                now = time.time()
                if now - self.last_log_time > 10.0:
                    elapsed = now - self.start_time
                    avg_fps = self.frames_written / elapsed if elapsed > 0 else 0
                    audio_duration = self.audio_bytes_written / (self.sample_rate * self.sample_width)
                    print(f"[RECORDER] 录制中 - 帧数={self.frames_written}, "
                          f"实际FPS={avg_fps:.1f}, "
                          f"视频时长={current_video_time:.1f}s, "
                          f"音频时长={audio_duration:.1f}s")
                    self.last_log_time = now
                    
        except Exception as e:
            print(f"[RECORDER] 添加帧失败: {e}")
            import traceback
            traceback.print_exc()
    
    def add_audio(self, pcm_data: bytes, text: str = ""):
        """
        添加音频数据（PCM 16bit）
        :param pcm_data: PCM格式音频数据
        :param text: 语音文本（用于日志）
        """
        if not self.is_recording:
            return
        
        try:
            with self.lock:
                # 当前视频时长
                current_video_time = self.frame_count * self.frame_duration
                
                # 在添加音频前，先填充静音到视频时长
                self._sync_audio_to_video(current_video_time)
                
                # 写入实际音频
                self.audio_writer.writeframes(pcm_data)
                audio_duration = len(pcm_data) / (self.sample_rate * self.sample_width)
                self.last_audio_time = current_video_time + audio_duration
                self.audio_bytes_written += len(pcm_data)
                
                if text:
                    print(f"[RECORDER] 录制语音: {text[:30]}... (时间={current_video_time:.2f}s, 时长={audio_duration:.2f}s)")
                    
        except Exception as e:
            print(f"[RECORDER] 添加音频失败: {e}")
    
    def _sync_audio_to_video(self, video_time: float):
        """
        同步音频到视频时长（填充静音）
        :param video_time: 当前视频时长（秒）
        """
        # 计算需要填充的静音时长
        silence_duration = video_time - self.last_audio_time
        
        if silence_duration > 0.01:  # 大于10ms才填充
            # 生成静音数据
            silence_samples = int(silence_duration * self.sample_rate)
            silence_bytes = silence_samples * self.sample_width
            silence_data = b'\x00' * silence_bytes
            
            # 写入静音
            self.audio_writer.writeframes(silence_data)
            self.audio_bytes_written += len(silence_data)
            self.last_audio_time = video_time
    
    def stop_recording(self):
        """停止录制并保存文件"""
        if not self.is_recording:
            return
        
        print("[RECORDER] 正在保存录制文件...")
        self.is_recording = False
        
        with self.lock:
            # 最后一次音频同步
            try:
                if self.frame_count > 0:
                    final_video_time = self.frame_count * self.frame_duration
                    self._sync_audio_to_video(final_video_time)
            except Exception as e:
                print(f"[RECORDER] 最终音频同步失败: {e}")
            
            # 关闭视频写入器（关键步骤）
            if self.video_writer is not None:
                try:
                    print("[RECORDER] 正在关闭视频写入器...")
                    self.video_writer.release()
                    print("[RECORDER] 视频写入器已关闭")
                except Exception as e:
                    print(f"[RECORDER] 关闭视频写入器失败: {e}")
                finally:
                    self.video_writer = None
            
            # 关闭音频写入器
            if self.audio_writer is not None:
                try:
                    print("[RECORDER] 正在关闭音频写入器...")
                    self.audio_writer.close()
                    print("[RECORDER] 音频写入器已关闭")
                except Exception as e:
                    print(f"[RECORDER] 关闭音频写入器失败: {e}")
                finally:
                    self.audio_writer = None
            
            # 统计信息
            try:
                elapsed = time.time() - self.start_time if self.start_time else 0
                video_duration = self.frame_count * self.frame_duration
                audio_duration = self.audio_bytes_written / (self.sample_rate * self.sample_width)
                
                print(f"\n{'='*60}")
                print(f"[RECORDER] 录制完成")
                print(f"{'='*60}")
                print(f"  总耗时: {elapsed:.1f}秒")
                print(f"\n  视频: {self.video_path}")
                print(f"    - 帧数: {self.frames_written}")
                print(f"    - 时长: {video_duration:.2f}秒")
                if elapsed > 0:
                    print(f"    - 平均FPS: {self.frames_written/elapsed:.1f}")
                print(f"\n  音频: {self.audio_path}")
                print(f"    - 数据量: {self.audio_bytes_written/1024:.1f} KB")
                print(f"    - 时长: {audio_duration:.2f}秒")
                print(f"\n  时间差: {abs(video_duration - audio_duration):.3f}秒")
                
                # 验证文件
                if os.path.exists(self.video_path):
                    video_size = os.path.getsize(self.video_path) / 1024 / 1024
                    print(f"  视频文件大小: {video_size:.2f} MB ✓")
                else:
                    print(f"  ⚠ 警告：视频文件未生成")
                
                if os.path.exists(self.audio_path):
                    audio_size = os.path.getsize(self.audio_path) / 1024
                    print(f"  音频文件大小: {audio_size:.2f} KB ✓")
                else:
                    print(f"  ⚠ 警告：音频文件未生成")
                
                print(f"{'='*60}\n")
            except Exception as e:
                print(f"[RECORDER] 显示统计信息失败: {e}")


# 全局录制器实例
_global_recorder = None
_recorder_lock = threading.Lock()

def get_recorder():
    """获取全局录制器实例"""
    global _global_recorder
    with _recorder_lock:
        if _global_recorder is None:
            _global_recorder = SyncRecorder()
        return _global_recorder

def start_recording():
    """启动录制"""
    recorder = get_recorder()
    return recorder.start_recording()

def stop_recording():
    """停止录制"""
    recorder = get_recorder()
    recorder.stop_recording()

def record_frame(jpeg_data: bytes):
    """记录一帧（供外部调用）"""
    recorder = get_recorder()
    if recorder.is_recording:
        recorder.add_frame(jpeg_data)

def record_audio(pcm_data: bytes, text: str = ""):
    """记录音频（供外部调用）"""
    recorder = get_recorder()
    if recorder.is_recording:
        recorder.add_audio(pcm_data, text)

