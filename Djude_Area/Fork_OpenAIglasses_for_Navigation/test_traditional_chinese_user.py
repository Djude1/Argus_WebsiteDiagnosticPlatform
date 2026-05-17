# test_traditional_chinese_user.py
# -*- coding: utf-8 -*-
"""
繁體中文使用者模擬測試 — 模擬真實台灣使用者場景。

測試目標：
1. 分析 Google STT 不同 language_code 設定（cmn-Hant-TW vs zh-CN）對指令匹配成功率的影響
2. 模擬各種使用者場景：正常語速、快語速、慢語速、台灣國語口音、懶音
3. 模擬 ASR 可能的輸出變體：純繁體、純簡體、繁簡混合、同音字誤辨
4. 每條指令反覆測試多種變體，計算各設定的成功率

場景覆蓋：
- 正常語速使用者
- 快語速（字詞連音、吞音）
- 慢語速（斷句、拉長音）
- 台灣國語口音（捲舌不分、前後鼻音不分）
- 懶音（省略字詞）
- 吵雜環境下的 ASR 誤辨
- 繁簡混合輸出

不依賴外部 API，純本地分析。
"""

import sys
import os
import re
import json
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from asr_core import (
    WAKE_WORDS, END_WORDS, INTERRUPT_KEYWORDS,
    _normalize_cn, _s2t, GoogleASR,
)

_MAMBO_VARIANTS = GoogleASR._MAMBO_VARIANTS


# ═══════════════════════════════════════════════════════════════════════════════
# 繁簡體對照表（指令相關）
# ═══════════════════════════════════════════════════════════════════════════════

# 繁→簡 對照（用於模擬 ASR 可能的簡體輸出）
TRAD_TO_SIMP = {
    "開": "开", "始": "始", "導": "导", "航": "航",
    "停": "停", "結": "结", "束": "束",
    "過": "过", "馬": "马", "路": "路",
    "紅": "红", "綠": "绿", "燈": "灯",
    "檢": "检", "測": "测",
    "幫": "帮", "找": "找", "到": "到",
    "說": "说", "明": "明", "書": "书",
    "礦": "矿", "泉": "泉", "水": "水",
    "幫": "帮", "謝": "谢", "囉": "喽",
    "認": "认", "識": "识", "這": "这",
    "過": "过", "開": "开", "啟": "启",
    "幫": "帮", "現": "现", "在": "在",
    "繼": "继", "續": "续",
    "機": "机", "車": "车",
    "鑰": "钥", "匙": "匙",
    "電": "电", "話": "话",
    "處": "处", "理": "理",
    "種": "种", "樣": "样",
    "紅": "红", "牛": "牛",
    "看": "看", "見": "见",
    "謝": "谢", "請": "请",
    "點": "点", "個": "个",
    "還": "还", "沒": "没",
    "東": "东", "西": "西",
    "問": "问", "題": "题",
    "嗎": "吗", "吧": "吧",
    "什": "什", "麼": "么",
    "怎": "怎", "樣": "样",
    "藍": "蓝", "色": "色",
    "黃": "黄", "黑": "黑",
    "白": "白", "紫": "紫",
    "臺": "台", "灣": "湾",
}

def to_simplified(text: str) -> str:
    """將繁體中文轉為簡體（用於模擬 zh-CN ASR 輸出）"""
    return "".join(TRAD_TO_SIMP.get(c, c) for c in text)


# ═══════════════════════════════════════════════════════════════════════════════
# ASR 輸出變體生成器
# ═══════════════════════════════════════════════════════════════════════════════

