# AI 智能盲人眼镜系统 - AGENTS.md

**生成日期**: 2026-03-29
**项目**: OpenAIglasses_for_Navigation
**描述**: 面向视障人士的智能导航与辅助系统

---

## 📁 项目结构

```
OpenAIglasses_for_Navigation/
├── app_main.py                 # FastAPI 主服务入口
├── navigation_master.py        # 导航统领器（状态机）
├── workflow_blindpath.py       # 盲道导航工作流
├── workflow_crossstreet.py     # 过马路导航工作流
├── yolomedia.py               # 物品查找工作流
├── bridge_io.py               # 线程安全的帧缓冲
├── sync_recorder.py           # 音视频同步录制
│
├── 🎙️ 语音处理
│   ├── asr_core.py            # 语音识别核心（VAD + 指令解析）
│   ├── openai_asr.py          # OpenAI Whisper ASR
│   ├── moonshine_asr.py       # Moonshine ASR（阿里云）
│   ├── omni_client.py         # OpenAI Omni 多模态对话
│   ├── gemini_client.py       # Google Gemini 多模态对话
│   ├── qwen_extractor.py      # 标签提取（中文→英文）
│   ├── audio_player.py        # 音频播放器
│   └── audio_stream.py        # 音频流管理
│
├── 🤖 模型推理
│   ├── yoloe_backend.py       # YOLO-E 开放词汇检测
│   ├── trafficlight_detection.py  # 红绿灯检测
│   ├── obstacle_detector_client.py # 障碍物检测
│   ├── crosswalk_awareness.py # 斑马线检测
│   └── models.py              # 模型定义
│
├── 🌐 前端
│   ├── templates/index.html   # Web 监控界面
│   └── static/                # 静态资源
│
├── 📹 录制/模型
│   ├── recordings/            # 录制的视频/音频
│   ├── model/                 # YOLO 模型文件
│   ├── voice/                 # 预录语音
│   └── music/                 # 系统提示音
│
└── ⚙️ 配置
    ├── .env                   # 环境变量配置
    ├── Dockerfile             # Docker 镜像
    └── docker-compose.yml     # Docker Compose
```

---

## 🔑 环境变量完整参考

### API 密钥

| 变量名 | 必需 | 默认值 | 用途 |
|--------|------|--------|------|
| `OPENAI_API_KEY` | 是* | - | OpenAI API 密钥（用于 Whisper ASR 和 Omni 对话）|
| `DASHSCOPE_API_KEY` | 是* | - | 阿里云 DashScope API 密钥（用于 Moonshine ASR、Qwen）|
| `GEMINI_API_KEY` | 否 | - | Google Gemini API 密钥（支持密钥轮换）|
| `GEMINI_API_KEY_2` ~ `GEMINI_API_KEY_10` | 否 | - | Gemini 备用密钥池 |
| `GROQ_API_KEY` | 否 | - | Groq Whisper ASR 备用 |
| `OPENROUTER_API_KEY` | 否 | - | OpenRouter 备用 |

> * 至少需要配置一个 API 密钥，取决于使用的 ASR/AI 提供商

### ASR 语音识别配置

| 变量名 | 默认值 | 用途 |
|--------|--------|------|
| `ASR_PROVIDER` | `openai` | ASR 提供商：`openai` / `moonshine` |
| `OPENAI_ASR_MODEL` | `whisper-1` | Whisper 模型名称 |
| `OPENAI_ASR_LANGUAGE` | `zh` | 识别语言 |
| `OPENAI_ASR_VAD_RMS` | `160` | 主语音阈值 |
| `OPENAI_ASR_MAX_EFFECTIVE_RMS` | `50` | 最高有效能量 |
| `OPENAI_ASR_FALLBACK_RMS` | `12` | 弱语音阈值 |
| `OPENAI_ASR_END_SILENCE_FRAMES` | `10` | 连续静音帧数判定结束 |
| `MOONSHINE_MODEL` | `medium_streaming` | Moonshine 模型 |
| `MOONSHINE_LANGUAGE` | `zh` | Moonshine 语言 |
| `MOONSHINE_UPDATE_INTERVAL` | `0.5` | 流式更新间隔 |
| `ASR_VAD_RMS` | `140` | 通用 VAD 阈值 |
| `ASR_MIN_FINAL_CHARS` | `2` | 允许最短句子 |
| `ASR_FILLER_PHRASES` | `请问,在吗,有接吗...` | 过滤填充词 |
| `ASR_FINAL_COMMIT_DELAY_MS` | `900` | 提交延迟 |
| `INTERRUPT_KEYWORDS` | `停下,别说了,停止` | 中断关键词 |

