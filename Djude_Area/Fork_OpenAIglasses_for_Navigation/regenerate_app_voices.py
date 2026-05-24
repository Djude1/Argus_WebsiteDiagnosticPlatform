# regenerate_app_voices.py
# 重新生成 APP 端高品質語音 wav（24kHz Chirp3-HD），取代原本的 8kHz
#
# 設計：
# - 不動 voice/（保留 8kHz 給 ESP32 用）
# - 在 Android/assets/audio/ 加 *_App.wav（24kHz）
# - 更新 Android/assets/voice_map.json：file → *_App.wav，duration_ms 重新計算
#
# 執行：
#   uv run python regenerate_app_voices.py            # 全部重生（跳過已存在）
#   uv run python regenerate_app_voices.py --test 3   # 只跑前 3 個驗證
#   uv run python regenerate_app_voices.py --force    # 強制覆蓋已存在的 *_App.wav

import os
import sys
import json
import wave
import time
import base64
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(ROOT, "Android", "assets")
AUDIO_DIR = os.path.join(ASSETS_DIR, "audio")
MAP_FILE = os.path.join(ASSETS_DIR, "voice_map.json")

TARGET_SR = 24000  # APP 端要的高品質採樣率（vs 舊 8kHz）

GOOGLE_CREDENTIALS_PATH = os.environ.get(
    "GOOGLE_CREDENTIALS_PATH",
    os.path.join(ROOT, "google_Speech_to_Text.json"),
)

# Gemini TTS 備援（Chirp3 失敗時）
_TTS_MODEL = "gemini-2.5-flash-preview-tts"
_TTS_VOICE = "Sulafat"
_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_GEMINI_KEYS = [k for k in [
    os.getenv(f"GEMINI_API_KEY{'_' + str(i) if i > 1 else ''}", "")
    for i in range(1, 17)
] if k]
_key_index = 0


def _next_key() -> str:
    global _key_index
    _key_index = (_key_index + 1) % len(_GEMINI_KEYS)
    return _GEMINI_KEYS[_key_index]


def _current_key() -> str:
    return _GEMINI_KEYS[_key_index] if _GEMINI_KEYS else ""


def _chirp3_tts(text: str) -> bytes | None:
    """Google Cloud TTS Chirp3-HD Sulafat → 24kHz PCM16 bytes"""
    try:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_CREDENTIALS_PATH
        from google.cloud import texttospeech
        client = texttospeech.TextToSpeechClient()
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=text),
            voice=texttospeech.VoiceSelectionParams(
                language_code="cmn-CN",
                name="cmn-CN-Chirp3-HD-Sulafat",
            ),
            audio_config=texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                sample_rate_hertz=TARGET_SR,
            ),
        )
        # response.audio_content 含 WAV header (44 byte) → 跳過取 PCM
        return response.audio_content[44:]
    except Exception as e:
        print(f" [Chirp3 失敗: {e}]", end="")
        return None


def _gemini_tts(text: str, retries: int = 3) -> bytes | None:
    """Gemini TTS 備援，回傳 24kHz PCM16 bytes"""
    if not _GEMINI_KEYS:
        return None
    styled = f"用明亮、親切的語氣說：{text}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": styled}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": _TTS_VOICE}}
            },
        },
    }).encode()
    for attempt in range(retries):
        key = _current_key()
        url = f"{_BASE_URL}/{_TTS_MODEL}:generateContent?key={key}"
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
            cand = result.get("candidates", [{}])[0]
            if "content" not in cand:
                return None
            data = cand["content"]["parts"][0].get("inlineData", {}).get("data", "")
            return base64.b64decode(data) if data else None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                _next_key()
                time.sleep(2)
                continue
            return None
        except Exception:
            if attempt < retries - 1:
                time.sleep(1)
                continue
            return None
    return None


def _synthesize(text: str) -> bytes | None:
    """Chirp3 優先，失敗降級 Gemini"""
    pcm = _chirp3_tts(text)
    if pcm:
        return pcm
    print(" → 降級 Gemini", end="")
    return _gemini_tts(text)


def _save_wav(path: str, pcm: bytes, sr: int = TARGET_SR):
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm)


def _app_filename(old_file: str) -> str:
    """xxx.wav → xxx_App.wav；若已是 _App 後綴則不變"""
    base, ext = os.path.splitext(old_file)
    if base.endswith("_App"):
        return old_file
    return f"{base}_App{ext}"


def main():
    test_n = None
    force = False
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--test" and i + 1 <= len(sys.argv) - 1:
            test_n = int(sys.argv[i + 1])
        elif arg == "--force":
            force = True

    with open(MAP_FILE, 'r', encoding='utf-8') as f:
        voice_map = json.load(f)

    keys = list(voice_map.keys())
    if test_n:
        keys = keys[:test_n]
        print(f"[TEST MODE] 只跑前 {test_n} 個")

    print("═" * 60)
    print(f"目標：{len(keys)} 個語音 → 24kHz Chirp3-HD")
    print(f"輸出：{AUDIO_DIR}/*_App.wav")
    print(f"更新：{MAP_FILE} (file → *_App.wav, duration_ms 重算)")
    print("═" * 60 + "\n")

    generated = 0
    skipped = 0
    failed = 0

    for key in keys:
        info = voice_map[key]
        old_file = info.get("file", "")
        if not old_file:
            print(f"  [跳過] {key}：無 file 欄位")
            continue

        new_file = _app_filename(old_file)
        new_path = os.path.join(AUDIO_DIR, new_file)

        if not force and os.path.exists(new_path) and os.path.getsize(new_path) > 500:
            print(f"  [跳過] {key} → {new_file} (已存在)")
            skipped += 1
            continue

        print(f"  [生成] {key} → {new_file}...", end="", flush=True)
        pcm = _synthesize(key)
        if pcm is None:
            print(" 失敗")
            failed += 1
            continue

        _save_wav(new_path, pcm, TARGET_SR)
        dur_ms = int(len(pcm) / 2 / TARGET_SR * 1000)
        info["file"] = new_file
        info["duration_ms"] = dur_ms
        print(f" OK ({dur_ms}ms, {len(pcm)//1024}KB)")
        generated += 1
        time.sleep(0.3)

    with open(MAP_FILE, 'w', encoding='utf-8') as f:
        json.dump(voice_map, f, ensure_ascii=False, indent=2)

    print(f"\n完成：生成 {generated}，跳過 {skipped}，失敗 {failed}")
    print(f"voice_map.json 已更新")


if __name__ == "__main__":
    main()
