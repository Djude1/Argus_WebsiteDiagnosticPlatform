# qwen_extractor.py
# -*- coding: utf-8 -*-
"""
將中文語音指令轉換為 YOLO 英文標籤。
使用 Groq Llama 3.1 8B Instant（透過 urllib 直接呼叫，避免 openai SDK 版本問題）。
"""
import os, json, urllib.request, urllib.error
from typing import Tuple

# ── 本地優先對照表（命中直接回傳，不呼叫 API）──────────────────────────────
LOCAL_CN2EN = {
    "红牛": "Red_Bull",
    "ad钙奶": "AD_milk",
    "ad 钙奶": "AD_milk",
    "ad": "AD_milk",
    "钙奶": "AD_milk",
    "矿泉水": "bottle",
    "水瓶": "bottle",
    "可乐": "coke",
    "雪碧": "sprite",
}

PROMPT_SYS = (
    "You are a label normalizer. Convert the given Chinese object "
    "description into a short, lowercase English YOLO/vision class name "
    "(1~3 words). If multiple are given, return the single most likely one. "
    "Output ONLY the label, no punctuation."
)

def _groq_label(query_cn: str) -> str:
    """呼叫 Groq Llama 3.1 8B Instant 將中文物品名轉為英文標籤"""
    from config import GROQ_API_KEY
    payload = json.dumps({
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": PROMPT_SYS},
            {"role": "user",   "content": query_cn.strip()},
        ],
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "groq-extractor/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        result = json.loads(r.read())
    return (result["choices"][0]["message"]["content"] or "").strip()

def extract_english_label(query_cn: str) -> Tuple[str, str]:
    """
    回傳 (label_en, source)；source ∈ {'local', 'groq', 'fallback'}
    """
    q = (query_cn or "").strip().lower()

    # ① 精確命中本地對照表
    if q in LOCAL_CN2EN:
        return LOCAL_CN2EN[q], "local"

    # ② 模糊命中（包含關鍵詞）
    for k, v in LOCAL_CN2EN.items():
        if k in q:
            return v, "local"

    # ③ 呼叫 Groq Llama
    try:
        label = _groq_label(query_cn)
        label = label.replace(".", "").replace(",", "").replace("  ", " ").strip()
        return (label or "bottle"), "groq"
    except Exception as e:
        print(f"[qwen_extractor] Groq 呼叫失敗: {e}", flush=True)
        return "bottle", "fallback"
