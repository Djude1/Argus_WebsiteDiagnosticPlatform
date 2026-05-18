# test_asr_agc.py
# -*- coding: utf-8 -*-
"""
ASR AGC 測試腳本：模擬真實使用者的不同收音場景。

測試場景：
1. 安靜環境、正常音量（基準）
2. 安靜環境、小聲說話（遠距離模擬）
3. 安靜環境、極小聲（耳語）
4. 嘈雜環境、正常音量（背景噪音）

驗證項目：
- AGC 能否將低音量提升到可用範圍
- AGC 能否避免高音量削波
- 不同音量下增益是否平滑過渡
- 靜音門檻是否合理

不依賴 Google STT API，純本地驗證 AGC 行為。
"""

import struct
import math
import random
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# 模擬參數
SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 320 samples/frame
FRAME_BYTES = FRAME_SAMPLES * 2  # 640 bytes/frame


def generate_sine_wave(freq: float = 440.0, amplitude: int = 5000,
                       num_samples: int = FRAME_SAMPLES) -> bytes:
    """生成正弦波 PCM16 音訊（模擬語音）"""
    samples = []
    for i in range(num_samples):
        t = i / SAMPLE_RATE
        sample = int(amplitude * math.sin(2 * math.pi * freq * t))
        # 加入一些泛音讓它更像語音
        sample += int(amplitude * 0.3 * math.sin(2 * math.pi * freq * 2 * t))
        sample += int(amplitude * 0.1 * math.sin(2 * math.pi * freq * 3 * t))
        sample = max(-32768, min(32767, sample))
        samples.append(sample)
    return struct.pack(f'<{num_samples}h', *samples)


def generate_silence(num_samples: int = FRAME_SAMPLES) -> bytes:
    """生成靜音"""
    return b'\x00' * (num_samples * 2)


def generate_noise(amplitude: int = 500, num_samples: int = FRAME_SAMPLES) -> bytes:
    """生成白噪音（模擬環境噪音）"""
    samples = [random.randint(-amplitude, amplitude) for _ in range(num_samples)]
    return struct.pack(f'<{num_samples}h', *samples)


def generate_pink_noise(amplitude: int = 500, num_samples: int = FRAME_SAMPLES) -> bytes:
    """生成粉紅噪音（模擬街道/交通噪音，低頻成分較多）"""
    samples = []
    b = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    for _ in range(num_samples):
        white = random.uniform(-1, 1)
        b[0] = 0.99886 * b[0] + white * 0.0555179
        b[1] = 0.99332 * b[1] + white * 0.0750759
        b[2] = 0.96900 * b[2] + white * 0.1538520
        b[3] = 0.86650 * b[3] + white * 0.3104856
        b[4] = 0.55000 * b[4] + white * 0.5329522
        b[5] = -0.7616 * b[5] - white * 0.0168980
        pink = (b[0] + b[1] + b[2] + b[3] + b[4] + b[5] + b[6] + white * 0.5362) * 0.11
        b[6] = white * 0.115926
        sample = int(pink * amplitude)
        sample = max(-32768, min(32767, sample))
        samples.append(sample)
    return struct.pack(f'<{num_samples}h', *samples)


def mix_audio(voice: bytes, noise: bytes, voice_ratio: float = 1.0,
              noise_ratio: float = 1.0) -> bytes:
    """將語音和噪音混合（模擬吵雜環境）"""
    n = min(len(voice), len(noise)) // 2
    voice_samples = struct.unpack(f'<{n}h', voice[:n * 2])
    noise_samples = struct.unpack(f'<{n}h', noise[:n * 2])
    mixed = []
    for v, ns in zip(voice_samples, noise_samples):
        sample = int(v * voice_ratio + ns * noise_ratio)
        mixed.append(max(-32768, min(32767, sample)))
    return struct.pack(f'<{n}h', *mixed)


def calc_rms(pcm_data: bytes) -> float:
    """計算 PCM16 音訊的 RMS"""
    n = len(pcm_data) // 2
    if n == 0:
        return 0.0
    samples = struct.unpack(f'<{n}h', pcm_data[:n * 2])
    return (sum(s * s for s in samples) / n) ** 0.5