def generate_asr_variants(phrase: str) -> list:
    """
    模擬 Google STT 在不同情境下可能的輸出變體。
    回傳 [(變體文字, 情境描述), ...]
    """
    variants = []

    # 1. 原始輸入（理想情況）
    variants.append((phrase, "理想-原始輸入"))

    # 2. 全簡體（模擬 zh-CN 模式輸出）
    simp = to_simplified(phrase)
    if simp != phrase:
        variants.append((simp, "全簡體（zh-CN模式）"))

    # 3. 繁簡混合（模擬 cmn-Hant-TW 偶爾輸出簡體）
    # 隨機將部分繁體字替換為簡體
    mixed_positions = []
    for i, c in enumerate(phrase):
        if c in TRAD_TO_SIMP:
            mixed_positions.append(i)

    if len(mixed_positions) >= 2:
        # 替換第 1 個繁體字為簡體
        chars = list(phrase)
        chars[mixed_positions[0]] = TRAD_TO_SIMP[chars[mixed_positions[0]]]
        variants.append(("".join(chars), "繁簡混合（第1字簡化）"))

    if len(mixed_positions) >= 3:
        # 替換多個繁體字為簡體
        chars = list(phrase)
        for idx in mixed_positions[1::2]:  # 每隔一個替換
            chars[idx] = TRAD_TO_SIMP.get(chars[idx], chars[idx])
        variants.append(("".join(chars), "繁簡混合（間隔簡化）"))

    # 4. 同音字誤辨（台灣國語常見）
    common_misrecognitions = {
        "開始": ["開是", "開使", "開駛"],
        "導航": ["倒航", "到航", "導行"],
        "停止": ["停值", "停制"],
        "結束": ["結數", "結樹"],
        "過馬路": ["過馬鹿", "過碼路"],
        "紅綠燈": ["紅路燈", "紅驢燈"],
        "幫我": ["忙我", "邦我", "榜我"],
        "找一下": ["找一下", "找一下", "照一下"],
        "使用說明書": ["使用說明書", "使用說明舒", "使用說名書"],
        "曼波": ["漫波", "漫播", "慢播", "慢波", "滿波"],
        "哈囉": ["哈囉", "哈羅", "哈洛", "哈漏"],
        "謝謝": ["謝謝", "謝協", "謝寫"],
        "停下": ["停瞎", "停夏"],
        "找到了": ["找到了", "照到了", "找道了"],
        "拿到了": ["拿到了", "哪到了", "拉到了"],
        "檢測": ["簡測", "檢側", "簡側"],
        "識別": ["識別", "十別", "視別"],
        "前面": ["前面", "錢面", "前棉"],
        "什麼": ["什麼", "什摸", "神摸", "什麼"],
        "看看": ["看看", "侃侃"],
        "開啟": ["開啟", "開起", "開氣"],
        "繼續": ["繼續", "技續", "記續"],
        "盲道": ["盲道", "忙道", "茫道"],
        "這是": ["這是", "真是", "誓"],
        "物品": ["物品", "無品"],
        "說明": ["說明", "說名", "碩明"],
    }

    for orig, mislist in common_misrecognitions.items():
        if orig in phrase:
            for mis in mislist:
                if mis != orig:
                    mis_phrase = phrase.replace(orig, mis)
                    variants.append((mis_phrase, f"同音字誤辨（{orig}→{mis}）"))

    # 5. 快語速 — 吞音/連音
    if "開始導航" in phrase:
        variants.append(("開導航", "快語速-吞音（開始→開）"))
        variants.append(("開使導航", "快語速-連音（始→使）"))
    if "停止導航" in phrase:
        variants.append(("停導航", "快語速-吞音（停止→停）"))
    if "開始過馬路" in phrase:
        variants.append(("過馬路", "快語速-省略前綴"))
        variants.append(("幫我過馬路", "口語化-幫我開頭"))
    if "開始避障" in phrase:
        variants.append(("避障", "快語速-省略前綴"))
    if "幫我找一下" in phrase:
        variants.append(("找一下", "快語速-省略幫我"))
        variants.append(("幫我找", "快語速-省略一下"))
    if "使用說明書" in phrase:
        variants.append(("說明書", "快語速-省略使用"))
    if "檢測紅綠燈" in phrase:
        variants.append(("看紅綠燈", "口語化-檢測→看"))
        variants.append(("紅綠燈", "快語速-省略前綴"))

    # 6. 慢語速 — 多餘語氣詞
    filler_prefixes = ["嗯", "啊", "那個", "就是", "呃"]
    filler_suffixes = ["啊", "呢", "吧", "嘛"]
    if len(phrase) >= 3:
        variants.append((f"嗯{phrase}", "慢語速-前綴語氣詞"))
        variants.append((f"{phrase}啊", "慢語速-後綴語氣詞"))
        variants.append((f"那個{phrase}", "慢語速-前綴口頭禪"))

    # 7. 台灣國語口音
    # 捲舌不分（zh/ch/sh → z/c/s）
    tw_mandarin = {
        "這": "這", "是": "四", "說": "所", "知道": "資道",
        "什麼": "什麼", "開始": "開始", "使用": "使用",
    }
    # 主要是語音層面，文字層面不影響太多
    # 但可以模擬部分常見口語化替換
    colloquial = {
        "開始導航": "我要導航",
        "停止導航": "不要導航了",
        "開始過馬路": "我要過馬路",
        "幫我找一下": "幫我找",
    }
    for orig, col in colloquial.items():
        if orig in phrase and col != phrase:
            variants.append((phrase.replace(orig, col), f"口語化（{orig}→{col}）"))

    return variants


