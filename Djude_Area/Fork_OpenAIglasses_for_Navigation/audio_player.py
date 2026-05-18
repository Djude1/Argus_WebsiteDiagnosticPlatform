# audio_player.py
# 处理预录音频文件的播放，通过ESP32扬声器输出

import os
import wave
import json
import asyncio
import threading
import queue
import time
from audio_stream import broadcast_pcm16_realtime
from audio_compressor import compressed_audio_cache

# 导入录制器（避免循环导入，在需要时动态导入）
_recorder_imported = False
_sync_recorder = None

def _get_recorder():
    """延迟导入录制器"""
    global _recorder_imported, _sync_recorder
    if not _recorder_imported:
        try:
            import sync_recorder as sr
            _sync_recorder = sr
            _recorder_imported = True
        except Exception as e:
            print(f"[AUDIO] 无法导入录制器: {e}")
            _recorder_imported = True  # 标记已尝试，避免重复
    return _sync_recorder

# 音訊目錄從 config.py 讀取（路徑由 .env 的 AUDIO_BASE_DIR / VOICE_DIR 提供）
from config import AUDIO_BASE_DIR, VOICE_DIR, GOOGLE_CREDENTIALS_PATH
VOICE_MAP_FILE = os.path.join(VOICE_DIR, "map.zh-CN.json")

# 音频文件映射（将合并 voice 映射）
AUDIO_MAP = {
    "检测到物体": os.path.join(AUDIO_BASE_DIR, "音频1.wav"),
    "向上": os.path.join(AUDIO_BASE_DIR, "音频2.wav"),
    "向下": os.path.join(AUDIO_BASE_DIR, "音频3.wav"),
    "向左": os.path.join(AUDIO_BASE_DIR, "音频4.wav"),
    "向右": os.path.join(AUDIO_BASE_DIR, "音频5.wav"),
    "OK": os.path.join(AUDIO_BASE_DIR, "音频6.wav"),
    "向前": os.path.join(AUDIO_BASE_DIR, "音频7.wav"),
    "后退": os.path.join(AUDIO_BASE_DIR, "音频8.wav"),
    "拿到物体": os.path.join(AUDIO_BASE_DIR, "音频9.wav"),
    # 開機歡迎音效
    "歡迎使用AI智慧眼鏡": os.path.join(AUDIO_BASE_DIR, "歡迎使用AI智慧眼鏡.wav"),
    # 喚醒詞 / 結束詞回應音效
    "開始對話": os.path.join(AUDIO_BASE_DIR, "開始對話.wav"),
    "結束對話": os.path.join(AUDIO_BASE_DIR, "結束收音.wav"),  # 原 結束對話.wav 已重新命名為 結束收音.wav
    "結束收音": os.path.join(AUDIO_BASE_DIR, "結束收音.wav"),
    "使用說明書": os.path.join(AUDIO_BASE_DIR, "使用說明書.wav"),
}

# 音频缓存，避免重复读取
_audio_cache = {}

# 音频播放队列和工作线程 - 使用优先级队列
_audio_queue = queue.PriorityQueue(maxsize=10)
_audio_priority = 0  # 递增的优先级计数器
_worker_thread = None
_worker_loop = None
_is_playing = False  # 标记是否正在播放音频
_playing_lock = threading.Lock()  # 播放锁
_initialized = False
_last_play_ts = 0.0  # 记录上次播放结束时间，用于决定预热静音长度

def load_mp3_file(filepath):
    """使用 pydub 載入 MP3 並轉換為 PCM16 8kHz 單聲道（與 load_wav_file 輸出格式一致）"""
    if filepath in _audio_cache:
        return _audio_cache[filepath]
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_mp3(filepath)
        # 統一轉換為單聲道、16-bit、8kHz
        audio = audio.set_channels(1).set_sample_width(2).set_frame_rate(8000)
        frames = audio.raw_data
        _audio_cache[filepath] = frames
        print(f"[AUDIO] MP3 載入完成: {filepath} ({len(frames)//16000:.1f}s)")
        return frames
    except Exception as e:
        print(f"[AUDIO] MP3 載入失敗 {filepath}: {e}")
        return None