### AI 对话配置

| 变量名 | 默认值 | 用途 |
|--------|--------|------|
| `AI_PROVIDER` | `openai` | AI 提供商：`openai` / `gemini` |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI API 端点 |
| `OPENAI_VISION_MODEL` | `gpt-4o-mini` | 视觉对话模型 |
| `OPENAI_TTS_MODEL` | `tts-1` | 语音合成模型 |
| `OPENAI_TTS_VOICE` | `alloy` | TTS 音色 |
| `OPENAI_LABEL_MODEL` | `gpt-4o-mini` | 标签提取模型 |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini 文本模型 |
| `GEMINI_VISION_MODEL` | `gemini-2.0-flash` | Gemini 视觉模型 |
| `GEMINI_TTS_MODEL` | `gemini-2.0-flash-exp` | Gemini 音频模型 |
| `GEMINI_MAX_TOKENS` | `500` | 最大输出 tokens |
| `GEMINI_TEMPERATURE` | `0.7` | 生成温度 |
| `GEMINI_USE_TTS` | `true` | 启用 Gemini TTS |
| `GEMINI_TTS_VOICE` | `Puck` | Gemini TTS 音色 |
| `OPENAI_VISION_ALWAYS_ON` | `0` | 始终使用视觉输入 |

### TTS 语音播报配置

| 变量名 | 默认值 | 用途 |
|--------|--------|------|
| `TTS_INTERVAL_SEC` | `1.0` | 语音播报间隔 |
| `ENABLE_TTS` | `true` | 启用 TTS |
| `ASR_PCM_GAIN` | `10.0` | ESP32 麦克风增益 |
| `ASR_STANDBY_RMS_THRESH` | `50.0` | 待机模式 RMS 阈值 |

### 模型路径配置

| 变量名 | 默认值 | 用途 |
|--------|--------|------|
| `BLIND_PATH_MODEL` | `model/yolo-seg.pt` | 盲道分割模型 |
| `OBSTACLE_MODEL` | `model/yoloe-11l-seg.pt` | 障碍物检测模型 |
| `YOLOE_MODEL_PATH` | `model/yoloe-11l-seg.pt` | YOLO-E 模型 |
| `TRAFFIC_LIGHT_MODEL` | `model/trafficlight.pt` | 红绿灯检测模型 |
| `ITEM_SEARCH_MODEL` | `model/shoppingbest5.pt` | 物品识别模型 |
| `SHOPPING_MODEL` | `model/shoppingbest5.pt` | 购物物品模型 |
| `HAND_TASK_PATH` | `model/hand_landmarker.task` | MediaPipe 手部模型 |
| `HAND_LANDMARKER_PATH` | `model/hand_landmarker.task` | 手部地标模型 |

### 服务器配置

| 变量名 | 默认值 | 用途 |
|--------|--------|------|
| `SERVER_HOST` | `0.0.0.0` | 服务器地址 |
| `SERVER_PORT` | `8081` | HTTP 端口 |
| `UDP_IP` | `0.0.0.0` | IMU UDP 地址 |
| `UDP_PORT` | `12345` | IMU UDP 端口 |
| `AUDIO_SAMPLE_RATE` | `16000` | 音频采样率 |
| `AUDIO_CHUNK_MS` | `20` | 音频块大小 |

### 本机模式配置

| 变量名 | 默认值 | 用途 |
|--------|--------|------|
| `LOCAL_MODE` | `false` | 启用本机模式（使用电脑摄像头/麦克风）|
| `CAM_INDEX` | `0` | 摄像头索引 |
| `LOCAL_CAM_QUALITY` | `70` | 摄像头画质 (1-100) |

### 导航调校参数

| 变量名 | 默认值 | 用途 |
|--------|--------|------|
| `AIGLASS_MASK_MIN_AREA` | `1500` | 最小掩码面积 |
| `AIGLASS_MASK_MORPH` | `3` | 形态学核大小 |
| `AIGLASS_PANEL_SCALE` | `0.65` | 数据面板缩放 |
| `AIGLASS_OBS_INTERVAL` | `15` | 障碍物检测间隔 |
| `AIGLASS_BLINDPATH_INTERVAL` | `8` | 盲道导航间隔 |
| `AIGLASS_OBS_CONF` | `0.25` | 障碍物检测置信度 |
| `NEMOTRON_MIN_INTERVAL` | `3.0` | Nemotron 最小间隔 |