# ═══════════════════════════════════════════════════════════════════════════════
# 指令匹配模擬（與 test_voice_commands.py 相同邏輯）
# ═══════════════════════════════════════════════════════════════════════════════

def classify_command(user_text: str, current_state: str = "IDLE") -> dict:
    """模擬 start_ai_with_text_custom 的指令匹配（含繁簡體轉換 + 口語化）"""

    # 簡→繁統一（與 app_main.py 相同邏輯）
    user_text = _s2t(user_text)

    # 使用說明書
    if ("眼鏡使用說明書" in user_text or "使用說明書" in user_text or
        "眼鏡使用說明書" in user_text or "使用說明書" in user_text):
        return {"command": "usage_guide", "state_after": current_state}

    # 導航模式過濾
    if current_state not in ["CHAT", "IDLE"]:
        allowed_keywords = [
            "帮我看", "帮我看下", "帮我看一下", "帮我找", "帮我找下", "帮我找一下",
            "找一下", "看看", "识别一下", "找到了", "拿到了",
            "幫我看", "幫我看下", "幫我找", "識別一下",
        ]
        is_allowed = any(k in user_text for k in allowed_keywords)
        nav_control = [
            "开始过马路", "过马路结束", "开始导航", "开启导航", "盲道导航",
            "停止导航", "结束导航", "检测红绿灯", "看红绿灯", "停止检测", "停止红绿灯",
            "開始過馬路", "過馬路結束", "開始導航", "開啟導航",
            "停止導航", "結束導航", "檢測紅綠燈", "看紅綠燈", "停止檢測", "停止紅綠燈",
        ]
        is_nav = any(k in user_text for k in nav_control)
        if not is_allowed and not is_nav:
            return {"command": None}

    # 過馬路
    # 過馬路結束（必須在開始之前判斷，避免被「過馬路」搶先匹配）
    for kw in ["過馬路結束", "結束過馬路"]:
        if kw in user_text:
            return {"command": "stop_crossing", "state_after": "CHAT"}

    # 過馬路開始
    for kw in ["開始過馬路", "幫我過馬路", "我要過馬路"]:
        if kw in user_text:
            return {"command": "start_crossing", "state_after": "CROSSING"}
    # 短指令「過馬路」需限制長度避免誤匹配
    if "過馬路" in user_text and len(user_text) <= 4:
        return {"command": "start_crossing", "state_after": "CROSSING"}

    # 紅綠燈
    for kw in ["檢測紅綠燈", "看紅綠燈"]:
        if kw in user_text:
            return {"command": "start_traffic_light", "state_after": "TRAFFIC_LIGHT_DETECTION"}
    for kw in ["停止檢測", "停止紅綠燈"]:
        if kw in user_text:
            return {"command": "stop_traffic_light", "state_after": "CHAT"}

    # 盲道導航（含口語化）
    for kw in ["開始導航", "開啟導航", "盲道導航", "幫我導航", "忙導航", "我要導航", "開導航"]:
        if kw in user_text:
            return {"command": "start_blindpath", "state_after": "BLINDPATH_NAV"}
    for kw in ["停止導航", "結束導航", "不要導航", "停導航"]:
        if kw in user_text:
            return {"command": "stop_blindpath", "state_after": "CHAT"}

    # 導航副指令
    for kw in ["立即通过", "现在通过", "继续", "立即通過", "現在通過", "繼續"]:
        if kw in user_text:
            return {"command": "nav_sub_command", "state_after": current_state}

    # 找物品
    find_pattern = r"(?:^\s*(?:帮我|幫我))?\s*找一下\s*(.+?)(?:。|！|？|$)"
    match = re.search(find_pattern, user_text)
    if match:
        item = match.group(1).strip()
        if item:
            return {"command": "find_item", "state_after": "ITEM_SEARCH"}

    # 找到了
    if "找到了" in user_text or "拿到了" in user_text:
        return {"command": "item_found", "state_after": "CHAT"}

    # AI 對話
    _CHAT_TRIGGER_KEYWORDS = [
        "帮我", "幫我", "看看", "看一下", "前面", "什么", "什麼",
        "有没有", "有沒有", "告訴", "告诉", "描述", "識別", "识别",
        "找", "開始", "开始", "導航", "导航", "過馬路", "过马路",
        "說明書", "使用說明", "紅綠燈", "红绿灯",
    ]
    keyword_hits = [kw for kw in _CHAT_TRIGGER_KEYWORDS if kw in user_text]
    if len(user_text) < 3 and len(keyword_hits) < 2:
        return {"command": None}

    return {"command": "ai_chat", "state_after": "CHAT"}