def load_wav_file(filepath):
    """加载WAV文件并返回PCM数据（自动转换为8kHz）"""
    if filepath in _audio_cache:
        return _audio_cache[filepath]
    
    # 使用压缩缓存
    if os.getenv("AIGLASS_COMPRESS_AUDIO", "1") == "1":
        compressed_data = compressed_audio_cache.load_and_compress(filepath)
        if compressed_data:
            # 存储压缩后的数据
            _audio_cache[filepath] = compressed_data
            return compressed_data
    
    # 原始加载方式（不压缩）
    try:
        with wave.open(filepath, 'rb') as wav:
            # 检查音频格式
            channels = wav.getnchannels()
            sampwidth = wav.getsampwidth()
            framerate = wav.getframerate()
            
            if channels != 1:
                print(f"[AUDIO] 警告: {filepath} 不是单声道，将只使用第一个声道")
            if sampwidth != 2:
                print(f"[AUDIO] 警告: {filepath} 不是16位音频")
            
            # 读取所有帧
            frames = wav.readframes(wav.getnframes())
            
            # 如果是立体声，只取左声道
            if channels == 2:
                import audioop
                frames = audioop.tomono(frames, sampwidth, 1, 0)
            
            # 统一转换为8kHz（使用ratecv保证音调和速度不变）
            if framerate != 8000:
                import audioop
                frames, _ = audioop.ratecv(frames, sampwidth, 1, framerate, 8000, None)
                print(f"[AUDIO] 重采样: {filepath} {framerate}Hz -> 8000Hz")
            
            _audio_cache[filepath] = frames
            return frames
            
    except Exception as e:
        print(f"[AUDIO] 加载音频文件失败 {filepath}: {e}")
        return None

# text → duration_ms（從 map.zh-CN.json 載入，供 APP 本地播音計算靜音時長）
_voice_duration_map: dict = {}

def _merge_voice_map():
    """读取 voice/map.zh-CN.json 并合并到 AUDIO_MAP"""
    global _voice_duration_map
    try:
        if not os.path.exists(VOICE_MAP_FILE):
            print(f"[AUDIO] 未找到映射文件: {VOICE_MAP_FILE}")
            return
        with open(VOICE_MAP_FILE, "r", encoding="utf-8") as f:
            m = json.load(f)
        added = 0
        for text, info in (m or {}).items():
            files = (info or {}).get("files") or []
            if not files:
                continue
            fname = files[0]
            fpath = os.path.join(VOICE_DIR, fname)
            if os.path.exists(fpath):
                AUDIO_MAP[text] = fpath
                _voice_duration_map[text] = (info or {}).get("duration_ms", 2000)
                added += 1
            else:
                print(f"[AUDIO] 映射文件缺失: {fpath}")
        print(f"[AUDIO] 已合并 voice 映射 {added} 条")
    except Exception as e:
        print(f"[AUDIO] 读取 voice 映射失败: {e}")

def preload_all_audio():
    """预加载所有音频文件到内存"""
    print("[AUDIO] 开始预加载音频文件...")
    loaded_count = 0
    
    # 【暂时禁用变速】因为需要修改缓存机制
    # 需要加速的音频列表（斑马线相关）
    # speedup_keywords = ["斑马线", "画面"]
    # speedup_factor = 1.3  # 加速30%
    
    for audio_key, filepath in AUDIO_MAP.items():
        if os.path.exists(filepath):
            data = load_wav_file(filepath)
            if data:
                loaded_count += 1
        else:
            # 降低噪声输出
            pass
    print(f"[AUDIO] 预加载完成，共加载 {loaded_count} 个音频文件")

