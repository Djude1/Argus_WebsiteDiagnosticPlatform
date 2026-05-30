# speaker_verifier.py
# -*- coding: utf-8 -*-
"""
說話人聲紋驗證模組。

功能：
  1. 聲紋錄製（Enrollment）：呼叫 enroll() 儲存使用者聲紋幀序列
  2. 聲紋比對（Verification）：幀級別最近鄰匹配，準確度遠高於全局均值比對
  3. resemblyzer 可用時自動切換至 256-dim d-vector（更準）

核心演算法（numpy 後端）：
  - 提取 MFCC 幀（25ms/10ms，20 維 + CMN）
  - 過濾靜音幀（底部 25% 能量）
  - 計算測試幀 × 錄製幀的餘弦相似度矩陣
  - 對稱最近鄰平均作為最終分數（同人 ≈0.90+，不同人 ≈0.70 以下）

.env 可調參數：
  SPEAKER_VERIFY_ENABLED=true       是否啟用說話人驗證（預設 false）
  SPEAKER_EMBED_PATH=model/speaker_embed.pkl  聲紋儲存路徑
  SPEAKER_THRESHOLD=0.82            比對分數門檻（0~1，越高越嚴格）
  SPEAKER_BACKEND=auto              auto / resemblyzer / numpy
"""

import os
import pickle
import numpy as np
from pathlib import Path
from typing import Optional

# ── 設定讀取 ────────────────────────────────────────────────────────────────
ENABLED    = os.getenv("SPEAKER_VERIFY_ENABLED", "false").lower() == "true"
EMBED_PATH = os.getenv("SPEAKER_EMBED_PATH", "model/speaker_embed.pkl")
THRESHOLD  = float(os.getenv("SPEAKER_THRESHOLD", "0.82"))
BACKEND    = os.getenv("SPEAKER_BACKEND", "auto")  # auto / resemblyzer / numpy

def set_threshold(value: float):
    """動態設定聲紋相似度門檻（0~1，越高越嚴格，不需重啟）"""
    global THRESHOLD
    THRESHOLD = max(0.0, min(1.0, float(value)))


# ── Mel 濾波器組 ─────────────────────────────────────────────────────────────

def _hz_to_mel(hz: float) -> float:
    return 2595.0 * np.log10(1.0 + hz / 700.0)

def _mel_to_hz(mel: float) -> float:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