# ═══════════════════════════════════════════════════════════════════════════════
# 測試執行
# ═══════════════════════════════════════════════════════════════════════════════

# 核心指令列表（使用者最常用的指令）
CORE_COMMANDS = [
    ("開始導航", "start_blindpath"),
    ("停止導航", "stop_blindpath"),
    ("開始過馬路", "start_crossing"),
    ("過馬路結束", "stop_crossing"),
    ("檢測紅綠燈", "start_traffic_light"),
    ("停止檢測", "stop_traffic_light"),
    ("幫我找一下紅牛", "find_item"),
    ("找到了", "item_found"),
    ("使用說明書", "usage_guide"),
    ("幫我看看這是什麼", "ai_chat"),
    ("停止所有功能", "interrupt"),
]

# 額外的口語化/場景變體
EXTRA_SCENARIOS = [
    ("我要導航", "start_blindpath", "口語化"),
    ("不要導航了", "stop_blindpath", "口語化"),
    ("我要過馬路", "start_crossing", "口語化"),
    ("看紅綠燈", "start_traffic_light", "口語化"),
    ("紅綠燈", "start_traffic_light", "極短指令"),
    ("過馬路", "start_crossing", "極短指令"),
    ("幫我找礦泉水", "find_item", "不同物品"),
    ("拿到了", "item_found", "找到了變體"),
    ("前面有什麼", "ai_chat", "場景-問路"),
    ("幫我找一下鑰匙", "find_item", "場景-找鑰匙"),
]


def test_traditional_chinese_variants():
    """測試 1：繁體中文使用者的 ASR 輸出變體覆蓋率"""
    print("=" * 70)
    print("測試 1：繁體中文使用者 — ASR 輸出變體對指令匹配的影響")
    print("=" * 70)

    total_variants = 0
    matched_variants = 0
    results_by_command = defaultdict(lambda: {"total": 0, "matched": 0, "failed": []})

    for phrase, expected_cmd in CORE_COMMANDS:
        variants = generate_asr_variants(phrase)
        # 去重
        seen = set()
        unique_variants = []
        for v_text, v_desc in variants:
            if v_text not in seen:
                seen.add(v_text)
                unique_variants.append((v_text, v_desc))

        for v_text, v_desc in unique_variants:
            result = classify_command(v_text, "IDLE")

            # 中斷熱詞特殊處理
            if expected_cmd == "interrupt":
                actual_match = result["command"] is not None
                norm = _normalize_cn(v_text)
                has_interrupt = any(w and _normalize_cn(w) in norm for w in INTERRUPT_KEYWORDS)
                actual_match = has_interrupt
            else:
                actual_match = (result["command"] == expected_cmd)

            total_variants += 1
            results_by_command[expected_cmd]["total"] += 1

            if actual_match:
                matched_variants += 1
                results_by_command[expected_cmd]["matched"] += 1
            else:
                results_by_command[expected_cmd]["failed"].append(
                    (v_text, v_desc, result.get("command", "None"))
                )

    # 額外場景
    for phrase, expected_cmd, desc in EXTRA_SCENARIOS:
        result = classify_command(phrase, "IDLE")
        if expected_cmd == "interrupt":
            norm = _normalize_cn(phrase)
            actual_match = any(w and _normalize_cn(w) in norm for w in INTERRUPT_KEYWORDS)
        else:
            actual_match = (result["command"] == expected_cmd)

        total_variants += 1
        results_by_command[expected_cmd]["total"] += 1
        if actual_match:
            matched_variants += 1
            results_by_command[expected_cmd]["matched"] += 1
        else:
            results_by_command[expected_cmd]["failed"].append(
                (phrase, desc, result.get("command", "None"))
            )

    # 印結果
    overall_rate = matched_variants / total_variants * 100 if total_variants > 0 else 0

    print(f"\n  📊 整體變體覆蓋率: {matched_variants}/{total_variants} = {overall_rate:.1f}%\n")

    for cmd, data in results_by_command.items():
        rate = data["matched"] / data["total"] * 100 if data["total"] > 0 else 0
        status = "✅" if rate >= 80 else "⚠️" if rate >= 50 else "❌"
        print(f"  {status} {cmd}: {data['matched']}/{data['total']} = {rate:.0f}%")
        for v_text, v_desc, actual in data["failed"][:5]:  # 只印前 5 個失敗
            print(f"      ❌ 「{v_text}」({v_desc}) → 實際: {actual}")
        if len(data["failed"]) > 5:
            print(f"      ... 還有 {len(data['failed']) - 5} 個失敗")

    return {"total": total_variants, "matched": matched_variants, "rate": overall_rate,
            "by_command": dict(results_by_command)}