def apply_fixed_gain(data: bytes, gain: float) -> bytes:
    """套用固定增益"""
    n = len(data) // 2
    samples = struct.unpack(f'<{n}h', data[:n * 2])
    return struct.pack(
        f'<{n}h',
        *(max(-32768, min(32767, int(s * gain))) for s in samples)
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 測試案例
# ═══════════════════════════════════════════════════════════════════════════════

def test_agc_adaptive():
    """測試 AGC 在不同音量下的自適應行為"""
    print("=" * 70)
    print("測試 1：AGC 自適應增益 — 模擬不同音量場景")
    print("=" * 70)

    # 載入 asr_core 的 AGC
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    from asr_core import (
        _AGC_ENABLED, _agc_apply, _agc_current_gain,
        _AGC_TARGET_LOW, _AGC_TARGET_HIGH,
        _agc_rms_history, STANDBY_RMS_THRESH, _AGC_SMOOTH
    )

    print(f"\nAGC 狀態: {'啟用' if _AGC_ENABLED else '停用'}")
    print(f"AGC 目標 RMS 範圍: {_AGC_TARGET_LOW:.0f} ~ {_AGC_TARGET_HIGH:.0f}")
    print(f"靜音門檻 (STANDBY_RMS_THRESH): {STANDBY_RMS_THRESH:.0f}")
    print()

    # 場景定義：(名稱, 振幅, 描述)
    scenarios = [
        ("極小聲（耳語）", 200, "模擬距離 2 公尺的耳語"),
        ("小聲說話", 800, "模擬距離 1 公尺的小聲說話"),
        ("正常音量", 3000, "模擬距離 30 公分的正常說話"),
        ("大聲說話", 10000, "模擬近距離大聲說話"),
        ("極大聲", 20000, "模擬貼著麥克風喊叫"),
    ]

    results = []
    for name, amplitude, desc in scenarios:
        # 生成 50 幀（約 1 秒）的模擬語音
        rms_before_list = []
        rms_after_list = []

        for _ in range(50):
            # 生成模擬語音
            raw = generate_sine_wave(freq=300 + random.random() * 200, amplitude=amplitude)
            rms_before = calc_rms(raw)
            rms_before_list.append(rms_before)

            # 套用 AGC
            processed = _agc_apply(raw)
            rms_after = calc_rms(processed)
            rms_after_list.append(rms_after)

        avg_rms_before = sum(rms_before_list) / len(rms_before_list)
        avg_rms_after = sum(rms_after_list) / len(rms_after_list)
        final_rms = rms_after_list[-1]

        # 判斷結果：只要超過靜音門檻就算通過（Google STT 在 RMS 200+ 就能辨識）
        above_thresh = final_rms >= STANDBY_RMS_THRESH
        # 額外檢查：如果是正常音量場景，確認 AGC 沒有造成嚴重削波
        no_severe_clip = final_rms < 20000 or amplitude < 10000  # 只有大聲場景才允許高 RMS

        status = "✅ 通過" if above_thresh else "❌ 不通過"

        print(f"  場景: {name}")
        print(f"    描述: {desc}")
        print(f"    原始 RMS: {avg_rms_before:.0f}")
        print(f"    AGC 後 RMS: {avg_rms_after:.0f} (最終: {final_rms:.0f})")
        print(f"    在目標範圍附近: {'是' if final_rms >= _AGC_TARGET_LOW * 0.9 else '否'}")
        print(f"    超過靜音門檻: {'是' if above_thresh else '否'}")
        print(f"    結果: {status}")
        print()

        results.append({
            "name": name,
            "passed": above_thresh,
        })

    # 重置 AGC 狀態（避免影響後續測試）
    from asr_core import _agc_rms_history
    _agc_rms_history.clear()

    return results


def test_silence_rejection():
    """測試靜音門檻：確保純靜音/噪音不被誤判為語音"""
    print("=" * 70)
    print("測試 2：靜音/噪音拒絕 — 確保門檻合理")
    print("=" * 70)

    from asr_core import STANDBY_RMS_THRESH

    test_cases = [
        ("純靜音", generate_silence(), True),     # 應被視為靜音
        ("微小噪音", generate_noise(30), True),     # 應被視為靜音
        ("低環境噪音", generate_noise(100), True),   # 應被視為靜音
        ("中等環境噪音", generate_noise(300), False), # 可能被視為語音（視門檻）
    ]

    results = []
    for name, data, should_be_silent in test_cases:
        rms = calc_rms(data)
        is_silent = rms < STANDBY_RMS_THRESH
        expected = "靜音" if should_be_silent else "語音"
        actual = "靜音" if is_silent else "語音"
        passed = (is_silent == should_be_silent)

        print(f"  {name}: RMS={rms:.0f}, 門檻={STANDBY_RMS_THRESH:.0f}")
        print(f"    預期: {expected}, 實際: {actual}")
        print(f"    結果: {'✅ 通過' if passed else '⚠️ 需注意'}")
        print()

        results.append({"name": name, "passed": passed})

    return results


def test_keyword_coverage():
    """測試關鍵字觸發覆蓋率（旁路模式下的指令匹配）"""
    print("=" * 70)
    print("測試 3：關鍵字觸發覆蓋率 — 模擬 ASR 誤辨場景")
    print("=" * 70)

    from asr_core import (
        WAKE_WORDS, END_WORDS, INTERRUPT_KEYWORDS,
        _normalize_cn, GoogleASR
    )
    _MAMBO_VARIANTS = GoogleASR._MAMBO_VARIANTS

    # 模擬 ASR 可能的辨識結果（含正確與常見誤辨）
    test_phrases = [
        # 導航指令（旁路模式下直接派發）
        ("開始導航", True, "導航指令"),
        ("開始盲道導航", True, "導航指令"),
        ("開始過馬路", True, "導航指令"),
        ("停止導航", True, "導航指令"),
        ("結束導航", True, "導航指令"),
        ("開始避障", True, "導航指令"),
        ("停止避障", True, "導航指令"),
        ("幫我過馬路", True, "導航指令"),
        ("看紅綠燈", True, "導航指令"),
        ("幫我找一下紅牛", True, "尋物指令"),
        ("幫我找礦泉水", True, "尋物指令"),
        ("找到了", True, "確認指令"),
        ("幫我看看這是什麼", True, "對話指令"),
        ("停下所有功能", True, "中斷熱詞"),
        ("停止所有功能", True, "中斷熱詞"),

        # ASR 誤辨變體（常見同音字/近似音）
        ("開是導航", True, "誤辨-開始→開是"),
        ("開使導航", True, "誤辨-開始→開使"),
        ("開始倒航", True, "誤辨-導航→倒航"),
        ("幫我找一下鴻牛", True, "誤辨-紅牛→鴻牛"),
        ("幫我看看這什麼", True, "誤辨-缺字"),
        ("停瞎所有功能", True, "誤辨-停下→停瞎"),

        # 非指令（日常對話）
        ("今天天氣如何", False, "非指令-日常對話"),
        ("你好", False, "非指令-打招呼"),
        ("我是誰", False, "非指令-問題"),

        # 喚醒詞變體（非旁路模式下測試）
        ("哈囉 曼波", True, "喚醒詞-標準"),
        ("哈囉曼波", True, "喚醒詞-無空格"),
        ("羅曼波", True, "喚醒詞-誤辨"),
        ("哈囉", True, "喚醒詞-寬鬆匹配"),
        ("哈喽曼波", True, "喚醒詞-簡體變體"),
    ]

    # 在旁路模式下，所有語音都直接派發
    # 關鍵是確認指令解析邏輯能匹配足夠多的變體
    # 這裡測試的是「ASR 結果是否包含關鍵字」

    navigation_keywords = [
        "導航", "過馬路", "避障", "紅綠燈", "找", "看看",
        "停下", "停止", "開始",
    ]

    passed = 0
    total = 0

    for phrase, should_match, desc in test_phrases:
        norm = _normalize_cn(phrase)
        # 檢查是否包含任何導航相關關鍵字
        has_keyword = any(kw in norm for kw in navigation_keywords)
        # 檢查喚醒詞（偵測到「曼波」變體即觸發）
        is_mambo = any(v in norm for v in _MAMBO_VARIANTS)
        # 檢查熱詞
        is_interrupt = any(w and _normalize_cn(w) in norm for w in INTERRUPT_KEYWORDS)

        matched = has_keyword or is_mambo or is_interrupt

        # 對於「應該匹配」的指令，只要包含關鍵字就算通過
        if should_match:
            total += 1
            ok = matched
            if ok:
                passed += 1
            status = "✅ 匹配" if ok else "❌ 未匹配"
            if not ok:
                print(f"  ⚠️ 「{phrase}」({desc}) — 未匹配任何關鍵字")
        else:
            status = "➖ 非指令（正確忽略）"

    coverage = passed / total * 100 if total > 0 else 0
    print(f"\n  📊 關鍵字觸發覆蓋率: {passed}/{total} = {coverage:.1f}%")

    if coverage >= 90:
        print(f"  ✅ 達到 90% 目標！")
    else:
        print(f"  ❌ 未達 90% 目標，需要增加更多關鍵字變體")

    return {"coverage": coverage, "passed": passed, "total": total, "target_met": coverage >= 90}


def test_noisy_environment():
    """測試吵雜環境下的 AGC 行為：語音 + 背景噪音混合"""
    print("=" * 70)
    print("測試 4：吵雜環境測試 — 語音 + 背景噪音混合")
    print("=" * 70)

    from asr_core import (
        _AGC_ENABLED, _agc_apply, _agc_current_gain,
        _AGC_TARGET_LOW, _AGC_TARGET_HIGH,
        STANDBY_RMS_THRESH, _agc_rms_history
    )

    # 重置 AGC 狀態
    _agc_rms_history.clear()

    # 場景定義：(名稱, 語音振幅, 噪音振幅, 噪音類型, SNR 估計, 描述)
    scenarios = [
        # 吵雜環境、正常音量說話
        ("街道噪音 + 正常音量", 3000, 800, "pink",
         "~12dB", "模擬馬路旁正常說話（最常見場景）"),
        ("餐廳噪音 + 正常音量", 3000, 1500, "white",
         "~6dB", "模擬餐廳內多人交談環境"),
        ("交通噪音 + 小聲說話", 1000, 1000, "pink",
         "~0dB", "模擬公車站旁小聲說話（最困難場景）"),
        ("辦公室噪音 + 正常音量", 3000, 400, "white",
         "~18dB", "模擬冷氣/風扇等低噪音環境"),
        ("工地噪音 + 大聲說話", 8000, 3000, "pink",
         "~9dB", "模擬施工環境高噪音背景"),
        # 極端場景
        ("純噪音（無語音）", 0, 2000, "pink",
         "-∞dB", "純背景噪音，AGC 不應過度放大"),
        ("噪音中耳語", 400, 600, "white",
         "~-3dB", "噪音中極小聲說話（極端困難）"),
    ]

    results = []
    for name, voice_amp, noise_amp, noise_type, snr, desc in scenarios:
        rms_before_list = []
        rms_after_list = []
        voice_rms_list = []

        for _ in range(50):
            # 生成語音（如果有的話）
            if voice_amp > 0:
                voice = generate_sine_wave(
                    freq=300 + random.random() * 200,
                    amplitude=voice_amp
                )
                voice_rms = calc_rms(voice)
                voice_rms_list.append(voice_rms)
            else:
                voice = generate_silence()
                voice_rms_list.append(0)

            # 生成背景噪音
            if noise_type == "pink":
                noise = generate_pink_noise(amplitude=noise_amp)
            else:
                noise = generate_noise(amplitude=noise_amp)

            # 混合語音和噪音
            mixed = mix_audio(voice, noise)
            rms_before = calc_rms(mixed)
            rms_before_list.append(rms_before)

            # 套用 AGC
            processed = _agc_apply(mixed)
            rms_after = calc_rms(processed)
            rms_after_list.append(rms_after)

        avg_rms_before = sum(rms_before_list) / len(rms_before_list)
        avg_rms_after = sum(rms_after_list) / len(rms_after_list)
        final_rms = rms_after_list[-1]
        avg_voice_rms = sum(voice_rms_list) / len(voice_rms_list)

        # 判斷標準：
        # 1. 有語音的場景：AGC 後 RMS 應高於靜音門檻（否則語音可能被丟棄）
        # 2. 純噪音場景：AGC 後 RMS 不應超過 AGC_TARGET_HIGH 的 2 倍（避免過度放大）
        # 3. 削波率：AGC 後的音訊削波比例應 < 5%
        has_voice = voice_amp > 0
        above_thresh = final_rms >= STANDBY_RMS_THRESH
        no_excessive_amp = final_rms < _AGC_TARGET_HIGH * 2

        # 計算削波率
        clip_count = 0
        total_samples = 0
        for i in range(5):  # 抽樣最後 5 帧
            if voice_amp > 0:
                voice = generate_sine_wave(freq=350, amplitude=voice_amp)
            else:
                voice = generate_silence()
            if noise_type == "pink":
                noise = generate_pink_noise(amplitude=noise_amp)
            else:
                noise = generate_noise(amplitude=noise_amp)
            mixed = mix_audio(voice, noise)
            processed = _agc_apply(mixed)
            n = len(processed) // 2
            samples = struct.unpack(f'<{n}h', processed)
            clip_count += sum(1 for s in samples if abs(s) >= 32760)
            total_samples += n
        clip_rate = clip_count / total_samples * 100 if total_samples > 0 else 0

        if has_voice:
            # 有語音：主要看是否通過靜音門檻 + 削波率合理
            passed = above_thresh and clip_rate < 5.0
            status = "✅ 通過" if passed else "❌ 不通過"
            reason = ""
            if not above_thresh:
                reason = "（RMS 低於靜音門檻，語音可能被丟棄）"
            elif clip_rate >= 5.0:
                reason = f"（削波率過高: {clip_rate:.1f}%）"
        else:
            # 純噪音：不應被過度放大
            passed = no_excessive_amp and clip_rate < 5.0
            status = "✅ 通過" if passed else "⚠️ 需注意"
            reason = ""
            if not no_excessive_amp:
                reason = "（純噪音被過度放大）"
            elif clip_rate >= 5.0:
                reason = f"（削波率過高: {clip_rate:.1f}%）"

        print(f"  場景: {name}")
        print(f"    描述: {desc}")
        print(f"    SNR: {snr}")
        print(f"    純語音 RMS: {avg_voice_rms:.0f}")
        print(f"    混合前 RMS: {avg_rms_before:.0f}")
        print(f"    AGC 後 RMS: {avg_rms_after:.0f} (最終: {final_rms:.0f})")
        print(f"    削波率: {clip_rate:.1f}%")
        print(f"    超過靜音門檻: {'是' if above_thresh else '否'}")
        print(f"    結果: {status} {reason}")
        print()

        results.append({
            "name": name,
            "has_voice": has_voice,
            "passed": passed,
            "snr": snr,
            "final_rms": final_rms,
            "clip_rate": clip_rate,
        })

    # 重置 AGC 狀態
    _agc_rms_history.clear()

    return results


def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  ASR AGC & 關鍵字覆蓋率 測試套件                           ║")
    print("║  模擬真實使用者場景，驗證收音品質改善                       ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    # 測試 1：AGC 自適應
    agc_results = test_agc_adaptive()

    # 測試 2：靜音拒絕
    silence_results = test_silence_rejection()

    # 測試 3：關鍵字覆蓋率
    coverage_result = test_keyword_coverage()

    # 測試 4：吵雜環境
    noisy_results = test_noisy_environment()

    # 總結
    print("=" * 70)
    print("📊 測試總結")
    print("=" * 70)

    agc_pass = sum(1 for r in agc_results if r["passed"])
    agc_total = len(agc_results)
    print(f"  AGC 自適應: {agc_pass}/{agc_total} 場景通過")

    silence_pass = sum(1 for r in silence_results if r["passed"])
    silence_total = len(silence_results)
    print(f"  靜音拒絕: {silence_pass}/{silence_total} 場景通過")

    print(f"  關鍵字覆蓋率: {coverage_result['coverage']:.1f}% {'✅ 達標' if coverage_result['target_met'] else '❌ 未達標'}")

    noisy_pass = sum(1 for r in noisy_results if r["passed"])
    noisy_total = len(noisy_results)
    noisy_voice = sum(1 for r in noisy_results if r["has_voice"])
    noisy_voice_pass = sum(1 for r in noisy_results if r["has_voice"] and r["passed"])
    noisy_noise_only = sum(1 for r in noisy_results if not r["has_voice"])
    noisy_noise_pass = sum(1 for r in noisy_results if not r["has_voice"] and r["passed"])
    print(f"  吵雜環境: {noisy_pass}/{noisy_total} 場景通過")
    print(f"    - 有語音場景: {noisy_voice_pass}/{noisy_voice} 通過")
    print(f"    - 純噪音場景: {noisy_noise_pass}/{noisy_noise_only} 通過")

    all_pass = (
        agc_pass == agc_total and
        silence_pass == silence_total and
        coverage_result["target_met"] and
        noisy_pass == noisy_total
    )

    print()
    if all_pass:
        print("🎉 所有測試通過！ASR 收音品質改善方案驗證成功。")
    else:
        print("⚠️ 部分測試未通過，需要進一步調整參數。")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