def _audio_worker():
    """音频播放工作线程"""
    global _worker_loop
    
    # 尝试设置线程优先级（Windows特定）
    try:
        import ctypes
        import sys
        if sys.platform == "win32":
            # 设置线程为高优先级
            ctypes.windll.kernel32.SetThreadPriority(
                ctypes.windll.kernel32.GetCurrentThread(),
                1  # THREAD_PRIORITY_ABOVE_NORMAL
            )
            print("[AUDIO] 设置音频线程为高优先级")
    except Exception as e:
        print(f"[AUDIO] 设置线程优先级失败: {e}")
    
    _worker_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_worker_loop)
    
    async def process_queue():
        while True:
            try:
                # 从优先级队列获取数据
                priority_data = await asyncio.get_event_loop().run_in_executor(None, _audio_queue.get, True)
                if priority_data is None:
                    break
                # 解包优先级和实际音频数据
                if isinstance(priority_data, tuple) and len(priority_data) == 2:
                    _, audio_data = priority_data
                else:
                    audio_data = priority_data
                await _broadcast_audio_optimized(audio_data)
            except Exception as e:
                print(f"[AUDIO] 工作线程错误: {e}")
    
    _worker_loop.run_until_complete(process_queue())

async def _broadcast_audio_optimized(pcm_data: bytes):
    """优化的音频广播：单次调用由底层按20ms节拍发送，移除重复节拍和Python层sleep"""
    global _last_play_ts, _is_playing
    try:
        # 设置播放标志
        with _playing_lock:
            _is_playing = True
        # 此时 pcm_data 应该已经是解压后的16位PCM数据了（8kHz）
        now = time.monotonic()
        idle_sec = now - (_last_play_ts or now)
        # 首次或长时间空闲后，预热更长静音；否则小静音
        lead_ms = 160 if idle_sec > 3.0 else 60
        tail_ms = 40

        lead_silence = b'\x00' * (lead_ms * 8000 * 2 // 1000)  # 8k * 2B
        tail_silence = b'\x00' * (tail_ms * 8000 * 2 // 1000)

        # 完整音频数据（包含静音）
        full_audio = lead_silence + pcm_data + tail_silence
        
        # 注意：录制在 broadcast_pcm16_realtime 中统一完成，避免重复

        # 单次调用交给底层 pacing（20ms节拍在 broadcast_pcm16_realtime 内部实现）
        await broadcast_pcm16_realtime(full_audio)

        _last_play_ts = time.monotonic()
    except Exception as e:
        print(f"[AUDIO] 广播音频失败: {e}")
    finally:
        # 清除播放标志
        with _playing_lock:
            _is_playing = False

def initialize_audio_system():
    """初始化音频系统"""
    global _initialized, _worker_thread, _last_play_ts
    
    if _initialized:
        return
    
    # 先合并 voice 映射，再预加载
    _merge_voice_map()
    preload_all_audio()
    
    _worker_thread = threading.Thread(target=_audio_worker, daemon=True)
    _worker_thread.start()
    _initialized = True
    _last_play_ts = 0.0
    
    # 显示压缩统计
    if os.getenv("AIGLASS_COMPRESS_AUDIO", "1") == "1":
        stats = compressed_audio_cache.get_compression_stats()
        print("[AUDIO] 音频压缩统计:")
        print(f"  - 文件数: {stats['files_cached']}")
        print(f"  - 原始大小: {stats['total_original_size'] / 1024:.1f} KB")
        print(f"  - 压缩后: {stats['total_compressed_size'] / 1024:.1f} KB")
        print(f"  - 压缩率: {stats['compression_ratio']:.1%}")
        print(f"  - 节省: {stats['bytes_saved'] / 1024:.1f} KB")
    
    print("[AUDIO] 音频系统初始化完成（预加载+工作线程）")

def play_audio_threadsafe(audio_key):
    """线程安全的音频播放函数"""
    global _audio_queue, _audio_priority
    
    if not _initialized:
        initialize_audio_system()
    
    if audio_key not in AUDIO_MAP:
        print(f"[AUDIO] 未知的音频键: {audio_key}")
        return
    
    filepath = AUDIO_MAP[audio_key]
    pcm_data = _audio_cache.get(filepath)
    if pcm_data is None:
        print(f"[AUDIO] 音频未在缓存中: {audio_key}")
        return
    
    # 如果是压缩的数据，先解压
    if pcm_data and len(pcm_data) > 5 and pcm_data[0] in [0x01, 0x02]:
        pcm_data = compressed_audio_cache.decompress(pcm_data)
        if not pcm_data:
            print(f"[AUDIO] 解压失败: {audio_key}")
            return
    
    # 【优化】实时播报策略：保持队列最小化，避免积压延迟
    queue_size = _audio_queue.qsize()
    
    # 检查是否正在播放
    with _playing_lock:
        currently_playing = _is_playing
    
    # 实时策略：只允许1个积压，超过立即清空
    if queue_size > 0 and not currently_playing:
        # 未播放时立即清空，播放最新语音
        print(f"[AUDIO] 清空队列（当前{queue_size}个），播放最新语音")
        _audio_queue = queue.PriorityQueue(maxsize=10)
    elif queue_size > 1 and currently_playing:
        # 正在播放时，如果积压>1个则清空（保持实时性）
        print(f"[AUDIO] 队列积压({queue_size}个)，清空以保持实时")
        _audio_queue = queue.PriorityQueue(maxsize=10)
    try:
        # 使用优先级队列，确保音频按顺序播放
        _audio_priority += 1
        _audio_queue.put_nowait((_audio_priority, pcm_data))
        if queue_size >= 1:
            print(f"[AUDIO] 播放队列当前大小: {queue_size + 1}")
    except queue.Full:
        # 播放队列满则丢弃，保持实时性
        print(f"[AUDIO] 队列满，丢弃: {audio_key}")
        pass

# 全局语音节流
_last_voice_time = 0
_last_voice_text = ""
_voice_cooldown = 1.0  # 相同语音至少间隔1秒

# ── APP 本地語音推播鉤子 ──────────────────────────────────────────────────────
# app_main.py 在啟動時呼叫 register_speak_push() 注入廣播函式
# 每次成功命中預錄 WAV 時，額外推送 SPEAK:JSON 給 /ws_ui 客戶端
# 讓 APP 能用本地 WAV 播放，不依賴 /stream.wav 傳輸音訊
_speak_push_fn = None  # Callable[[str, int], None] | None

def register_speak_push(fn) -> None:
    """注入 push 函式：fn(text: str, duration_ms: int)"""
    global _speak_push_fn
    _speak_push_fn = fn


def _notify_speak(key: str) -> None:
    """成功命中 WAV 後，推送文字給 APP 做本地語音播放"""
    if _speak_push_fn is None:
        return
    try:
        duration_ms = _voice_duration_map.get(key, 2000)
        _speak_push_fn(key, duration_ms)
    except Exception:
        pass

# 语音优先级定义
VOICE_PRIORITY = {
    'obstacle': 100,     # 障碍物 - 最高优先级
    'direction': 50,     # 转向/平移 - 中等优先级  
    'straight': 10,      # 保持直行 - 最低优先级
    'other': 30          # 其他 - 默认优先级
}

# 新增：根据中文提示文案直接播放（会做轻度规范化与降级）
import re as _re

# ── 紅綠燈自然語句 → 短格式 WAV key ──────────────────────────────────────────
_TRAFFIC_LIGHT_MAP = {
    "红灯": "红灯", "紅燈": "红灯",
    "绿灯": "绿灯", "綠燈": "绿灯",
    "黄灯": "黄灯", "黃燈": "黄灯",
}

def _normalize_traffic_light(text: str):
    """若文字包含紅/綠/黃燈關鍵字，回傳對應短格式 key，否則回傳 None。"""
    for kw, key in _TRAFFIC_LIGHT_MAP.items():
        if kw in text:
            return key
    return None

# ── 時鐘方向 → 前方/左側/右側 ─────────────────────────────────────────────────
_CLOCK_FRONT  = {10, 11, 12, 1, 2}
_CLOCK_RIGHT  = {2, 3, 4, 5}
_CLOCK_LEFT   = {7, 8, 9, 10}

def _normalize_clock_direction(text: str):
    """
    偵測「N點鐘方向有X，urgency」模式，轉換為可匹配預錄 WAV 的方向式描述。
    例：「4點鐘方向有人，小心！」→「右側有人請向左避開」
    """
    m = _re.search(r'(\d{1,2})點鐘方向有(\S+?)(?:[，,。！]|$)', text)
    if not m:
        return None
    hour = int(m.group(1))
    obj  = m.group(2)

    # 決定方向
    if hour in _CLOCK_FRONT:
        direction = "前方"
    elif hour in _CLOCK_RIGHT:
        direction = "右側"
    elif hour in _CLOCK_LEFT:
        direction = "左側"
    else:
        return None  # 後方暫不處理

    # 決定物件類型
    obj_l = obj.lower()
    if "人" in obj_l:
        obj_key = "person"
    elif "公車" in obj_l or "巴士" in obj_l:
        obj_key = "bus"
    elif "機車" in obj_l or "摩托車" in obj_l or "摩托" in obj_l:
        obj_key = "motorcycle"
    elif "自行車" in obj_l or "腳踏車" in obj_l:
        obj_key = "bicycle"
    elif "車" in obj_l:
        obj_key = "car"
    elif "動物" in obj_l or "狗" in obj_l:
        obj_key = "dog"
    else:
        obj_key = "other"

    # 組合方向式語音（對應 _speech_for_obstacle_dir 邏輯）
    if direction == "前方":
        map_table = {
            "person":     "前方有人可往右移",
            "car":        "前方有車請稍等",
            "motorcycle": "前方有機車請稍等",
            "bicycle":    "前方有機車請稍等",
            "bus":        "前方有公車請稍等",
            "dog":        "前方有動物請小心",
        }
        return map_table.get(obj_key, "前方有障礙物請往右繞行")
    elif direction == "右側":
        map_table = {
            "person": "右側有人請向左避開",
            "car":    "右側有車請向左避開",
        }
        return map_table.get(obj_key, "右側有障礙請向左避開")
    else:  # 左側
        map_table = {
            "person": "左側有人請向右避開",
            "car":    "左側有車請向右避開",
        }
        return map_table.get(obj_key, "左側有障礙請向右避開")

# ── 應過濾不播報的除錯訊息 ──────────────────────────────────────────────────────
_SKIP_PHRASES = {
    "路径特征提取失败", "路徑特征提取失敗", "路径特征提取",
}

# ── 缺失語音記錄（供日後預錄，存到 voice_missing_log/）──────────────────────────
_MISSING_LOG_DIR = os.path.join(os.path.dirname(__file__), "voice_missing_log")
_missing_voice_set: set[str] = set()   # 當次執行期去重，避免同文字重複寫入

def _log_missing_voice(text: str) -> None:
    """將未命中預錄 WAV 的語音文字記錄到 voice_missing_log/YYYY-MM-DD.txt。
    部署機執行時自動累積，push 到 GitHub 後由本地 Claude Code 處理並預錄。
    """
    import datetime
    t = text.strip()
    if not t or t in _missing_voice_set:
        return
    try:
        os.makedirs(_MISSING_LOG_DIR, exist_ok=True)
        today = datetime.date.today().isoformat()
        log_path = os.path.join(_MISSING_LOG_DIR, f"{today}.txt")
        # 若檔案已有該行則不重複寫入
        existing: set[str] = set()
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                existing = {l.strip() for l in f if l.strip()}
        if t not in existing:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(t + "\n")
        _missing_voice_set.add(t)  # 只有寫入成功才記入 set
    except Exception as e:
        print(f"[AUDIO] 缺失語音記錄失敗: {e}（路徑: {_MISSING_LOG_DIR}）")

def play_voice_text(text: str):
    """
    传入中文提示，自动匹配 voice 映射并播放。
    - 正規化：紅綠燈短格式、時鐘方向→方向式、過濾除錯訊息
    - 尝试原文
    - 尝试补全/去除句末标点（。.!！?？）
    - 若包含"前方有…注意避让"但未命中，降级到"前方有障碍物，注意避让。"
    """
    global _last_voice_time, _last_voice_text

    if not text:
        return
    if not _initialized:
        initialize_audio_system()

    # ── 過濾除錯訊息，不播報 ──────────────────────────────────────────────────
    t_stripped = text.strip()
    if t_stripped in _SKIP_PHRASES:
        return

    # ── 正規化：紅綠燈自然語句 → 短格式 WAV key ──────────────────────────────
    tl_key = _normalize_traffic_light(t_stripped)
    if tl_key and tl_key in AUDIO_MAP:
        play_audio_threadsafe(tl_key)
        _notify_speak(tl_key)
        _last_voice_text = text
        _last_voice_time = time.time()
        return

    # ── 正規化：時鐘方向 → 方向式語音（對應現有預錄 WAV）─────────────────────
    clock_key = _normalize_clock_direction(t_stripped)
    if clock_key and clock_key in AUDIO_MAP:
        play_audio_threadsafe(clock_key)
        _notify_speak(clock_key)
        _last_voice_text = text
        _last_voice_time = time.time()
        return

    # 全局节流：相同文本短时间内不重复播放
    current_time = time.time()
    if text == _last_voice_text and current_time - _last_voice_time < _voice_cooldown:
        return  # 静默跳过

    candidates = []
    t = text.strip()
    candidates.append(t)
    # 尝试补全句号
    if t[-1:] not in ("。", "！", "!", "？", "?", "."):
        candidates.append(t + "。")
    else:
        # 尝试去掉标点
        t2 = t.rstrip("。.!！?？")
        if t2 and t2 != t:
            candidates.append(t2)

    # 逐一尝试匹配
    for ck in candidates:
        if ck in AUDIO_MAP:
            play_audio_threadsafe(ck)
            _notify_speak(ck)
            _last_voice_text = text
            _last_voice_time = current_time
            return

    # 繁體避障語音降級：未精確命中時，依方向降級到通用版本
    if "\u6709" in t and ("\u907f\u958b" in t or "\u8acb\u7a0d\u7b49" in t or "\u8acb\u5c0f\u5fc3" in t or "\u7e5e\u884c" in t or "\u53ef\u5f80" in t):
        # 左側/右側 → 降級到「有障礙請向X避開」
        for side, opp in [("左側", "右"), ("右側", "左")]:
            if t.startswith(side):
                fallback = f"{side}有障礙請向{opp}避開"
                if fallback in AUDIO_MAP:
                    play_audio_threadsafe(fallback)
                    _notify_speak(fallback)
                    _last_voice_text = text
                    _last_voice_time = current_time
                    return
                break
        # 前方 → 降級到「前方有障礙物請往右繞行」
        if t.startswith("前方"):
            fallback = "前方有障礙物請往右繞行"
            if fallback in AUDIO_MAP:
                play_audio_threadsafe(fallback)
                _notify_speak(fallback)
                _last_voice_text = text
                _last_voice_time = current_time
                return

    # 簡體避障語音降級（相容舊版語音檔）
    if ("前方有" in t) and ("注意避让" in t):
        fallback = "前方有障碍物，注意避让。"
        if fallback in AUDIO_MAP:
            play_audio_threadsafe(fallback)
            _notify_speak(fallback)
            _last_voice_text = text
            _last_voice_time = current_time
            return

    # 针对"请向…平移/微调/转动"类词条，常见变体尝试
    base = t.rstrip("。.!！?？")
    if base in AUDIO_MAP:
        play_audio_threadsafe(base)
        _notify_speak(base)
        _last_voice_text = text
        _last_voice_time = current_time
        return
    if base + "。" in AUDIO_MAP:
        play_audio_threadsafe(base + "。")
        _notify_speak(base + "。")
        _last_voice_text = text
        _last_voice_time = current_time
        return

    # 未命中預錄 WAV → 使用 Gemini TTS 動態合成（背景執行緒，不阻塞）
    print(f"[AUDIO] 未找到匹配語音，啟動 Gemini TTS: {text}")
    _last_voice_text = text
    _last_voice_time = current_time
    _log_missing_voice(text)   # 記錄缺失語音供日後預錄
    _play_tts_fallback(text)

def _wavenet_tts(text: str) -> bytes | None:
    """
    呼叫 Google Cloud TTS WaveNet（cmn-TW-Wavenet-A），回傳 PCM16 24kHz bytes。
    使用服務帳號憑證，消耗 Google Cloud 試用金。
    """
    try:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_CREDENTIALS_PATH
        from google.cloud import texttospeech
        client = texttospeech.TextToSpeechClient()
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=text),
            voice=texttospeech.VoiceSelectionParams(
                language_code="cmn-TW",
                name="cmn-TW-Wavenet-A",
            ),
            audio_config=texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                sample_rate_hertz=24000,
            ),
        )
        # response.audio_content 為含 WAV header 的 bytes，跳過 44-byte header 取 PCM
        return response.audio_content[44:]
    except Exception as e:
        print(f"[AUDIO TTS] WaveNet TTS 失敗: {e}", flush=True)
        return None