def test_cmn_hant_vs_zh_cn():
    """測試 2：cmn-Hant-TW vs zh-CN 輸出差異對成功率的影響"""
    print("=" * 70)
    print("測試 2：ASR 語言設定對比 — cmn-Hant-TW（繁體）vs zh-CN（簡體）")
    print("=" * 70)

    # 模擬使用者在台灣說繁體中文時，兩種設定的 ASR 輸出
    scenarios = [
        # (使用者說的, 繁體ASR預期輸出, 簡體ASR預期輸出, 預期指令)
        ("開始導航", "開始導航", "开始导航", "start_blindpath"),
        ("停止導航", "停止導航", "停止导航", "stop_blindpath"),
        ("開始過馬路", "開始過馬路", "开始过马路", "start_crossing"),
        ("過馬路結束", "過馬路結束", "过马路结束", "stop_crossing"),
        ("檢測紅綠燈", "檢測紅綠燈", "检测红绿灯", "start_traffic_light"),
        ("停止檢測", "停止檢測", "停止检测", "stop_traffic_light"),
        ("幫我找一下紅牛", "幫我找一下紅牛", "帮我找一下红牛", "find_item"),
        ("找到了", "找到了", "找到了", "item_found"),
        ("使用說明書", "使用說明書", "使用说明书", "usage_guide"),
        ("幫我看看這是什麼", "幫我看看這是什麼", "帮我看看这是什么", "ai_chat"),
        ("開啟導航", "開啟導航", "开启导航", "start_blindpath"),
        ("結束導航", "結束導航", "结束导航", "stop_blindpath"),
        ("看紅綠燈", "看紅綠燈", "看红绿灯", "start_traffic_light"),
        ("停止紅綠燈", "停止紅綠燈", "停止红绿灯", "stop_traffic_light"),
        ("停止所有功能", "停止所有功能", "停止所有功能", "interrupt"),
        ("謝謝曼波", "謝謝曼波", "谢谢曼波", "end_word"),
    ]

    trad_pass = 0
    simp_pass = 0
    total = len(scenarios)

    print(f"\n  {'指令':<20} {'繁體輸出':<6} {'簡體輸出':<6}")
    print(f"  {'─'*20} {'─'*6} {'─'*6}")

    for spoken, trad_output, simp_output, expected_cmd in scenarios:
        trad_result = classify_command(trad_output, "IDLE")
        simp_result = classify_command(simp_output, "IDLE")

        if expected_cmd == "interrupt":
            norm_t = _normalize_cn(trad_output)
            norm_s = _normalize_cn(simp_output)
            trad_ok = any(w and _normalize_cn(w) in norm_t for w in INTERRUPT_KEYWORDS)
            simp_ok = any(w and _normalize_cn(w) in norm_s for w in INTERRUPT_KEYWORDS)
        elif expected_cmd == "end_word":
            norm_t = _normalize_cn(trad_output)
            norm_s = _normalize_cn(simp_output)
            trad_ok = any(w and _normalize_cn(w) in norm_t for w in END_WORDS)
            simp_ok = any(w and _normalize_cn(w) in norm_s for w in END_WORDS)
        else:
            trad_ok = trad_result["command"] == expected_cmd
            simp_ok = simp_result["command"] == expected_cmd

        trad_pass += 1 if trad_ok else 0
        simp_pass += 1 if simp_ok else 0

        trad_mark = "✅" if trad_ok else "❌"
        simp_mark = "✅" if simp_ok else "❌"
        print(f"  {spoken:<20} {trad_mark:^6} {simp_mark:^6}")

        if not trad_ok:
            print(f"    ⚠️ 繁體「{trad_output}」→ {trad_result.get('command', 'None')}（預期 {expected_cmd}）")
        if not simp_ok:
            print(f"    ⚠️ 簡體「{simp_output}」→ {simp_result.get('command', 'None')}（預期 {expected_cmd}）")

    trad_rate = trad_pass / total * 100
    simp_rate = simp_pass / total * 100

    print(f"\n  📊 cmn-Hant-TW（繁體）成功率: {trad_pass}/{total} = {trad_rate:.1f}%")
    print(f"  📊 zh-CN（簡體）成功率:       {simp_pass}/{total} = {simp_rate:.1f}%")

    if trad_rate > simp_rate:
        print(f"\n  🏆 cmn-Hant-TW（繁體）表現較佳（+{trad_rate - simp_rate:.1f}%）")
    elif simp_rate > trad_rate:
        print(f"\n  🏆 zh-CN（簡體）表現較佳（+{simp_rate - trad_rate:.1f}%）")
    else:
        print(f"\n  🤝 兩種設定表現相同")

    return {"trad_rate": trad_rate, "simp_rate": simp_rate,
            "trad_pass": trad_pass, "simp_pass": simp_pass, "total": total}