def _mel_filterbank(sample_rate: int, n_fft: int, n_filters: int) -> np.ndarray:
    low_mel  = _hz_to_mel(80.0)
    high_mel = _hz_to_mel(sample_rate / 2.0)
    mel_pts  = np.linspace(low_mel, high_mel, n_filters + 2)
    hz_pts   = np.array([_mel_to_hz(m) for m in mel_pts])
    bin_pts  = np.floor(hz_pts / (sample_rate / n_fft)).astype(int)
    fbank    = np.zeros((n_filters, n_fft // 2 + 1))
    for m in range(n_filters):
        lo, center, hi = bin_pts[m], bin_pts[m + 1], bin_pts[m + 2]
        for k in range(lo, center):
            fbank[m, k] = (k - lo) / max(center - lo, 1)
        for k in range(center, hi):
            fbank[m, k] = (hi - k) / max(hi - center, 1)
    return fbank


# ── MFCC 幀提取（含 delta 動態特徵）─────────────────────────────────────────

def _compute_delta(mfcc: np.ndarray, N: int = 2) -> np.ndarray:
    """計算一階差分（delta）係數，反映聲音的動態變化"""
    T, D = mfcc.shape
    delta  = np.zeros_like(mfcc)
    denom  = 2.0 * sum(n * n for n in range(1, N + 1))
    for t in range(T):
        for n in range(1, N + 1):
            delta[t] += n * (mfcc[min(t + n, T - 1)] - mfcc[max(t - n, 0)])
    return delta / (denom + 1e-10)


def _extract_mfcc_frames(pcm_data: bytes, sample_rate: int = 16000,
                         n_mfcc: int = 20, n_filters: int = 40,
                         with_delta: bool = True) -> np.ndarray:
    """
    提取 MFCC 幀序列，回傳 (T, n_mfcc) 或 (T, n_mfcc*2) 陣列。
    使用 25ms 幀長 / 10ms 步長 + pre-emphasis + CMN。
    with_delta=True 時加入 delta 特徵，維度加倍（靜態 + 動態）。
    """
    wav = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0

    # Pre-emphasis
    wav = np.append(wav[0], wav[1:] - 0.97 * wav[:-1])

    n_fft      = 512
    frame_len  = int(sample_rate * 0.025)   # 400 samples @ 16kHz
    frame_step = int(sample_rate * 0.010)   # 160 samples @ 16kHz
    if len(wav) < frame_len:
        wav = np.pad(wav, (0, frame_len - len(wav)))
    num_frames = max(1, (len(wav) - frame_len) // frame_step + 1)

    fbank = _mel_filterbank(sample_rate, n_fft, n_filters)
    log_mel_frames = []
    for i in range(num_frames):
        s     = i * frame_step
        frame = wav[s: s + frame_len]
        if len(frame) < frame_len:
            frame = np.pad(frame, (0, frame_len - len(frame)))
        windowed = frame * np.hamming(frame_len)
        spec     = np.abs(np.fft.rfft(windowed, n=n_fft)) ** 2
        log_mel_frames.append(np.log(np.dot(fbank, spec) + 1e-10))
    log_mel = np.array(log_mel_frames)   # (T, n_filters)

    # DCT-II → MFCC
    k_idx   = np.arange(n_mfcc)[:, None]
    m_idx   = np.arange(n_filters)[None, :]
    dct_mat = np.sqrt(2.0 / n_filters) * np.cos(
        np.pi * k_idx * (2 * m_idx + 1) / (2 * n_filters)
    )
    dct_mat[0] /= np.sqrt(2)
    mfcc = log_mel @ dct_mat.T   # (T, n_mfcc)

    # Cepstral Mean Normalization（消除麥克風通道差異）
    mfcc -= mfcc.mean(axis=0, keepdims=True)

    if with_delta:
        delta = _compute_delta(mfcc)
        mfcc  = np.concatenate([mfcc, delta], axis=1)  # (T, n_mfcc*2)

    return mfcc


# 最少需要多少比例的「有聲幀」才認為音訊含有效語音（0~1）
_MIN_VOICED_RATIO = 0.25

def _frame_similarity(enrolled_frames: np.ndarray,
                      test_frames: np.ndarray) -> float:
    """
    幀級別對稱 Top-K 最近鄰相似度。

    改進點（相較於 top-1）：
      - 靜音幀過濾更嚴格：保留能量前 60%（過濾掉低能量 40%）
      - 若有聲幀比例低於 _MIN_VOICED_RATIO，視為無語音回傳 0
      - 使用 Top-K（K=3）最近鄰平均，抑制偶發噪音造成的高分異常
      - 相同說話人有聲幀 ≈ 0.90+，環境音 / 無語音 → 被過濾後分數 < 0.70
    """
    TOP_K = 3

    # 過濾靜音幀（保留能量較高的 60%）
    e_energy = np.linalg.norm(enrolled_frames, axis=1)
    t_energy = np.linalg.norm(test_frames,     axis=1)
    e = enrolled_frames[e_energy >= np.percentile(e_energy, 40)]
    t = test_frames[    t_energy >= np.percentile(t_energy, 40)]

    # 若測試片段有聲幀不足，判斷為無語音輸入
    voiced_ratio = len(t) / max(len(test_frames), 1)
    if len(e) == 0 or len(t) == 0 or voiced_ratio < _MIN_VOICED_RATIO:
        return 0.0

    # L2 正規化
    e_norm = e / (np.linalg.norm(e, axis=1, keepdims=True) + 1e-10)
    t_norm = t / (np.linalg.norm(t, axis=1, keepdims=True) + 1e-10)

    # 餘弦相似度矩陣 (T_test, T_enroll)
    sim = t_norm @ e_norm.T   # (|t|, |e|)

    # 對稱 Top-K 最近鄰平均（K=3 比 top-1 更穩定）
    k_te = min(TOP_K, sim.shape[1])
    k_et = min(TOP_K, sim.shape[0])
    score_te = np.partition(sim,  -k_te, axis=1)[:, -k_te:].mean()
    score_et = np.partition(sim.T, -k_et, axis=1)[:, -k_et:].mean()
    return float((score_te + score_et) / 2)


# ── 主類別 ──────────────────────────────────────────────────────────────────

class SpeakerVerifier:
    """說話人聲紋驗證器（設計為全域單例）"""

    def __init__(self):
        self._encoder         = None      # resemblyzer VoiceEncoder（懶加載）
        self._use_resemblyzer = False
        self._enabled         = ENABLED

        # numpy 後端：儲存 MFCC 幀序列
        self._enrolled_frames: Optional[np.ndarray] = None
        # resemblyzer 後端：儲存 d-vector
        self._enrolled_embed:  Optional[np.ndarray] = None

        # 無論 SPEAKER_VERIFY_ENABLED 為何，都嘗試載入磁碟上已有的聲紋
        self._load_enrolled()
        self._try_load_resemblyzer()

        # 若磁碟有聲紋但環境變數未設定，自動啟用（避免錄了聲紋卻沒作用）
        if self._has_enrollment() and not self._enabled:
            self._enabled = True
            print("[SpeakerVerifier] 偵測到已儲存聲紋，自動啟用說話人驗證", flush=True)

    # ── 公開介面 ────────────────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        return self._enabled and self._has_enrollment()

    def has_enrollment(self) -> bool:
        return self._has_enrollment()

    def enable(self):
        self._enabled = True
        self._load_enrolled()
        self._try_load_resemblyzer()

    def disable(self):
        self._enabled = False

    def enroll(self, pcm_data: bytes, sample_rate: int = 16000) -> bool:
        """
        從 PCM16 音訊建立說話人聲紋並儲存至磁碟。
        建議提供 5~10 秒清晰語音。
        """
        if len(pcm_data) < sample_rate * 2 * 2:
            print("[SpeakerVerifier] 音訊太短（需至少 2 秒），enrollment 失敗", flush=True)
            return False
        try:
            if self._use_resemblyzer and self._encoder is not None:
                embed = self._resemblyzer_embed(pcm_data, sample_rate)
                payload = {"embed": embed, "backend": "resemblyzer"}
                self._enrolled_embed  = embed
                self._enrolled_frames = None
            else:
                # v2：靜態 MFCC + delta，維度 40（更準確）
                frames = _extract_mfcc_frames(pcm_data, sample_rate, with_delta=True)
                payload = {"frames": frames, "backend": "numpy_frames", "version": 2}
                self._enrolled_frames = frames
                self._enrolled_embed  = None

            Path(EMBED_PATH).parent.mkdir(parents=True, exist_ok=True)
            with open(EMBED_PATH, "wb") as f:
                pickle.dump(payload, f)

            self._enabled = True
            backend_name  = "resemblyzer" if self._use_resemblyzer else "numpy 幀匹配 v2"
            n_info = (f"幀數={frames.shape[0]}, 維度={frames.shape[1]}"
                      if not self._use_resemblyzer else f"維度={embed.shape}")
            print(
                f"[SpeakerVerifier] ✓ 聲紋已建立（backend={backend_name}，"
                f"{n_info}，儲存至 {EMBED_PATH}）",
                flush=True,
            )
            return True
        except Exception as e:
            print(f"[SpeakerVerifier] 聲紋建立失敗: {e}", flush=True)
            return False

    def verify(self, pcm_data: bytes, sample_rate: int = 16000) -> bool:
        passed, _ = self.verify_with_score(pcm_data, sample_rate)
        return passed

    def verify_with_score(self, pcm_data: bytes,
                          sample_rate: int = 16000) -> tuple[bool, float | None]:
        """
        驗證並回傳 (passed, similarity)。
        - 未啟用 / 無聲紋 / 音訊太短 → (True, None)
        """
        if not self._enabled or not self._has_enrollment():
            return True, None
        if len(pcm_data) < sample_rate * 2 * 0.8:
            return True, None
        try:
            if self._use_resemblyzer and self._enrolled_embed is not None:
                embed      = self._resemblyzer_embed(pcm_data, sample_rate)
                similarity = float(np.dot(embed, self._enrolled_embed))
            else:
                # 偵測 enrolled 格式版本，決定是否加 delta
                enr = self._enrolled_frames
                use_delta = (enr is not None and enr.ndim == 2 and enr.shape[1] > 20)
                test_frames = _extract_mfcc_frames(pcm_data, sample_rate,
                                                   with_delta=use_delta)
                # 若維度不符（舊格式），降回無 delta 模式
                if enr is not None and test_frames.shape[1] != enr.shape[1]:
                    test_frames = _extract_mfcc_frames(pcm_data, sample_rate,
                                                       with_delta=False)
                similarity  = _frame_similarity(enr, test_frames)

            passed = similarity >= THRESHOLD
            status = "✓ 通過" if passed else "✗ 拒絕"
            print(
                f"[SpeakerVerifier] {status}  相似度={similarity:.3f}  門檻={THRESHOLD}",
                flush=True,
            )
            return passed, similarity
        except Exception as e:
            print(f"[SpeakerVerifier] 驗證錯誤（放行）: {e}", flush=True)
            return True, None

    def delete_enrollment(self) -> bool:
        p = Path(EMBED_PATH)
        self._enrolled_frames = None
        self._enrolled_embed  = None
        if p.exists():
            p.unlink()
            print("[SpeakerVerifier] 聲紋已刪除", flush=True)
            return True
        return False

    def status_dict(self) -> dict:
        try:
            import asr_core
            rms_thr     = asr_core.STANDBY_RMS_THRESH
            pcm_gain    = asr_core.PCM_GAIN
            from asr_core import GoogleASR
            silence_sec = GoogleASR.SILENCE_SEC
            silence_rms = GoogleASR.SILENCE_RMS_THRESH
        except Exception:
            rms_thr = pcm_gain = silence_sec = silence_rms = None
        return {
            "enabled":        self._enabled,
            "enrolled":       self._has_enrollment(),
            "has_enrollment": self._has_enrollment(),
            "backend":        "resemblyzer" if self._use_resemblyzer else "numpy",
            "threshold":      THRESHOLD,
            "rms_threshold":  rms_thr,
            "pcm_gain":       pcm_gain,
            "silence_sec":    silence_sec,
            "silence_rms":    silence_rms,
            "embed_path":     EMBED_PATH,
        }

    # ── 內部方法 ────────────────────────────────────────────────────────────

    def _has_enrollment(self) -> bool:
        return self._enrolled_frames is not None or self._enrolled_embed is not None

    def _try_load_resemblyzer(self):
        if BACKEND == "numpy":
            print("[SpeakerVerifier] 強制使用 numpy 幀匹配後端", flush=True)
            return
        try:
            from resemblyzer import VoiceEncoder
            self._encoder         = VoiceEncoder()
            self._use_resemblyzer = True
            print("[SpeakerVerifier] resemblyzer VoiceEncoder 載入完成", flush=True)
        except ImportError:
            print(
                "[SpeakerVerifier] resemblyzer 未安裝，使用 numpy 幀匹配後端\n"
                "  安裝指令：uv add resemblyzer",
                flush=True,
            )
        except Exception as e:
            print(f"[SpeakerVerifier] resemblyzer 載入失敗（{e}），使用 numpy 幀匹配後端",
                  flush=True)

    def _resemblyzer_embed(self, pcm_data: bytes, sample_rate: int) -> np.ndarray:
        from resemblyzer import preprocess_wav
        wav_f32 = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
        wav_pp  = preprocess_wav(wav_f32, source_sr=sample_rate)
        embed   = self._encoder.embed_utterance(wav_pp)
        return embed

    def _load_enrolled(self):
        p = Path(EMBED_PATH)
        if not p.exists():
            print(f"[SpeakerVerifier] 尚無聲紋（{EMBED_PATH} 不存在）", flush=True)
            return
        try:
            with open(p, "rb") as f:
                data = pickle.load(f)

            if isinstance(data, np.ndarray):
                # 舊格式（全局 embed）：無法做幀匹配，需重新錄製
                print(
                    "[SpeakerVerifier] ⚠ 偵測到舊格式聲紋，請重新錄製以啟用幀匹配功能",
                    flush=True,
                )
                return

            backend = data.get("backend", "")
            if backend == "numpy_frames" and "frames" in data:
                self._enrolled_frames = data["frames"]
                ver   = data.get("version", 1)
                dim   = self._enrolled_frames.shape[1]
                hint  = "" if ver >= 2 else "  ⚠ 舊格式(v1)，建議重新錄製以啟用 delta 特徵"
                print(
                    f"[SpeakerVerifier] 已載入聲紋（numpy 幀匹配 v{ver}，"
                    f"幀數={self._enrolled_frames.shape[0]}，維度={dim}）{hint}",
                    flush=True,
                )
            elif "embed" in data:
                self._enrolled_embed = data["embed"]
                print(
                    f"[SpeakerVerifier] 已載入聲紋（resemblyzer，"
                    f"維度={self._enrolled_embed.shape}）",
                    flush=True,
                )
            else:
                print("[SpeakerVerifier] 聲紋格式無法識別，請重新錄製", flush=True)

        except Exception as e:
            print(f"[SpeakerVerifier] 聲紋載入失敗: {e}", flush=True)


# ── 全域單例 ────────────────────────────────────────────────────────────────
speaker_verifier = SpeakerVerifier()