_tts_semaphore = threading.Semaphore(2)   # 最多 2 條 TTS 執行緒並發
_tts_last_time  = 0.0                      # 上次 TTS 開始時間
_TTS_MIN_INTERVAL = 2.0                    # 兩次 TTS 至少間隔 2 秒
_tts_rate_lock  = threading.Lock()

def _play_tts_fallback(text: str) -> None:
    """
    在背景執行緒中呼叫 Google Cloud TTS WaveNet，將結果重採樣後放入播放佇列。
    - WaveNet 回傳 PCM16 24kHz → audioop 重採樣至 8kHz
    - 最多 2 個並發 TTS 執行緒，且每 2 秒只允許 1 次 TTS，避免積壓
    """
    global _tts_last_time

    # 速率限制：2 秒內已有 TTS → 丟棄
    with _tts_rate_lock:
        now = time.time()
        if now - _tts_last_time < _TTS_MIN_INTERVAL:
            print(f"[AUDIO TTS] 速率限制，丟棄: {text}", flush=True)
            return
        _tts_last_time = now

    def _worker():
        if not _tts_semaphore.acquire(blocking=False):
            print(f"[AUDIO TTS] 並發上限，丟棄: {text}", flush=True)
            return
        try:
            import audioop
            pcm24k: bytes | None = _wavenet_tts(text)
            if not pcm24k:
                print(f"[AUDIO TTS] WaveNet TTS 回傳空音訊: {text}", flush=True)
                return

            # 24kHz 單聲道 → 8kHz（與預錄 WAV 相同格式）
            pcm8k, _ = audioop.ratecv(pcm24k, 2, 1, 24000, 8000, None)

            # 放入播放佇列（與 play_audio_threadsafe 相同機制）
            global _audio_priority
            _audio_priority += 1
            try:
                _audio_queue.put_nowait((_audio_priority, pcm8k))
                print(f"[AUDIO TTS] WaveNet 語音已加入佇列: {text}", flush=True)
            except queue.Full:
                print(f"[AUDIO TTS] 佇列已滿，丟棄: {text}", flush=True)
        except Exception as e:
            print(f"[AUDIO TTS] fallback 失敗: {e}", flush=True)
        finally:
            _tts_semaphore.release()

    threading.Thread(target=_worker, daemon=True, name="TTS-Fallback").start()


# 兼容旧接口
play_audio_on_esp32 = play_audio_threadsafe