def test_speech_speed_and_accent():
    """測試 3：不同語速和口音的指令觸發成功率"""
    print("=" * 70)
    print("測試 3：語速 × 口音 — 真實使用者場景模擬")
    print("=" * 70)

    # 模擬不同使用者類型
    user_types = {
        "正常語速-標準發音": [
            "開始導航", "停止導航", "開始過馬路", "檢測紅綠燈",
            "幫我找一下紅牛", "找到了", "使用說明書",
        ],
        "快語速-吞音": [
            "開導航", "停導航", "過馬路", "看紅綠燈",
            "找一下紅牛", "找到了", "說明書",
            "紅綠燈", "導航", "避障",
        ],
        "慢語速-多語氣詞": [
            "嗯開始導航", "那個停止導航", "就是開始過馬路",
            "呃檢測紅綠燈", "幫我找一下紅牛啊", "找到了呢",
            "使用說明書吧",
        ],
        "台灣國語-口語化": [
            "我要導航", "不要導航了", "我要過馬路",
            "看紅綠燈", "幫我找紅牛", "拿到啦",
            "說明書",
        ],
        "ASR 常見誤辨": [
            "開是導航", "忙導航", "開使導航",
            "倒航", "開啟導航", "哈囉慢播",
            "停下所有功能",
        ],
    }

    # 每條輸入的預期指令（如果能匹配到任何有效指令就算成功）
    expected_commands = {
        "開始導航": "start_blindpath", "停止導航": "stop_blindpath",
        "開始過馬路": "start_crossing", "檢測紅綠燈": "start_traffic_light",
        "幫我找一下紅牛": "find_item", "找到了": "item_found",
        "使用說明書": "usage_guide",
        # 快語速（有些可能匹配不到，這是預期中的）
        "開導航": "start_blindpath",  # 已加入匹配列表
        "停導航": "stop_blindpath",  # 已加入匹配列表
        "過馬路": "start_crossing",
        "看紅綠燈": "start_traffic_light",
        "找一下紅牛": "find_item",
        "說明書": None,  # 太短，不含「使用」
        "紅綠燈": None,  # 太短
        "導航": None,
        "避障": None,
        # 慢語速
        "嗯開始導航": "start_blindpath",
        "那個停止導航": "stop_blindpath",
        "就是開始過馬路": "start_crossing",
        "呃檢測紅綠燈": "start_traffic_light",
        "幫我找一下紅牛啊": "find_item",
        "找到了呢": "item_found",
        "使用說明書吧": "usage_guide",
        # 口語化（已加入匹配列表）
        "我要導航": "start_blindpath",  # 已加入
        "不要導航了": "stop_blindpath",  # 已加入（包含「不要導航」）
        "我要過馬路": "start_crossing",  # 已加入
        "拿到啦": None,  # 「拿到啦」≠「拿到了」
        # ASR 誤辨
        "開是導航": None,  # 不匹配
        "忙導航": "start_blindpath",
        "開使導航": None,
        "倒航": None,
        "開啟導航": "start_blindpath",
        "哈囉慢播": "wake_word",
        "停下所有功能": "interrupt",
    }

    results_by_type = {}

    for user_type, phrases in user_types.items():
        matched = 0
        total = 0
        failed = []

        for phrase in phrases:
            result = classify_command(phrase, "IDLE")
            expected = expected_commands.get(phrase)

            total += 1

            if expected is None:
                # 預期無法匹配 — 如果確實沒匹配到有效指令，算通過
                if result["command"] is None:
                    matched += 1
                else:
                    # 意外匹配到了 — 不算失敗，但記錄
                    pass
            elif expected == "wake_word":
                # 喚醒詞特殊處理：偵測到「曼波」變體即觸發
                norm = _normalize_cn(phrase)
                if any(v in norm for v in _MAMBO_VARIANTS):
                    matched += 1
                else:
                    failed.append((phrase, expected, result.get("command")))
            elif expected == "interrupt":
                norm = _normalize_cn(phrase)
                has_interrupt = any(w and _normalize_cn(w) in norm for w in INTERRUPT_KEYWORDS)
                if has_interrupt:
                    matched += 1
                else:
                    failed.append((phrase, expected, result.get("command")))
            else:
                if result["command"] == expected:
                    matched += 1
                else:
                    failed.append((phrase, expected, result.get("command")))

        rate = matched / total * 100 if total > 0 else 0
        results_by_type[user_type] = {"matched": matched, "total": total, "rate": rate, "failed": failed}

        status = "✅" if rate >= 70 else "⚠️" if rate >= 40 else "❌"
        print(f"\n  {status} {user_type}: {matched}/{total} = {rate:.0f}%")
        for phrase, expected, actual in failed:
            print(f"      ❌ 「{phrase}」預期: {expected}, 實際: {actual}")

    return results_by_type


