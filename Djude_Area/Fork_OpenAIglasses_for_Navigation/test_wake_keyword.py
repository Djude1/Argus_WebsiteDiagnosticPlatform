# test_wake_keyword.py
# -*- coding: utf-8 -*-
"""喚醒詞「哈囉」偵測測試（繁體 / 簡體 / 英文變體，包含即命中）。

設計重點：
- 喚醒詞改為「哈囉」，涵蓋諧音、簡體、英文誤辨，最大化觸發率。
- 結束詞已移除：結束對話改由主動模式靜音 / 超時自動結束。
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import asr_core
from asr_core import is_wake_word


# ── 應觸發喚醒的文字 ──────────────────────────────────────────────────────────
WAKE_HIT = [
    "哈囉", "哈嘍", "哈羅", "哈摟", "哈漏",   # 繁體諧音
    "哈啰", "哈喽", "哈罗",                   # 簡體
    "hello", "Hello", "HALLO", "halo",       # 英文（大小寫不限）
    "哈囉幫我看前面",                         # 喚醒詞＋指令同句
    "那個哈囉",                               # 前綴語氣詞
]

# ── 不應觸發喚醒的文字 ────────────────────────────────────────────────────────
WAKE_MISS = [
    "幫我看前面", "開始導航", "今天天氣如何",
    "你好", "曼波", "謝謝", "",
    # 英文整詞匹配：halo 子字串不應誤命中（halogen / halocline 等）
    "halogen lamp", "halocline study", "shallow water",
]


def test_wake_word_hits():
    """所有「哈囉」變體都應被偵測為喚醒詞。"""
    for t in WAKE_HIT:
        assert is_wake_word(t), f"應觸發喚醒卻沒有：{t!r}"


def test_wake_word_misses():
    """非喚醒詞文字不應誤觸發。"""
    for t in WAKE_MISS:
        assert not is_wake_word(t), f"不應觸發喚醒卻觸發了：{t!r}"


def test_end_word_removed():
    """結束詞功能已移除：asr_core 不應再有 END_WORDS。"""
    assert not hasattr(asr_core, "END_WORDS"), "END_WORDS 應已移除（改靠靜音自動結束）"


def test_interrupt_keywords_intact():
    """中斷熱詞不受本次改動影響。"""
    assert "停止所有功能" in asr_core.INTERRUPT_KEYWORDS