### GPU 配置

| 变量名 | 默认值 | 用途 |
|--------|--------|------|
| `AIGLASS_DEVICE` | `cuda:0` | GPU 设备 |
| `AIGLASS_AMP` | `bf16` | 自动混合精度 (`fp16` / `bf16`) |
| `AIGLASS_GPU_SLOTS` | `2` | GPU 槽位 |

### 说话人验证

| 变量名 | 默认值 | 用途 |
|--------|--------|------|
| `SPEAKER_VERIFY_ENABLED` | `false` | 启用说话人验证 |
| `SPEAKER_EMBED_PATH` | `model/speaker_embed.pkl` | 声纹存储路径 |
| `SPEAKER_THRESHOLD` | `0.82` | 余弦相似度阈值 |
| `SPEAKER_BACKEND` | `auto` | 验证后端 |

### 运行时参数

| 变量名 | 默认值 | 用途 |
|--------|--------|------|
| `CAM_PROCESS_EVERY_N` | `2` | 视频处理帧间隔 |
| `CAM_STREAM_EVERY_N` | `2` | 视频流发送帧间隔 |
| `CAM_JPEG_QUALITY` | `75` | JPEG 压缩质量 |
| `RECORDER_EVERY_N` | `2` | 录制帧间隔 |
| `RECORDER_CAPTURE_UPLINK` | `1` | 录制上行音频 |

---

## 🎯 核心模块说明

### 状态机 (navigation_master.py)

系统包含以下主要状态：
- `IDLE` - 空闲
- `CHAT` - 对话模式
- `BLINDPATH_NAV` - 盲道导航
- `CROSSING` - 过马路
- `TRAFFIC_LIGHT_DETECTION` - 红绿灯检测
- `ITEM_SEARCH` - 物品查找

### 语音指令

```
导航控制:
  "开始导航" / "盲道导航" → 启动盲道导航
  "停止导航" / "结束导航" → 停止导航
  "开始过马路" / "帮我过马路" → 启动过马路
  "过马路结束" / "结束过马路" → 停止过马路

物品查找:
  "帮我找一下 [物品名]" → 启动物品搜索
  "找到了" / "拿到了" → 确认找到

对话:
  "帮我看看这是什么" → 拍照识别
  任何其他问题 → AI 对话
```

---

## 🔧 开发规范

### 环境变量优先级

1. `.env` 文件中的值
2. 系统环境变量
3. 代码中的默认值

### 添加新环境变量

1. 在 `.env` 文件中添加（带注释和默认值）
2. 在对应模块中使用 `os.getenv("VAR_NAME", "default")` 读取
3. 在本 AGENTS.md 中添加文档

### 模块接口约定

```python
# 语音客户端接口 (与 omni_client.py 兼容)
async def stream_chat(
    content_list: List[Dict[str, Any]],  # 支持 text 和 image_url
    voice: str = "alloy",
    audio_format: str = "wav",
) -> AsyncGenerator[Union[OmniStreamPiece, GeminiStreamPiece], None]:
    """
    流式返回 text_delta 和/或 audio_b64
    """
    yield OmniStreamPiece(text_delta="...", audio_b64="...")
```

---

## 🚀 快速启动

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API 密钥

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动服务
python app_main.py

# 4. 访问 Web 界面
# http://localhost:8081
```

---

## 📝 注意事项

1. **API 密钥安全**: 不要提交 `.env` 文件到 Git
2. **模型文件**: 需要从 ModelScope 下载模型文件到 `model/` 目录
3. **GPU 支持**: 推荐使用 NVIDIA RTX 3060+ 以获得最佳性能
4. **ASR 提供商**: 默认使用 OpenAI Whisper，可切换到 Moonshine
5. **AI 提供商**: 可通过 `AI_PROVIDER` 切换到 Gemini

---

## 🔗 外部资源

- 模型下载: https://www.modelscope.cn/models/archifancy/AIGlasses_for_navigation
- 阿里云 DashScope: https://dashscope.console.aliyun.com/
- Google Gemini: https://ai.google.dev/
- MediaPipe 手部模型: https://developers.google.com/mediapipe/solutions/vision/hand_landmarker