def test_mixed_trad_simp_output():
    """測試 4：繁簡混合輸出（ASR 最常見的真實問題）"""
    print("=" * 70)
    print("測試 4：繁簡混合輸出 — 真實 ASR 輸出中最常見的問題")
    print("=" * 70)

    # 模擬 cmn-Hant-TW 偶爾輸出簡體字的真实场景
    mixed_cases = [
        # (ASR 輸出, 預期指令, 描述)
        # 完全繁體
        ("開始導航", "start_blindpath", "純繁體"),
        ("停止導航", "stop_blindpath", "純繁體"),
        ("幫我找一下紅牛", "find_item", "純繁體"),

        # 完全簡體
        ("开始导航", "start_blindpath", "純簡體"),
        ("停止导航", "stop_blindpath", "純簡體"),
        ("帮我找一下红牛", "find_item", "純簡體"),

        # 繁簡混合 — 第一字簡體，其餘繁體
        ("开始導航", "start_blindpath", "混合-開→开"),
        ("停止導航", "stop_blindpath", "混合-停→停（相同）"),
        ("幫我找一下紅牛", "find_item", "混合-幫→帮"),
        ("检测紅綠燈", "start_traffic_light", "混合-檢→检"),
        ("开始過馬路", "start_crossing", "混合-開→开"),
        ("停止检测", "stop_traffic_light", "混合-檢→检"),
        ("使用说明书", "usage_guide", "混合-書→书"),
        ("帮我找一下紅牛", "find_item", "混合-幫→帮+紅牛繁體"),
        ("过马路結束", "stop_crossing", "混合-過→过"),
        ("看红綠燈", "start_traffic_light", "混合-紅→红"),
        ("停下所有功能", "interrupt", "混合-停→停（同）"),
        ("谢謝曼波", "end_word", "混合-謝→谢（第一字）"),
        ("謝谢曼波", "end_word", "混合-謝→谢（第二字）"),
    ]

    matched = 0
    total = 0
    failed = []

    for asr_output, expected_cmd, desc in mixed_cases:
        result = classify_command(asr_output, "IDLE")

        if expected_cmd == "interrupt":
            norm = _normalize_cn(asr_output)
            ok = any(w and _normalize_cn(w) in norm for w in INTERRUPT_KEYWORDS)
        elif expected_cmd == "end_word":
            norm = _normalize_cn(asr_output)
            ok = any(w and _normalize_cn(w) in norm for w in END_WORDS)
        else:
            ok = result["command"] == expected_cmd

        total += 1
        if ok:
            matched += 1
        else:
            failed.append((asr_output, desc, expected_cmd, result.get("command", "None")))

    rate = matched / total * 100 if total > 0 else 0
    status = "✅" if rate >= 80 else "⚠️" if rate >= 50 else "❌"

    print(f"\n  {status} 繁簡混合覆蓋率: {matched}/{total} = {rate:.1f}%\n")

    for asr_output, desc, expected, actual in failed:
        print(f"  ❌ 「{asr_output}」({desc}) → 預期: {expected}, 實際: {actual}")

    return {"matched": matched, "total": total, "rate": rate, "failed": failed}


def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  繁體中文使用者模擬測試套件                                ║")
    print("║  模擬台灣使用者在各種場景下的語音指令成功率                ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    # 測試 1：繁體中文變體覆蓋率
    variant_result = test_traditional_chinese_variants()
    print()

    # 測試 2：cmn-Hant-TW vs zh-CN 對比
    lang_result = test_cmn_hant_vs_zh_cn()
    print()

    # 測試 3：語速 × 口音
    speed_result = test_speech_speed_and_accent()
    print()

    # 測試 4：繁簡混合
    mixed_result = test_mixed_trad_simp_output()
    print()

    # ═══ 最終總結 ═══
    print("=" * 70)
    print("📊 繁體中文使用者測試總結")
    print("=" * 70)

    print(f"\n  1. ASR 變體覆蓋率:        {variant_result['rate']:.1f}%（{variant_result['matched']}/{variant_result['total']}）")
    print(f"  2. cmn-Hant-TW 成功率:     {lang_result['trad_rate']:.1f}%")
    print(f"     zh-CN 成功率:           {lang_result['simp_rate']:.1f}%")
    print(f"  3. 語速×口音 場景:")
    for utype, data in speed_result.items():
        status = "✅" if data["rate"] >= 70 else "⚠️"
        print(f"     {status} {utype}: {data['rate']:.0f}%")
    print(f"  4. 繁簡混合覆蓋率:        {mixed_result['rate']:.1f}%")

    # 推薦設定
    print(f"\n  ═══ 建議 ═══")
    if lang_result['trad_rate'] >= lang_result['simp_rate']:
        print(f"  🏆 推薦維持 cmn-Hant-TW（繁體）— 與台灣使用者最匹配")
        print(f"     繁體成功率 {lang_result['trad_rate']:.1f}% >= 簡體 {lang_result['simp_rate']:.1f}%")
    else:
        print(f"  ⚠️ 簡體設定成功率反而較高，但差異不大")
        print(f"     建議仍維持 cmn-Hant-TW，因為指令匹配同時支援繁簡體")

    if mixed_result['rate'] < 90:
        print(f"\n  ⚠️ 繁簡混合輸出覆蓋率僅 {mixed_result['rate']:.1f}%")
        print(f"     建議：在指令匹配中加入繁簡轉換（opencc 或字元映射）")

    variant_ok = variant_result['rate'] >= 80
    lang_ok = lang_result['trad_rate'] >= 80
    mixed_ok = mixed_result['rate'] >= 80

    all_pass = variant_ok and lang_ok and mixed_ok

    if all_pass:
        print(f"\n  ✅ 繁體中文使用者在大多數場景下指令觸發成功率良好")
    else:
        print(f"\n  ⚠️ 部分場景成功率不足，建議改善指令匹配邏輯")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
